"""DASH-4: Roadmap sub-views (6-month, proposed Gantt, releases). Offline, no model calls, no browser."""
import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
if not os.path.isfile(os.path.join(ROOT, "scripts", "obs", "roadmap_data.py")):
    raise unittest.SkipTest("no roadmap views in this tree")
import dashboard  # noqa: E402
from obs import roadmap_data as D, roadmap_views as V  # noqa: E402

TODAY = datetime.date(2026, 11, 11)  # a Wednesday

BACKLOG = """# Backlog
## Milestone: M1 — First (target: 2026-12-15)
- [x] AAA-1 Done one (S) #feature
- [x] AAA-2 Done two (M) (release: v0.1) #feature
- [ ] AAA-3 Open small (S) #feature
- [ ] AAA-4 Open medium (M) (after: AAA-5) #feature
- [ ] AAA-5 Open large (L) #feature
- [!] AAA-6 Blocked one (S) #feature
- [ ] AAA-7 No size here #feature
## Milestone: M2 — Next (release: v0.3)
- [ ] BBB-1 <script>alert(1)</script> item (S)
"""


def ms(text=BACKLOG):
    return dashboard.parse_backlog(text)


def hist():
    return {"AAA-1": {"title": "", "todo": "2026-10-01", "doing": "2026-10-20", "done": "2026-10-28"},
            "AAA-2": {"title": "", "todo": "2026-10-01", "doing": "2026-11-02", "done": "2026-11-05"}}


def data(text=BACKLOG, conf=None, h=None, ok=True, tags=None):
    return D.build(ms(text), TODAY, conf, hist() if h is None else h, ok, tags)


def page(d):
    return V.render(d, "<p>SEQ</p>")


