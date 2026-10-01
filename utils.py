import random
from typing import List

from questions import QUESTIONS


def escape_md(text) -> str:
    if text is None:
        return ""
    text = str(text)
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def generate_question_set(count: int = 5) -> List[int]:
    """Generates a random set of 5 unique questions"""
    if count > len(QUESTIONS):
        count = len(QUESTIONS)
    return random.sample(range(1, len(QUESTIONS) + 1), count)


def format_profile(profile: dict, questions_dict: dict) -> str:
    """Formats a profile for display"""
    if not profile:
        return "Profile not found"

    text = f"🧑‍🚀 *Name:* {escape_md(profile['name'])}\n\n"

    for i in range(1, 6):
        q_id = profile[f'question{i}_id']
        answer = profile[f'answer{i}']
        if q_id and answer:
            question_text = questions_dict.get(q_id, f"Question #{q_id}")
            text += f"❓ *{escape_md(question_text)}*\n"
            text += f"💬 {escape_md(answer)}\n\n"

    text += "⏳ *Contact:* will become available upon mutual match"
    return text


def check_answer_length(text: str, max_length: int = 200) -> bool:
    """Checks the length of an answer"""
    if not text:
        return False
    return 0 < len(text.strip()) <= max_length
