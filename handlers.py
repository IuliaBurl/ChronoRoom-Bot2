import logging
from enum import Enum

from aiogram import Router, types, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions

from config import (
    CHANNEL_USERNAME,
    MAX_ANSWER_LENGTH,
    MAX_DAILY_ROLLS,
    MAX_MESSAGE_LENGTH,
    MAX_NAME_LENGTH,
)
import database
import utils
import questions
from utils import escape_attr, escape_html

logger = logging.getLogger(__name__)

# All messages are sent with parse_mode=HTML (set once as the bot default in bot.py).
# Every piece of user-supplied text MUST go through escape_html() before it is
# interpolated into a message.

router = Router()
db = database.Database()

CAPTION_LIMIT = 1024
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else ""


class ProfileStates(StatesGroup):
    waiting_for_answer_1 = State()
    waiting_for_answer_2 = State()
    waiting_for_answer_3 = State()
    waiting_for_answer_4 = State()
    waiting_for_answer_5 = State()
    waiting_for_photo = State()
    waiting_for_name = State()


class ChatStates(StatesGroup):
    waiting_for_message = State()


class SubscriptionStatus(Enum):
    SUBSCRIBED = "subscribed"
    NOT_SUBSCRIBED = "not_subscribed"
    UNKNOWN = "unknown"  # Telegram could not tell us (outage, bot is not a channel admin, ...)


async def reject_outdated_buttons(handler, event: types.CallbackQuery, data: dict):
    """Buttons on messages older than 48h arrive without an accessible message.

    Handlers rely on callback.message (edit / answer / delete), so instead of
    crashing we ask the user to open a fresh menu.
    """
    if not isinstance(event.message, types.Message):
        await event.answer("This button is outdated. Send /start to open the menu.", show_alert=True)
        return None
    return await handler(event, data)


router.callback_query.outer_middleware(reject_outdated_buttons)


async def check_subscription(user_id: int, bot) -> SubscriptionStatus:
    """Checks if the user is subscribed to the channel.

    Fails closed: if Telegram cannot confirm the membership, the user is NOT
    let in, but gets a distinct UNKNOWN status so the UI can say
    "try again later" instead of wrongly claiming "you are not subscribed".
    """
    if not CHANNEL_USERNAME:
        return SubscriptionStatus.SUBSCRIBED
    try:
        member = await bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}",
            user_id=user_id
        )
    except TelegramAPIError as e:
        # Besides outages this also covers a misconfiguration (wrong channel name,
        # bot is not an admin of the channel), so it is logged as an error.
        logger.error("Subscription check failed for user %s: %s", user_id, e)
        return SubscriptionStatus.UNKNOWN

    if member.status in ('creator', 'administrator', 'member'):
        return SubscriptionStatus.SUBSCRIBED
    if member.status == 'restricted' and bool(getattr(member, 'is_member', False)):
        return SubscriptionStatus.SUBSCRIBED
    return SubscriptionStatus.NOT_SUBSCRIBED


async def delete_quietly(message: types.Message):
    """Deletes a message, ignoring Telegram errors (already deleted, too old, ...)"""
    try:
        await message.delete()
    except TelegramAPIError:
        pass


async def edit_or_send(callback: types.CallbackQuery, text: str, reply_markup=None):
    """Edits the message of a callback; falls back to a new message for photo or stale messages.

    The old message is deleted only AFTER the new one has been delivered, so a
    failed send never leaves the user with nothing on screen.
    """
    message = callback.message
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW
        )
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.debug("Cannot edit message, sending a new one: %s", e)

    await message.answer(
        text,
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW
    )
    await delete_quietly(message)


async def send_with_photo(bot, chat_id: int, photo_id, text: str, reply_markup=None):
    """Sends text with an optional photo, respecting the caption length limit"""
    if photo_id and len(text) <= CAPTION_LIMIT:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo_id,
            caption=text,
            reply_markup=reply_markup
        )
        return
    if photo_id:
        await bot.send_photo(chat_id=chat_id, photo=photo_id)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW
    )


