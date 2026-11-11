"""Dashboard stylesheet in the Carbon v11 visual language (White light theme, g100 dark theme). Inline CSS only.

Colours live here as CSS custom properties; obs SVG modules emit classes only and the rules below paint them
with var(--...). Light is the default; dark applies for prefers-color-scheme: dark unless data-theme="light",
and always for data-theme="dark" (same switching pattern as before).
"""

ATTRIBUTION = ("Visual language after the Carbon Design System (Apache-2.0, https://carbondesignsystem.com); "
               "tokens reimplemented as inline CSS, no Carbon package or asset is loaded. Font names reference IBM Plex "
               "(SIL OFL 1.1) but no font file is embedded; the stack falls back to system fonts.")

# Carbon v11 tokens. Keys are CSS custom property names (without --).
LIGHT = {
    "background": "#ffffff", "layer-01": "#f4f4f4", "layer-02": "#ffffff", "layer-accent-01": "#e0e0e0",
    "layer-hover-01": "#e8e8e8",
    "border-subtle-01": "#c6c6c6", "border-strong-01": "#8d8d8d", "border-interactive": "#0f62fe",
    "text-primary": "#161616", "text-secondary": "#525252", "text-helper": "#6f6f6f", "text-on-color": "#ffffff",
    "link-primary": "#0f62fe", "focus": "#0f62fe", "button-primary": "#0f62fe",
    "support-error": "#da1e28", "support-success": "#198038", "support-warning": "#f1c21b", "support-info": "#0043ce",
    "text-error": "#da1e28", "text-success": "#0e6027", "text-warning": "#8e6a00",
    "notification-background-error": "#fff1f1", "notification-background-success": "#defbe6",
    "notification-background-warning": "#fcf4d6", "notification-background-info": "#edf5ff",
    "tag-red-bg": "#ffd7d9", "tag-red-text": "#a2191f", "tag-green-bg": "#a7f0ba", "tag-green-text": "#0e6027",
    "tag-yellow-bg": "#fcf4d6", "tag-yellow-text": "#684e00", "tag-blue-bg": "#d0e2ff", "tag-blue-text": "#0043ce",
    "tag-gray-bg": "#e0e0e0", "tag-gray-text": "#161616",
    "dv-1": "#6929c4", "dv-2": "#1192e8", "dv-3": "#005d5d", "dv-4": "#9f1853", "dv-5": "#fa4d56", "dv-6": "#b28600",
    "hm-0-bg": "#edf5ff", "hm-0-text": "#161616", "hm-1-bg": "#a6c8ff", "hm-1-text": "#161616",
    "hm-2-bg": "#4589ff", "hm-2-text": "#161616", "hm-3-bg": "#0043ce", "hm-3-text": "#ffffff",
    "am-mot": "#f6f2ff", "am-app": "#e5f6ff", "am-tech": "#d9fbfb",
}
DARK = {
    "background": "#161616", "layer-01": "#262626", "layer-02": "#393939", "layer-accent-01": "#393939",
    "layer-hover-01": "#333333",
    "border-subtle-01": "#525252", "border-strong-01": "#6f6f6f", "border-interactive": "#4589ff",
    "text-primary": "#f4f4f4", "text-secondary": "#c6c6c6", "text-helper": "#a8a8a8", "text-on-color": "#ffffff",
    "link-primary": "#78a9ff", "focus": "#ffffff", "button-primary": "#0f62fe",
    "support-error": "#fa4d56", "support-success": "#42be65", "support-warning": "#f1c21b", "support-info": "#4589ff",
    "text-error": "#ff8389", "text-success": "#42be65", "text-warning": "#f1c21b",
    "notification-background-error": "#262626", "notification-background-success": "#262626",
    "notification-background-warning": "#262626", "notification-background-info": "#262626",
    "tag-red-bg": "#750e13", "tag-red-text": "#ffb3b8", "tag-green-bg": "#044317", "tag-green-text": "#a7f0ba",
    "tag-yellow-bg": "#483700", "tag-yellow-text": "#fddc69", "tag-blue-bg": "#002d9c", "tag-blue-text": "#a6c8ff",
    "tag-gray-bg": "#393939", "tag-gray-text": "#f4f4f4",
    "dv-1": "#a56eff", "dv-2": "#33b1ff", "dv-3": "#08bdba", "dv-4": "#ff7eb6", "dv-5": "#fa4d56", "dv-6": "#f1c21b",
    "hm-0-bg": "#001d6c", "hm-0-text": "#ffffff", "hm-1-bg": "#002d9c", "hm-1-text": "#ffffff",
    "hm-2-bg": "#0f62fe", "hm-2-text": "#ffffff", "hm-3-bg": "#78a9ff", "hm-3-text": "#161616",
    "am-mot": "#31135e", "am-app": "#012749", "am-tech": "#022b30",
}


