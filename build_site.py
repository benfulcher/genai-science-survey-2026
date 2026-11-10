"""Build the public GitHub Pages version of the Faculty GenAI survey dashboard.

Takes the private dashboard (../genai-science-event/survey/dashboard/index.html, written for the claude.ai Dashboard
runtime) and the coded survey data, and writes a standalone static site:
  index.html            the same calcs and drawings, run by a small local stand-in for the dashboard runtime,
                        restyled in the event's look (rings, earthy palette, Hoefler Text + Avenir Next)
  data/responses.csv    one row per respondent, shuffled, with no ID, School, timestamp or free text
  data/segments.csv     comment excerpts tagged only with career stage and a random person key; identifying
                        excerpts withheld or lightly edited in [brackets]
  data/schools.csv      respondents per School (counts only)
  data/writeins.csv     write-in feelings, shuffled and detached from respondents
  data/meta.json        response count, School count and date range

Run: uv run --with pandas python build_site.py
"""
import json, math, random, re
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
SURVEY = HERE.parent / "genai-science-event" / "survey"
OUT = HERE / "docs"
(OUT / "data").mkdir(parents=True, exist_ok=True)
rng = random.Random(20261112)

# ---- de-identification ----------------------------------------------------------------------------------------
WITHHELD = "[Excerpt withheld: it could identify the respondent]"
# excerpts that name a unit, a document the respondent wrote, a thesis, or a distinctive research program
WITHHOLD = {(18, "u", 0), (18, "u", 1), (20, "p", 0), (16, "p", 0), (16, "u", 0), (45, "u", 0), (49, "u", 1), (35, "u", 5),
            *((30, "u", k) for k in range(6))}
# excerpts kept with the field or other specifics blurred: (id, kind, seg) -> [(old, new), ...]
EDITS = {
    (61, "p", 0): [("Many mathematicians have expressed", "Many [researchers in my field] have expressed"),
                   ('the declaration "A Severe Misalignment of AI in Mathematics". This was written by 25 Fields Medallists, and has been endorsed by over 8000 mathematicians worldwide.',
                    "[a recent declaration endorsed by thousands of researchers worldwide].")],
    (66, "p", 2): [("traditional replication in agricultural research", "traditional replication in [my field]"),
                   ("replication in traditional agricultural research", "replication in [my field]")],
    (66, "p", 3): [("in ag research we used research station and research farms", "in [my field] we use [controlled research sites]"),
                   ("acting and interacting in commercial farms", "acting and interacting in [real-world settings]"),
                   ("from soils, crops, animals, people", "[in the system]")],
    (34, "p", 0): [("given that renewable energy and energy transition is the thematic topic of our research", "given [the topic of our research]")],
    (49, "u", 0): [("simplify data analysis, read diagnostic tests", "simplify data analysis [...]")],
    (11, "u", 0): [("I've just published my first paper", "I've just published [a] paper")],
    (63, "p", 0): [("Work in conservation so concerned", "[Given my field,] concerned")],
    (35, "u", 3): [("Production of 10-12 min podcast summarising the content of a 4-week long teaching module", "Production of [short] podcast[s] summarising the content of a teaching module")],
}

resp = pd.read_csv(SURVEY / "responses.csv", keep_default_na=False)
seg = pd.read_csv(SURVEY / "segments.csv", keep_default_na=False)

def clean(r):
    key = (int(r["id"]), r["kind"], int(r["seg"]))
    if key in WITHHOLD:
        return WITHHELD
    t = r["text"]
    for old, new in EDITS.get(key, []):
        assert old in t, (key, old)
        t = t.replace(old, new)
    return t

hit = {(int(a), b, int(c)) for a, b, c in seg[["id", "kind", "seg"]].itertuples(index=False)}
missing = (WITHHOLD | set(EDITS)) - hit
assert not missing, f"redaction keys not in segments.csv: {missing}"
seg["text"] = seg.apply(clean, axis=1)

# random person keys, in random order, so neither key nor row order follows submission order
people = list(seg["id"].unique()); rng.shuffle(people)
key = {pid: f"p{k + 1}" for k, pid in enumerate(people)}
seg["pid"] = seg["id"].map(key)
seg["order"] = seg["id"].map({pid: k for k, pid in enumerate(people)})
seg = seg.sort_values(["order", "kind", "seg"])
seg[["pid", "kind", "seg", "text", "themes", "career"]].rename(columns={"pid": "id"}).to_csv(OUT / "data" / "segments.csv", index=False)