def username_text(profile: dict) -> str:
    username = profile.get('username')
    if username:
        return "@" + escape_html(username)
    return "not set"


async def show_subscription_gate(message: types.Message, status: SubscriptionStatus):
    """Tells the user why they cannot continue yet"""
    if status is SubscriptionStatus.UNKNOWN:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Try again", callback_data="check_subscription")]
            ]
        )
        await message.answer(
            "⚠️ I couldn't verify your channel subscription right now.\n\n"
            "Please try again in a minute.",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ I subscribed", callback_data="check_subscription"),
                InlineKeyboardButton(text="🔗 Go to channel", url=CHANNEL_URL)
            ]
        ]
    )

    await message.answer(
        f"📢 <b>To use the bot, you need to subscribe to "
        f"<a href=\"{escape_attr(CHANNEL_URL)}\">our channel</a></b>\n\n"
        "This is needed for:\n"
        "• Receiving notifications about new features\n"
        "• Participating in giveaways\n"
        "• A community of like-minded people\n\n"
        "After subscribing, press the button below",
        reply_markup=keyboard,
        link_preview_options=NO_PREVIEW
    )


async def enter_bot(message: types.Message, user: types.User):
    """Registers the user and shows the menu (or the welcome screen for newcomers)"""
    db.add_user(user.id, user.username, user.full_name)

    if db.get_profile(user.id):
        await show_main_menu(message)
    else:
        await show_welcome_message(message)


async def process_start(message: types.Message, state: FSMContext, user: types.User):
    """Common start flow for a given user"""
    await state.clear()

    status = await check_subscription(user.id, message.bot)
    if status is not SubscriptionStatus.SUBSCRIBED:
        await show_subscription_gate(message, status)
        return

    await enter_bot(message, user)


@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Handler for the /start command"""
    await process_start(message, state, message.from_user)


async def show_welcome_message(message: types.Message):
    """Shows a welcome message and offers to create a profile"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✨ Create profile", callback_data="create_profile")
            ]
        ]
    )

    await message.answer(
        "👋 <b>Welcome to ChronoRoom!</b>\n\n"
        "I will help you find your 'lucky person' through the dice of fate.\n\n"
        "<b>How it works:</b>\n"
        "1. You create a unique profile (5 random questions)\n"
        f"2. You roll the dice up to {MAX_DAILY_ROLLS} times a day\n"
        "3. You find random profiles of other people\n"
        "4. If there is mutual sympathy, you get the contact\n\n"
        "Ready to start?",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handler for pressing 'I subscribed' / 'Try again'"""
    status = await check_subscription(callback.from_user.id, callback.bot)

    if status is SubscriptionStatus.SUBSCRIBED:
        await callback.answer()
        await delete_quietly(callback.message)
        await state.clear()
        await enter_bot(callback.message, callback.from_user)
    elif status is SubscriptionStatus.UNKNOWN:
        await callback.answer(
            "Couldn't verify your subscription right now. Please try again in a minute.",
            show_alert=True
        )
    else:
        await callback.answer("You are not subscribed to the channel yet!", show_alert=True)


@router.callback_query(F.data == "create_profile")
async def create_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Starts profile creation"""
    await callback.answer()
    await delete_quietly(callback.message)
    await start_profile_creation(callback.message, state)


async def start_profile_creation(message: types.Message, state: FSMContext):
    """Starts the profile creation process"""
    await message.answer(
        "📝 <b>Profile creation</b>\n\n"
        "Now I will ask you <b>5 random questions</b> from our database.\n"
        "Answer honestly and interestingly - this way you will increase your chances!\n\n"
        f"💡 <b>Important:</b> each answer must be no more than {MAX_ANSWER_LENGTH} characters.\n\n"
        "Ready? Let's go! 🚀"
    )

    question_ids = utils.generate_question_set()

    await state.update_data(
        question_ids=question_ids,
        answers=[],
        current_question=0,
        photo_id=None
    )

    await ask_next_question(message, state)


async def ask_next_question(message: types.Message, state: FSMContext):
    """Asks the next question to the user"""
    data = await state.get_data()
    question_ids = data.get('question_ids', [])
    current_q = data.get('current_question', 0)

    if not question_ids:
        await message.answer("Something went wrong. Start over: /start")
        await state.clear()
        return

    if current_q >= len(question_ids):
        await state.set_state(ProfileStates.waiting_for_photo)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⏭ Skip photo", callback_data="skip_photo")
                ]
            ]
        )

        await message.answer(
            "✨ Great! All questions have been completed.\n\n"
            "Now send your <b>photo</b> for the profile (this will increase your chances 10 times!).\n"
            "Or press the 'Skip' button",
            reply_markup=keyboard
        )
        return

    question_id = question_ids[current_q]
    question_text = questions.QUESTIONS_DICT.get(question_id, f"Question #{question_id}")

    states = [
        ProfileStates.waiting_for_answer_1,
        ProfileStates.waiting_for_answer_2,
        ProfileStates.waiting_for_answer_3,
        ProfileStates.waiting_for_answer_4,
        ProfileStates.waiting_for_answer_5
    ]

    await state.set_state(states[current_q])

    await message.answer(
        f"<b>Question {current_q + 1} of 5:</b>\n{escape_html(question_text)}\n\n"
        f"💡 <b>Limit:</b> {MAX_ANSWER_LENGTH} characters"
    )