def _vars(tokens, indent="  "):
    return "\n".join("%s--%s:%s;" % (indent, k, v) for k, v in tokens.items())


def _root():
    return (":root {\n%s\n  --sp-01:2px; --sp-02:4px; --sp-03:8px; --sp-04:12px; --sp-05:16px; --sp-06:24px; --sp-07:32px; --sp-09:48px;\n"
            "  --font-sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;\n"
            "  --font-mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;\n}\n"
            "@media (prefers-color-scheme: dark) {\n  :root:not([data-theme=\"light\"]) {\n%s\n  }\n}\n"
            ":root[data-theme=\"dark\"] {\n%s\n}\n") % (_vars(LIGHT), _vars(DARK, "    "), _vars(DARK))


RULES = """
* { box-sizing:border-box; }
body { margin:0; background:var(--background); color:var(--text-primary); font:400 .875rem/1.25rem var(--font-sans); }
main { max-width:1584px; margin:0 auto; padding:var(--sp-06) var(--sp-05) var(--sp-09); }
header { display:flex; flex-wrap:wrap; gap:var(--sp-04) var(--sp-06); align-items:flex-end; justify-content:space-between; margin-bottom:var(--sp-06); }
h1 { font:400 1.75rem/2.25rem var(--font-sans); margin:0; }
h2 { font:600 1rem/1.375rem var(--font-sans); margin:0 0 var(--sp-04); }
h3 { font:600 .75rem/1rem var(--font-sans); letter-spacing:.32px; color:var(--text-secondary); margin:var(--sp-05) 0 var(--sp-03); }
.muted { color:var(--text-secondary); } .small { font-size:.75rem; line-height:1rem; }
.mono, code { font-family:var(--font-mono); font-size:.8125rem; }
a { color:var(--link-primary); text-decoration:underline; }
a:hover { text-decoration:none; }
a:focus-visible, .tabs label:focus-visible { outline:2px solid var(--focus); outline-offset:1px; }
.meta { color:var(--text-secondary); font-size:.8125rem; text-align:right; }
.steps { display:flex; gap:var(--sp-03); list-style:none; padding:0; margin:var(--sp-04) 0 0; flex-wrap:wrap; }
.tag, .steps li, .chip, .imp, .pf, .rm-card .size, .rm-card .state, .rm-card .prd, .rv-st, .rv-list .state { border-radius:1.5rem; }
.steps li { font-size:.75rem; line-height:1rem; padding:var(--sp-02) var(--sp-03); border:1px solid var(--border-strong-01); color:var(--text-secondary); }
.steps li.done { background:var(--tag-green-bg); border-color:var(--tag-green-bg); color:var(--tag-green-text); }
.steps li.done::before { content:"\\2713\\00a0"; }
.steps li.now { background:var(--button-primary); border-color:var(--button-primary); color:var(--text-on-color); font-weight:600; }
.chip { display:inline-block; font-size:.75rem; line-height:1rem; padding:var(--sp-02) var(--sp-03); background:var(--tag-gray-bg); color:var(--tag-gray-text); margin:var(--sp-03) var(--sp-03) 0 0; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:var(--sp-02); margin-bottom:var(--sp-05); }
.tile { background:var(--layer-01); padding:var(--sp-05); border-top:3px solid var(--border-strong-01); }
.tile.ok { border-top-color:var(--support-success); } .tile.bad { border-top-color:var(--support-error); } .tile.warn { border-top-color:var(--support-warning); }
.tile .label { font-size:.75rem; line-height:1rem; letter-spacing:.32px; color:var(--text-secondary); }
.tile .value { font:400 1.75rem/2.25rem var(--font-sans); font-variant-numeric:tabular-nums; margin:var(--sp-02) 0; }
.tile .sub { font-size:.75rem; line-height:1rem; color:var(--text-secondary); }
.tile .badge { font-weight:600; }
.tile.ok .badge { color:var(--text-success); } .tile.bad .badge { color:var(--text-error); } .tile.warn .badge { color:var(--text-warning); }
.tile.ok .badge::before { content:"\\2713\\00a0"; } .tile.bad .badge::before { content:"\\2715\\00a0"; } .tile.warn .badge::before { content:"\\25B2\\00a0"; }
.spark { width:100%; height:36px; margin-top:var(--sp-03); display:block; }
.spark polyline { fill:none; stroke:var(--dv-2); stroke-width:1.75; vector-effect:non-scaling-stroke; }
.spark circle { fill:var(--dv-2); }
.bars { margin:0; } .bars figcaption { font-size:.75rem; } .bars svg { width:100%; height:44px; display:block; }
.bars rect { fill:var(--dv-2); } .bars rect.zero { fill:var(--layer-accent-01); } .bars .axis { display:flex; justify-content:space-between; font-size:.6875rem; color:var(--text-secondary); }
.charts { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:var(--sp-04); margin-bottom:var(--sp-04); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:var(--sp-05); }
.card { background:var(--layer-01); padding:var(--sp-05); min-width:0; }
ul.plain, ul.ms { list-style:none; padding:0; margin:0; }
ul.plain li { padding:var(--sp-03) 0; border-bottom:1px solid var(--border-subtle-01); }
ul.plain li:last-child { border-bottom:0; }
ul.ms li { margin-bottom:var(--sp-04); }
.row { display:flex; justify-content:space-between; gap:var(--sp-03); }
.bar { height:8px; background:var(--layer-accent-01); margin-top:var(--sp-02); overflow:hidden; }
.bar span { display:block; height:100%; background:var(--button-primary); }
.counts { display:grid; grid-template-columns:repeat(4,1fr); gap:var(--sp-02); }
.count { background:var(--layer-02); padding:var(--sp-03); text-align:center; }
.count b { display:block; font:400 1.5rem/2rem var(--font-sans); font-variant-numeric:tabular-nums; }
.count span { font-size:.75rem; color:var(--text-secondary); }
.count.blocked b { color:var(--text-error); } .count.doing b { color:var(--link-primary); } .count.done b { color:var(--text-success); }
.scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:.875rem; }
th { text-align:left; font-size:.875rem; font-weight:600; color:var(--text-primary); background:var(--layer-accent-01); padding:var(--sp-03) var(--sp-05); }
td { padding:var(--sp-03) var(--sp-05); border-bottom:1px solid var(--border-subtle-01); vertical-align:top; }
td.mono, td.nowrap { white-space:nowrap; }
.imp, .pf, .rm-card .size, .rm-card .state, .rm-card .prd { font-size:.75rem; line-height:1rem; padding:0 var(--sp-03); background:var(--tag-gray-bg); color:var(--tag-gray-text); white-space:nowrap; }
.imp { display:inline-block; }
.imp.high, .pf.c-uncovered { background:var(--tag-red-bg); color:var(--tag-red-text); }
.imp.medium, .pf.s-weak, .pf.c-covered-weak, .rm-card .prd { background:var(--tag-yellow-bg); color:var(--tag-yellow-text); }
.imp.low, .pf.s-strong, .pf.c-covered, .rm-card .prd.approved { background:var(--tag-green-bg); color:var(--tag-green-text); }
.pf.c-uncovered { font-weight:600; }
.dots { letter-spacing:1px; color:var(--dv-2); }
td.hm { text-align:center; font-variant-numeric:tabular-nums; min-width:70px; font-family:var(--font-mono); }
td.hm.h0 { background:var(--hm-0-bg); color:var(--hm-0-text); font-weight:600; } td.hm.h1 { background:var(--hm-1-bg); color:var(--hm-1-text); }
td.hm.h2 { background:var(--hm-2-bg); color:var(--hm-2-text); } td.hm.h3 { background:var(--hm-3-bg); color:var(--hm-3-text); }
.econ { display:grid; grid-template-columns:minmax(260px,420px) 1fr; gap:var(--sp-05); align-items:start; } tr.best td { font-weight:600; }
svg.scatter .ax { stroke:var(--border-strong-01); } svg.scatter .tk, svg.scatter text { font-size:10px; fill:var(--text-secondary); }
svg.flow .fl-cov, .fl-key .fl-cov { fill:var(--dv-3); } svg.flow .fl-done, .fl-key .fl-done { fill:var(--dv-2); }
svg.flow .fl-doing, .fl-key .fl-doing { fill:var(--dv-6); } svg.flow .fl-todo, .fl-key .fl-todo { fill:var(--layer-accent-01); }
svg.flow .ax { stroke:var(--border-strong-01); } svg.flow .tk { font-size:10px; fill:var(--text-secondary); } .fl-key { margin-right:var(--sp-04); font-size:.75rem; white-space:nowrap; }
svg.scatter .pt circle { fill:var(--dv-2); } svg.scatter .pt.best circle { fill:var(--dv-3); stroke:var(--text-primary); stroke-width:2; }
li.alert, ul.plain li.alert { display:flex; gap:var(--sp-03); background:var(--notification-background-error); color:var(--text-primary);
  border-left:3px solid var(--support-error); border-bottom:0; padding:var(--sp-03) var(--sp-05); margin-bottom:var(--sp-02); }
li.alert::before { content:"\\2715"; flex:none; font-weight:600; color:var(--support-error); }
footer { margin-top:var(--sp-06); font-size:.75rem; color:var(--text-secondary); }
.tabs { display:flex; border-bottom:1px solid var(--border-subtle-01); margin-bottom:var(--sp-05); overflow-x:auto; white-space:nowrap; }
.tabs label { flex:none; padding:var(--sp-04) var(--sp-05) 11px; cursor:pointer; color:var(--text-secondary); border-bottom:2px solid transparent; margin-bottom:-1px; font-size:.875rem; line-height:1.125rem; }
.tabs label:hover { background:var(--layer-hover-01); color:var(--text-primary); }
.tab-input { position:absolute; opacity:0; pointer-events:none; }
.panel { display:none; }
"""

