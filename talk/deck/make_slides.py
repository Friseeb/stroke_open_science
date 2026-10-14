"""Generate the talk's slides (talk/deck/project/slides/*.html and deck.json) from one place.

Version 6 (2026-10-14), the speaker's brief: white background, black text, less text and clutter, one idea per
slide, stories told from the benchmark data with a pointer to where each one lives on the dashboard, numbered
references with a QR code to the full list. Details live in the speaker notes (<aside>).

Each slide follows the Slides artifact format (one <section>, inline styles, px units, no font under 24 px). The
congress .pptx is converted from these files by talk/deck/congress/extract_slides.js + build_wsc_pptx.py.

    python talk/deck/make_slides.py            # writes slides + deck.json (+ talk/references.md when refs exist)
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import qrcode
import qrcode.image.svg

ROOT = Path(__file__).resolve().parent
SLIDES = ROOT / "project" / "slides"
REFS_JSON = ROOT / "references.json"          # resolved references (key -> vancouver, doi, url, short)
REFS_MD = ROOT.parent / "references.md"

DASHBOARD = "https://friseeb.github.io/stroke-open-science/"
CODE = "https://github.com/Friseeb/stroke_open_science"
REFS_URL = "https://github.com/Friseeb/stroke_open_science/blob/talk/wsc2026/talk/references.md"

# ---- design tokens ------------------------------------------------------------------------------
BG, INK, MID, GREY, HAIR, RED = "#ffffff", "#000000", "#333333", "#555555", "#d0d0d0", "#d7263d"
PAID, FREE, BRONZE, TRACK = "#eda100", "#1baf7a", "#9a5a1f", "#d6d6d2"
FIELD_COLORS = {"stroke": RED, "cardiology": "#eda100", "neurology": "#2a78d6", "neuroscience": "#1baf7a"}
SANS = "'Instrument Sans', Helvetica, Arial, sans-serif"
EYEBROW = "World Stroke Congress 2026 · Seoul"
DASH_SHORT = "friseeb.github.io/stroke-open-science"
CODE_SHORT = "github.com/Friseeb/stroke_open_science"

# ---- references, numbered by first appearance ---------------------------------------------------
REF_ORDER: list[str] = []


def cite(*keys: str, prefix=True) -> str:
    nums = []
    for k in keys:
        if k not in REF_ORDER:
            REF_ORDER.append(k)
        nums.append(REF_ORDER.index(k) + 1)
    nums = sorted(set(nums))
    groups, run = [], [nums[0]]
    for n in nums[1:]:
        if n == run[-1] + 1:
            run.append(n)
        else:
            groups.append(run)
            run = [n]
    groups.append(run)
    parts = [f"{g[0]}" if len(g) == 1 else f"{g[0]}, {g[1]}" if len(g) == 2 else f"{g[0]}–{g[-1]}" for g in groups]
    if not prefix:
        return ", ".join(parts)
    return ("Reference " if len(nums) == 1 else "References ") + ", ".join(parts)


# ---- building blocks ----------------------------------------------------------------------------
def p(text, size=32, weight=400, color=INK, lh=None, extra=""):
    lh = lh or round(size * 1.3)
    w = f"font-weight:{weight};" if weight != 400 else ""
    return f'<p style="font-size:{size}px;line-height:{lh}px;{w}color:{color};{extra}">{text}</p>'


def title(text, size=68):
    return (f'<h2 style="font-size:{size}px;font-weight:600;line-height:1.08;letter-spacing:-1.5px;'
            f'color:{INK}">{text}</h2>')


def illustration(name, alt, width=1640, height=540):
    return (f'<img src="../../assets/{name}" alt="{alt}" '
            f'style="width:{width}px;height:{height}px;object-fit:contain;align-self:center">')


def evidence_rows(items, maximum=100, width=1100, height=70, gap=28, label_width=380):
    """One comparison, directly labelled; denominator and provenance stay in the notes/footer."""
    rows = []
    for label, value, shown, color in items:
        rows.append(f'<div style="display:flex;gap:28px;align-items:center">'
                    f'{p(label, 40, 600, INK, 50, f"width:{label_width}px;")}'
                    f'<div style="width:{width}px">{bar(width * value / maximum, color, height)}</div>'
                    f'{p(shown, 46, 600, color, 56, "width:150px;")}</div>')
    return f'<div style="display:flex;flex-direction:column;gap:{gap}px">{"".join(rows)}</div>'


def slide(sid, body, notes, page=None, gap=40, footer=""):
    head = (f'<section id="{sid}" data-transition="fade" style="background:{BG};color:{INK};font-family:{SANS};'
            f'padding:128px 128px 160px;display:flex;flex-direction:column;gap:{gap}px">\n')
    pins = ""
    if footer:
        pins += (f'<p style="position:absolute;left:128px;bottom:64px;width:1480px;font-size:26px;line-height:32px;'
                 f'color:{GREY}">{footer}</p>\n')
    if page:
        pins += (f'<p style="position:absolute;left:1672px;bottom:64px;width:120px;font-size:26px;line-height:32px;'
                 f'text-align:right;color:{GREY}">{page}</p>\n')
    notes = notes.strip()
    assert len(notes) <= 4000, (sid, len(notes))
    return head + pins + "\n".join(body) + f"\n<aside>{notes}</aside>\n</section>\n"


def tiles(items, num_size=112, cap_size=34, border=True):
    """Row of big numbers: (number, caption, colour)."""
    cells = []
    for num, cap, col in items:
        b = f"border-top:2px solid {INK};" if border else ""
        cells.append(f'<div style="flex:1;display:flex;flex-direction:column;gap:14px;padding:24px 36px 0 0;{b}">'
                     f'{p(num, num_size, 600, col, round(num_size * 1.0), "letter-spacing:-3px;")}'
                     f'{p(cap, cap_size, 400, MID)}</div>')
    return f'<div style="display:flex;gap:0">{"".join(cells)}</div>'


def bar(width_px, color, height=40):
    return f'<div style="width:{max(2, round(width_px))}px;height:{height}px;background:{color}"></div>'


def legend(items, size=30):
    cells = "".join(f'<div style="display:flex;gap:12px;align-items:center"><div style="width:30px;height:30px;'
                    f'background:{c}"></div>{p(t, size, 400, MID)}</div>' for t, c in items)
    return f'<div style="display:flex;gap:44px;align-items:center">{cells}</div>'


def qr_svg(url, size=220, label=""):
    """QR code with its own 4-module quiet zone, so it scans on any background."""
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=4)
    svg = img.to_string(encoding="unicode")
    m = re.search(r'viewBox="([^"]+)"', svg)
    view = m.group(1) if m else "0 0 100 100"
    d = re.search(r' d="([^"]+)"', svg).group(1)
    vb = [float(v) for v in view.split()]
    return (f'<svg aria-label="{label or "QR code: " + url}" viewBox="{view}" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg"><rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="#ffffff"/>'
            f'<path d="{d}" fill="{INK}"/></svg>')


def line_chart_svg(series, years, width=1664, height=600, y0=40, y1=85, ticks=(40, 60, 80), focus="stroke"):
    """Open access by year, drawn natively: one line per field, direct end labels, no legend."""
    L, R, T, B = 110, 370, 20, 70
    pw, ph = width - L - R, height - T - B
    X = lambda i: L + pw * i / (len(years) - 1)
    Y = lambda v: T + ph * (1 - (v - y0) / (y1 - y0))
    out = [f'<svg aria-label="Open access in stroke articles, 2015 to 2024" '
           f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    for t in ticks:
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="#e4e4e1" stroke-width="2"/>')
        out.append(f'<text x="{L - 18}" y="{Y(t) + 11:.1f}" font-size="32" fill="{GREY}" text-anchor="end">{t}%</text>')
    for i, y in enumerate(years):
        if i in (0, len(years) - 1):
            out.append(f'<text x="{X(i):.1f}" y="{height - 16}" font-size="30" fill="{GREY}" text-anchor="middle">{y}</text>')
    order = sorted(series, key=lambda k: k == focus)            # draw the focus line last
    for k in order:
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(series[k]))
        w = 8 if k == focus else 5
        out.append(f'<polyline points="{pts}" fill="none" stroke="{FIELD_COLORS[k]}" stroke-width="{w}" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
    # end labels, dodged so they never overlap
    ends = sorted(((series[k][-1], k) for k in series), reverse=True)
    pos, last = {}, None
    for v, k in ends:
        y = Y(v)
        if last is not None and y - last < 40:
            y = last + 40
        pos[k], last = y, y
    for v, k in ends:
        name = k.capitalize()
        wgt = "700" if k == focus else "400"
        out.append(f'<line x1="{L + pw + 16}" x2="{L + pw + 50}" y1="{pos[k]:.1f}" y2="{pos[k]:.1f}" '
                   f'stroke="{FIELD_COLORS[k]}" stroke-width="{8 if k == focus else 6}"/>')
        out.append(f'<text x="{L + pw + 62}" y="{pos[k] + 11:.1f}" font-size="34" font-weight="{wgt}" '
                   f'fill="{RED if k == focus else INK}">{v:.0f}% {name}</text>')
    out.append("</svg>")
    return "".join(out)


# ---- the deck -----------------------------------------------------------------------------------
def build():
    S = []
    NOTES = json.loads((ROOT / "speaker_notes.json").read_text())

    S.append(("cover", slide("cover", [
        '<img src="../../assets/wsc2026-banner.jpg" alt="Official WSC 2026 Seoul congress banner" '
        'style="position:absolute;left:0;top:0;width:1920px;height:192px;object-fit:contain">',
        '<div style="height:96px"></div>',
        f'<h1 style="font-size:132px;font-weight:600;line-height:0.98;letter-spacing:-5px;color:{INK}">Open science<br>in stroke research</h1>',
        p("What stroke research makes available", 48, 400, MID, 60),
        '<div style="flex:1"></div>',
        p("Sebastian Fridman, MD", 40, 600),
        p("Western University · London Health Sciences Centre", 30, 400, MID),
    ], "Ten seconds. This benchmark measures transparency and the availability of research materials; it does not "
       "test whether reported findings reproduce or replicate. Official WSC banner, used at the speaker's request: "
       "https://worldstrokecongress.org/promotional-toolkit/ ; asset: "
       "https://wsc2026.kenes.com/wp-content/uploads/sites/32/2025/11/WSC-2026-banner-900x90px_v3.jpg", gap=28)))

    box = lambda mark: (f'<div style="width:52px;height:52px;border:3px solid {INK};display:flex;align-items:center;'
                        f'justify-content:center">' + (p("×", 38, 600, INK, 38) if mark else "") + "</div>")
    heads = ["Company", "Honoraria / expenses", "Consulting / advisory", "Funded research", "Royalties / patent",
             "Stock options", "Ownership / equity", "Employee", "Other"]
    th = "".join(f'<th style="width:184px;text-align:left;vertical-align:bottom;padding:0 16px 12px 0;font-size:26px;'
                 f'line-height:32px;font-weight:400;color:{GREY};border-bottom:2px solid {INK}">{h}</th>' for h in heads)
    td = (f'<td style="text-align:left;padding:16px 16px 16px 0;font-size:30px;line-height:36px;color:{INK};'
          f'border-bottom:1px solid {HAIR}">None</td>'
          + "".join(f'<td style="padding:16px 16px 16px 0;border-bottom:1px solid {HAIR}"></td>' for _ in heads[1:]))
    S.append(("disclosure", slide("disclosure", [
        title("Disclosure"),
        f'<div style="display:flex;flex-direction:column;gap:22px">'
        f'<div style="display:flex;gap:28px;align-items:center">{box(True)}{p("No, nothing to disclose", 44, 600)}</div>'
        f'<div style="display:flex;gap:28px;align-items:center">{box(False)}{p("Yes, please specify", 44, 400, GREY)}</div></div>',
        f'<table style="width:1664px;table-layout:fixed"><tr>{th}</tr><tr>{td}</tr></table>',
    ], "Required by the congress as the second slide: nothing to disclose. Two seconds, then move on.", page=2)))

    refs = cite("yushkevich2006", "delarosa2025", "rorden2012", "avants2008", "bates2003", "pustina2018", "boes2015", "foulon2018", "gorgolewski2016", "markiewicz2021", "liew2022", "hernandez2022", "gibson2024")
    S.append(("spark", slide("spark", [title("Open tools shaped my stroke research"),
        illustration("open-lesion-science.png", "Conceptual stroke imaging, lesion analysis, network mapping and shared materials", height=570),
        p("Open imaging tools. Reusable lesion datasets.", 44, 600), p("Sharing enables independent checks.", 40, 400, MID),
    ], NOTES["spark"], page=3, footer=refs, gap=22)))

    refs = cite("nas2019")
    S.append(("crisis", slide("crisis", [title("Reproducibility and replication"),
        illustration("reproducibility-replication.png", "Same data and code reanalysed; independent participants assessed for the same question", height=540),
        '<div style="display:flex;gap:100px"><div style="flex:1;text-align:center">' + p("Reproducibility",46,600) + p("Same data, same analysis.",40,400,MID)
        + '</div><div style="flex:1;text-align:center">' + p("Replication",46,600) + p("New data, same question.",40,400,MID) + '</div></div>',
    ], NOTES["crisis"], page=4, footer=refs, gap=20)))

    refs = cite("osc2015", "tyner2026")
    dots = ''.join(f'<div style="width:24px;height:24px;border-radius:50%;background:{RED if i<151 else TRACK}"></div>' for i in range(274))
    S.append(("crisis-now", slide("crisis-now", [title("SCORE: 55% of claims replicated"),
        p("Social and behavioural science",40,400,MID),
        f'<div style="display:grid;grid-template-columns:repeat(22,24px);gap:12px;align-self:center;margin-top:24px">{dots}</div>',
        legend([("Replicated",RED),("Not replicated",TRACK)],36),
    ], NOTES["crisis-now"], page=5, footer=refs + " · One mark per tested claim", gap=24)))

    refs = cite("nas2019", "rauh2020")
    S.append(("stroke-crisis", slide("stroke-crisis", [title("Stroke research needs inspectable evidence"),
        illustration("stroke-transparency.png", "Stroke protocol, data and code available for independent inspection", height=530),
        p("Protocols explain what was planned.",40,600), p("Data and code enable independent checks.",40),
        p("Different patients can produce different results.",40,400,MID),
    ], NOTES["stroke-crisis"], page=6, footer=refs, gap=16)))

    refs = cite("rauh2020", "heckerman2025", "scutt2020", "priem2022", "europepmc", "benchmark2026")
    S.append(("method", slide("method", [title("Four transparency checks"),
        p("Can we read the paper?",58,600), p("Can we inspect and reuse materials?",58,600), p("Was the study registered?",58,600),
        '<div style="flex:1"></div>', f'<div style="display:flex;gap:48px;align-items:center">{qr_svg(DASHBOARD,220,"Live stroke benchmark")}'
        + p("Stroke publications since 2015",38,400,MID) + '</div>',
    ], NOTES["method"] + " The four indicators are access, data, code and registration. Data and code are grouped in one spoken question. These measure transparency, not successful reproducibility.", page=7, footer=refs, gap=34)))

    bench = cite("benchmark2026")
    years = list(range(2015,2025))
    series = {"stroke":[52.8,53.9,53.8,58.2,57.3,64.9,69.9,73.8,76.9,75.2]}
    S.append(("oa-trend",slide("oa-trend",[title("Stroke papers became easier to read"),line_chart_svg(series,years)],
        NOTES["oa-trend"] + " Figure shows stroke only; comparators remain on the live dashboard.",page=8,footer=f"{bench} · Stroke articles · 2015–2024",gap=32)))

    strips = []
    for year,gold,free,bronze in [("2015",18.6,18.9,15.3),("2024",44.1,23.9,7.2)]:
        segments = ''.join(bar(v*11.8,c,120) for v,c in [(gold,PAID),(free,FREE),(bronze,BRONZE),(100-gold-free-bronze,TRACK)])
        strips.append(f'<div style="display:flex;gap:32px;align-items:center">{p(year,44,600,INK,54,"width:130px;")}<div style="display:flex">{segments}</div>{p(f"{gold:.0f}%",48,600,PAID)}</div>')
    S.append(("oa-type",slide("oa-type",[title("Gold and hybrid drove access growth"),
        legend([("Gold / hybrid",PAID),("Diamond / green",FREE),("Bronze",BRONZE),("Closed",TRACK)],34),
        '<div style="height:50px"></div>','<div style="display:flex;flex-direction:column;gap:80px">'+''.join(strips)+'</div>',
    ],NOTES["oa-type"],page=9,footer=f"{bench} · All stroke articles · Publication routes",gap=36)))

    S.append(("who-pays",slide("who-pays",[title("Funding is associated with open access"),p("Stroke · High-income first authors",40,400,MID),
        '<div style="height:55px"></div>',evidence_rows([("Funder listed",83,"83%",RED),("No funder listed",56,"56%",INK)],width=1000,height=120,gap=90),
    ],NOTES["who-pays"],page=10,footer=f"{bench} · OpenAlex funding metadata · 2015–2025",gap=30)))

    rows = []
    for country,gold,free,bronze in [("Indonesia",26.2,63.8,5.4),("Netherlands",61.0,17.9,11.5),("Korea",36.9,31.1,7.2),("United States",23.5,19.9,14.4)]:
        segments = ''.join(bar(v*9.5,c,85) for v,c in [(gold,PAID),(free,FREE),(bronze,BRONZE),(100-gold-free-bronze,TRACK)])
        rows.append(f'<div style="display:flex;gap:30px;align-items:center">{p(country,42,600,INK,54,"width:370px;")}<div style="display:flex">{segments}</div>{p(f"{gold+free+bronze:.0f}%",42,600)}</div>')
    S.append(("countries",slide("countries",[title("Access differs across stroke research communities"),
        legend([("Gold / hybrid",PAID),("Diamond / green",FREE),("Bronze",BRONZE),("Closed",TRACK)],30),
        '<div style="display:flex;flex-direction:column;gap:38px">'+''.join(rows)+'</div>',
    ],NOTES["countries"],page=11,footer=f"{bench} · Selected first-author countries · 2015–2025",gap=32)))

    # Reuse the pipeline's exact metadata rates, rather than inventing tiny bar lengths.
    import csv
    with (ROOT.parent / "outputs/tables/rates_by_discipline_year.csv").open() as fh:
        rates = next(r for r in csv.DictReader(fh) if r["discipline"]=="stroke" and r["year"]=="2024")
    metadata = [("Open access",float(rates["oa_rate"])*100,"75%",INK),("Data links",float(rates["data_rate"])*100,"0.2%",RED),("Code links",float(rates["code_rate"])*100,"&lt;0.1%",RED)]
    S.append(("flat",slide("flat",[title("Access grew; sharing links remained scarce"),p("From abstracts and metadata",40,400,MID),
        '<div style="height:24px"></div>',evidence_rows(metadata,width=970,height=75,gap=62),
    ],NOTES["flat"],page=12,footer=f"{bench} · Stroke articles · 2024",gap=30)))

    refs = cite("benchmark2026","gabelica2022","scutt2020")
    S.append(("das",slide("das",[title("Statements outnumber deposits and public sources"),
        evidence_rows([("Statement",74,"74%",INK),("On request",29,"29%",MID),("Deposit / public source",9.8,"9.8%",RED)],width=940,height=85,gap=75,label_width=450),
    ],NOTES["das"] + " Statement presence overlaps the other indicators; these rows do not partition all statements.",page=13,footer=f"{refs} · OA stroke full texts · 2025",gap=65)))

    S.append(("equity",slide("equity",[title("Stroke data access differs by income"),p("Deposited or public source",40,400,MID),
        evidence_rows([("High income",4.0,"4.0%",INK),("Upper-middle",5.2,"5.2%",INK),("Lower-middle",1.8,"1.8%",RED)],maximum=6,width=960,height=80,gap=60),
    ],NOTES["equity"] + " This figure shows only deposit/public-source rates, with a 0-6% scale.",page=14,footer=f"{bench} · OA stroke audit · 2015–2025",gap=45)))

    S.append(("commitment",slide("commitment",[title("Sharing practices can be measured"),p("Deposit · Code · Registration",38,400,MID),
        evidence_rows([("Charité",4.4,"4.4×",RED),("Oxford",2.9,"2.9×",INK),("UKE Hamburg",2.6,"2.6×",INK),("Edinburgh",2.5,"2.5×",INK)],maximum=5,width=960,height=64,gap=35),
        p("Relative to the stroke average",36,400,MID),
    ],NOTES["commitment"] + " Four descriptive examples; sample sizes and full comparison remain on the dashboard.",page=15,footer=f"{bench} · Descriptive index · Sample sizes differ",gap=28)))

    refs = cite("bergeat2022")
    S.append(("mandates",slide("mandates",[title("A rule does not ensure access"),p("Obtainable data from surgical trials",40,400,MID),
        evidence_rows([("Before ICMJE rule",3.1,"3.1%",INK),("After ICMJE rule",3.1,"3.1%",RED)],maximum=5,width=900,height=120,gap=100,label_width=480),
    ],NOTES["mandates"],page=16,footer=refs + " · Bergeat et al. · JAMA Network Open",gap=48)))

    S.append(("future",slide("future",[title("A proposal for the WSO"),p("Create a WSO task force.",62,600),p("Reward verified sharing.",62,600),p("Track progress through this benchmark.",62,600)],NOTES["future"],page=17,gap=90)))

    qr = lambda url,label: (f'<div style="flex:1;display:flex;flex-direction:column;gap:24px;align-items:start">{qr_svg(url,320,label)}{p(label,40,600)}</div>')
    S.append(("close",slide("close",[title("Measure, share, and improve stroke research"),'<div style="height:35px"></div>',
        '<div style="display:flex;gap:70px">'+qr(DASHBOARD,"Benchmark")+qr(CODE,"Code and data")+qr(REFS_URL,"References")+'</div>',
        '<div style="flex:1"></div>',p("Sebastian Fridman · sfridma@uwo.ca",38,600),
    ],NOTES["close"],page=18,gap=35)))
    return S


# ---- references slides and page -----------------------------------------------------------------
def load_refs():
    if REFS_JSON.exists():
        return json.loads(REFS_JSON.read_text())
    return {}


SHORT_OVERRIDE = {"benchmark2026": "Fridman S. Stroke Open-Science Benchmark, run of 2026-10-13", "priem2022": "Priem J et al. arXiv. 2022"}


def short_ref(key, vancouver):
    """'Authors. Title. Journal. Year;...' -> 'First author et al. Journal. Year'."""
    if key in SHORT_OVERRIDE:
        return SHORT_OVERRIDE[key]
    authors = vancouver.split(". ")[0]
    first = re.split(r"[,;]", authors)[0].strip()
    etal = " et al." if ("," in authors or "et al" in authors) else ""
    m = re.search(r"\.\s(\d{4})\s*[;(]", vancouver)
    name = first + (etal or ".")
    if not m:
        return name
    journal = vancouver[:m.start()].rsplit(". ", 1)[-1].strip()
    return f"{name} {journal}. {m.group(1)}"


def ref_slides(start_page):
    refs = load_refs()
    items = []
    for i, k in enumerate(REF_ORDER, 1):
        r = refs.get(k, {})
        items.append((i, short_ref(k, r["vancouver"]) if r.get("vancouver") else k))
    per = (len(items) + 1) // 2
    out = []
    for part, chunk in enumerate([items[:per], items[per:]]):
        if not chunk:
            continue
        half = (len(chunk) + 1) // 2
        col = lambda xs: (f'<div style="flex:1;display:flex;flex-direction:column;gap:6px">'
                          + "".join(f'<div style="display:flex;gap:14px">{p(str(n), 24, 400, GREY, 30, "width:40px;text-align:right;")}'
                                    f'{p(t, 24, 400, INK, 30, "flex:1;")}</div>' for n, t in xs)
                          + "</div>")
        body = [title("References" if part == 0 else "References, continued", 56)]
        if part == 0:
            body.append(f'<div style="display:flex;gap:56px;align-items:start">{col(chunk[:half])}{col(chunk[half:])}'
                        f'<div style="width:240px;display:flex;flex-direction:column;gap:12px">{qr_svg(REFS_URL, 240, "References")}'
                        f'{p("Full list with DOIs", 24, 400, MID, 30)}</div></div>')
        else:
            body.append(f'<div style="display:flex;gap:56px;align-items:start">{col(chunk[:half])}{col(chunk[half:])}'
                        f'<div style="width:240px"></div></div>')
        sid = f"refs-{part + 1}"
        out.append((sid, slide(sid, body, "Appendix: not presented. Full references with DOIs at the QR code link.",
                               page=start_page + part, gap=32)))
    return out


def write_references_md():
    refs = load_refs()
    if not refs:
        return False
    lines = ["# References: Open science in stroke research (World Stroke Congress 2026)", "",
             "Sebastian Fridman. World Stroke Congress 2026, Seoul, 22 October 2026. Numbered as cited on the slides.",
             f"Benchmark dashboard: {DASHBOARD} · Code and data: {CODE}", ""]
    for i, k in enumerate(REF_ORDER, 1):
        r = refs.get(k, {})
        text = (r.get("vancouver") or k).strip()
        # turn "doi:10.x/y" into a link; add a link only when the text carries none
        text, n = re.subn(r"doi:\s*(10\.\S+?)(?=[\s]|$)", lambda m: f"[doi:{m.group(1).rstrip('.')}](https://doi.org/{m.group(1).rstrip('.')})", text)
        if not n and "http" not in text and r.get("url"):
            text += f" {r['url']}"
        lines.append(f"{i}. {text}")
    REFS_MD.write_text("\n".join(lines) + "\n")
    return True


OUTLINE = ROOT.parent / "talk_outline.md"
SECONDS = {"cover": 10, "disclosure": 5, "spark": 50, "crisis": 45, "crisis-now": 60, "stroke-crisis": 50, "method": 45,
           "oa-trend": 35, "oa-type": 40, "who-pays": 45, "countries": 40, "flat": 35, "das": 60, "equity": 40,
           "commitment": 45, "mandates": 50, "future": 105, "close": 30}
OUTLINE_HEAD = """# Open science in stroke research: measuring reproducibility and transparency