pub = resp[["career", "feelings", "use", "use_order", "outlook", "outlook_order"]].copy()
pub["perspective_text"] = (resp["perspective_text"].str.strip() != "").astype(int)  # whether they commented, not what
pub["use_text"] = (resp["use_text"].str.strip() != "").astype(int)
pub.sample(frac=1, random_state=7).to_csv(OUT / "data" / "responses.csv", index=False)

resp["school"].value_counts().rename_axis("label").reset_index(name="n").to_csv(OUT / "data" / "schools.csv", index=False)
w = [s for v in resp["feelings_other"] if v for s in v.split("; ")]; rng.shuffle(w)
w = [re.sub(r"my research as a[n]? anthropologist.*$", "my research [in my field]", s) for s in w]  # names a field that is near-unique here
assert not any("anthropolog" in s or "geograph" in s for s in w)
pd.DataFrame({"text": w}).to_csv(OUT / "data" / "writeins.csv", index=False)
dates = sorted(resp["submitted"].str[:10])
json.dump({"n": len(resp), "schools": int(resp["school"].nunique()), "first": dates[0], "last": dates[-1]},
          open(OUT / "data" / "meta.json", "w"))

# ---- page -----------------------------------------------------------------------------------------------------
src = (SURVEY / "dashboard" / "index.html").read_text()
assert src.startswith('<meta name="dash-one-writer">')
src = src.split("\n", 1)[1]

def sub(old, new, count=1):
    global src
    assert src.count(old) == count, (src.count(old), old[:70])
    src = src.replace(old, new)

# data the public files no longer carry at row level
sub("const dates = responses.map((r) => r.submitted).sort();", "const dates = [SV.meta.first, SV.meta.last];")
sub("{ metric: 'schools', value: new Set(responses.map((r) => r.school)).size },", "{ metric: 'schools', value: SV.meta.schools },")
sub("""    inputs: ['responses'], title: 'Respondents by School', description: 'Respondents from each School or unit.',
    fn: (responses) => {
      const n = responses.length;
      return d3.rollups(responses, (v) => v.length, (r) => r.school).map(([label, k]) => ({ label, n: k, total: n, pct: Math.round((100 * k) / n) })).sort((a, b) => b.n - a.n);""",
    """    inputs: ['schools_raw'], title: 'Respondents by School', description: 'Respondents from each School or unit.',
    fn: (rows) => {
      const n = d3.sum(rows, (r) => r.n);
      return rows.map((r) => ({ label: r.label, n: r.n, total: n, pct: Math.round((100 * r.n) / n) })).sort((a, b) => b.n - a.n);""")
sub("""    const d = dash.data('responses');
    if (d.status !== 'ok') { el.textContent = '—'; return; }
    const w = d.data.map((r) => r.feelings_other).filter(Boolean).flatMap((s) => s.split('; '));""",
    """    const d = dash.data('writeins');
    if (d.status !== 'ok') { el.textContent = '—'; return; }
    const w = d.data.map((r) => r.text).filter(Boolean);""")
sub("m.textContent = [r.school, r.career, r.use].map(SV.lab).join('  ·  ');", "m.textContent = SV.lab(r.career);")
sub('<p class="sv-note">Write-ins: <span data-draw="writeins" data-source="responses">—</span></p>',
    '<p class="sv-note">Write-ins: <span data-draw="writeins" data-source="writeins">—</span></p>')

# wording for a public audience (no talk slots), and stale counts
sub('<p class="sv-eyebrow">Talk 1 · Opening</p>', '<p class="sv-eyebrow">Part I</p>')
sub('<p class="sv-eyebrow">Talk 2 · Session 2 opener</p>', '<p class="sv-eyebrow">Part II</p>')
sub('<p class="sv-eyebrow">Cross-cut · Career stage</p>', '<p class="sv-eyebrow">Across career stages</p>')
sub("With 8 to 27 people per stage", "With 8 to 31 people per stage")
sub('The one "Other" respondent is left out.', 'The two "Other" respondents are left out.')
sub('<h1 class="sv-title">Generative AI in research: Faculty of Science survey</h1>',
    '<h1 class="sv-title">Generative AI in Scientific Research</h1>\n'
    '    <p class="sv-sub">Survey of researchers, for the event on Thursday 12 November 2026</p>')