@router.message(ProfileStates.waiting_for_answer_1)
@router.message(ProfileStates.waiting_for_answer_2)
@router.message(ProfileStates.waiting_for_answer_3)
@router.message(ProfileStates.waiting_for_answer_4)
@router.message(ProfileStates.waiting_for_answer_5)
async def handle_answer(message: types.Message, state: FSMContext):
    """Handler for answering a question"""
    if not message.text:
        await message.answer("❌ Please send your answer as a text message.")
        return

    if not utils.check_answer_length(message.text, MAX_ANSWER_LENGTH):
        await message.answer(f"❌ The answer is too long! Maximum {MAX_ANSWER_LENGTH} characters.")
        return

    data = await state.get_data()
    question_ids = data.get('question_ids', [])
    answers = data.get('answers', [])
    current_q = data.get('current_question', 0)

    if current_q >= len(question_ids):
        await message.answer("Error: questions are over. Start over: /start")
        await state.clear()
        return

    answers.append(message.text.strip())

    await state.update_data(
        answers=answers,
        current_question=current_q + 1
    )

    await ask_next_question(message, state)


@router.callback_query(F.data == "skip_photo")
async def skip_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    """Skip photo"""
    await callback.answer()
    await delete_quietly(callback.message)

    # The photo is kept in the FSM data and written to the DB only together with
    # the finished profile, so an abandoned flow never changes the current profile.
    await state.update_data(photo_id=None)
    await state.set_state(ProfileStates.waiting_for_name)

    await callback.message.answer(
        "Okay, there will be no photo.\n\n"
        "Now enter your <b>name</b> that will be displayed in the profile "
        "(it can be real or fictional):"
    )


@router.message(ProfileStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    """Handler for receiving a photo"""
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ProfileStates.waiting_for_name)

    await message.answer(
        "📸 Photo saved!\n\n"
        "Now enter your <b>name</b> that will be displayed in the profile "
        "(it can be real or fictional):"
    )


@router.message(ProfileStates.waiting_for_photo)
async def handle_photo_invalid(message: types.Message, state: FSMContext):
    """Handler for anything that is not a photo while waiting for a photo"""
    await message.answer("📸 Please send a photo or press the 'Skip photo' button.")


