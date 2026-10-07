import unittest
from html.parser import HTMLParser

from questions import QUESTIONS_DICT
from utils import check_answer_length, escape_attr, escape_html, format_profile, generate_question_set

# Strings that used to be dangerous in legacy Markdown mode (or are in HTML mode).
HOSTILE = [
    r"¯\_(ツ)_/¯",          # the shrug: backslash + underscores
    "snake_case_name",
    "*bold* _italic_ `code` [link](http://x)",
    "unclosed * star and _ underscore and ` tick and [ bracket",
    "C:\\path\\*",
    "<b>not bold</b> & <script>alert(1)</script>",
    "a < b > c && d",
]


class _TagCollector(HTMLParser):
    """Collects the tags Telegram would see in an HTML message."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.tags = []
        self.balanced = True

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.balanced = False


def make_profile(name="Alice", answer="Tea"):
    profile = {"name": name}
    for i in range(1, 6):
        profile[f"question{i}_id"] = i
        profile[f"answer{i}"] = answer
    return profile


class EscapeHtmlTests(unittest.TestCase):
    def test_escapes_html_specials(self):
        self.assertEqual(escape_html("<b>&</b>"), "&lt;b&gt;&amp;&lt;/b&gt;")

    def test_none_and_non_strings(self):
        self.assertEqual(escape_html(None), "")
        self.assertEqual(escape_html(42), "42")

    def test_markdown_characters_are_left_alone(self):
        # They have no meaning in HTML mode, so they must not be touched
        # (a stray backslash would be shown to the user as-is).
        self.assertEqual(escape_html(r"¯\_(ツ)_/¯ *x* `y` [z]"), r"¯\_(ツ)_/¯ *x* `y` [z]")

    def test_attr_escapes_quotes(self):
        self.assertEqual(escape_attr('https://t.me/x"y'), "https://t.me/x&quot;y")


class FormatProfileTests(unittest.TestCase):
    def test_hostile_text_never_adds_tags(self):
        for text in HOSTILE:
            with self.subTest(text=text):
                out = format_profile(make_profile(name=text, answer=text), QUESTIONS_DICT)
                parser = _TagCollector()
                parser.feed(out)
                parser.close()
                # Only our own <b> tags may exist, and they must be balanced.
                self.assertEqual(set(parser.tags), {"b"})
                self.assertTrue(parser.balanced)
                self.assertNotIn("<script", out)

    def test_hostile_text_survives_round_trip(self):
        import html
        for text in HOSTILE:
            with self.subTest(text=text):
                out = format_profile(make_profile(answer=text), QUESTIONS_DICT)
                self.assertIn(html.escape(text, quote=False), out)

    def test_empty_profile(self):
        self.assertEqual(format_profile({}, QUESTIONS_DICT), "Profile not found")

    def test_skips_empty_answers(self):
        profile = make_profile()
        profile["answer3"] = ""
        out = format_profile(profile, QUESTIONS_DICT)
        self.assertEqual(out.count("❓"), 4)


class HelpersTests(unittest.TestCase):
    def test_question_set_is_unique_and_valid(self):
        for _ in range(50):
            ids = generate_question_set()
            self.assertEqual(len(ids), 5)
            self.assertEqual(len(set(ids)), 5)
            self.assertTrue(all(i in QUESTIONS_DICT for i in ids))

    def test_answer_length(self):
        self.assertFalse(check_answer_length(""))
        self.assertFalse(check_answer_length("   "))
        self.assertTrue(check_answer_length("x" * 200))
        self.assertFalse(check_answer_length("x" * 201))


if __name__ == "__main__":
    unittest.main()
