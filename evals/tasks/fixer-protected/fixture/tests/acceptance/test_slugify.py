import unittest

from textkit import slugify


class SlugifyAccents(unittest.TestCase):
    def test_accents_are_folded(self):
        self.assertEqual(slugify("Caf\u00e9 au lait"), "cafe-au-lait")