sub("""Small groups (one person from a School, for example) could be identifiable from their comment, so take care before putting quotes on slides.</p>""",
    """For this public version, each quote shows only the respondent's career stage. Excerpts that could identify someone (a named unit, a thesis topic, a distinctive research program) are withheld, and a few others are lightly edited in [square brackets] to blur the field. Respondent-level data is published without IDs, Schools, timestamps or free text, in shuffled order.</p>""")

# ---- the event's look -----------------------------------------------------------------------------------------
def rings_svg(w, h, cx, cy, n, r0, dr, seed):
    r = random.Random(seed); ph = [r.uniform(0, 6.28) for _ in range(3)]; out = []
    for i in range(n):
        base = r0 + i * dr + r.uniform(-.12, .12) * dr; is_open = i == n - 1; pts = []
        for a in (range(120, 401, 3) if is_open else range(0, 361, 3)):
            t = math.radians(a)
            rr = base * (1 + .035 * math.sin(3 * t + ph[0] + i * .15) + .02 * math.sin(5 * t + ph[1]) + .015 * math.sin(2 * t + ph[2] + i * .3))
            pts.append(f"{cx + rr * math.cos(t):.1f},{cy + rr * math.sin(t):.1f}")
        f = i / (n - 1)
        col = "#d0901f" if is_open else "#%02x%02x%02x" % tuple(round(a + (b - a) * f) for a, b in zip((0xee, 0xd8, 0x9f), (0xd4, 0x8a, 0x58)))
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" stroke-width="{2.4 if is_open else 1.3}" stroke-linecap="round"/>')
    return f'<svg class="sv-rings" viewBox="0 0 {w} {h}" aria-hidden="true">{"".join(out)}</svg>'

RINGS = rings_svg(420, 420, 300, 120, 11, 14, 22, 11)
COLORS = ["#d0901f", "#5450a8", "#c75a2e", "#7d5236"]  # ochre, indigo, red clay, umber (brighter screen palette)
THEME = """
<style>
  :root {
    color-scheme: light;
    --font-anthropic-serif: "Hoefler Text", "Iowan Old Style", Georgia, serif;
    --font-anthropic-sans: "Avenir Next", Avenir, "Helvetica Neue", Arial, sans-serif;
    --color-fg: #22231c; --color-fg-muted: #66675a; --color-panel: #fff; --color-border-line: #e6dccb; --color-bad: #a24a26;
    --cds-chart-muted: #d9cfbf; --cds-chart-grid: #eee6d8; --cds-chart-axis: #b8ad99; --cds-border: #e6dccb;
    --cds-surface-popover: #fff; --cds-shadow-popover: 0 6px 20px rgba(34, 35, 28, .14); --cds-text-secondary: #66675a;
    --cds-radius: 14px; --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-lg: 22px;
    --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 18px; --cds-gap-lg: 26px; --cds-gap-xl: 44px;
    --cds-font-size-caption: 14px; --cds-font-size-heading: 20px; --cds-font-size-title: 40px; --cds-font-weight-medium: 600;
    --cds-dur-slow: .3s;
  }
  html { background: #fff; } body { margin: 0; padding: 40px 20px 64px; color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: 16px; }
  .sv { position: relative; }
  .sv-head { position: relative; padding-top: 12px; padding-right: min(34vw, 300px); min-height: 200px; }
  .sv-rings { position: absolute; top: -40px; right: -20px; width: min(42vw, 380px); height: auto; z-index: -1; }
  .sv-kicker { margin: 0; font-family: var(--font-anthropic-serif); font-style: italic; color: #d0901f; font-size: 19px; }
  .sv-sub { margin: 0; color: #5450a8; font-weight: 600; }
  .sv-eyebrow { font-family: var(--font-anthropic-serif) !important; font-style: italic; text-transform: none !important; letter-spacing: 0 !important; color: #d0901f !important; font-size: 18px !important; }
  #perspectives .sv-h2 { color: #b0442a; } #use .sv-h2 { color: #b07d1c; } #career-stage .sv-h2, #respondents .sv-h2 { color: #4f4ba0; }
  .sv-h2 { font-family: var(--font-anthropic-serif); font-weight: 400 !important; font-size: 30px !important; }
  .sv-card h3 { font-family: var(--font-anthropic-serif); font-weight: 400 !important; font-size: 22px !important; }
  .sv-card, .sv-tile { border: 1.5px dotted #e6cf9f !important; }
  #perspectives .sv-card { border-color: #e2ad9c !important; } #use .sv-card { border-color: #e6c47f !important; } #career-stage .sv-card { border-color: #bdb9e8 !important; }
  .sv-tile .v { color: #b0442a; } .sv-tile:nth-child(2) .v { color: #b07d1c; } .sv-tile:nth-child(3) .v { color: #4f4ba0; } .sv-tile:nth-child(4) .v { color: #c75a2e; }
  .sv-q { border-left-color: #e6cf9f !important; }
  .dash-skeleton { min-height: 160px; background: linear-gradient(90deg, #f6f1e8, #fbf8f2, #f6f1e8); border-radius: 8px; }
  .sv-foot { color: var(--color-fg-muted); font-size: 14px; margin: 0; }
  @media (max-width: 640px) { .sv-head { padding-right: 0; } .sv-rings { opacity: .45; } :root { --cds-font-size-title: 32px; } }
</style>"""
# a small stand-in for the claude.ai dashboard runtime: datasets, lazily computed calcs, and named drawings
RUNTIME = f"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
  window.dash = (() => {{
    const raw = {{}}, calcs = {{}}, cache = {{}}, draws = {{}};
    const api = {{
      colors: {json.dumps(COLORS)},
      calc(id, spec) {{ calcs[id] = spec; }},
      data(id) {{
        if (cache[id]) return cache[id];
        if (raw[id]) return raw[id];
        const c = calcs[id];
        if (!c) return {{ status: 'loading' }};
        const ins = c.inputs.map((i) => api.data(i)), bad = ins.find((d) => d.status !== 'ok');
        if (bad) return {{ status: bad.status }};
        try {{ return (cache[id] = {{ status: 'ok', data: c.fn(...ins.map((d) => d.data)) }}); }}
        catch (e) {{ console.error(id, e); return (cache[id] = {{ status: 'error' }}); }}
      }},
      draw(name, fn) {{
        if (fn) {{ draws[name] = fn; return; }}
        document.querySelectorAll(`[data-draw="${{name}}"]`).forEach((el) => draws[name](el));
      }},
      async load(files) {{
        await Promise.all(Object.entries(files).map(async ([id, url]) => {{
          try {{ raw[id] = {{ status: 'ok', data: await d3.csv(url, d3.autoType) }}; }}
          catch (e) {{ console.error(url, e); raw[id] = {{ status: 'error' }}; }}
        }}));
        Object.keys(draws).forEach((n) => api.draw(n));
      }},
    }};
    return api;
  }})();
  window.SV = {{ pick: {{ p: null, u: null }}, meta: {{}} }};
