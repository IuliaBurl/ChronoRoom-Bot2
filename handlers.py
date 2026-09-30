from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, CHANNEL_USERNAME, MAX_ANSWER_LENGTH, MAX_DAILY_ROLLS
import database
import utils
import questions

router = Router()
db = database.Database()

class ProfileStates(StatesGroup):
    waiting_for_answer_1 = State()
    waiting_for_answer_2 = State()
    waiting_for_answer_3 = State()
    waiting_for_answer_4 = State()
    waiting_for_answer_5 = State()
    waiting_for_photo = State()
    waiting_for_name = State()

# === STATES FOR COMMUNICATION ===
class ChatStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_username_request = State()


async def check_subscription(user_id: int, bot) -> bool:
    """Checks if the user is subscribed to the channel"""
    try:
        member = await bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}",
            user_id=user_id
        )
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        print(f"Subscription check error: {e}")
        return True


@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Handler for the /start command"""
    await state.clear()

    user = message.from_user

    # Subscription check
    is_subscribed = await check_subscription(user.id, message.bot)

    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ I subscribed", callback_data="check_subscription"),
                    InlineKeyboardButton(text="🔗 Go to channel", url=f"https://t.me/{CHANNEL_USERNAME}")
                ]
            ]
        )

        await message.answer(
            "📢 *To use the bot, you need to subscribe to [our channel](https://t.me/"
            + CHANNEL_USERNAME +
            ")*\n\n"
            "This is needed for:\n"
            "• Receiving notifications about new features\n"
            "• Participating in giveaways\n"
            "• A community of like-minded people\n\n"
            "After subscribing, press the button below",
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return

    db.add_user(user.id, user.username, user.full_name)

    profile = db.get_profile(user.id)

    if profile:
        await show_main_menu(message)
    else:
        await show_welcome_message(message, state)


async def show_welcome_message(message: types.Message, state: FSMContext):
    """Shows a welcome message and offers to create a profile"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✨ Create profile", callback_data="create_profile")
            ]
        ]
    )

    await message.answer(
        "👋 *Welcome to ChronoRoom!*\n\n"
        "I will help you find your 'lucky person' through the dice of fate.\n\n"
        "*How it works:*\n"
        "1. You create a unique profile (5 random questions)\n"
        "2. You roll the dice up to 3 times a day\n"
        "3. You find random profiles of other people\n"
        "4. If there is mutual sympathy, you get the contact\n\n"
        "Ready to start?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handler for pressing 'I subscribed'"""
    if await check_subscription(callback.from_user.id, callback.bot):
        await callback.message.delete()
        await start_command(callback.message, state)
    else:
        await callback.answer("You are not subscribed to the channel yet!", show_alert=True)


@router.callback_query(F.data == "create_profile")
async def create_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Starts profile creation"""
    await callback.message.delete()
    await start_profile_creation(callback.message, state)


async def start_profile_creation(message: types.Message, state: FSMContext):
    """Starts the profile creation process"""
    user_id = message.from_user.id

    await message.answer(
        "📝 *Profile creation*\n\n"
        "Now I will ask you *5 random questions* from our database.\n"
        "Answer honestly and interestingly - this way you will increase your chances!\n\n"
        f"💡 *Important:* each answer must be no more than {MAX_ANSWER_LENGTH} characters.\n\n"
        "Ready? Let's go! 🚀"
    )

    question_ids = utils.generate_question_set()

    await state.update_data(
        question_ids=question_ids,
        answers=[],
        current_question=0
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
            "Now send your *photo* for the profile (this will increase your chances 10 times!).\n"
            "Or press the 'Skip' button",
            reply_markup=keyboard,
            parse_mode="Markdown"
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
        f"*Question {current_q + 1} of 5:*\n{question_text}\n\n"
        f"💡 *Limit:* {MAX_ANSWER_LENGTH} characters",
        parse_mode="Markdown"
    )


@router.message(ProfileStates.waiting_for_answer_1)
@router.message(ProfileStates.waiting_for_answer_2)
@router.message(ProfileStates.waiting_for_answer_3)
@router.message(ProfileStates.waiting_for_answer_4)
@router.message(ProfileStates.waiting_for_answer_5)
async def handle_answer(message: types.Message, state: FSMContext):
    """Handler for answering a question"""

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

    # Ask the next question
    await ask_next_question(message, state)


@router.callback_query(F.data == "skip_photo")
async def skip_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    """Skip photo"""
    await callback.message.delete()
    await state.set_state(ProfileStates.waiting_for_name)
    await callback.message.answer(
        "Okay, there will be no photo.\n\n"
        "Now enter your *name* that will be displayed in the profile "
        "(it can be real or fictional):",
        parse_mode="Markdown"
    )


@router.message(ProfileStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    """Handler for receiving a photo"""
    # Save the photo_id
    photo_id = message.photo[-1].file_id
    user_id = message.from_user.id

    # Update the photo in the DB
    db.update_user_photo(user_id, photo_id)

    # Move on to the name
    await state.set_state(ProfileStates.waiting_for_name)
    await message.answer(
        "📸 Photo saved!\n\n"
        "Now enter your *name* that will be displayed in the profile "
        "(it can be real or fictional):",
        parse_mode="Markdown"
    )


@router.message(ProfileStates.waiting_for_name)
async def handle_name(message: types.Message, state: FSMContext):
    """Handler for receiving the name"""
    user_id = message.from_user.id
    name = message.text.strip()

    if len(name) > 50:
        await message.answer("❌ The name is too long! Maximum 50 characters.")
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

    db.create_profile(
        user_id=user_id,
        name=name,
        questions_ids=question_ids,
        answers=answers
    )

    await state.clear()

    await message.answer(
        "🎉 *Profile successfully created!*\n\n"
        f"Now you can search for your 'lucky person'. "
        f"You have {MAX_DAILY_ROLLS} dice rolls per day.",
        parse_mode="Markdown"
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
        "✨ *Main menu*\n\n"
        "Choose an action:",
        reply_markup=keyboard,
        parse_mode="Markdown"
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

    await callback.message.edit_text(
        "🔄 *Creating a new profile*\n\n"
        "⚠️ *Attention:* When creating a new profile:\n"
        "• The current profile will be deleted\n"
        "• You will be asked 5 new random questions\n"
        "• You will need to add a photo and name again\n\n"
        "Are you sure you want to create a new profile?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_new_profile")
async def confirm_new_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Confirmation of creating a new profile"""
    await callback.message.delete()
    await start_profile_creation(callback.message, state)


@router.callback_query(F.data == "roll_dice")
async def roll_dice_callback(callback: types.CallbackQuery):
    """Dice roll handler"""
    user_id = callback.from_user.id

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

        db.use_roll(user_id)

    except Exception as e:
        print(f"User {profile['user_id']} is unavailable: {e}")

        db.deactivate_profile(profile['user_id'])

        db.refund_roll(user_id)

        await callback.answer(
            "😔 This user is no longer available. Try again!",
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

    if profile.get('photo_id'):
        await callback.bot.send_photo(
            chat_id=callback.from_user.id,
            photo=profile['photo_id'],
            caption=profile_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            profile_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    """Return to the main menu"""
    await callback.message.delete()
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
        chat_from=from_user_id
    )

    await callback.message.edit_text(
        f"💌 *Write a message for {target_profile['name']}*\n\n"
        "This message will be sent anonymously through the bot. "
        "The recipient will see your full profile and will be able to reply.\n\n"
        "Write your first message:",
        parse_mode="Markdown"
    )

    await state.set_state(ChatStates.waiting_for_message)
    await callback.answer()


@router.message(ChatStates.waiting_for_message)
async def handle_chat_message(message: types.Message, state: FSMContext):
    """Chat message handler"""
    data = await state.get_data()
    target_user_id = data.get('chat_with')
    from_user_id = data.get('chat_from')

    if not target_user_id:
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

    try:
        if from_profile.get('photo_id'):
            await message.bot.send_photo(
                chat_id=target_user_id,
                photo=from_profile['photo_id'],
                caption=f"🎯 *You have become someone's LUCKY PERSON!*\n\n"
                        f"Someone rolled the dice of fate and it landed on your profile. "
                        f"Here is their profile:\n\n{from_profile_text}",
                parse_mode="Markdown"
            )
        else:
            await message.bot.send_message(
                chat_id=target_user_id,
                text=f"🎯 *You have become someone's LUCKY PERSON!*\n\n"
                     f"Someone rolled the dice of fate and it landed on your profile. "
                     f"Here is their profile:\n\n{from_profile_text}",
                parse_mode="Markdown"
            )

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
            text=f"💌 *Message from {from_profile['name']}:*\n\n"
                 f"*{message.text}*\n\n"
                 f"*Choose an action:*\n"
                 f"• 💌 Reply - continue communicating through the bot\n"
                 f"• 🤝 Exchange usernames - request a mutual exchange of contacts\n"
                 f"• ❌ Reject - stop communicating",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        keyboard_back = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
                ]
            ]
        )

        await message.answer(
            f"✅ *Message sent to {target_profile['name']}!*\n\n"
            f"Your profile was shown to the recipient. Now wait for a reply. "
            f"If the user wants to exchange contacts, "
            f"you will receive a request for consent.",
            reply_markup=keyboard_back,
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"Message sending error: {e}")
        await message.answer("❌ Failed to send the message. The user may have blocked the bot.")

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
        chat_from=current_user_id
    )

    await callback.message.edit_text(
        f"💬 *Reply to {from_profile['name']}*\n\n"
        "Write your message. It will be sent anonymously through the bot.",
        parse_mode="Markdown"
    )

    await state.set_state(ChatStates.waiting_for_message)
    await callback.answer()


