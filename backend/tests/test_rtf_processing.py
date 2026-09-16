import unittest

from app.rtf_processing import parse_rtf


class RtfTokenizerTests(unittest.TestCase):
    def test_unicode_and_hidden_destination(self):
        raw = rb"{\rtf1\ansi\ansicpg1252\uc1 A {\*\comment HIDDEN \cell} Caf\'e9 \u945?}"
        text, rows = __import__("app.rtf_processing", fromlist=["_parse"])._parse(raw)
        self.assertIn("Café α", text)
        self.assertNotIn("HIDDEN", text)

    def test_surrogate_pair_and_scoped_uc(self):
        raw = rb"{\rtf1\uc1 A {\uc0 \u55357\u56832} B}"
        text, _ = __import__("app.rtf_processing", fromlist=["_parse"])._parse(raw)
        self.assertIn("A 😀 B", text)

    def test_binary_braces_and_truncation(self):
        raw = rb"{\rtf1 A {\pict\bin4 {}{} } B}"
        self.assertEqual(parse_rtf(raw)[1], "A  B")
        with self.assertRaises(ValueError): parse_rtf(rb"{\rtf1 A \bin9 abc}")

    def test_malformed_and_empty(self):
        with self.assertRaises(ValueError): parse_rtf(rb"{\rtf1 abc")
        with self.assertRaises(ValueError): parse_rtf(rb"{\rtf1 {\fonttbl{\f0 Arial;}}}")


if __name__ == "__main__": unittest.main()