World Stroke Congress 2026, Seoul. Thu 22 Oct 2026, 15:45-16:00 (15 min), session
"The latest in stroke implementation science" (ID 340), Conference Room 202-203.
Speaker: Sebastian Fridman (Western University, London, Canada).

Version 6 (2026-10-14). The speaker's brief: white background and black text; less clutter and less text, one idea
per slide with the details in the speaker notes; stories told from the benchmark data, each pointing to the dashboard
section where it can be seen (e.g. who pays for open access, and which countries are open); numbered references with a
QR code to the full list (talk/references.md). Slides and this outline are generated by talk/deck/make_slides.py; edit
there, not in the slide files. The congress .pptx is the same deck converted to editable PowerPoint
(talk/deck/congress/).

Numbers come from the published run of 2026-10-13 (`data/runs/2026-10-13T111229Z`): `talk/outputs/numbers.json`,
`talk/outputs/tables/` and the run frames. Stroke corpus: OpenAlex journal articles and reviews with a DOI from the six
title terms, 2015-2025, n = 140,281; open access = any OpenAlex status other than closed; full-text audit = up to 1,500
open-access articles per year with full text in Europe PMC, 16,362 for stroke. Literature numbers come from
`talk/evidence_brief.md` and `talk/evidence_intro.md`; references were resolved and re-checked against Crossref and
PubMed (`talk/deck/references.json`).