@router.message(ProfileStates.waiting_for_name)
async def handle_name(message: types.Message, state: FSMContext):
    """Handler for receiving the name"""
    user_id = message.from_user.id

    if not message.text:
        await message.answer("❌ Please send your name as a text message.")
        return

    name = message.text.strip()

    if len(name) > MAX_NAME_LENGTH:
        await message.answer(f"❌ The name is too long! Maximum {MAX_NAME_LENGTH} characters.")
        return

    if len(name) < 2:
        await message.answer("❌ The name is too short!")
        return

    data = await state.get_data()
    question_ids = data.get('question_ids', [])
    answers = data.get('answers', [])

    if not question_ids or len(answers) != 5:
        await message.answer("❌ Error! Not all questions have been answered. Start over: /start")
        await state.clear()
        return

    db.add_user(user_id, message.from_user.username, message.from_user.full_name)
    db.update_user_photo(user_id, data.get('photo_id'))
    db.create_profile(
        user_id=user_id,
        name=name,
        questions_ids=question_ids,
        answers=answers
    )

    await state.clear()

    await message.answer(
        "🎉 <b>Profile successfully created!</b>\n\n"
        "Now you can search for your 'lucky person'. "
        f"You have {MAX_DAILY_ROLLS} dice rolls per day."
    )

    await show_main_menu(message)


async def show_main_menu(message: types.Message):
    """Shows the main menu with buttons"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎲 My lucky person", callback_data="roll_dice"),
                InlineKeyboardButton(text="🔄 New profile", callback_data="new_profile")
            ],
            [
                InlineKeyboardButton(text="👤 My profile", callback_data="my_profile"),
                InlineKeyboardButton(text="📊 Statistics", callback_data="stats")
            ]
        ]
    )

    await message.answer(
        "✨ <b>Main menu</b>\n\n"
        "Choose an action:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "new_profile")
async def new_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Creating a new profile (instead of editing)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, create a new one", callback_data="confirm_new_profile"),
                InlineKeyboardButton(text="❌ No, keep the current one", callback_data="main_menu")
            ]
        ]
    )

    await edit_or_send(
        callback,
        "🔄 <b>Creating a new profile</b>\n\n"
        "⚠️ <b>Attention:</b> When creating a new profile:\n"
        "• The current profile will be deleted\n"
        "• You will be asked 5 new random questions\n"
        "• You will need to add a photo and name again\n\n"
        "Are you sure you want to create a new profile?",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_new_profile")
async def confirm_new_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Confirmation of creating a new profile"""
    await callback.answer()
    await delete_quietly(callback.message)
    await start_profile_creation(callback.message, state)


