import unittest

from textkit.core import most_common_word


class MostCommonWord(unittest.TestCase):
    def test_counts_case_insensitively(self):
        self.assertEqual(most_common_word("the cat and The dog and THE bird"), "the")

    def test_tie_goes_to_first_seen(self):
        self.assertEqual(most_common_word("b a a b"), "b")

    def test_empty(self):
        self.assertIsNone(most_common_word(""))