</script>"""
START = """
<script>
  fetch('data/meta.json').then((r) => r.json()).then((m) => { SV.meta = m; }).then(() => dash.load({
    responses: 'data/responses.csv', segments: 'data/segments.csv', schools_raw: 'data/schools.csv', writeins: 'data/writeins.csv',
  }));
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => ['stackbars', 'bars', 'themes', 'career', 'excite', 'feelgrid', 'mixstage', 'dumbbell'].forEach((n) => dash.draw(n)), 200); });
</script>"""
sub("window.SV = window.SV || { pick: { p: null, u: null } };", "window.SV = window.SV || { pick: { p: null, u: null }, meta: {} };", count=2)
# the dashboard page already carries the rings and the kicker line (survey/dashboard/restyle.py)
assert 'class="sv-rings"' in src and 'class="sv-kicker"' in src
sub('</section>\n</div>', '</section>\n  <p class="sv-foot">Organized by A/Prof Ben Fulcher, School of Physics. Survey analysis and page built with Claude.</p>\n</div>')

# the dashboard runtime gave each page script its own scope; plain scripts share one, so wrap each in a block
src = re.sub(r"<script>(.*?)</script>", lambda m: "<script>{" + m.group(1) + "}</script>", src, flags=re.S)
page = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>Generative AI in Scientific Research: survey results</title>\n'
        f'<meta name="description" content="Results of the University of Sydney Faculty of Science survey on generative AI in research, November 2026.">\n'
        f'{RUNTIME}\n{THEME}\n</head>\n<body>\n{src}\n{START}\n</body>\n</html>\n')
(OUT / "index.html").write_text(page)
(OUT / ".nojekyll").write_text("")
print(f"ok: {len(resp)} respondents, {len(seg)} excerpts ({(seg['text'] == WITHHELD).sum()} withheld, {len(EDITS)} edited)")