@router.callback_query(F.data == "roll_dice")
async def roll_dice_callback(callback: types.CallbackQuery, state: FSMContext):
    """Dice roll handler"""
    await state.clear()

    user = callback.from_user
    user_id = user.id

    db.add_user(user_id, user.username, user.full_name)

    can_roll, rolls_left = db.can_roll_today(user_id)

    if not can_roll:
        await callback.answer(
            f"❌ You have used all {MAX_DAILY_ROLLS} attempts for today. Come back tomorrow!",
            show_alert=True
        )
        return

    profile = db.get_random_profile(user_id)

    if not profile:
        await callback.answer(
            "😔 There are no other profiles yet. Invite friends or come back later!",
            show_alert=True
        )
        return

    try:
        await callback.bot.send_chat_action(profile['user_id'], 'typing')
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.info("User %s is unavailable: %s", profile['user_id'], e)
        db.deactivate_profile(profile['user_id'])
        await callback.answer(
            "😔 This user is no longer available. Try again!",
            show_alert=True
        )
        return
    except TelegramAPIError as e:
        logger.warning("Availability check failed for %s: %s", profile['user_id'], e)
        await callback.answer("😔 Something went wrong. Try again!", show_alert=True)
        return

    if not db.use_roll(user_id):
        await callback.answer(
            f"❌ You have used all {MAX_DAILY_ROLLS} attempts for today. Come back tomorrow!",
            show_alert=True
        )
        return

    profile_text = utils.format_profile(profile, questions.QUESTIONS_DICT)

    inline_keyboard = [
        [InlineKeyboardButton(text="❤️ Write to this person",
                              callback_data=f"request_chat_{profile['user_id']}")]
    ]

    if rolls_left - 1 > 0:
        inline_keyboard.append([
            InlineKeyboardButton(text="🎲 Roll again", callback_data="roll_dice"),
            InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
        ])
    else:
        inline_keyboard.append([
            InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    try:
        if profile.get('photo_id'):
            await send_with_photo(callback.bot, user_id, profile['photo_id'], profile_text, keyboard)
        else:
            await edit_or_send(callback, profile_text, reply_markup=keyboard)
    except TelegramAPIError as e:
        # The user did not get to see the profile, so the roll must not be burnt.
        logger.warning("Could not show profile %s to %s: %s", profile['user_id'], user_id, e)
        db.refund_roll(user_id)
        await callback.answer(
            "😔 Something went wrong. Your roll was not spent. Try again!",
            show_alert=True
        )
        return

    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Return to the main menu"""
    await state.clear()
    await callback.answer()
    await delete_quietly(callback.message)
    await show_main_menu(callback.message)


@router.callback_query(F.data.startswith("request_chat_"))
async def request_chat_callback(callback: types.CallbackQuery, state: FSMContext):
    """Chat request - send a message to the person"""
    target_user_id = int(callback.data.split("_")[-1])
    from_user_id = callback.from_user.id

    from_profile = db.get_profile(from_user_id)
    if not from_profile:
        await callback.answer("You don't have a profile!", show_alert=True)
        return

    target_profile = db.get_profile(target_user_id)
    if not target_profile:
        await callback.answer("This user is no longer active.", show_alert=True)
        return

    await state.update_data(
        chat_with=target_user_id,
        chat_from=from_user_id,
        is_reply=False
    )

    await edit_or_send(
        callback,
        f"💌 <b>Write a message for {escape_html(target_profile['name'])}</b>\n\n"
        "This message will be sent anonymously through the bot. "
        "The recipient will see your full profile and will be able to reply.\n\n"
        "Write your first message:"
    )

    await state.set_state(ChatStates.waiting_for_message)
    await callback.answer()


@router.message(ChatStates.waiting_for_message)
async def handle_chat_message(message: types.Message, state: FSMContext):
    """Chat message handler"""
    if not message.text:
        await message.answer("❌ Please send your message as text.")
        return

    if len(message.text) > MAX_MESSAGE_LENGTH:
        await message.answer(f"❌ The message is too long! Maximum {MAX_MESSAGE_LENGTH} characters.")
        return

    data = await state.get_data()
    target_user_id = data.get('chat_with')
    from_user_id = data.get('chat_from')
    is_reply = data.get('is_reply', False)

    if not target_user_id or not from_user_id:
        await message.answer("Chat error. Start over.")
        await state.clear()
        return

    from_profile = db.get_profile(from_user_id)
    target_profile = db.get_profile(target_user_id)

    if not from_profile or not target_profile:
        await message.answer("One of the users was not found.")
        await state.clear()
        return

    from_profile_text = utils.format_profile(from_profile, questions.QUESTIONS_DICT)

    if is_reply:
        intro = f"💬 <b>You received a reply!</b>\n\nHere is the profile of the sender:\n\n{from_profile_text}"
    else:
        intro = (
            "🎯 <b>You have become someone's LUCKY PERSON!</b>\n\n"
            "Someone rolled the dice of fate and it landed on your profile. "
            f"Here is their profile:\n\n{from_profile_text}"
        )

    try:
        await send_with_photo(message.bot, target_user_id, from_profile.get('photo_id'), intro)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="💌 Reply", callback_data=f"reply_chat_{from_user_id}")
                ],
                [
                    InlineKeyboardButton(text="🤝 Exchange usernames", callback_data=f"mutual_username_{from_user_id}")
                ],
                [
                    InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_chat_{from_user_id}")
                ]
            ]
        )

        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"💌 <b>Message from {escape_html(from_profile['name'])}:</b>\n\n"
                 f"<b>{escape_html(message.text)}</b>\n\n"
                 "<b>Choose an action:</b>\n"
                 "• 💌 Reply - continue communicating through the bot\n"
                 "• 🤝 Exchange usernames - request a mutual exchange of contacts\n"
                 "• ❌ Reject - stop communicating",
            reply_markup=keyboard
        )

        keyboard_back = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
                ]
            ]
        )

        await message.answer(
            f"✅ <b>Message sent to {escape_html(target_profile['name'])}!</b>\n\n"
            "Your profile was shown to the recipient. Now wait for a reply. "
            "If the user wants to exchange contacts, "
            "you will receive a request for consent.",
            reply_markup=keyboard_back
        )

    except TelegramForbiddenError:
        db.deactivate_profile(target_user_id)
        await message.answer("❌ Failed to send the message. The user has blocked the bot.")
    except TelegramAPIError as e:
        logger.warning("Message sending error: %s", e)
        await message.answer("❌ Failed to send the message. Try again later.")

    await state.clear()


@router.callback_query(F.data.startswith("reply_chat_"))
async def reply_chat_callback(callback: types.CallbackQuery, state: FSMContext):
    """Reply to a message"""
    from_user_id = int(callback.data.split("_")[-1])
    current_user_id = callback.from_user.id

    from_profile = db.get_profile(from_user_id)

    if not from_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    await state.update_data(
        chat_with=from_user_id,
        chat_from=current_user_id,
        is_reply=True
    )

    await edit_or_send(
        callback,
        f"💬 <b>Reply to {escape_html(from_profile['name'])}</b>\n\n"
        "Write your message. It will be sent anonymously through the bot."
    )

    await state.set_state(ChatStates.waiting_for_message)
    await callback.answer()


@router.callback_query(F.data.startswith("mutual_username_"))
async def mutual_username_callback(callback: types.CallbackQuery):
    """Request for mutual username exchange"""
    target_user_id = int(callback.data.split("_")[-1])
    current_user = callback.from_user
    current_user_id = current_user.id

    # Refresh the stored username: the person may have changed it since /start.
    db.add_user(current_user_id, current_user.username, current_user.full_name)

    target_profile = db.get_profile(target_user_id)
    current_profile = db.get_profile(current_user_id)

    if not target_profile or not current_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    if not current_profile.get('username'):
        await callback.answer(
            "To exchange usernames, set a @username in your Telegram settings first.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, I agree", callback_data=f"accept_mutual_{current_user_id}"),
                InlineKeyboardButton(text="❌ No, reject", callback_data=f"reject_mutual_{current_user_id}")
            ]
        ]
    )

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=f"🤝 <b>{escape_html(current_profile['name'])} suggests exchanging usernames!</b>\n\n"
                 "If you agree, both of you will receive each other's usernames.\n\n"
                 "Do you agree to a mutual exchange of contacts?",
            reply_markup=keyboard
        )
    except TelegramAPIError as e:
        logger.warning("Request sending error: %s", e)
        await callback.answer("Failed to send the request.", show_alert=True)
        return

    await edit_or_send(
        callback,
        "🤝 <b>Username exchange request sent!</b>\n\n"
        f"You suggested to {escape_html(target_profile['name'])} to exchange contacts.\n"
        "Wait for a reply. If the user agrees, both of you will receive each other's usernames."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("accept_mutual_"))
async def accept_mutual_callback(callback: types.CallbackQuery):
    """Accepting mutual username exchange"""
    requester_id = int(callback.data.split("_")[-1])
    accepter = callback.from_user
    accepter_id = accepter.id

    # Refresh the stored username: the person may have changed it since /start.
    db.add_user(accepter_id, accepter.username, accepter.full_name)

    requester_profile = db.get_profile(requester_id)
    accepter_profile = db.get_profile(accepter_id)

    if not requester_profile or not accepter_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    if not accepter_profile.get('username'):
        await callback.answer(
            "To exchange usernames, set a @username in your Telegram settings first.",
            show_alert=True
        )
        return

    if not requester_profile.get('username'):
        await callback.answer(
            "This user no longer has a public @username, so the exchange is not possible.",
            show_alert=True
        )
        return

    requester_username = username_text(requester_profile)
    accepter_username = username_text(accepter_profile)

    try:
        await callback.bot.send_message(
            chat_id=requester_id,
            text=f"🎉 <b>{escape_html(accepter_profile['name'])} agreed to exchange usernames!</b>\n\n"
                 "🤝 <b>Mutual exchange completed:</b>\n\n"
                 f"• Your username: {requester_username}\n"
                 f"• {escape_html(accepter_profile['name'])}'s username: {accepter_username}\n\n"
                 "Now you can write to each other directly on Telegram!"
        )
    except TelegramAPIError as e:
        logger.warning("Could not notify requester %s: %s", requester_id, e)

    await edit_or_send(
        callback,
        f"🎉 <b>You agreed to exchange usernames with {escape_html(requester_profile['name'])}!</b>\n\n"
        "🤝 <b>Mutual exchange completed:</b>\n\n"
        f"• Your username: {accepter_username}\n"
        f"• {escape_html(requester_profile['name'])}'s username: {requester_username}\n\n"
        "Now you can write to each other directly on Telegram!"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reject_mutual_"))
async def reject_mutual_callback(callback: types.CallbackQuery):
    """Rejecting mutual username exchange"""
    requester_id = int(callback.data.split("_")[-1])
    accepter_id = callback.from_user.id

    requester_profile = db.get_profile(requester_id)
    accepter_profile = db.get_profile(accepter_id)

    if not requester_profile or not accepter_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    try:
        await callback.bot.send_message(
            chat_id=requester_id,
            text=f"❌ <b>{escape_html(accepter_profile['name'])} rejected the username exchange request.</b>\n\n"
                 "You can continue communicating through the bot."
        )
    except TelegramAPIError as e:
        logger.warning("Could not notify requester %s: %s", requester_id, e)

    await edit_or_send(
        callback,
        f"❌ <b>You rejected the username exchange request from {escape_html(requester_profile['name'])}.</b>\n\n"
        "The user has been notified of the rejection."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reject_chat_"))
async def reject_chat_callback(callback: types.CallbackQuery):
    """Rejecting chat"""
    from_user_id = int(callback.data.split("_")[-1])

    from_profile = db.get_profile(from_user_id)
    current_profile = db.get_profile(callback.from_user.id)

    if from_profile and current_profile:
        try:
            await callback.bot.send_message(
                chat_id=from_user_id,
                text=f"❌ <b>{escape_html(current_profile['name'])} rejected your message.</b>\n\n"
                     "This user is not ready to communicate."
            )
        except TelegramAPIError as e:
            logger.warning("Could not notify sender %s: %s", from_user_id, e)

    await edit_or_send(
        callback,
        "❌ <b>You rejected the message.</b>\n\n"
        "The sender has been notified of the rejection."
    )
    await callback.answer()


@router.callback_query(F.data == "my_profile")
async def my_profile_callback(callback: types.CallbackQuery):
    """Shows your profile"""
    user_id = callback.from_user.id

    profile = db.get_profile(user_id)

    if not profile:
        await callback.answer("You don't have a profile! Create one.", show_alert=True)
        return

    profile_text = utils.format_profile(profile, questions.QUESTIONS_DICT)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
            ]
        ]
    )

    if profile.get('photo_id'):
        await send_with_photo(callback.bot, user_id, profile['photo_id'], profile_text, keyboard)
    else:
        await edit_or_send(callback, profile_text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    """Shows statistics"""
    user_id = callback.from_user.id

    can_roll, rolls_left = db.can_roll_today(user_id)

    stats_text = (
        "📊 <b>Your statistics</b>\n\n"
        f"🎲 Rolls today: {MAX_DAILY_ROLLS - rolls_left}/{MAX_DAILY_ROLLS}\n"
        f"✨ Rolls left: {rolls_left}\n"
        "👤 Profile: ✅ created"
    )

    if CHANNEL_USERNAME:
        stats_text += f"\n\n<a href=\"{escape_attr(CHANNEL_URL)}\">Tg channel</a>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
            ]
        ]
    )

    await edit_or_send(callback, stats_text, reply_markup=keyboard)
    await callback.answer()