RULES2 = """
.stack { display:grid; gap:var(--sp-05); }
tr.grp td { background:var(--layer-accent-01); }
.arch { display:block; }
.arch text { fill:var(--text-primary); font-size:12px; text-anchor:middle; }
.arch .sub { font-size:10px; fill:var(--text-secondary); }
.arch .band { fill:var(--layer-01); }
.arch .band-l { text-anchor:start; font-weight:600; font-size:13px; fill:var(--text-secondary); }
.arch .band-e { text-anchor:start; fill:var(--text-secondary); }
.arch .box rect { stroke:var(--border-strong-01); stroke-width:1; }
.arch .box.am-mot rect { fill:var(--am-mot); } .arch .box.am-app rect { fill:var(--am-app); } .arch .box.am-tech rect { fill:var(--am-tech); }
.arch .box.drift rect { stroke:var(--support-error); stroke-width:2; stroke-dasharray:5 3; }
.arch .edges line { stroke:var(--text-secondary); stroke-width:1; opacity:.45; }
.rm { --lane-w:minmax(150px,180px); --col-w:minmax(220px,1fr); display:grid; gap:var(--sp-03); min-width:max-content;
  grid-template-columns:var(--lane-w) repeat(var(--cols),var(--col-w)); }
.rm-col-h { display:flex; flex-direction:column; font-size:.875rem; padding:var(--sp-02); border-bottom:2px solid var(--border-strong-01); }
.rm-lane-h { display:flex; flex-direction:column; justify-content:flex-start; font-size:.875rem; padding:var(--sp-04); border-left:4px solid var(--border-interactive); background:var(--layer-accent-01);
  position:sticky; left:0; z-index:1; border-right:8px solid var(--background); }
.rm-lane-h.foundation { border-left-color:var(--support-warning); }
.rm-cell { list-style:none; margin:0; padding:var(--sp-03); background:var(--layer-01); border:1px dashed var(--border-subtle-01); display:flex; flex-direction:column; gap:var(--sp-03); }
.rm-card { display:flex; flex-wrap:wrap; align-items:baseline; gap:var(--sp-03); background:var(--layer-02); border-left:3px solid var(--border-interactive); padding:var(--sp-03); font-size:.8125rem; }
.rm-cell.foundation .rm-card { border-left-color:var(--support-warning); }
.rm-card .t { flex:1 1 120px; }
.rm-card .b { display:flex; gap:var(--sp-02); }
.rm-card .seq, .rm-next .seq { font-variant-numeric:tabular-nums; font-weight:600; color:var(--text-secondary); min-width:1.4em; }
.rm-card .size, .rm-card .state, .rm-card .prd { font-size:.6875rem; }
.rm-card.doing { outline:2px solid var(--border-interactive); outline-offset:-2px; } .rm-card.doing .state { background:var(--tag-blue-bg); color:var(--tag-blue-text); }
.rm-card.blocked .state { background:var(--tag-red-bg); color:var(--tag-red-text); }
.rm-col-h .why { color:var(--text-primary); margin-top:var(--sp-02); max-width:40ch; }
.rm-next { margin:0 0 var(--sp-04); padding:var(--sp-03) var(--sp-05); background:var(--notification-background-info); border-left:3px solid var(--support-info); font-size:.8125rem; }
.rm-next ol { list-style:none; margin:var(--sp-03) 0 0; padding:0; display:flex; flex-direction:column; gap:var(--sp-02); }
.rm-next li { display:flex; align-items:baseline; gap:var(--sp-03); }
.rm-next .t { flex:1 1 0; min-width:0; }
.rm-done { font-size:.8125rem; color:var(--text-success); margin:0 0 var(--sp-03); }
.rm-card.done { opacity:.7; } .rm-card.done .t { text-decoration:line-through; } .rm-card.done .seq { color:var(--text-success); }
.rmv > .tab-input { position:absolute; opacity:0; pointer-events:none; }
.subtabs { display:flex; border-bottom:1px solid var(--border-subtle-01); margin-bottom:var(--sp-04); overflow-x:auto; white-space:nowrap; }
.subtabs label { flex:none; padding:var(--sp-03) var(--sp-05) 7px; cursor:pointer; color:var(--text-secondary); border-bottom:2px solid transparent; margin-bottom:-1px; font-size:.8125rem; }
.subtabs label:hover { background:var(--layer-hover-01); color:var(--text-primary); }
.rv { display:none; }
#rv-sequence:checked ~ .rv-sequence { display:block; }
#rv-months:checked ~ .rv-months { display:block; }
#rv-gantt:checked ~ .rv-gantt { display:block; }
#rv-releases:checked ~ .rv-releases { display:block; }
#rv-sequence:checked ~ .subtabs label[for="rv-sequence"], #rv-months:checked ~ .subtabs label[for="rv-months"], #rv-gantt:checked ~ .subtabs label[for="rv-gantt"], #rv-releases:checked ~ .subtabs label[for="rv-releases"] { color:var(--text-primary); font-weight:600; border-bottom-color:var(--border-interactive); }
#rv-sequence:focus-visible ~ .subtabs label[for="rv-sequence"], #rv-months:focus-visible ~ .subtabs label[for="rv-months"], #rv-gantt:focus-visible ~ .subtabs label[for="rv-gantt"], #rv-releases:focus-visible ~ .subtabs label[for="rv-releases"] { outline:2px solid var(--focus); outline-offset:-2px; }
.rv-chart { border:1px solid var(--border-subtle-01); background:var(--background); margin-top:var(--sp-04); max-width:100%; }
.rv-chart svg { display:block; max-width:none; }
.rv-empty { padding:var(--sp-03) var(--sp-05); background:var(--notification-background-info); border-left:3px solid var(--support-info); margin:var(--sp-03) 0; }
.rv-assume { padding:var(--sp-03) var(--sp-05); background:var(--notification-background-warning); border-left:3px solid var(--support-warning); font-size:.8125rem; margin:0 0 var(--sp-04); }
.rv-list li { display:flex; flex-wrap:wrap; gap:var(--sp-03); align-items:baseline; }
.rv-rel { margin-bottom:var(--sp-05); } .rv-rel h3 { font-size:.875rem; color:var(--text-primary); }
.rv-st { font-size:.75rem; padding:0 var(--sp-03); } .rv-st.shipped { background:var(--tag-green-bg); color:var(--tag-green-text); }
.rv-st.planned { background:var(--tag-blue-bg); color:var(--tag-blue-text); }
.rv-list .state { font-size:.6875rem; padding:0 var(--sp-03); background:var(--tag-gray-bg); color:var(--tag-gray-text); }
.rv-list .state.done { background:var(--tag-green-bg); color:var(--tag-green-text); } .rv-list .state.doing { background:var(--tag-blue-bg); color:var(--tag-blue-text); }
.rv-list .state.blocked { background:var(--tag-red-bg); color:var(--tag-red-text); }
svg.tl text, svg.gantt text { font-size:11px; fill:var(--text-primary); font-family:var(--font-sans); }
svg.tl .col, svg.gantt .col { fill:var(--background); } svg.tl .col.a { fill:var(--layer-01); }
svg.tl .mh { font-weight:600; font-size:12px; } svg.tl .rl, svg.gantt .rl, svg.tl .more, svg.gantt .tk, svg.gantt .bl2 { fill:var(--text-secondary); }
svg.tl .ax, svg.gantt .ax, svg.gantt .grid { stroke:var(--border-subtle-01); } svg.tl .ms path { fill:var(--support-info); } svg.tl .dn circle { fill:var(--support-success); }
svg .today line { stroke:var(--support-error); stroke-width:1.5; stroke-dasharray:4 3; } svg .today text { fill:var(--text-error); font-weight:600; }
svg.gantt .bar.done { fill:var(--dv-3); } svg.gantt .bar.est { stroke:var(--border-interactive); stroke-width:1.5; stroke-dasharray:4 2; }
svg.gantt .bar.est.blocked { stroke:var(--support-error); } svg.gantt .hb { fill:var(--layer-01); } svg.gantt .hl { stroke:var(--dv-2); stroke-width:2; }
svg.gantt .gl.bl { fill:var(--text-error); } svg.gantt .dep { fill:none; stroke:var(--text-secondary); stroke-width:1.25; }
@media (min-width:1056px) { main { padding-left:var(--sp-07); padding-right:var(--sp-07); } }
@media (max-width:671px) { .rm { --lane-w:104px; --col-w:260px; } .rm-col-h .why { max-width:none; max-height:3.75rem; overflow-y:auto; } .rm-col-h, .rm-cell, .rm-lane-h { align-self:start; } .rm-lane-h { padding:var(--sp-03); } .meta { text-align:left; } .grid, .econ { grid-template-columns:1fr; } h1 { font-size:1.25rem; line-height:1.75rem; } }
"""


def css():
    return "/* %s */\n%s%s%s" % (ATTRIBUTION, _root(), RULES.strip("\n") + "\n", RULES2.strip("\n"))
