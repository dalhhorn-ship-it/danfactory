import unittest


def _p(text):
    import semverlite
    return semverlite.parse(text)


class SemverCore(unittest.TestCase):
    def test_c1_core_fields(self):
        v = _p("1.2.3")
        self.assertEqual((v.major, v.minor, v.patch), (1, 2, 3))
        self.assertFalse(v.prerelease)
        self.assertFalse(v.build)

    def test_c2_prerelease_and_build(self):
        v = _p("1.0.0-alpha.1+exp.sha.5114f85")
        self.assertEqual(tuple(v.prerelease), ("alpha", "1"))
        self.assertEqual(tuple(v.build), ("exp", "sha", "5114f85"))

    def test_c3_leading_zeros(self):
        for bad in ("01.2.3", "1.2.3-01"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _p(bad)
        v = _p("1.2.3-0a")
        self.assertEqual(tuple(v.prerelease), ("0a",))

    def test_c4_invalid_strings(self):
        for bad in ("", "1.2", "1.2.3.4", "v1.2.3", "1.2.3-", "1.2.3+",
                    "1.2.3-a..b", "-1.2.3"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _p(bad)

    def test_c5_numeric_core_order(self):
        self.assertTrue(_p("1.10.0") > _p("1.9.0"))
        self.assertTrue(_p("1.9.0") < _p("1.10.0"))
        self.assertTrue(_p("2.0.0") > _p("1.99.99"))
        self.assertTrue(_p("1.0.10") > _p("1.0.9"))

    def test_c6_prerelease_lower(self):
        self.assertTrue(_p("1.0.0-alpha") < _p("1.0.0"))
        self.assertTrue(_p("1.0.0") > _p("1.0.0-alpha"))

    def test_c7_spec_chain(self):
        chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta",
                 "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11",
                 "1.0.0-rc.1", "1.0.0"]
        vs = [_p(s) for s in chain]
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                with self.subTest(a=chain[i], b=chain[j]):
                    self.assertTrue(vs[i] < vs[j])
                    self.assertTrue(vs[j] > vs[i])

    def test_c8_build_ignored_in_ordering(self):
        a, b = _p("1.0.0+a"), _p("1.0.0+b")
        self.assertFalse(a < b)
        self.assertFalse(a > b)
        self.assertTrue(a <= b)
        self.assertTrue(a >= b)

    def test_c9_str_roundtrip(self):
        for s in ("1.2.3", "0.0.0", "1.0.0-alpha.1+exp.sha.5114f85",
                  "1.0.0-rc.1", "1.0.0+build.5", "1.2.3-0a", "10.20.30"):
            with self.subTest(s=s):
                self.assertEqual(str(_p(s)), s)

    def test_c10_bump(self):
        import semverlite
        self.assertEqual(str(semverlite.bump(_p("1.2.3"), "major")), "2.0.0")
        self.assertEqual(str(semverlite.bump(_p("1.2.3"), "minor")), "1.3.0")
        self.assertEqual(str(semverlite.bump(_p("1.2.3"), "patch")), "1.2.4")
        self.assertEqual(str(semverlite.bump(_p("1.2.3-rc.1"), "patch")), "1.2.4")
        self.assertEqual(str(semverlite.bump(_p("1.2.3+b.1"), "minor")), "1.3.0")

    def test_c10_bump_invalid_part(self):
        import semverlite
        for part in ("prerelease", "", "Major"):
            with self.subTest(part=part):
                with self.assertRaises(ValueError):
                    semverlite.bump(_p("1.2.3"), part)


if __name__ == "__main__":
    unittest.main()