"""


def write_outline(slides):
    import html as _html
    tail = ""
    if OUTLINE.exists():
        old = OUTLINE.read_text()
        i = old.find("## Sources added in version 3")
        tail = old[i:] if i >= 0 else ""
    total = sum(SECONDS.get(sid, 0) for sid, _ in slides)
    out = [OUTLINE_HEAD, f"Timing: {len([1 for sid, _ in slides if sid in SECONDS])} presented slides in "
           f"{total // 60}:{total % 60:02d} (the two reference slides are an appendix). Minutes in brackets are cumulative "
           f"at the start of the slide.", "", "---", ""]
    t = 0
    for n, (sid, h) in enumerate(slides, 1):
        notes = re.search(r"<aside>(.*?)</aside>", h, re.S)
        notes = _html.unescape(re.sub(r"<[^>]+>", "", notes.group(1))).strip() if notes else ""
        body = re.sub(r"<aside>.*?</aside>", "", h, flags=re.S)
        foot = re.search(r'<p style="position:absolute;left:128px;bottom:64px;[^"]*">(.*?)</p>', body)
        foot = _html.unescape(re.sub(r"<[^>]+>", "", foot.group(1))) if foot else ""
        body = re.sub(r'<p style="position:absolute;[^"]*">.*?</p>', "", body)        # eyebrow, footer, page number
        ttl = re.search(r"<h[12][^>]*>(.*?)</h[12]>", body, re.S)
        ttl = _html.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", ttl.group(1)))) if ttl else ""
        body = re.sub(r"<h[12][^>]*>.*?</h[12]>", "", body, flags=re.S)
        body = re.sub(r"<svg.*?</svg>", "[QR code]", body, flags=re.S)
        body = re.sub(r"<img [^>]*alt=\"([^\"]*)\"[^>]*>", r"\n[Figure: \1]\n", body)
        body = re.sub(r"<br\s*/?>", " ", body)
        body = re.sub(r"</(p|h1|h2|div|td|th|tr)>", "\n", body)
        lines = [l.strip() for l in _html.unescape(re.sub(r"<[^>]+>", " ", body)).splitlines()]
        lines = [re.sub(r"\s+", " ", l) for l in lines if l.strip() and l.strip() != EYEBROW.upper() and l.strip() != EYEBROW]
        head_ = re.sub(r"\s+", " ", ttl).strip() or (lines.pop(0) if lines else sid)
        d = SECONDS.get(sid)
        when = f" ({t // 60}:{t % 60:02d}, {d} s)" if d else " (appendix)"
        out.append(f"## {n}. {head_}{when}")
        out.append("")
        out += [f"- {l}" for l in lines]
        if foot:
            out.append(f"- Footer: {foot}")
        out += ["", f"Notes: {notes}", ""]
        t += d or 0
    OUTLINE.write_text("\n".join(out) + ("\n---\n\n" + tail if tail else ""))


def write_preview(slides):
    """Portable browser preview: generated from the same slide sources, with assets embedded."""
    def embed(match):
        path = ROOT / "assets" / match.group(1)
        mime = "image/jpeg" if path.suffix == ".jpg" else "image/png"
        return 'src="data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode() + '"'
    frames = []
    for sid, html in slides:
        html = re.sub(r'src="\.\./\.\./assets/([^\"]+)"', embed, html)
        frames.append('<div class="frame">' + html + '</div>')
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WSC 2026 · Open science in stroke research</title><style>'
    css = '*{box-sizing:border-box;margin:0}body{background:#dedede;font-family:Arial,sans-serif}.frame{width:min(100vw,1920px);aspect-ratio:16/9;margin:24px auto;overflow:hidden;box-shadow:0 2px 10px #aaa}section{position:relative;width:1920px;height:1080px;overflow:hidden;transform:scale(var(--scale));transform-origin:top left;font-family:Arial,sans-serif!important}section *{font-family:Arial,sans-serif!important}aside{display:none}table{border-collapse:collapse}'
    script = '<script>function scale(){document.documentElement.style.setProperty("--scale",Math.min(innerWidth/1920,1))}scale();addEventListener("resize",scale)</script>'
    (ROOT / "preview.html").write_text(head + css + '</style></head><body>' + ''.join(frames) + script + '</body></html>')


def main():
    slides = build()
    slides += ref_slides(len(slides) + 1)
    SLIDES.mkdir(parents=True, exist_ok=True)
    keep = {sid for sid, _ in slides}
    for sid, html in slides:
        (SLIDES / f"{sid}.html").write_text(html, encoding="utf-8")
    deck_path = ROOT / "project" / "deck.json"
    deck = json.loads(deck_path.read_text())
    deck["order"] = [sid for sid, _ in slides]
    deck["sections"] = {
        "story": {"description": "Open imaging, definitions, replication evidence and transparency in stroke", "start": "cover"},
        "measure": {"description": "What we measured and how", "start": "method"},
        "findings": {"description": "Stroke access routes, funding associations, detected sharing and inspectable data", "start": "oa-trend"},
        "next": {"description": "Access after a journal rule; proposed WSO action; collaborate; references", "start": "mandates"},
    }
    deck["faces"] = {k: v for k, v in deck.get("faces", {}).items() if k == "instrument-sans"}
    deck_path.write_text(json.dumps(deck, indent=2, ensure_ascii=False) + "\n")
    stale = sorted(f.stem for f in SLIDES.glob("*.html") if f.stem not in keep)
    write_outline(slides)
    write_preview(slides)
    print("slides:", len(slides), "| references:", len(REF_ORDER), "| stale slide files:", stale,
          "| references.md:", write_references_md(), "| outline: written")


if __name__ == "__main__":
    main()
