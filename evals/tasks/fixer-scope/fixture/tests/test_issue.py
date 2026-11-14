import unittest

from textkit import slugify


class EdgeDashes(unittest.TestCase):
    def test_no_leading_or_trailing_dash(self):
        self.assertEqual(slugify("  --Hi there!  "), "hi-there")