class Views(unittest.TestCase):
    def test_ac1_default_and_override(self):
        self.assertIn('id="rv-sequence" class="tab-input" checked', page(data()))
        self.assertIn('id="rv-gantt" class="tab-input" checked', page(data(conf={"roadmap_view": "gantt"})))
        for bad in ("nope", 7, None, ["gantt"]):
            self.assertIn('id="rv-sequence" class="tab-input" checked', page(data(conf={"roadmap_view": bad})))
        self.assertIn("<p>SEQ</p>", page(data()))
        self.assertEqual(page(data()).count(" checked"), 1)

    def test_ac2_css_only_subtabs(self):
        h = page(data())
        self.assertEqual(h.count('type="radio" name="rmview"'), 4)
        self.assertNotIn("<script", h)
        css = dashboard.theme.css()
        for v in D.VIEWS:
            self.assertIn("#rv-%s:checked ~ .rv-%s" % (v, v), css)
            self.assertIn('#rv-%s:focus-visible ~ .subtabs label[for="rv-%s"]' % (v, v), css)

    def test_markers_do_not_leak_into_sequence_view(self):
        titles = [i["title"] for m in ms() for i in m["items"]]
        self.assertFalse(any("release:" in t or "after:" in t for t in titles))
        self.assertEqual(ms()[1]["name"], "M2 — Next")
        self.assertEqual(ms()[1]["release"], "v0.3")

    def test_ac3_month_with_target(self):
        m = data()["months"]
        self.assertEqual([c.strftime("%Y-%m") for c in m["cols"]][0], "2026-10")
        self.assertEqual([c.strftime("%Y-%m") for c in m["cols"]][-1], "2027-03")
        self.assertEqual([(n, str(d)) for n, d in m["targets_in"]], [("M1 — First", "2026-12-15")])
        self.assertNotIn("No dates yet", V.months_view(m))

    def test_ac3_no_targets_empty_state_and_done_items(self):
        d = data(BACKLOG.replace(" (target: 2026-12-15)", ""))
        html = V.months_view(d["months"])
        self.assertIn("No dates yet: add (target: YYYY-MM-DD) to a milestone", html)
        self.assertEqual([i["id"] for i in d["months"]["done"]], ["AAA-1", "AAA-2"])
        self.assertIn("AAA-2", html)

    def test_ac4_unscheduled_not_in_a_month(self):
        m = data()["months"]
        self.assertEqual([i["id"] for i in m["unscheduled"]][:3], ["AAA-3", "AAA-4", "AAA-5"])
        self.assertTrue(all(i["state"] != "done" for i in m["unscheduled"]))
        self.assertFalse({i["id"] for i in m["unscheduled"]} & {i["id"] for i in m["done"]})
        self.assertIn("Unscheduled", V.months_view(m))

    def test_ac5_today_marker_inside_window(self):
        m = data()["months"]
        self.assertTrue(m["start"] <= TODAY < m["end"])
        self.assertIn("today 2026-11-11", V.months_view(m))

    def test_ac6_gantt_order_width_wip(self):
        g = data()["gantt"]
        o = {r["id"]: r for r in g["open"]}
        self.assertEqual(o["AAA-3"]["start"], TODAY)
        # WIP=1: sequential, no overlap, in backlog order except dependency and blocked rules
        rows = sorted(g["open"], key=lambda r: r["start"])
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(a["end"], b["start"])
        self.assertEqual(g["open"][0]["id"], "AAA-3")
        # working days: S = 1 day starting Wed 11-11 ends Thu 11-12; L = 8 working days spans a weekend
        self.assertEqual(o["AAA-3"]["end"], datetime.date(2026, 11, 12))
        l = o["AAA-5"]
        self.assertEqual((l["end"] - l["start"]).days, 12)  # Thu 11-12 + 8 working days = Tue 11-24
        # bar width is proportional to calendar days in the SVG (9px per day)
        svg = V.gantt_view(g)
        self.assertIn('class="bar est" x=', svg)
        self.assertRegex(svg, r'width="%d" height="14" fill="url\(#gt-hatch\)"' % (9 * 12))

    def test_ac6_wip_two_runs_in_parallel(self):
        g = data(conf={"wip": 2})["gantt"]
        o = {r["id"]: r for r in g["open"]}
        self.assertEqual(o["AAA-3"]["start"], o["AAA-5"]["start"])  # two slots: both start today
        self.assertEqual(data(conf={"wip": 0})["settings"]["wip"], 1)

    def test_ac7_size_override_and_missing(self):
        g = data(conf={"size_days": {"S": 2, "M": 5, "L": 10}})["gantt"]
        o = {r["id"]: r for r in g["open"]}
        self.assertEqual(o["AAA-3"]["days"], 2)
        self.assertEqual(o["AAA-7"]["days"], 5)
        self.assertTrue(o["AAA-7"]["size_missing"])
        self.assertIn("size missing", V.gantt_view(g))
        self.assertEqual(data(conf={"size_days": {"S": -1, "X": 4, "M": "a"}})["settings"]["size_days"], D.DEFAULT_DAYS)

    def test_ac6_blocked_after_unblocked_and_marked(self):
        ids = [r["id"] for r in data()["gantt"]["open"]]
        self.assertGreater(ids.index("AAA-6"), ids.index("AAA-7"))
        self.assertEqual(ids[-1], "AAA-6")
        self.assertIn("blocked", V.gantt_view(data()["gantt"]))

    def test_ac8_estimates_labelled(self):
        svg = V.gantt_view(data()["gantt"])
        for w in ("Proposed, not a commitment", "estimated", "est.", "S=1, M=3, L=8", "WIP=1", "hatch"):
            self.assertIn(w, svg)

    def test_ac9_done_bars_from_history(self):
        g = data()["gantt"]
        d = {r["id"]: r for r in g["done"]}
        self.assertEqual((str(d["AAA-1"]["start"]), str(d["AAA-1"]["end"])), ("2026-10-20", "2026-10-28"))
        self.assertIn('class="bar done"', V.gantt_view(g))

    def test_ac9_no_history(self):
        d = data(h={}, ok=False)
        g = d["gantt"]
        self.assertEqual(g["done"], [])
        self.assertEqual([i["id"] for i in g["undated"]], ["AAA-1", "AAA-2"])
        html = V.gantt_view(g)
        self.assertIn("date unknown", html)
        self.assertIn("Done, date unknown", V.months_view(d["months"]))
        page(d)

    def test_ac10_after_dependency(self):
        g = data()["gantt"]
        o = {r["id"]: r for r in g["open"]}
        self.assertGreaterEqual(o["AAA-4"]["start"], o["AAA-5"]["end"])
        self.assertIn('class="dep"', V.gantt_view(g))
        self.assertNotIn('class="dep"', V.gantt_view(data(BACKLOG.replace(" (after: AAA-5)", ""))["gantt"]))

    def test_ac10_cycle_does_not_hang(self):
        t = "## Milestone: M\n- [ ] AAA-1 a (after: AAA-2)\n- [ ] AAA-2 b (after: AAA-1)\n- [ ] AAA-3 c (after: ZZZ-9)\n"
        self.assertEqual(len(data(t)["gantt"]["open"]), 3)

    def test_ac11_releases_with_tags_and_markers(self):
        tags = [("v0.1.0", datetime.date(2026, 11, 6)), ("v0.2.0", datetime.date(2026, 11, 20))]
        t = BACKLOG.replace("(release: v0.1) ", "").replace("AAA-3 Open small (S)", "AAA-3 Open small (S) (release: v0.2)")
        r = data(t, tags=tags)["releases"]
        names = [g["name"] for g in r["groups"]]
        self.assertEqual(names, ["v0.3", "v0.2", "v0.1.0"])  # planned first, then shipped newest first
        g = {x["name"]: x for x in r["groups"]}
        self.assertTrue(g["v0.2"]["shipped"])
        self.assertEqual(str(g["v0.2"]["date"]), "2026-11-20")
        self.assertFalse(g["v0.3"]["shipped"])
        self.assertEqual([i["id"] for i in g["v0.1.0"]["items"]], ["AAA-1", "AAA-2"])  # done by date <= tag date
        html = V.releases_view(r, True)
        self.assertIn("shipped 2026-11-20", html)
        self.assertIn("planned", html)
        self.assertIn("AAA-3", html)

    def test_ac12_no_tags_no_markers(self):
        t = BACKLOG.replace(" (release: v0.1)", "").replace(" (release: v0.3)", "")
        d = data(t)
        self.assertFalse(d["releases"]["any"])
        html = V.releases_view(d["releases"], True)
        self.assertIn("No releases yet", html)
        self.assertIn("git tag vX.Y.Z", html)
        self.assertIn("(release: vX.Y)", html)
        self.assertEqual([i["id"] for i in d["releases"]["unassigned"]], ["AAA-1", "AAA-2"])

    def test_ac13_git_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:  # not a git repo: git fails, files are absent
            d = D.collect(tmp, ms(), None, TODAY)
        self.assertFalse(d["history"])
        self.assertEqual(d["releases"]["groups"][0]["name"], "v0.3")
        h = page(d)
        for view in ("6-month", "Gantt", "releases"):
            self.assertIn(view.lower(), h.lower())

    def test_tags_read_from_real_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True, capture_output=True)  # noqa: E731
            run("init", "-q")
            run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "x")
            run("tag", "v0.1.0")
            run("tag", "release-1")  # not vX.Y.Z: ignored
            self.assertEqual([t for t, _d in D.read_tags(tmp)], ["v0.1.0"])

    def test_ac15_escaping_and_no_script(self):
        h = page(data())
        self.assertNotIn("<script", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertNotRegex(h, r"https?://")

    def test_ac17_no_hex_in_view_modules(self):
        for fn in ("roadmap_data.py", "roadmap_views.py"):
            with open(os.path.join(ROOT, "scripts", "obs", fn), encoding="utf-8") as fh:
                self.assertNotRegex(fh.read(), r"""['"(=:\s]#[0-9a-fA-F]{3,8}\b""")

    def test_real_backlog_renders(self):
        d = dashboard.collect()
        self.assertIn("roadmap_views", d)
        h = dashboard.render(d)
        self.assertEqual(len(re.findall(r'class="rv rv-', h)), 4)


if __name__ == "__main__":
    unittest.main()
