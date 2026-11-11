"""DASH-3: Carbon look. Token parity, WCAG contrast, offline/no-JS, square corners, size budget. No browser needed."""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
if not os.path.isfile(os.path.join(ROOT, "scripts", "obs", "theme.py")):
    raise unittest.SkipTest("no theme module in this tree")
import dashboard  # noqa: E402
from obs import theme  # noqa: E402

# Checked-in Carbon v11 reference table (White and g100), independent of theme.py.
CARBON = {
    "background": ("#ffffff", "#161616"), "layer-01": ("#f4f4f4", "#262626"), "layer-02": ("#ffffff", "#393939"),
    "border-subtle-01": ("#c6c6c6", "#525252"), "border-strong-01": ("#8d8d8d", "#6f6f6f"),
    "text-primary": ("#161616", "#f4f4f4"), "text-secondary": ("#525252", "#c6c6c6"), "text-helper": ("#6f6f6f", "#a8a8a8"),
    "text-on-color": ("#ffffff", "#ffffff"), "link-primary": ("#0f62fe", "#78a9ff"), "focus": ("#0f62fe", "#ffffff"),
    "support-error": ("#da1e28", "#fa4d56"), "support-success": ("#198038", "#42be65"),
    "support-warning": ("#f1c21b", "#f1c21b"), "support-info": ("#0043ce", "#4589ff"),
    "notification-background-error": ("#fff1f1", "#262626"), "notification-background-success": ("#defbe6", "#262626"),
    "notification-background-warning": ("#fcf4d6", "#262626"), "notification-background-info": ("#edf5ff", "#262626"),
}

# (foreground token, background token, minimum ratio): text 4.5, non-text indicators 3.
PAIRS = []
for bg in ("background", "layer-01", "layer-02", "layer-accent-01"):
    for fg in ("text-primary", "text-secondary", "text-helper", "link-primary", "text-error", "text-success", "text-warning"):
        # helper text and status text are only used on background/layer-01/layer-02, not on the table header band
        if bg == "layer-accent-01" and fg not in ("text-primary", "text-secondary"):
            continue
        PAIRS.append((fg, bg, 4.5))
for n in ("error", "success", "warning", "info"):
    PAIRS.append(("text-primary", "notification-background-" + n, 4.5))
for c in ("red", "green", "yellow", "blue", "gray"):
    PAIRS.append(("tag-%s-text" % c, "tag-%s-bg" % c, 4.5))
for i in range(4):
    PAIRS.append(("hm-%d-text" % i, "hm-%d-bg" % i, 4.5))
PAIRS += [("text-on-color", "button-primary", 4.5), ("text-primary", "am-mot", 4.5), ("text-primary", "am-app", 4.5),
          ("text-primary", "am-tech", 4.5), ("focus", "background", 3.0), ("border-interactive", "background", 3.0),
          ("support-error", "notification-background-error", 3.0), ("support-info", "notification-background-info", 3.0)]
PAIRS += [("dv-%d" % i, bg, 3.0) for i in range(1, 7) for bg in ("background", "layer-01")]
PAIRS += [("support-success", "layer-01", 3.0), ("support-error", "layer-01", 3.0), ("border-strong-01", "background", 3.0)]


def lum(hexc):
    ch = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def block_vars(block):
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-fA-F]{6});", block))


class CarbonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = dashboard.render(dashboard.collect())
        cls.css = re.search(r"<style>(.*?)</style>", cls.page, re.S).group(1)
        i = cls.css.index("@media (prefers-color-scheme: dark)")
        j = cls.css.index(':root[data-theme="dark"]')
        cls.light = block_vars(cls.css[:i])
        cls.dark_media = block_vars(cls.css[i:j])
        cls.dark = block_vars(cls.css[j:cls.css.index("\n}\n", j)])

    def test_token_parity_with_carbon_table(self):
        for tok, (lt, dk) in CARBON.items():
            self.assertEqual(self.light.get(tok), lt, "light " + tok)
            self.assertEqual(self.dark.get(tok), dk, "dark " + tok)
        self.assertEqual(self.dark, self.dark_media)  # prefers-color-scheme and data-theme blocks never drift

    def test_theme_switching_pattern(self):
        self.assertIn(':root:not([data-theme="light"])', self.css)
        self.assertIn(':root[data-theme="dark"]', self.css)

    def test_contrast_aa_over_token_pairs(self):
        bad = []
        for theme_name, toks in (("light", self.light), ("dark", self.dark)):
            for fg, bg, need in PAIRS:
                r = ratio(toks[fg], toks[bg])
                if r < need:
                    bad.append("%s %s on %s %.2f < %.1f" % (theme_name, fg, bg, r, need))
        self.assertEqual(bad, [])

    def test_no_script_no_external_reference(self):
        self.assertNotRegex(self.page, r"(?i)<script|<link\b|@import|@font-face")
        self.assertNotRegex(self.css, r"url\(")
        for m in re.finditer(r'\b(?:src|href)="([^"]*)"', self.page):
            self.assertFalse(m.group(1).startswith(("http://", "https://", "//")) and "<a " not in self.page[m.start() - 40:m.start()],
                             m.group(1))
        self.assertNotRegex(re.sub(r"<a [^>]*>", "", self.page), r'(?:src|href)="https?:')

    def test_square_corners_no_shadows_no_gradients(self):
        self.assertNotRegex(self.css, r"box-shadow|gradient")
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", self.css, flags=re.S))
        radii = [(sel.strip(), body) for sel, body in rules if re.search(r"border-radius:\s*(?!0[;\s]|0px)", body)]
        tags = {".tag", ".steps li", ".chip", ".imp", ".pf", ".rm-card .size", ".rm-card .state", ".rm-card .prd", ".rv-st", ".rv-list .state"}
        for sel, _b in radii:
            self.assertTrue({s.strip() for s in sel.split(",")} <= tags, "rounded non-tag: " + sel)

    def test_no_vendor_name_in_page_chrome(self):
        # Project data (backlog titles) may mention the vendor; the page's own markup, title and header must not.
        chrome = re.sub(r"<style>.*?</style>", "", dashboard.TEMPLATE, flags=re.S)
        self.assertNotIn("IBM", chrome)
        self.assertNotIn("IBM", re.search(r"<title>(.*?)</title>", self.page).group(1))
        self.assertNotRegex(self.page, r"(?i)<img|<svg[^>]*ibm")

    def test_attribution_and_fonts(self):
        self.assertIn("Carbon Design System", self.css)
        self.assertIn("Apache-2.0", self.css)
        self.assertRegex(self.css, r"--font-sans:'IBM Plex Sans',system-ui")
        self.assertRegex(self.css, r"--font-mono:'IBM Plex Mono',ui-monospace")

    def test_obs_modules_use_no_hard_coded_colours(self):
        odir = os.path.join(ROOT, "scripts", "obs")
        for fn in os.listdir(odir):
            if fn.endswith(".py") and fn != "theme.py":
                with open(os.path.join(odir, fn), encoding="utf-8") as fh:
                    src = fh.read()
                self.assertNotRegex(src, r"""['"(=:\s]#[0-9a-fA-F]{3,8}\b""", fn)

    def test_size_budget(self):
        # Baseline before DASH-3: page 90239 B, stylesheet 12671 B. The stylesheet may grow by at most 20% of the old page.
        self.assertLessEqual(len(self.css.encode()), 12671 + int(0.2 * 90239))
        self.assertLessEqual(len(self.page.encode()), 1_000_000)

    def test_alerts_have_icon_and_text(self):
        self.assertRegex(self.css, r"li\.alert::before\s*\{\s*content:")
        self.assertRegex(self.css, r"\.tile\.bad \.badge::before\s*\{\s*content:")


if __name__ == "__main__":
    unittest.main()
