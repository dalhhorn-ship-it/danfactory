"""Acceptance tests for docs/specs/truncate.md (one or more per criterion)."""
import unittest


def truncate(*a, **k):
    from textkit import truncate as f
    return f(*a, **k)


class TruncateAcceptance(unittest.TestCase):
    # 1. short enough -> unchanged
    def test_c1_shorter_than_width_unchanged(self):
        self.assertEqual(truncate("hi", 10), "hi")

    def test_c1_exactly_width_unchanged(self):
        self.assertEqual(truncate("hello", 5), "hello")

    def test_c1_unchanged_with_custom_suffix(self):
        self.assertEqual(truncate("hello world", 11, suffix="~"), "hello world")

    # 2. longer -> ends with suffix, total length <= width
    def test_c2_ends_with_suffix_and_fits(self):
        r = truncate("hello world foo", 10)
        self.assertTrue(r.endswith("..."))
        self.assertLessEqual(len(r), 10)

    def test_c2_long_word_ends_with_suffix_and_fits(self):
        r = truncate("abcdefghijklmnopqrstuvwxyz", 12)
        self.assertTrue(r.endswith("..."))
        self.assertLessEqual(len(r), 12)

    def test_c2_one_char_over_width(self):
        r = truncate("abcdef gh", 8)
        self.assertTrue(r.endswith("..."))
        self.assertLessEqual(len(r), 8)

    # 3. cut at last word boundary that fits
    def test_c3_cuts_at_last_space(self):
        # kept part (12 chars) is "the quick br"; last space is after "quick"
        self.assertEqual(truncate("the quick brown fox", 15), "the quick...")

    def test_c3_cuts_at_last_space_other_text(self):
        # kept part (15 chars) is "alpha beta gamm"
        self.assertEqual(truncate("alpha beta gamma delta", 18), "alpha beta...")

    def test_c3_no_word_is_split(self):
        text = "alpha beta gamma delta"
        r = truncate(text, 18)
        body = r[: -len("...")]
        for word in body.split():
            self.assertIn(word, text.split())

    # 4. one long word -> hard cut, exactly width
    def test_c4_hard_cut_exact_width(self):
        r = truncate("abcdefghijklmnopqrstuvwxyz", 10)
        self.assertEqual(len(r), 10)
        self.assertEqual(r, "abcdefg...")

    def test_c4_hard_cut_exact_width_other_width(self):
        r = truncate("abcdefghijklmnopqrstuvwxyz", 15)
        self.assertEqual(len(r), 15)
        self.assertEqual(r, "abcdefghijkl...")

    def test_c4_hard_cut_with_custom_suffix(self):
        r = truncate("abcdefghijklmnopqrstuvwxyz", 6, suffix="~")
        self.assertEqual(r, "abcde~")

    # 5. trailing spaces / ,;:. removed before suffix
    def test_c5_trailing_comma_removed(self):
        # kept part "hello, world"; cut at last space -> "hello," -> "hello"
        self.assertEqual(truncate("hello, world and more", 15), "hello...")

    def test_c5_multiple_trailing_spaces_and_punctuation_removed(self):
        # kept part "one ;, tw"; cut at last space -> "one ;," -> "one"
        self.assertEqual(truncate("one ;, two three", 12), "one...")

    def test_c5_each_listed_punctuation_removed(self):
        for p in ",;:.":
            with self.subTest(p=p):
                r = truncate("abc" + p + "defghijkl", 7)
                self.assertEqual(r, "abc...")

    # 6. width < len(suffix) -> ValueError
    def test_c6_width_smaller_than_default_suffix(self):
        with self.assertRaises(ValueError):
            truncate("hello world", 2)

    def test_c6_width_smaller_than_custom_suffix(self):
        with self.assertRaises(ValueError):
            truncate("hello world", 1, suffix="--")

    def test_c6_width_equal_to_suffix_length_is_allowed(self):
        r = truncate("hello world", 3)
        self.assertTrue(r.endswith("..."))
        self.assertLessEqual(len(r), 3)

    # 7. custom suffix, including empty
    def test_c7_custom_suffix_used(self):
        r = truncate("hello world foo", 10, suffix="~~")
        self.assertTrue(r.endswith("~~"))
        self.assertFalse(r.endswith("..."))
        self.assertLessEqual(len(r), 10)

    def test_c7_empty_suffix_word_boundary(self):
        # kept part (8 chars) is "hello wo"; cut at last space
        self.assertEqual(truncate("hello world foo", 8, suffix=""), "hello")

    def test_c7_empty_suffix_hard_cut(self):
        self.assertEqual(truncate("abcdefghijkl", 5, suffix=""), "abcde")


if __name__ == "__main__":
    unittest.main()