@router.callback_query(F.data.startswith("mutual_username_"))
async def mutual_username_callback(callback: types.CallbackQuery):
    """Request for mutual username exchange"""
    target_user_id = int(callback.data.split("_")[-1])  # The one from whom we request
    current_user_id = callback.from_user.id  # The one who requests

    target_profile = db.get_profile(target_user_id)
    current_profile = db.get_profile(current_user_id)

    if not target_profile or not current_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    # Send the username exchange request TO THE ONE FROM WHOM WE REQUEST
    try:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, I agree", callback_data=f"accept_mutual_{current_user_id}"),
                    InlineKeyboardButton(text="❌ No, reject", callback_data=f"reject_mutual_{current_user_id}")
                ]
            ]
        )

        await callback.bot.send_message(
            chat_id=target_user_id,
            text=f"🤝 *{current_profile['name']} suggests exchanging usernames!*\n\n"
                 f"If you agree, both of you will receive each other's usernames.\n\n"
                 f"Do you agree to a mutual exchange of contacts?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        # Notify the requester
        await callback.message.edit_text(
            f"🤝 *Username exchange request sent!*\n\n"
            f"You suggested to {target_profile['name']} to exchange contacts.\n"
            f"Wait for a reply. If the user agrees, both of you will receive each other's usernames.",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"Request sending error: {e}")
        await callback.answer("Failed to send the request.", show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("accept_mutual_"))
async def accept_mutual_callback(callback: types.CallbackQuery):
    """Accepting mutual username exchange"""
    requester_id = int(callback.data.split("_")[-1])  # The one who requested
    accepter_id = callback.from_user.id  # The one who accepts

    # Get information about the users
    requester_profile = db.get_profile(requester_id)
    accepter_profile = db.get_profile(accepter_id)

    if not requester_profile or not accepter_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    cursor = db.conn.cursor()

    cursor.execute("SELECT username FROM users WHERE user_id = ?", (requester_id,))
    requester_result = cursor.fetchone()
    requester_username = requester_result['username'] if requester_result and requester_result['username'] else "not set"

    cursor.execute("SELECT username FROM users WHERE user_id = ?", (accepter_id,))
    accepter_result = cursor.fetchone()
    accepter_username = accepter_result['username'] if accepter_result and accepter_result['username'] else "not set"

    try:
        await callback.bot.send_message(
            chat_id=requester_id,
            text=f"🎉 *{accepter_profile['name']} agreed to exchange usernames!*\n\n"
                 f"🤝 *Mutual exchange completed:*\n\n"
                 f"• Your username: @{requester_username if requester_username != 'not set' else 'not set'}\n"
                 f"• {accepter_profile['name']}'s username: @{accepter_username if accepter_username != 'not set' else 'not set'}\n\n"
                 f"Now you can write to each other directly on Telegram!",
            parse_mode="Markdown"
        )
    except:
        pass  # If sending failed

    try:
        await callback.message.edit_text(
            f"🎉 *You agreed to exchange usernames with {requester_profile['name']}!*\n\n"
            f"🤝 *Mutual exchange completed:*\n\n"
            f"• Your username: @{accepter_username if accepter_username != 'not set' else 'not set'}\n"
            f"• {requester_profile['name']}'s username: @{requester_username if requester_username != 'not set' else 'not set'}\n\n"
            f"Now you can write to each other directly on Telegram!",
            parse_mode="Markdown"
        )
    except:
        # If the message was already edited, send a new one
        await callback.message.answer(
            f"🎉 *You agreed to exchange usernames with {requester_profile['name']}!*\n\n"
            f"🤝 *Mutual exchange completed:*\n\n"
            f"• Your username: @{accepter_username if accepter_username != 'not set' else 'not set'}\n"
            f"• {requester_profile['name']}'s username: @{requester_username if requester_username != 'not set' else 'not set'}\n\n"
            f"Now you can write to each other directly on Telegram!",
            parse_mode="Markdown"
        )

    await callback.answer()


@router.callback_query(F.data.startswith("reject_mutual_"))
async def reject_mutual_callback(callback: types.CallbackQuery):
    """Rejecting mutual username exchange"""
    requester_id = int(callback.data.split("_")[-1])
    accepter_id = callback.from_user.id

    # Get information about the users
    requester_profile = db.get_profile(requester_id)
    accepter_profile = db.get_profile(accepter_id)

    if not requester_profile or not accepter_profile:
        await callback.answer("User not found.", show_alert=True)
        return

    try:
        await callback.bot.send_message(
            chat_id=requester_id,
            text=f"❌ *{accepter_profile['name']} rejected the username exchange request.*\n\n"
                 f"You can continue communicating through the bot.",
            parse_mode="Markdown"
        )
    except:
        pass  # If sending failed

    await callback.message.edit_text(
        f"❌ *You rejected the username exchange request from {requester_profile['name']}.*\n\n"
        f"The user has been notified of the rejection.",
        parse_mode="Markdown"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("reject_chat_"))
async def reject_chat_callback(callback: types.CallbackQuery):
    """Rejecting chat"""
    from_user_id = int(callback.data.split("_")[-1])

    # Get information about the users
    from_profile = db.get_profile(from_user_id)
    current_profile = db.get_profile(callback.from_user.id)

    if from_profile and current_profile:
        # Optionally notify the sender about the rejection
        try:
            await callback.bot.send_message(
                chat_id=from_user_id,
                text=f"❌ *{current_profile['name']} rejected your message.*\n\n"
                     f"This user is not ready to communicate.",
                parse_mode="Markdown"
            )
        except:
            pass

    await callback.message.edit_text(
        "❌ *You rejected the message.*\n\n"
        "The sender has been notified of the rejection.",
        parse_mode="Markdown"
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
        await callback.bot.send_photo(
            chat_id=user_id,
            photo=profile['photo_id'],
            caption=profile_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            profile_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    await callback.answer()


@router.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    """Shows statistics"""
    user_id = callback.from_user.id

    can_roll, rolls_left = db.can_roll_today(user_id)

    stats_text = (
        f"📊 *Your statistics*\n\n"
        f"🎲 Rolls today: {MAX_DAILY_ROLLS - rolls_left}/{MAX_DAILY_ROLLS}\n"
        f"✨ Rolls left: {rolls_left}\n"
        f"👤 Profile: ✅ created\n\n"
        f"[Tg channel](https://t.me/{CHANNEL_USERNAME})"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ To menu", callback_data="main_menu")
            ]
        ]
    )

    await callback.message.edit_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

    await callback.answer()
