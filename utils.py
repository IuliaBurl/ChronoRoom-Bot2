import html
import random
from typing import List

from questions import QUESTIONS


def escape_html(text) -> str:
    """Escapes user-supplied text for Telegram's HTML parse mode.

    In HTML mode only '<', '>' and '&' are special, so there are no
    context-dependent escaping rules (unlike legacy Markdown).
    """
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


def escape_attr(text) -> str:
    """Escapes a value for use inside an HTML attribute (e.g. a link href)."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def generate_question_set(count: int = 5) -> List[int]:
    """Generates a random set of 5 unique questions"""
    if count > len(QUESTIONS):
        count = len(QUESTIONS)
    return random.sample(range(1, len(QUESTIONS) + 1), count)


def format_profile(profile: dict, questions_dict: dict) -> str:
    """Formats a profile for display (Telegram HTML)"""
    if not profile:
        return "Profile not found"

    text = f"🧑‍🚀 <b>Name:</b> {escape_html(profile['name'])}\n\n"

    for i in range(1, 6):
        q_id = profile[f'question{i}_id']
        answer = profile[f'answer{i}']
        if q_id and answer:
            question_text = questions_dict.get(q_id, f"Question #{q_id}")
            text += f"❓ <b>{escape_html(question_text)}</b>\n"
            text += f"💬 {escape_html(answer)}\n\n"

    text += "⏳ <b>Contact:</b> will become available upon mutual match"
    return text


def check_answer_length(text: str, max_length: int = 200) -> bool:
    """Checks the length of an answer"""
    if not text:
        return False
    return 0 < len(text.strip()) <= max_length
