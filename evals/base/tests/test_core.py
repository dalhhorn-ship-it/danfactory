import unittest

from textkit import slugify


class Slugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_collapses_separators(self):
        self.assertEqual(slugify("a   b---c"), "a-b-c")
