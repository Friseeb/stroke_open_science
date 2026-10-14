"""Generate the talk's slides (talk/deck/project/slides/*.html and deck.json) from one place.

Version 5 (2026-10-14), the speaker's brief: white background, black text, less text and clutter, one idea per
slide, stories told from the benchmark data with a pointer to where each one lives on the dashboard, numbered
references with a QR code to the full list. Details live in the speaker notes (<aside>).

Each slide follows the Slides artifact format (one <section>, inline styles, px units, no font under 24 px). The
congress .pptx is converted from these files by talk/deck/congress/extract_slides.js + build_wsc_pptx.py.

    python talk/deck/make_slides.py            # writes slides + deck.json (+ talk/references.md when refs exist)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import qrcode
import qrcode.image.svg

ROOT = Path(__file__).resolve().parent
SLIDES = ROOT / "project" / "slides"
REFS_JSON = ROOT / "references.json"          # resolved references (key -> vancouver, doi, url, short)
REFS_MD = ROOT.parent / "references.md"

DASHBOARD = "https://friseeb.github.io/stroke_open_science_outputs/"
CODE = "https://github.com/Friseeb/stroke_open_science"
REFS_URL = "https://github.com/Friseeb/stroke_open_science/blob/talk/wsc2026/talk/references.md"

# ---- design tokens ------------------------------------------------------------------------------
BG, INK, MID, GREY, HAIR, RED = "#ffffff", "#000000", "#333333", "#555555", "#d0d0d0", "#d7263d"
PAID, FREE, BRONZE, TRACK = "#eda100", "#1baf7a", "#9a5a1f", "#d6d6d2"
FIELD_COLORS = {"stroke": RED, "cardiology": "#eda100", "neurology": "#2a78d6", "neuroscience": "#1baf7a"}
SANS = "'Instrument Sans', Helvetica, Arial, sans-serif"
EYEBROW = "World Stroke Congress 2026 · Seoul"
DASH_SHORT = "friseeb.github.io/stroke_open_science_outputs"
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


def line_chart_svg(series, years, width=1664, height=600, y0=40, y1=85, ticks=(40, 50, 60, 70, 80), focus="stroke"):
    """Open access by year, drawn natively: one line per field, direct end labels, no legend."""
    L, R, T, B = 110, 370, 20, 70
    pw, ph = width - L - R, height - T - B
    X = lambda i: L + pw * i / (len(years) - 1)
    Y = lambda v: T + ph * (1 - (v - y0) / (y1 - y0))
    out = [f'<svg aria-label="Open access by year, 2015 to 2024, stroke against cardiology, neurology and neuroscience" '
           f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    for t in ticks:
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="#e4e4e1" stroke-width="2"/>')
        out.append(f'<text x="{L - 18}" y="{Y(t) + 11:.1f}" font-size="32" fill="{GREY}" text-anchor="end">{t}%</text>')
    for i, y in enumerate(years):
        if i % 1 == 0:
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

    S.append(("cover", slide("cover", [
        p("World Stroke Congress 2026 · Seoul · The latest in stroke implementation science", 26, 400, GREY, 32,
          "letter-spacing:2px;text-transform:uppercase;"),
        '<div style="flex:1"></div>',
        f'<div style="width:120px;height:8px;background:{RED}"></div>',
        f'<h1 style="font-size:132px;font-weight:600;line-height:0.98;letter-spacing:-5px;color:{INK}">Open science<br>in stroke research</h1>',
        p("Measuring reproducibility and transparency, and what to do with the numbers", 44, 400, MID, 56,
          "width:1640px;"),
        '<div style="flex:1"></div>',
        '<div style="display:flex;flex-direction:column;gap:8px">'
        + p("Sebastian Fridman, MD", 38, 600) + p("Western University · London Health Sciences Centre · Canada", 30, 400, MID)
        + "</div>",
    ], "Ten seconds. One sentence, no agenda: how this project started, what it found, and what I think we should "
       "do with it.", gap=36)))

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

    stages = [("Segment", ["ITK-SNAP", "DeepISLES"]), ("Normalise", ["SPM Clinical Toolbox", "ANTs"]),
              ("Map symptoms", ["VLSM", "LESYMAP"]), ("Map networks", ["BCBtoolkit", "Lesion network mapping"]),
              ("Share", ["BIDS", "OpenNeuro"])]
    cols = "".join(
        f'<div style="flex:1;display:flex;flex-direction:column;gap:10px;padding:20px 28px 0 0;border-top:2px solid {INK}">'
        + p(f"{i + 1}&nbsp;&nbsp;{lab}", 32, 600, RED, 40) + "".join(p(t, 36, 400, INK, 46) for t in tools) + "</div>"
        for i, (lab, tools) in enumerate(stages))
    refs = cite("yushkevich2006", "delarosa2025", "rorden2012", "avants2008", "bates2003", "pustina2018",
                "foulon2018", "boes2015", "gorgolewski2016", "markiewicz2021", "liew2022", "hernandez2022", "gibson2024")
    S.append(("spark", slide("spark", [
        title("In lesion neuroscience, the whole pipeline is open"),
        f'<div style="display:flex">{cols}</div>',
        tiles([("955", "public stroke MRIs with traced lesions (ATLAS)", INK),
               ("250", "public acute stroke MRIs (ISLES 2022)", INK),
               ("230", "people with aphasia: MRI and language scores", INK)], num_size=88, cap_size=32),
        p("Yet 12 of 17 methods built on ATLAS reported no public code.", 44, 600, RED),
    ], "Fifty seconds, first person. I came to stroke from imaging and neuroscience. There, a lesion study is built "
       "from open parts at every step: segmentation (ITK-SNAP; DeepISLES, from the ISLES 2022 winners), normalisation "
       "that respects the lesion (SPM Clinical Toolbox, ANTs), lesion-symptom mapping (VLSM since 2003, LESYMAP), "
       "network and disconnection mapping (BCBtoolkit, lesion network mapping) and sharing (BIDS, OpenNeuro). The data "
       "are real: ATLAS v2.0 has 1,271 traced MRIs, 955 public; ISLES 2022 released 250 of 400 cases; the Aphasia "
       "Recovery Cohort is CC0 on OpenNeuro. The red line is the bridge: open data alone did not bring open code (Liew "
       "2022). Then the turn: when I moved to clinical stroke, the trial data and code were not there.",
       page=3, footer=refs, gap=40)))

    refs = cite("osc2015", "button2013", "begley2012", "baker2016", "simmons2011", "john2012")
    S.append(("crisis", slide("crisis", [
        title("The fields next door had their crisis first"),
        tiles([("36%", "of psychology findings replicated", RED),
               ("21%", "median statistical power in neuroscience", INK),
               ("6 of 53", "landmark cancer studies reproduced", INK),
               ("70%", "of 1,576 scientists had failed to reproduce another lab's experiment", INK)], num_size=100, cap_size=34),
        p("Why: small samples, flexible analyses, selective reporting.", 44, 600),
    ], "Forty-five seconds. These are my former fields; say so. Psychology: 35 of 97 replications significant (36%), "
       "effects half the size (Open Science Collaboration 2015). Neuroscience: median power 21% (Button 2013). "
       "Preclinical cancer: Amgen reproduced 6 of 53 landmark findings (Begley 2012). More than 70% of 1,576 researchers "
       "had failed to reproduce another scientist's experiment (Baker 2016). Why: four routine analysis choices raise "
       "a 5% false-positive rate to 61% (Simmons 2011); 63% of 2,155 psychologists admitted not reporting all their "
       "measures (John 2012).", page=4, footer=refs, gap=56)))

    agreed = [("2013", "Registered Reports: peer review before results, now in 300+ journals"),
              ("2015", "Transparency and Openness Promotion (TOP) guidelines for journals"),
              ("2025", "PECANS: a consensus checklist for neuropsychology studies")]
    rows = "".join(f'<div style="display:flex;gap:32px;align-items:baseline;padding:20px 0;border-top:1px solid {HAIR}">'
                   f'{p(y, 44, 600, INK, 52, "width:130px;")}{p(t, 36, 400, INK, 46, "flex:1;")}</div>' for y, t in agreed)
    now = [("55%", "of 274 published claims replicated (2026)", RED),
           ("14%", "of psychology papers share raw data (2022)", INK),
           ("1 of 62", "Cortex Registered Reports studied patients", INK)]
    stats = "".join(f'<div style="display:flex;flex-direction:column;gap:6px;padding:18px 0;border-top:1px solid {HAIR}">'
                    f'{p(n, 88, 600, c, 88, "letter-spacing:-2px;")}{p(t, 32, 400, MID)}</div>' for n, t, c in now)
    refs = cite("chambers2013", "nosek2015", "grant2026", "costa2025", "tyner2026", "miske2026",
                "hardwicke2024", "binney2025", "scheel2021", "protzko2023")
    S.append(("crisis-now", slide("crisis-now", [
        title("Ten years on, the rules exist. Practice lags."),
        f'<div style="display:flex;gap:80px;align-items:start">'
        f'<div style="flex:1;display:flex;flex-direction:column">{p("What they agreed on", 30, 600, GREY, 40, "padding:0 0 8px 0;")}{rows}</div>'
        f'<div style="width:600px;display:flex;flex-direction:column">{p("Where they are now", 30, 600, GREY, 40, "padding:0 0 8px 0;")}{stats}</div></div>',
    ], "Sixty seconds. Psychology did not fix itself: it measured itself, agreed on rules, and is still short of them. "
       "Agreed: Registered Reports (launched at Cortex in 2013, now more than 300 journals); the TOP guidelines (2015, "
       "5,000+ signatories, revised as TOP 2025, which adds independent verification to disclosing and sharing); PECANS "
       "(2025), a Delphi consensus checklist for cognitive and neuropsychological studies, 206 experts. Now: the SCORE "
       "project (Nature, April 2026) replicated 151 of 274 claims from social and behavioural science papers published "
       "2009-2018 (55%), effects fell from r = 0.25 to 0.10, and authors made data available for only 24% of 600 papers "
       "(Miske 2026). In 2022, 7% of psychology papers were preregistered and 14% shared raw data (Hardwicke 2024). Only "
       "1 of 62 Registered Reports in Cortex studied patients; the most common barrier neuropsychologists name is "
       "sharing sensitive clinical data (12 of 23; Binney 2025). Registered Reports report 44% positive results against "
       "96% (Scheel 2021). The best-known claim that rigour alone restores replication (Protzko 2023) was retracted in "
       "2024. Closest to this room: lesion network mapping, used in 200+ studies, was challenged in Nature Neuroscience "
       "in January 2026 using only public data; that debate exists because the data were open.",
       page=5, footer=refs)))

    stroke_rows = [("Neuroprotection", "1,026 candidates tested in animals; none helped patients"),
                   ("Tirofiban", "RESCUE BT (with thrombectomy): no benefit.<br>RESCUE BT2 (no large-vessel occlusion): benefit."),
                   ("MMA embolisation", "Subdural haematoma: three NEJM trials in one week, two positive, one neutral")]
    rows = "".join(f'<div style="display:flex;gap:40px;align-items:baseline;padding:32px 0;border-top:1px solid {HAIR}">'
                   f'{p(a, 40, 600, INK, 50, "width:420px;")}{p(b, 40, 400, INK, 50, "flex:1;")}</div>' for a, b in stroke_rows)
    refs = cite("ocollins2006", "sena2010", "lees2006", "shuaib2007", "qiu2022", "zi2023", "davies2024", "fiorella2024", "liu2024")
    S.append(("stroke-crisis", slide("stroke-crisis", [
        title("Stroke has the same problem"),
        f'<div style="display:flex;flex-direction:column;border-bottom:1px solid {HAIR}">{rows}</div>',
        p("Without protocols, data and code, we cannot tell why results differ.", 44, 600),
    ], "Fifty seconds, three examples the room knows; do not editorialise on any trial. O'Collins catalogued 1,026 "
       "experimental treatments in animal stroke, 114 taken to patients; no neuroprotectant translated (thrombolysis is "
       "the exception), and publication bias overstated animal efficacy by about a third (Sena 2010); NXY-059: SAINT I "
       "positive, SAINT II negative. Tirofiban: no benefit before thrombectomy in RESCUE BT (JAMA 2022), benefit over "
       "aspirin without large or medium vessel occlusion in RESCUE BT2 (NEJM 2023): a different question or a different "
       "answer? Middle meningeal artery embolisation for subdural haematoma: EMBOLISE positive (repeat surgery 4.1% vs "
       "11.3%), STEM positive (16% vs 36%), MAGIC-MT neutral (6.7% vs 9.9%, P = 0.10), all in the NEJM in the week of "
       "20 November 2024 (STEM online, print 2025).", page=6, footer=refs, gap=48)))

    four = [("Read it", "Open access?"), ("Check it", "Data or code linked?"),
            ("Reuse it", "Data deposited, not &ldquo;on request&rdquo;?"), ("Plan it", "Registered?")]
    cols = "".join(f'<div style="flex:1;display:flex;flex-direction:column;gap:10px;padding:20px 32px 0 0;border-top:2px solid {INK}">'
                   f'{p(a, 32, 600, RED, 40)}{p(b, 44, 600, INK, 52)}</div>' for a, b in four)
    refs = cite("rauh2020", "heckerman2025", "scutt2020", "priem2022", "europepmc", "benchmark2026")
    stats = tiles([("140,281", "stroke articles, 2015–2025 (OpenAlex)", INK),
                   ("16,362", "open-access full texts read (Europe PMC)", INK),
                   ("6", "months between open re-runs", INK)], num_size=96, cap_size=32)
    S.append(("method", slide("method", [
        title("Four measures, every stroke paper since 2015"),
        f'<div style="display:flex">{cols}</div>',
        '<div style="flex:1"></div>',
        f'<div style="display:flex;gap:56px;align-items:end"><div style="flex:1">{stats}</div>'
        f'<div style="display:flex;flex-direction:column;gap:10px;align-items:start">{qr_svg(DASHBOARD, 230, "QR code: benchmark dashboard")}'
        f'{p("Every number, live", 28, 600, INK, 34)}</div></div>',
    ], "Forty-five seconds. Audits like this exist for neurology (Rauh 2020) and cardiology (Heckerman 2025), and data "
       "requests have been tested in vascular and cognitive trials (Scutt 2020); we found none of stroke publications. "
       "The benchmark reads OpenAlex for every stroke journal article and review with a DOI since 2015 (140,281 for "
       "2015-2025, title search), then reads up to 1,500 open-access full texts a year through Europe PMC (16,362 for "
       "stroke), with neurology, neuroscience and cardiology measured the same way. It re-runs every six months; code "
       "and data are open, and every number on the next slides is on the public dashboard: the QR code. Open-access full "
       "text only, so full-text rates run high.", page=7, footer=refs)))

    years = list(range(2015, 2025))
    series = {"stroke": [52.8, 53.9, 53.8, 58.2, 57.3, 64.9, 69.9, 73.8, 76.9, 75.2],
              "cardiology": [59.6, 60.9, 60.7, 61.0, 60.4, 68.6, 72.7, 75.4, 79.9, 77.5],
              "neurology": [50.8, 49.6, 48.3, 54.3, 54.5, 62.1, 64.9, 68.8, 72.0, 71.9],
              "neuroscience": [55.9, 56.2, 57.0, 58.9, 60.6, 63.9, 66.4, 68.9, 72.3, 70.1]}
    bench = cite("benchmark2026")
    S.append(("oa-trend", slide("oa-trend", [
        title("Stroke went open access: 53% in 2015, 75% in 2024"),
        line_chart_svg(series, years),
    ], "Thirty-five seconds. The good-news slide. Open access = any OpenAlex status other than closed. Stroke sits "
       "between cardiology and neurology in every complete year (2015-2024); in the incomplete 2025 it edges past "
       "cardiology. Do not rank neuroscience: about 45% of it comes from the title term 'neural', much of it machine "
       "learning.", page=8, footer=f"{bench} · Open access: any status except closed · Dashboard: 02 Trends", gap=32)))

    yrs = [(2015, 18.6, 18.9, 15.3), (2016, 20.2, 21.0, 12.7), (2017, 20.7, 21.7, 11.4), (2018, 23.5, 21.6, 13.1),
           (2019, 24.9, 22.1, 10.4), (2020, 30.8, 24.5, 9.7), (2021, 37.2, 23.7, 9.0), (2022, 43.6, 22.1, 8.0),
           (2023, 42.5, 23.5, 10.9), (2024, 44.1, 23.9, 7.2)]
    H = 5.0   # px per percentage point: 100% = 500 px
    def column(y_, a_, b_, c_):
        lab = f'{p(f"{a_:.0f}%", 30, 600, INK, 34)}' if y_ in (2015, 2024) else p("&nbsp;", 30, 400, INK, 34)
        return (f'<div style="display:flex;flex-direction:column;align-items:center;gap:8px">{lab}'
                f'<div style="width:72px;height:{round((100 - a_ - b_ - c_) * H)}px;background:{TRACK}"></div>'
                f'<div style="display:flex;flex-direction:column;gap:0">{bar(72, BRONZE, round(c_ * H))}{bar(72, FREE, round(b_ * H))}{bar(72, PAID, round(a_ * H))}</div>'
                f'{p(str(y_), 28, 400, GREY, 34)}</div>')
    colsv = "".join(column(*r_) for r_ in yrs)
    S.append(("oa-type", slide("oa-type", [
        title("The growth was paid for"),
        legend([("Paid fee", PAID), ("Free to author", FREE), ("Bronze", BRONZE), ("Closed", TRACK)], 30),
        '<div style="display:flex;gap:72px;align-items:end">'
        f'<div style="display:flex;gap:14px;align-items:end">{colsv}</div>'
        '<div style="flex:1;display:flex;flex-direction:column;gap:44px">'
        + '<div style="display:flex;flex-direction:column;gap:10px">' + p("44%", 128, 600, RED, 128, "letter-spacing:-3px;")
        + p("of stroke articles paid a fee in 2024 (19% in 2015)", 36, 400, MID) + "</div>"
        + '<div style="display:flex;flex-direction:column;gap:10px">' + p("24%", 128, 600, INK, 128, "letter-spacing:-3px;")
        + p("were free to authors in 2024 (19% in 2015)", 36, 400, MID) + "</div></div></div>",
    ], "Forty seconds. Open access grew because someone paid. Paid routes (gold and hybrid) went from 19% of all stroke "
       "articles in 2015 to 44% in 2024; free routes (diamond and green) from 19% to 24%; bronze, free to read without a "
       "licence, fell from 15% to 7%. Of the open articles, 59% paid a fee in 2024 (35% in 2015). Next: who pays.",
       page=9, footer=f"{bench} · Share of all stroke articles by route, 2015–2024 · Dashboard: 02 Trends", gap=32)))

    groups = [("High income", 83, 56, 67), ("Upper-middle income", 72, 68, 70), ("Lower-middle income", 74, 75, 75)]
    scale = 9.0
    def grow(g, a, b, overall):
        lowest = g == "High income"
        return (f'<div style="display:flex;gap:32px;align-items:center;padding:18px 0;border-top:1px solid {HAIR}">'
                f'<div style="width:380px;display:flex;flex-direction:column;gap:4px">{p(g, 36, 600, INK, 44)}{p(f"{overall}% open overall", 28, 400, GREY, 34)}</div>'
                f'<div style="flex:1;display:flex;flex-direction:column;gap:10px">'
                f'<div style="display:flex;gap:16px;align-items:center">{bar(a * scale, INK, 44)}{p(f"{a}%", 36, 600)}</div>'
                f'<div style="display:flex;gap:16px;align-items:center">{bar(b * scale, RED if lowest else "#9a9a95", 44)}'
                f'{p(f"{b}%" + (" &nbsp;least open" if lowest else ""), 36, 600 if lowest else 400, RED if lowest else MID)}</div>'
                f'</div></div>')
    rows = "".join(grow(*g_) for g_ in groups)
    S.append(("who-pays", slide("who-pays", [
        title("In rich countries, open access depends on a funder"),
        legend([("A funder is listed", INK), ("No funder listed", "#9a9a95")], 30),
        f'<div style="display:flex;flex-direction:column;border-bottom:1px solid {HAIR}">{rows}</div>',
    ], "Forty-five seconds. This is the story behind 'paid for'. Funded papers are 79% open against 60% without a "
       "funder, and 54% of funded papers paid an article fee against 25%. In high-income countries the funder is the "
       "switch: 83% open with a funder, 56% without, the least open group of all (29,055 and 44,147 articles); overall, "
       "high-income first authors are the least open (67%). In lower-middle-income countries open access does not depend "
       "on a funder (74% vs 75%): it comes through free routes. Low-income countries: 400 articles, too few to show. "
       "Caveat: 'funder' means a funder listed in OpenAlex, which misses some acknowledgements.",
       page=10, footer=f"{bench} · Open access 2015–2025 by first author's World Bank income group · Dashboard: 04 Income groups")))

    countries = [("Indonesia", "upper-middle", 26.2, 63.8, 5.4), ("Netherlands", "high", 61.0, 17.9, 11.5),
                 ("United Kingdom", "high", 47.6, 19.5, 10.7), ("Korea", "high", 36.9, 31.1, 7.2),
                 ("India", "lower-middle", 21.0, 40.9, 8.3), ("Germany", "high", 51.5, 8.2, 9.2),
                 ("Japan", "high", 28.0, 28.9, 11.2), ("Australia", "high", 37.0, 15.7, 13.4),
                 ("China", "upper-middle", 51.3, 8.2, 4.8), ("Canada", "high", 31.4, 11.8, 15.5),
                 ("United States", "high", 23.5, 19.9, 14.4)]
    sc = 9.0
    rows = "".join(
        f'<div style="display:flex;gap:24px;align-items:center">'
        f'<div style="width:470px;display:flex;gap:14px;align-items:baseline">{p(c, 32, 600 if c in ("United States", "Indonesia") else 400, INK, 38)}{p(inc_, 24, 400, GREY, 30)}</div>'
        f'<div style="display:flex;gap:0;align-items:center">{bar(a * sc, PAID, 32)}{bar(b * sc, FREE, 32)}{bar(z * sc, BRONZE, 32)}</div>'
        f'{p(f"{a + b + z:.0f}%", 32, 600, INK, 38)}</div>' for c, inc_, a, b, z in countries)
    S.append(("countries", slide("countries", [
        title("Open access follows policy, not wealth"),
        legend([("Paid fee", PAID), ("Free to author", FREE), ("Bronze", BRONZE)], 30),
        f'<div style="display:flex;flex-direction:column;gap:8px">{rows}</div>',
    ], "Forty seconds. The ten largest producers plus the Netherlands, first-author country, 2015-2025. The United "
       "States, the largest high-income producer, is the least open (58%; 42% closed). The United Kingdom (78%) and the "
       "Netherlands (90%) are open mostly by paying: national funders there require and fund open access. Indonesia "
       "(95%, upper-middle income) and India (70%, lower-middle) are open mostly through free routes, national free "
       "journals. The Netherlands (61%), Germany and China (about half) pay most often. Wealth does not predict it; "
       "policy and the journals a community publishes in do.", page=11,
       footer=f"{bench} · Ten largest producers plus the Netherlands, 2015–2025 · Dashboard: 05 Rankings", gap=32)))

    S.append(("flat", slide("flat", [
        title("Data and code did not move in ten years"),
        p("Stroke articles, abstracts and metadata, 2024", 34, 400, GREY),
        tiles([("0.2%", "link data in a repository (0.2% in 2015)", RED),
               ("&lt;0.1%", "link code (below 0.1% every year since 2015)", INK)], num_size=144, cap_size=36),
        '<div style="flex:1"></div>',
        p("So we read the full text.", 44, 600),
    ], "Thirty-five seconds. Lower bounds from abstracts and metadata, 2024: data in a repository 0.2% (0.2% in 2015, "
       "never above 0.6%); code links below 0.1% in every complete year. What did move: registration IDs, 2.8% to 5.3% "
       "of articles with an abstract, and preprints, 2.7% in 2024, partly publisher-driven (Research Square, SSRN). "
       "Pooled over 2015-2025, high-impact articles are barely better at sharing (data 0.45% vs 0.34%). Then the pivot: "
       "so we read the full text.", page=12, footer=f"{bench} · Dashboard: 01 Indicators")))

    refs = cite("benchmark2026", "gabelica2022", "scutt2020")
    S.append(("das", slide("das", [
        title("Full texts promise data. Few deposit it."),
        p("Open-access stroke full texts published in 2025 (1,500 read)", 34, 400, GREY),
        tiles([("74%", "write a data statement<br>(14% in 2015)", INK), ("29%", "say &ldquo;available on request&rdquo;<br>(0.6% in 2015)", RED),
               ("9.8%", "deposit or cite public data<br>(0.7% in 2015)", INK)], num_size=144, cap_size=36),
        '<div style="flex:1"></div>',
        p("The statements arrived with journal mandates. The data did not.", 44, 600),
    ], "Sixty seconds; the slide people photograph. Open-access stroke full texts published in 2025 (the audit reads "
       "1,500 a year, so the year is complete for the audit): 74% write a data statement (14% in 2015), 29% say "
       "'available on request', now the most common answer, and 9.8% deposit data or name a public source (own "
       "repository deposit 5.9%). In 2024: 69%, 30% and 7.3%. 'On request' delivers little: 6.8% of authors shared when "
       "asked (Gabelica 2022); 20% of 391 vascular and cognitive trials, median 241 days (Scutt 2020). Against the other "
       "fields, 2022-2025, stroke says 'on request' most often (30%; neurology 27%, neuroscience 26%, cardiology 24%). "
       "Open-access full texts only, so these rates are optimistic for stroke overall.",
       page=13, footer=f"{refs} · Dashboard: 03 Data statements")))

    inc = [("High income", 43, 4.0), ("Upper-middle income", 57, 5.2), ("Lower-middle income", 23, 1.8)]
    u = 16.0   # one scale for both panels: px per percentage point
    def panel(head, idx, fmt):
        rows_ = "".join(
            f'<div style="display:flex;gap:24px;align-items:center">{p(g, 32, 400, INK, 40, "width:380px;")}'
            f'{bar(row[idx] * u, RED if g.startswith("Lower") else INK, 40)}{p(fmt(row[idx]), 32, 600, RED if g.startswith("Lower") else INK)}</div>'
            for row in inc for g in [row[0]])
        return f'<div style="display:flex;flex-direction:column;gap:14px">{p(head, 34, 600)}{rows_}</div>'
    S.append(("equity", slide("equity", [
        title("Free to read is not free to reuse"),
        p("Lower-middle-income authors: most open to read (75%), least likely to share data", 36, 400, MID),
        f'<div style="display:flex;flex-direction:column;gap:36px;padding:28px 0 0 0;border-top:2px solid {INK}">'
        f'{panel("Write a data statement", 1, lambda v: f"{v:.0f}%")}{panel("Deposit or cite public data", 2, lambda v: f"{v:.1f}%")}</div>',
    ], "Forty seconds. Among the three larger income groups, lower-middle-income first authors are the most open to "
       "read (75%, 42% through diamond or green), yet in open-access full texts, 2015-2025, they write a data statement "
       "in 23% (high 43%, upper-middle 57%) and deposit or name a public source in 1.8% (4.0%, 5.2%), from 609 audited "
       "articles; the gap holds in 2022-2025. Both panels use the same scale, which is the point: deposit is tiny "
       "everywhere. Low-income countries (400 articles, 77 audited) are too few to show. Korea: 5,490 first-author "
       "articles, 75% open.", page=14,
       footer=f"{bench} · Open-access full texts, 2015–2025; lower-middle n = 609 · Dashboard: 04 Income groups")))

    inst = [("Center for Stroke Research Berlin (Charité)", 5.2), ("Charité, Berlin", 4.4), ("University of Oxford", 2.9),
            ("UKE Hamburg-Eppendorf", 2.6), ("University of Edinburgh", 2.5), ("Stanford University", 2.3)]
    unit = 150
    rows = "".join(f'<div style="display:flex;gap:28px;align-items:center">{p(n, 34, 400, INK, 42, "width:680px;")}'
                   f'<div style="display:flex;gap:0">{bar(unit, "#c8c8c4", 40)}{bar((v - 1) * unit, RED, 40)}</div>'
                   f'{p(f"{v:.1f}&times;", 34, 600)}</div>' for n, v in inst)
    S.append(("commitment", slide("commitment", [
        title("Some teams already share, and we can measure them"),
        legend([("Stroke average (1&times;)", "#c8c8c4"), ("Above the average", RED)], 30),
        f'<div style="display:flex;flex-direction:column;gap:18px">{rows}</div>',
        p("Commitment index: data deposit, GitHub and trial registration in the full text, against the stroke average.", 30, 400, MID),
    ], "Forty-five seconds. The index is the mean, over three full-text signals (data deposited or public source, GitHub, "
       "trial registration), of an institution's rate divided by the stroke rate; 1 = stroke average. Shown: the top of "
       "the 60 institutions with the most audited articles (82 or more each), as on the dashboard. Small counts are a "
       "hint, not a ranking. Journals: among the 40 largest on the dashboard, the Journal of Cerebral Blood Flow and "
       "Metabolism leads (2.7x) and Stroke is fourth (1.5x); among smaller journals with at least 30 audited articles, "
       "Nature Communications, Brain Communications and PeerJ lead. The point: the measurement exists, is cheap, and is "
       "what a prize would recognise.", page=15,
       footer=f"{bench} · 60 institutions with 82+ audited full texts, 2015–2025 · Dashboard: 05 Rankings", gap=32)))

    rows_m = [("3.1% → 3.1%", "Data obtainable from surgical trials, before and after the ICMJE rule", RED),
              ("No effect", "Open-data badges in a medical-journal randomised trial (OR 0.9)", INK),
              ("1 of 92", "Promotion guidelines that mention data sharing", INK),
              ("44% vs 96%", "Positive results: Registered Reports vs standard papers", INK)]
    rows = "".join(f'<div style="display:flex;gap:40px;align-items:center;padding:20px 0;border-top:1px solid {HAIR}">'
                   f'{p(a, 56, 600, c, 60, "width:440px;letter-spacing:-1.5px;")}{p(b, 36, 400, INK, 46, "flex:1;")}</div>'
                   for a, b, c in rows_m)
    refs = cite("bergeat2022", "rowhanifarid2020", "kidwell2016", "rice2020", "scheel2021", "cobey2024")
    S.append(("mandates", slide("mandates", [
        title("Rules produced statements, not data"),
        f'<div style="display:flex;flex-direction:column;border-bottom:1px solid {HAIR}">{rows}</div>',
        '<div style="flex:1"></div>',
        p("We respond to incentives, and ours point the other way.", 44, 600),
    ], "Fifty seconds, the pivot. The ICMJE data-statement rule left obtainable data at 3.1% in surgical trials (Bergeat "
       "2022). Open-data badges: OR 0.9 in the first randomised trial in medicine, at BMJ Open (Rowhani-Farid 2020), "
       "though they took Psychological Science from under 3% to 23% open data, 39% by early 2015 (Kidwell 2016). In 2020, "
       "1 of 92 biomedical promotion guidelines mentioned data sharing, and none open access or registration (Rice 2020). "
       "Registered Reports: 44% positive results against 96% (Scheel 2021): changing when review happens changes what is "
       "published. Cardiology researchers name funding as the most essential incentive; 'policy alone will not lead to "
       "the effective implementation of open science' (Cobey 2024). Stroke researchers are not less honest than "
       "psychologists; they respond to the same incentives.", page=16, footer=refs)))

    asks = [("1", "A WSO task force", ["Open-science position statement", "Retire &ldquo;on request&rdquo; in stroke journals"]),
            ("2", "A prize", ["For the teams that share", "Scored by the commitment index"]),
            ("3", "Awareness", ["Benchmark every six months", "Open science in promotion criteria"])]
    cols = "".join(f'<div style="flex:1;display:flex;flex-direction:column;gap:16px;padding:24px 40px 0 0;border-top:2px solid {INK}">'
                   f'{p(n, 104, 600, RED if n == "1" else INK, 104)}{p(h, 44, 600, INK, 52)}'
                   + "".join(p(b, 36, 400, MID, 46) for b in bs) + "</div>" for n, h, bs in asks)
    S.append(("future", slide("future", [
        title("What to do next"),
        f'<div style="display:flex">{cols}</div>',
        '<div style="flex:1"></div>',
        p("A target to discuss: data deposited for 25% of stroke articles by 2030 (about 6% today).", 40, 600),
    ], "One minute forty-five. Task force: a WSO position statement (neither WSO nor ESO has one); retire 'available on "
       "request' in Stroke, IJS, ESJ and JSCVD in favour of a repository, VISTA or Vivli, or a stated reason; Registered "
       "Reports for stroke trials with in-principle acceptance tied to WSO and ESO grants; embargoed sharing as the trial "
       "default, twelve months after publication. Prize: the commitment index, verified in full text and recomputed every "
       "six months, for institutions, journals, funders and countries. Awareness: the public benchmark; open-science items "
       "in promotion criteria (in 2020, 1 of 92 guidelines mentioned data sharing, and none open access or registration). "
       "Targets to discuss: data in a repository or controlled-access platform for 25% of stroke articles by 2030 (own "
       "repository deposit was 5.9% of 2025 open-access full texts); 'on request' under 10%; one Registered Report track "
       "in a stroke journal by 2028. The statement, retiring 'on request' and promotion criteria cost nothing; Registered "
       "Reports, the prize and the infrastructure need money, and the infrastructure mostly exists: VISTA and Vivli for "
       "trial data, ATLAS and OpenNeuro for imaging, ENIGMA for pooled analysis. Invite the WSO leadership in the room "
       "to take the task force home.", page=17)))

    qr = lambda url, head, sub, short: (
        f'<div style="flex:1;display:flex;flex-direction:column;gap:12px;align-items:start">{qr_svg(url, 300, head)}'
        f'{p(head, 38, 600, INK, 46)}{p(sub, 30, 400, MID, 38)}{p(short, 24, 400, GREY, 30)}</div>')
    S.append(("close", slide("close", [
        p("The numbers are not flattering, but they are measurable, which means they are improvable.", 50, 600, INK, 60,
          "width:1640px;letter-spacing:-1px;"),
        '<div style="display:flex;gap:48px">'
        + qr(DASHBOARD, "Benchmark", "Explore every number; next update January 2027", DASH_SHORT)
        + qr(CODE, "Code and data", "Open source: run it on your field", CODE_SHORT)
        + qr(REFS_URL, "References", "Full list with DOIs", CODE_SHORT + " › talk/references.md")
        + "</div>",
        p("Sebastian Fridman · sfridma@uwo.ca · Join the task force, or audit your own field", 34, 600, INK),
    ], "Thirty seconds. One line, then stop. Leave the QR codes up during questions: the benchmark dashboard, the code "
       "and data, and the references. Thank the session chairs.", page=18, gap=48)))

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

Version 5 (2026-10-14). The speaker's brief: white background and black text; less clutter and less text, one idea
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
        "story": {"description": "Where I come from, the crisis next door and where it stands, the same problem in stroke", "start": "cover"},
        "measure": {"description": "What we measured and how", "start": "method"},
        "findings": {"description": "Open access grew and was paid for; who pays; data and code did not move; who shares", "start": "oa-trend"},
        "next": {"description": "Why mandates alone failed; what to do next; collaborate; references", "start": "mandates"},
    }
    deck["faces"] = {k: v for k, v in deck.get("faces", {}).items() if k == "instrument-sans"}
    deck_path.write_text(json.dumps(deck, indent=2, ensure_ascii=False) + "\n")
    stale = sorted(f.stem for f in SLIDES.glob("*.html") if f.stem not in keep)
    write_outline(slides)
    print("slides:", len(slides), "| references:", len(REF_ORDER), "| stale slide files:", stale,
          "| references.md:", write_references_md(), "| outline: written")


if __name__ == "__main__":
    main()
