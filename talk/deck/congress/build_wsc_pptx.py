"""Build the World Stroke Congress 2026 talk as a .pptx on the official speaker template.

One spec drives two outputs:
  * the .pptx, built on WSC-2026-PPT_w_disclosure_16_9.pptx (title slide, editable disclosure slide,
    content slides that copy the template's own white background with the congress lockup), and
  * PNG previews drawn with Arial metrics, used to check that every text box fits without opening
    PowerPoint.

Congress rules followed: 16:9, Arial, slide 1 = name and title, slide 2 = conflict-of-interest
disclosure from the template, JPG figures, content kept clear of the lockup (x > 8.3 in) and the
"one voice" mark (bottom right).

Usage:
  python talk/deck/congress/build_wsc_pptx.py --template WSC-2026-PPT_w_disclosure_16_9.pptx \
      --figures talk/outputs/figures/dashboard_white --slides talk/deck/project/slides \
      --out talk/deck/congress/Fridman_WSC2026_open_science.pptx --preview-dir /tmp/wsc_preview
"""
from __future__ import annotations

import argparse
import copy
import html
import io
import re
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt
from lxml import etree

# --- palette (congress blue for titles; the dashboard's stroke red for headline numbers) ---------
BLUE = "1D429C"
INK = "1F1F1F"
GREY = "5F5F5F"
HAIR = "C8C8C8"
RED = "D7263D"
WHITE = "FFFFFF"
PALE = "DCE6F5"
INDIGO = "2E247A"   # disclosure header, sampled from the template image
GREEN = "52AE32"    # disclosure rows, sampled from the template image

FONT = "Arial"
FONT_FILES = {
    (False, False): "/System/Library/Fonts/Supplemental/Arial.ttf",
    (True, False): "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    (False, True): "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    (True, True): "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
}
LINE = 1.2          # line height as a multiple of the font size (PowerPoint single spacing for Arial is ~1.17)
PX_IN = 192         # preview resolution: 1920 x 1080

# content frame on the white layout (inches): keep clear of the lockup at x > 8.3 and "one voice"
LX, RX = 0.34, 8.24
CW = RX - LX
CWF = 7.7           # footers stop short of the "one voice" mark
FOOT_BOTTOM = 5.42


# =============================================================================================
# spec helpers
# =============================================================================================
def R(text, size=12, bold=False, italic=False, color=INK):
    return {"text": text, "size": size, "bold": bold, "italic": italic, "color": color}


def P(*runs, align="l", after=0.0, bullet=False):
    return {"runs": list(runs), "align": align, "after": after, "bullet": bullet}


def T(x, y, w, h, paras, anchor="t", name=None):
    if isinstance(paras, dict):
        paras = [paras]
    return {"kind": "text", "x": x, "y": y, "w": w, "h": h, "paras": paras, "anchor": anchor, "name": name}


def IMG(path, x, y, w, h, align="l"):
    return {"kind": "img", "path": path, "x": x, "y": y, "w": w, "h": h, "align": align}


def RECT(x, y, w, h, fill=None, line=None, lw=0.75):
    return {"kind": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "line": line, "lw": lw}


def HLINE(x, y, w, color=HAIR, lw=0.75):
    return {"kind": "line", "x": x, "y": y, "w": w, "color": color, "lw": lw}


def TABLE(x, y, col_w, row_h, rows, header_fill, body_fill, header_style, body_style, grid="808080"):
    return {"kind": "table", "x": x, "y": y, "col_w": col_w, "row_h": row_h, "rows": rows,
            "header_fill": header_fill, "body_fill": body_fill, "header_style": header_style,
            "body_style": body_style, "grid": grid}


def kicker(num, label):
    return T(LX, 0.17, CW, 0.22, P(R(f"{num}  ", 11, True, color=RED), R(label, 11, color=GREY)))


def title(text, h=0.82):
    return T(LX, 0.38, CW, h, P(R(text, 21, True, color=BLUE)), anchor="t", name="title")


def footer(text, h=0.36, size=10):
    return T(LX, FOOT_BOTTOM - h, CWF, h, P(R(text, size, color=GREY)), anchor="b")


def tile(x, y, w, h, label, number, caption, cite=None, num_color=RED, num_size=30, first=True):
    """A bordered stat tile: label, headline number, caption (and an optional grey citation)."""
    els = [RECT(x, y, w, h, fill=None, line=HAIR)]
    pad = 0.12
    paras = [P(R(label, 11.5, True), after=4), P(R(number, num_size, True, color=num_color), after=4),
             P(R(caption, 11, color="3A3A3A"), after=3 if cite else 0)]
    if cite:
        paras.append(P(R(cite, 10, color=GREY)))
    els.append(T(x + pad, y + pad, w - 2 * pad, h - 2 * pad, paras))
    return els


# =============================================================================================
# the deck
# =============================================================================================
def deck_spec(fig: Path, qr: dict[str, Path]):
    f = lambda name: fig / f"{name}.jpg"
    S = []

    # 3 · the moment this started --------------------------------------------------------------
    S.append({"id": "spark", "els": [
        kicker("01", "Where I come from"),
        title("The moment this started", h=0.45),
        T(LX, 1.25, 7.6, 2.4, P(R("I came to stroke from imaging and neuroscience. [In 20__ I tried to build on a "
                                    "published result: the data were “available on request”, the code was not there, "
                                    "and the request went unanswered. I could not tell whether the finding was wrong "
                                    "or I was.]", 20, italic=True, color=INK))),
        T(LX, 4.35, CW, 0.35, P(R("imaging   ·   neuroscience   ·   neurology   ·   ", 14, color=GREY),
                                R("stroke", 14, True, color=RED))),
    ]})

    # 4 · the fields next door ------------------------------------------------------------------
    tw = CW / 4
    tiles = [
        ("Psychology", "36%", "of 100 published findings replicated with a significant result; effect sizes about "
         "half the originals", "Open Science Collaboration, Science 2015"),
        ("Neuroscience", "21%", "median statistical power of neuroscience studies",
         "Button et al., Nat Rev Neurosci 2013"),
        ("Preclinical cancer", "6 of 53", "landmark findings that Amgen could reproduce", "Begley and Ellis, Nature 2012"),
        ("Across science", "70%", "of 1,576 researchers had failed to reproduce another group’s experiment; 52% called "
         "it a significant crisis", "Baker, Nature 2016"),
    ]
    els = [kicker("02", "Why open science"), title("The fields next door had their crisis first")]
    for i, (lab, num, cap, cite) in enumerate(tiles):
        els += tile(LX + i * tw, 1.2, tw, 2.5, lab, num, cap, cite)
    els += [
        HLINE(LX, 3.88, CW, color=INK, lw=1),
        T(LX, 4.0, 1.75, 0.8, P(R("What those fields did about it", 12, True))),
        T(LX + 1.95, 4.0, CW - 1.95, 0.85, P(R("Preregistration and Registered Reports in more than 300 journals, "
                                               "open-data badges, the Open Science Framework, data and code as a "
                                               "condition of publication. In Registered Reports, 44% of results are "
                                               "positive, against 96% in the standard literature (Scheel 2021).", 12,
                                               color="3A3A3A"))),
        footer("Psychology and neuroscience measured themselves, it hurt, and they changed how they publish.", h=0.2),
    ]
    S.append({"id": "crisis", "els": els})

    # 5 · stroke is not immune -----------------------------------------------------------------
    rows = [
        ("Preclinical", "1,026 neuroprotectants tested in animal stroke; none translated. Publication bias "
         "overstated efficacy by about a third. NXY-059: SAINT I positive, SAINT II negative.",
         "O’Collins 2006; Sena 2010; Lees 2006; Shuaib 2007"),
        ("Tirofiban", "No benefit before thrombectomy in RESCUE BT (2022). Benefit without a large-vessel occlusion "
         "in RESCUE BT2 (2023). A different question, or a different answer?", "Qiu 2022, JAMA; Zi 2023, NEJM"),
        ("Middle meningeal artery embolisation", "Three trials in one NEJM issue: EMBOLISE positive (recurrence 4% "
         "vs 11%), STEM positive, MAGIC-MT neutral (6.7% vs 9.9%).", "Davies, Fiorella, Liu 2024, NEJM"),
    ]
    els = [kicker("03", "Stroke is not immune"),
           title("Same question, different answers, and no way to tell why from the papers alone")]
    y = 1.38
    rh = [0.86, 0.86, 0.8]
    for (lab, txt, cite), h in zip(rows, rh):
        els += [HLINE(LX, y, CW),
                T(LX, y + 0.1, 1.75, h - 0.15, P(R(lab, 12.5, True))),
                T(LX + 1.9, y + 0.1, 4.55, h - 0.15, P(R(txt, 12.5))),
                T(LX + 6.6, y + 0.1, CW - 6.6, h - 0.15, P(R(cite, 10, color=GREY)))]
        y += h
    els += [HLINE(LX, y, CW),
            T(LX, 4.3, CW, 0.7, P(R("Replication is how a field finds out which result to trust. Without the "
                                    "protocols, the data and the code, we are left arguing about it.", 15,
                                    italic=True)))]
    S.append({"id": "stroke-crisis", "els": els})

    # 6 · what open science is made of ---------------------------------------------------------
    cols = [
        ("Read it", "Can people read it?", "Open access, and by which route",
         "Diamond, gold, hybrid, green, bronze or closed"),
        ("Check it", "Can they check it?", "Data and code that someone else can run",
         "Repository links, GitHub, data-availability statements"),
        ("Reuse it", "Can they reuse it?", "Deposited, not promised on request",
         "A repository or a controlled-access platform"),
        ("Plan it", "Was it planned in advance?", "Registration and preregistration",
         "Trial registries, PROSPERO, Registered Reports"),
    ]
    els = [kicker("04", "What open science is made of"),
           title("Four questions a field should be able to answer about its own literature")]
    for i, (k, q, a, b) in enumerate(cols):
        x = LX + i * tw
        els += [RECT(x, 1.38, tw, 2.25, line=HAIR),
                T(x + 0.13, 1.5, tw - 0.26, 2.05, [P(R(k, 11, True, color=RED), after=4),
                                                    P(R(q, 15, True), after=6),
                                                    P(R(a, 12), after=6),
                                                    P(R(b, 11, color=GREY))])]
    els += [RECT(LX, 3.95, 0.05, 0.62, fill=RED),
            T(LX + 0.2, 3.95, CW - 0.2, 0.62, P(R("Reproducibility audits exist for neurology, cardiology and general "
                                                  "medicine. ", 13.5), R("None existed for stroke.", 13.5, True),
                                                R("  Rauh 2020; Heckerman 2025; Scutt 2020", 10.5, color=GREY)),
              anchor="m")]
    S.append({"id": "why", "els": els})

    # 7 · how we measured ----------------------------------------------------------------------
    steps = [("Retrieve", "OpenAlex, 2015 onward; stroke plus neurology, neuroscience, cardiology"),
             ("Clean", "Journal articles and reviews with a DOI; datasets, preprints, errata and chapters out"),
             ("Detect", "Open-access status, repository links, preprint versions, registration identifiers"),
             ("Read", "Data-availability statements in up to 1,500 open-access full texts per year, via Europe PMC"),
             ("Publish", "Open code, open data, public dashboard; re-run every six months")]
    els = [kicker("05", "How we measured"),
           title("A living pipeline measures the stroke literature every six months")]
    y = 1.3
    for lab, txt in steps:
        els += [HLINE(LX, y, 4.75), T(LX, y + 0.07, 0.95, 0.4, P(R(lab, 12, True))),
                T(LX + 1.0, y + 0.07, 3.75, 0.42, P(R(txt, 11, color="3A3A3A")))]
        y += 0.5
    nums = [("140,281", "stroke articles and reviews"), ("16,362", "stroke full texts read"),
            ("4", "fields, 2015 to 2025")]
    for i, (n, c) in enumerate(nums):
        els.append(T(LX + i * 1.6, 3.95, 1.55, 0.8, [P(R(n, 24, True)), P(R(c, 10.5, color=GREY))]))
    els += [IMG(f("matrix"), 5.3, 1.25, 2.94, 3.72, align="r"),
            footer("friseeb.github.io/stroke_open_science_outputs · Abstract and metadata signals are lower bounds; "
                   "the full-text audit narrows the gap for data sharing.", h=0.36)]
    S.append({"id": "method", "els": els})

    # 8 · finding 1 ----------------------------------------------------------------------------
    S.append({"id": "oa-trend", "els": [
        kicker("06", "Finding 1"),
        title("Stroke went open access: 53% in 2015, 75% in 2024", h=0.45),
        IMG(f("trend_oa"), LX, 1.08, CW, 3.55),
        footer("Open access = any OpenAlex status other than closed. Stroke 66% over the decade; cardiology 70%, "
               "neurology 62%, neuroscience 65% (its title term “neural” also catches machine-learning papers). "
               "2025 is incomplete.", h=0.36),
    ]})

    # 9 · finding 2 ----------------------------------------------------------------------------
    route_rows = [("Gold, paid journal", "25%"), ("Diamond, free journal", "16%"),
                  ("Hybrid, paid in a subscription journal", "10%"), ("Bronze, free to read, no licence", "10%"),
                  ("Green, repository copy", "6%"), ("Closed", "34%")]
    els = [kicker("07", "Finding 2"), title("The growth in open access was paid for, not deposited", h=0.45),
           IMG(f("oa_status"), LX, 1.08, 4.55, 3.6)]
    x0, w0 = 5.05, RX - 5.05
    els += [T(x0, 1.15, w0 - 0.5, 0.25, P(R("Route, 2015 to 2025", 11, True, color=GREY))),
            T(x0 + w0 - 0.5, 1.15, 0.5, 0.25, P(R("Share", 11, True, color=GREY), align="r")),
            HLINE(x0, 1.42, w0, color=INK, lw=1)]
    y = 1.48
    for lab, v in route_rows:
        els += [T(x0, y, w0 - 0.5, 0.27, P(R(lab, 11))), T(x0 + w0 - 0.5, y, 0.5, 0.27, P(R(v, 11), align="r"))]
        y += 0.29
    els += [T(x0, y + 0.12, w0, 1.25, P(R("From 2015 to 2024 gold, a paid route, grew the most (+18 points); diamond "
                                          "(+9) outgrew hybrid (+7). Green fell from 9% in 2015 to 3% in 2025. Bronze "
                                          "can be withdrawn at any time.", 11, color="3A3A3A"))),
            footer("Open access became a transaction between funders and publishers. It did not come with openness of "
                   "anything else.", h=0.2)]
    S.append({"id": "oa-type", "els": els})

    # 10 · finding 3 ---------------------------------------------------------------------------
    els = [kicker("08", "Finding 3"), title("In abstracts, data and code did not move in ten years", h=0.45)]
    sw = (CW - 0.3) / 3
    for i, (img, cap) in enumerate([("trend_data", "Data in a public repository"),
                                    ("trend_code", "GitHub or code link"), ("trend_preprint", "Preprint version")]):
        x = LX + i * (sw + 0.15)
        els += [IMG(f(img), x, 1.02, sw, 0.98, align="c"), T(x, 2.02, sw, 0.22, P(R(cap, 10, color=GREY), align="c"))]
    ftiles = [("Data in a repository", "0.2%", "of stroke articles in 2024; 0.2% in 2015, never above 0.6%", RED),
              ("Code link", "<0.1%", "every year 2015-2024; GitHub in 2.5% of 2024 full texts", RED),
              ("Preprint version", "2.7%", "in 2024; 1.5% in 2015-2025. A lower bound, partly publisher-driven", RED),
              ("Registration ID in the abstract", "5.3%", "in 2024, from 2.8% in 2015; stroke ahead of cardiology, "
               "neurology and neuroscience", INK)]
    for i, (lab, num, cap, col) in enumerate(ftiles):
        els += tile(LX + i * tw, 2.38, tw, 1.95, lab, num, cap, num_color=col, num_size=28)
    els.append(footer("High impact is barely better at sharing: top-cited or IF 10+ articles (16% of the corpus) are 74% "
                      "open access vs 65%, registration 10.0% vs 3.5%, but data 0.45% vs 0.34%, code 0.08% vs 0.06%. "
                      "These are lower bounds from abstracts and metadata. So we read the full text.", h=0.52))
    S.append({"id": "flat", "els": els})

    # 11 · data-availability statements ---------------------------------------------------------
    dw = CW / 3
    dt = [("Write a statement", "74%", "in 2025, from 14% in 2015; arrived with the journal mandates", INK),
          ("Say “available on request”", "29%", "in 2025, from 0.6% in 2015; now the largest answer", RED),
          ("Deposit or public source", "9.8%", "in 2025, from 0.7% in 2015; own deposit 5.9%", RED)]
    els = [kicker("09", "The full-text audit"), title("What data-availability statements actually say", h=0.45)]
    for i, (lab, num, cap, col) in enumerate(dt):
        els += tile(LX + i * dw, 1.02, dw, 1.42, lab, num, cap, num_color=col, num_size=28)
    els += [IMG(f("das_year"), LX, 2.55, CW, 2.3),
            footer("16,362 open-access stroke full texts, up to 1,500 per year, Europe PMC; optimistic for stroke "
                   "overall. Elsewhere, “on request” delivers little: 6.8% of authors shared when asked (Gabelica "
                   "2022); 20% of 391 vascular and cognitive trials, median 241 days (Scutt 2020).", h=0.52)]
    S.append({"id": "das", "els": els})

    # 12 · equity -------------------------------------------------------------------------------
    els = [kicker("10", "Who pays to be read, and who shares"),
           title("Reading access has been solved for the global South by free routes. Reuse has not."),
           IMG(f("eq_route"), LX, 1.35, 3.85, 2.52),
           T(LX, 3.9, 3.85, 0.4, P(R("Open-access route by World Bank income group of the first author’s country", 10,
                                     color=GREY))),
           IMG(f("eq_ft"), 4.35, 1.35, RX - 4.35, 1.78),
           T(4.35, 3.15, RX - 4.35, 0.22, P(R("What the full text shows, by income group", 10, color=GREY))),
           T(4.35, 3.45, RX - 4.35, 1.15, P(R("Lower-middle-income authors publish 42% through routes that cost "
                                              "nothing (high income 19%), yet over 2015-2025 deposit or name public "
                                              "data in 1.8% (high 4.0%), mention GitHub in 0.3% (1.6%) and a trial "
                                              "registration in 5.7% (15.0%).", 12))),
           footer("Income group known for 85% of the corpus: high 62%, upper-middle 32% (mostly China), lower-middle 6%, "
                  "low 0.3% (400 articles). Korea: 5,490 first-author articles, 75% open access.", h=0.36)]
    S.append({"id": "equity", "els": els})

    # 13 · commitment ---------------------------------------------------------------------------
    S.append({"id": "commitment", "els": [
        kicker("11", "Who is already doing it"),
        title("A commitment index, verified in the full text", h=0.45),
        IMG(f("cm_inst"), LX, 1.02, CW, 2.5),
        T(LX, 3.6, CW, 0.62, P(R("Journals: Nature Communications, Brain Communications, PeerJ, NeuroImage Clinical "
                                  "lead; ", 11.5, color="3A3A3A"), R("Stroke", 11.5, italic=True, color="3A3A3A"),
                                R(" is about 15th of 99, at 1.5×. Funders: US federal institutes, ANR, Swiss Heart "
                                  "Foundation, Leducq, DFG. Countries: Belgium 2.4×, Germany 2.2×, Switzerland 2.0×, "
                                  "France 1.8×, UK 1.5×.", 11.5, color="3A3A3A"))),
        footer("Index = mean over three full-text signals of the entity’s rate ÷ the stroke audit rate: data deposited "
               "or public source (4.2%), GitHub (1.3%), trial registration (14.1%). 1 = stroke average. Institutions: "
               "the 60 with the most audited articles (82+ each); countries 50+, journals and funders 30+.", h=0.52),
    ]})

    # 14 · mandates -----------------------------------------------------------------------------
    mrows = [("3.1% to 3.1%", "Data obtainable from surgical trials before and after the ICMJE statement requirement.",
              "Bergeat 2022, JAMA Netw Open", RED),
             ("OR 0.9", "Open-data badges in the only medical randomised trial, at BMJ Open. The same badges took "
              "Psychological Science from under 3% to 39% open data.", "Rowhani-Farid 2020; Kidwell 2016", RED),
             ("0 of 92", "Biomedical promotion guidelines worldwide that mention data sharing, registration or open "
              "access.", "Rice 2020, BMJ", RED),
             ("44% vs 96%", "Positive results in Registered Reports versus the standard literature. Changing when review "
              "happens changes what gets published.", "Scheel 2021", INK)]
    els = [kicker("12", "Why mandates alone did not work"),
           title("Rules produced statements. Incentives produce data.", h=0.45)]
    y = 1.08
    for num, txt, cite, col in mrows:
        els += [HLINE(LX, y, CW), T(LX, y + 0.07, 1.85, 0.6, P(R(num, 22, True, color=col)), anchor="m"),
                T(LX + 1.95, y + 0.07, 4.5, 0.6, P(R(txt, 11.5)), anchor="m"),
                T(LX + 6.6, y + 0.07, CW - 6.6, 0.6, P(R(cite, 10, color=GREY)), anchor="m")]
        y += 0.74
    els += [HLINE(LX, y, CW),
            T(LX, 4.18, CW, 0.62, P(R("Stroke researchers are not less honest than psychologists. They respond to the "
                                      "same incentives, and ours point the other way.", 15, italic=True))),
            footer("Cardiology survey, n = 198: funding named the most essential incentive; “policy alone will not "
                   "lead to implementation” (Cobey 2024).", h=0.36)]
    S.append({"id": "mandates", "els": els})

    # 15 · what to do next ----------------------------------------------------------------------
    fcols = [("1", "A WSO task force on open science",
              ["A position statement: no stroke society has one",
               "Retire “available on request” in Stroke, IJS, ESJ and JSCVD: a repository, VISTA or Vivli, or a "
               "stated reason",
               "Registered Reports for stroke trials, with in-principle acceptance tied to WSO and ESO grants",
               "Embargoed sharing as the trial default, twelve months after publication"]),
             ("2", "A prize for the teams that share",
              ["The commitment index: verified in the full text, recomputed every six months",
               "Institutions, journals, funders and countries",
               "On the Einstein Foundation model, presented at this congress"]),
             ("3", "Awareness",
              ["The public benchmark, updated every six months",
               "Open-science items in promotion criteria: 0 of 92 guidelines today",
               "Targets to discuss: data in a repository or controlled-access platform for 25% of stroke articles by "
               "2030; “on request” under 10%; one Registered Report track in a stroke journal by 2028"])]
    cw3 = CW / 3
    els = [kicker("13", "What to do next"), title("A task force, a prize, and awareness", h=0.45)]
    for i, (n, h3, bullets) in enumerate(fcols):
        x = LX + i * cw3
        els += [RECT(x, 1.02, cw3, 3.78, line=HAIR),
                T(x + 0.13, 1.12, cw3 - 0.26, 3.6, [P(R(n, 22, True, color=RED), after=2), P(R(h3, 13.5, True), after=6)]
                  + [P(R(b, 11), after=4, bullet=True) for b in bullets])]
    els.append(footer("The statement, retiring “on request” and promotion criteria cost nothing. Registered Reports, the "
                      "prize and the infrastructure need money, and the infrastructure mostly exists: VISTA, ATLAS, "
                      "ENIGMA.", h=0.34))
    S.append({"id": "future", "els": els})

    # 16 · close (on the blue title background; the palace photo starts near x = 6.1 in) -----------
    S.append({"id": "close", "bg": "title", "els": [
        T(0.6, 1.45, 5.3, 0.9, P(R("We measured ourselves. The numbers are not flattering, but they are measurable, "
                                   "which means they are improvable.", 17, italic=True, color=WHITE))),
        T(0.6, 2.47, 5.0, 0.22, P(R("COLLABORATE", 11, True, color="8CD17A"))),
        IMG(qr["dashboard"], 0.6, 2.76, 0.86, 0.86),
        T(1.6, 2.76, 4.4, 0.86, [P(R("Stroke Open-Science Benchmark", 12, True, color=WHITE), after=2),
                                 P(R("friseeb.github.io/stroke_open_science_outputs", 11, color=WHITE), after=2),
                                 P(R("Explore it, challenge it, run it on your field", 10.5, color=PALE))], anchor="m"),
        IMG(qr["repo"], 0.6, 3.74, 0.86, 0.86),
        T(1.6, 3.74, 4.4, 0.86, [P(R("Code and data", 12, True, color=WHITE), after=2),
                                 P(R("github.com/Friseeb/stroke_open_science", 11, color=WHITE), after=2),
                                 P(R("Open source; the next run is January 2027", 10.5, color=PALE))], anchor="m"),
        T(0.6, 4.78, 5.3, 0.64, [P(R("Sebastian Fridman · ", 12, True, color=WHITE),
                                   R("sfridma@uwo.ca", 12, True, color="8CD17A"), after=2),
                                 P(R("Western University · London Health Sciences Centre", 10.5, color=PALE), after=2),
                                 P(R("Write to join the task force or to audit your own field", 10.5, color=PALE))]),
    ]})
    return S


# =============================================================================================
# text measurement (shared by the fit check and the preview)
# =============================================================================================
_font_cache: dict = {}


def font(size_pt, bold=False, italic=False, scale=1.0):
    key = (round(size_pt * scale, 2), bold, italic)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_FILES[(bold, italic)], max(1, int(round(size_pt * scale))))
    return _font_cache[key]


def text_w(piece, run):
    """Width in points, measured on a 10x font so fractional point sizes (10.5, 11.5) are exact."""
    return font(run["size"], run["bold"], run["italic"], scale=10).getlength(piece) / 10


def layout_paragraph(para, width_pt):
    """Greedy word wrap of a paragraph made of styled runs. Returns lines of (text, run) pieces and line heights."""
    indent = 12.0 if para["bullet"] else 0.0
    avail = width_pt - indent
    tokens = []
    for run in para["runs"]:
        for piece in re.split(r"( )", run["text"]):
            if piece:
                tokens.append((piece, run))
    lines, cur, cur_w = [], [], 0.0
    for piece, run in tokens:
        w = text_w(piece, run)
        if piece != " " and cur and cur_w + w > avail + 0.01:
            while cur and cur[-1][0] == " ":
                cur_w -= text_w(" ", cur[-1][1])
                cur.pop()
            lines.append(cur)
            cur, cur_w = [], 0.0
        if piece == " " and not cur:
            continue
        cur.append((piece, run))
        cur_w += w
    if cur:
        lines.append(cur)
    if not lines:
        lines = [[]]
    heights = [max([r["size"] for _, r in ln] or [para["runs"][0]["size"]]) * LINE for ln in lines]
    return lines, heights, indent


def measure(el):
    """Height in points that a text element needs, and the widest single word overflow (if any)."""
    width_pt = el["w"] * 72
    total = 0.0
    too_wide = []
    for i, para in enumerate(el["paras"]):
        lines, heights, indent = layout_paragraph(para, width_pt)
        total += sum(heights)
        if i < len(el["paras"]) - 1:
            total += para["after"]
        for ln in lines:
            w = sum(text_w(p, r) for p, r in ln)
            if w > width_pt - indent + 0.5:
                too_wide.append("".join(p for p, _ in ln)[:40])
    return total, too_wide


def fit_report(spec):
    problems = []
    for n, slide in enumerate(spec, 3):
        for el in slide["els"]:
            if el["kind"] != "text":
                continue
            need, wide = measure(el)
            have = el["h"] * 72
            if need > have + 0.5:
                txt = "".join(r["text"] for r in el["paras"][0]["runs"])[:50]
                problems.append(f"slide {n} {slide['id']}: text needs {need / 72:.2f} in, box {el['h']:.2f} in: {txt!r}")
            for w in wide:
                problems.append(f"slide {n} {slide['id']}: word wider than box: {w!r}")
            right = el["x"] + el["w"]
            if slide.get("bg") != "title" and right > 8.3 and el["y"] < 1.65:
                problems.append(f"slide {n} {slide['id']}: text reaches x={right:.2f} under the congress lockup")
            if slide.get("bg") != "title" and right > 8.3 and el["y"] + el["h"] > 4.45:
                problems.append(f"slide {n} {slide['id']}: text reaches x={right:.2f} over the one-voice mark")
            if el["y"] + el["h"] > 5.5:
                problems.append(f"slide {n} {slide['id']}: text runs to y={el['y'] + el['h']:.2f} in")
    return problems


# =============================================================================================
# pptx writing
# =============================================================================================
def rgb(h):
    return RGBColor.from_string(h)


def contain(path, x, y, w, h, align):
    with Image.open(path) as im:
        iw, ih = im.size
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    dx = {"l": 0, "c": (w - dw) / 2, "r": w - dw}[align]
    return x + dx, y, dw, dh


def set_bullet(paragraph, indent_pt=12):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", str(int(Pt(indent_pt))))
    pPr.set("indent", str(-int(Pt(indent_pt))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for old in pPr.findall(qn(tag)):
            pPr.remove(old)
    bu_font = etree.SubElement(pPr, qn("a:buFont"))
    bu_font.set("typeface", FONT)
    bu = etree.SubElement(pPr, qn("a:buChar"))
    bu.set("char", "•")


def write_text(shape_tf, el):
    tf = shape_tf
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[el["anchor"]]
    for i, para in enumerate(el["paras"]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[para["align"]]
        p.line_spacing = 1.0
        p.space_before = Pt(0)
        p.space_after = Pt(para["after"]) if i < len(el["paras"]) - 1 else Pt(0)
        if para["bullet"]:
            set_bullet(p)
        for run in para["runs"]:
            r = p.add_run()
            r.text = run["text"]
            fnt = r.font
            fnt.name = FONT
            fnt.size = Pt(run["size"])
            fnt.bold = run["bold"]
            fnt.italic = run["italic"]
            fnt.color.rgb = rgb(run["color"])
            rPr = r._r.get_or_add_rPr()
            for tag in ("a:latin", "a:ea", "a:cs"):
                node = rPr.find(qn(tag))
                if node is None:
                    node = etree.SubElement(rPr, qn(tag))
                node.set("typeface", FONT)


def cell_border(cell, color, width_pt=0.75):
    tcPr = cell._tc.get_or_add_tcPr()
    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for old in tcPr.findall(qn(side)):
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, qn(side))
        ln.set("w", str(int(Pt(width_pt))))
        solid = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(solid, qn("a:srgbClr"))
        clr.set("val", color)
    # border elements must precede the fill in tcPr
    fills = [c for c in tcPr if c.tag in (qn("a:solidFill"), qn("a:noFill"))]
    for fnode in fills:
        tcPr.remove(fnode)
        tcPr.append(fnode)


def add_table(slide, el):
    nrows, ncols = len(el["rows"]), len(el["col_w"])
    gf = slide.shapes.add_table(nrows, ncols, Inches(el["x"]), Inches(el["y"]), Inches(sum(el["col_w"])),
                                Inches(sum(el["row_h"])))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        tblPr.remove(style)
    for j, w in enumerate(el["col_w"]):
        tbl.columns[j].width = Inches(w)
    for i, h in enumerate(el["row_h"]):
        tbl.rows[i].height = Inches(h)
    for i, row in enumerate(el["rows"]):
        st = el["header_style"] if i == 0 else el["body_style"]
        for j, txt in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            fill = el["header_fill"] if i == 0 else el["body_fill"]
            if isinstance(fill, (list, tuple)):
                fill = fill[j]
            cell.fill.fore_color.rgb = rgb(fill)
            cell.margin_left = cell.margin_right = Inches(0.03)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j in st.get("left_cols", ()) else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = txt
            r.font.name = FONT
            r.font.size = Pt(st["size"])
            r.font.italic = st.get("italic", False)
            r.font.bold = st.get("bold", False)
            r.font.color.rgb = rgb(st["color"])
            cell_border(cell, el["grid"])
    return gf


def copy_background(src_slide, dst_slide):
    """Copy a slide-level <p:bg> (the template's SVG backgrounds) together with its image relationships."""
    bg = src_slide._element.cSld.bg
    new_bg = copy.deepcopy(bg)
    for node in new_bg.iter():
        for attr in (qn("r:embed"), qn("r:link")):
            rid = node.get(attr)
            if rid:
                part = src_slide.part.related_part(rid)
                node.set(attr, dst_slide.part.relate_to(part, RT.IMAGE))
    cSld = dst_slide._element.cSld
    old = cSld.bg
    if old is not None:
        cSld.remove(old)
    cSld.insert(0, new_bg)


def delete_slide(prs, slide):
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        if prs.slides.part.related_part(sldId.rId) is slide.part:
            prs.part.drop_rel(sldId.rId)
            sldIdLst.remove(sldId)
            return


def remove_placeholders(slide):
    for ph in list(slide.placeholders):
        ph._element.getparent().remove(ph._element)


def add_elements(slide, els):
    E = 914400
    for el in els:
        k = el["kind"]
        if k == "text":
            if el.get("name") == "title" and slide.shapes.title is not None:
                shp = slide.shapes.title
                shp.left, shp.top, shp.width, shp.height = Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"])
                shp.text_frame.clear()
            else:
                shp = slide.shapes.add_textbox(Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"]))
            write_text(shp.text_frame, el)
        elif k == "img":
            x, y, w, h = contain(el["path"], el["x"], el["y"], el["w"], el["h"], el["align"])
            slide.shapes.add_picture(str(el["path"]), Emu(int(x * E)), Emu(int(y * E)), Emu(int(w * E)), Emu(int(h * E)))
        elif k == "rect":
            from pptx.enum.shapes import MSO_SHAPE
            shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(el["x"]), Inches(el["y"]), Inches(el["w"]),
                                         Inches(el["h"]))
            if el["fill"]:
                shp.fill.solid()
                shp.fill.fore_color.rgb = rgb(el["fill"])
            else:
                shp.fill.background()
            if el["line"]:
                shp.line.color.rgb = rgb(el["line"])
                shp.line.width = Pt(el["lw"])
            else:
                shp.line.fill.background()
            shp.shadow.inherit = False
        elif k == "line":
            from pptx.enum.shapes import MSO_CONNECTOR
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(el["x"]), Inches(el["y"]),
                                            Inches(el["x"] + el["w"]), Inches(el["y"]))
            ln.line.color.rgb = rgb(el["color"])
            ln.line.width = Pt(el["lw"])
        elif k == "table":
            add_table(slide, el)


def set_notes(slide, text):
    if text:
        slide.notes_slide.notes_text_frame.text = text


def notes_from_html(slides_dir: Path, slide_id: str) -> str:
    path = slides_dir / f"{slide_id}.html"
    if not path.exists():
        return ""
    m = re.search(r"<aside>(.*?)</aside>", path.read_text(encoding="utf-8"), re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


DISCLOSURE_HEADER = ["Company Name", "Honoraria/ Expenses", "Consulting/ Advisory Board", "Funded Research",
                     "Royalties/ Patent", "Stock Options", "Ownership/ Equity Position", "Employee",
                     "Other (please specify)"]
DISCLOSURE_COLS = [342, 122, 146, 109, 110, 118, 110, 123, 224]  # pixel widths in the template's own image, scaled to 8.51 in


def disclosure_elements():
    scale = 8.51 / sum(DISCLOSURE_COLS)
    cols = [c * scale for c in DISCLOSURE_COLS]
    box = TABLE(0.34, 0.31, [0.48, 4.25], [0.4, 0.4], [["", "No, nothing to disclose"], ["", "Yes, please specify:"]],
                header_fill=[INDIGO, GREEN], body_fill=[INDIGO, GREEN],
                header_style={"size": 15, "color": "000000", "left_cols": (1,)},
                body_style={"size": 15, "color": "000000", "left_cols": (1,)}, grid="000000")
    grid = TABLE(0.30, 1.63, cols, [0.75, 0.48, 0.48, 0.48, 0.48],
                 [DISCLOSURE_HEADER] + [[""] * 9 for _ in range(4)],
                 header_fill=INDIGO, body_fill=GREEN,
                 header_style={"size": 9, "italic": True, "color": WHITE},
                 body_style={"size": 12, "color": "000000", "left_cols": (0,)}, grid="808080")
    return [box, grid]


def build_pptx(template: Path, spec, out: Path, slides_dir: Path):
    prs = Presentation(str(template))
    title_slide, disc_slide, content_proto = prs.slides[0], prs.slides[1], prs.slides[2]
    content_layout = content_proto.slide_layout

    # slide 1: name and title on the official title background
    ph = title_slide.shapes.title
    ph.left, ph.top, ph.width, ph.height = Inches(0.6), Inches(1.72), Inches(5.3), Inches(1.25)
    ph.text_frame.clear()
    write_text(ph.text_frame, T(0.6, 1.72, 5.3, 1.25, P(R("Open science in stroke research", 32, True, color=WHITE)),
                                anchor="t"))
    add_elements(title_slide, title_slide_extras())
    set_notes(title_slide, notes_from_html(slides_dir, "cover"))

    # slide 2: the disclosure, rebuilt as editable tables (the template ships it as two pictures with "No" ticked)
    for shp in list(disc_slide.shapes):
        if shp.shape_type == 13:
            shp._element.getparent().remove(shp._element)
    add_elements(disc_slide, disclosure_elements())
    set_notes(disc_slide, "Required by the congress. Tick one box by typing an x in the blue cell, and list any "
                          "company in the table. The congress's published faculty disclosure list shows Speakers "
                          "Bureau, Regeneron/Bayer, under Other; confirm it, or ask wsc@kenes.com to correct it.")

    # content slides: each copies the template's own white background (an SVG on the slide, not the 4:3 layout image)
    for s in spec:
        slide = prs.slides.add_slide(content_layout)
        copy_background(title_slide if s.get("bg") == "title" else content_proto, slide)
        keep_title = any(el.get("name") == "title" for el in s["els"])
        for ph in list(slide.placeholders):
            if not (keep_title and ph.placeholder_format.idx == 0):
                ph._element.getparent().remove(ph._element)
        add_elements(slide, s["els"])
        set_notes(slide, notes_from_html(slides_dir, s["id"]))

    # drop the template's two empty content slides
    for proto in [prs.slides[2], prs.slides[3]]:
        delete_slide(prs, proto)
    prs.save(str(out))


def title_slide_extras():
    return [
        T(0.6, 2.98, 5.2, 0.62, P(R("Measuring reproducibility and transparency, and what to do with the numbers", 16,
                                    color=PALE))),
        T(0.6, 3.95, 5.2, 0.62, [P(R("Sebastian Fridman, MD", 16, True, color=WHITE), after=3),
                                 P(R("Western University · London Health Sciences Centre · Canada", 12, color=PALE))]),
        T(0.6, 4.8, 5.2, 0.42, P(R("The latest in stroke implementation science · Thursday 22 October 2026", 11,
                                   color=PALE))),
    ]


# =============================================================================================
# preview
# =============================================================================================
def draw_text(d, el, scale_px):
    x0, y0, w = el["x"] * PX_IN, el["y"] * PX_IN, el["w"] * PX_IN
    need, _ = measure(el)
    hpx = el["h"] * PX_IN
    need_px = need / 72 * PX_IN
    y = y0 + {"t": 0, "m": (hpx - need_px) / 2, "b": hpx - need_px}[el["anchor"]]
    for i, para in enumerate(el["paras"]):
        lines, heights, indent = layout_paragraph(para, el["w"] * 72)
        for li, (ln, lh) in enumerate(zip(lines, heights)):
            lw = sum(text_w(p, r) for p, r in ln) / 72 * PX_IN
            ix = indent / 72 * PX_IN
            x = x0 + ix + {"l": 0, "c": (w - ix - lw) / 2, "r": w - ix - lw}[para["align"]]
            if para["bullet"] and li == 0 and ln:
                r0 = ln[0][1]
                d.text((x0, y), "•", font=font(r0["size"], scale=scale_px), fill="#" + r0["color"])
            for piece, r in ln:
                fnt = font(r["size"], r["bold"], r["italic"], scale=scale_px)
                d.text((x, y + (lh - r["size"] * LINE) / 72 * PX_IN * 0.5), piece, font=fnt, fill="#" + r["color"])
                x += text_w(piece, r) / 72 * PX_IN
            y += lh / 72 * PX_IN
        if i < len(el["paras"]) - 1:
            y += para["after"] / 72 * PX_IN
    d.rectangle([x0, y0, x0 + w, y0 + hpx], outline="#f0a0ff")   # box outline, preview only


def draw_table(d, el, scale_px):
    y = el["y"] * PX_IN
    for i, (row, rh) in enumerate(zip(el["rows"], el["row_h"])):
        x = el["x"] * PX_IN
        st = el["header_style"] if i == 0 else el["body_style"]
        for j, (txt, cw) in enumerate(zip(row, el["col_w"])):
            fill = el["header_fill"] if i == 0 else el["body_fill"]
            if isinstance(fill, (list, tuple)):
                fill = fill[j]
            d.rectangle([x, y, x + cw * PX_IN, y + rh * PX_IN], fill="#" + fill, outline="#" + el["grid"])
            if txt:
                sub = T(x / PX_IN + 0.03, y / PX_IN, cw - 0.06, rh,
                        P(R(txt, st["size"], st.get("bold", False), st.get("italic", False), st["color"]),
                          align="l" if j in st.get("left_cols", ()) else "c"), anchor="m")
                draw_text(d, sub, scale_px)
            x += cw * PX_IN
        y += rh * PX_IN


def render_preview(spec, bg_title: Path, bg_content: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    scale_px = PX_IN / 72
    pages = [("01-title", "title", title_slide_extras() + [T(0.6, 1.72, 5.3, 1.25, P(R("Open science in stroke research",
                                                                                      32, True, color=WHITE)))]),
             ("02-disclosure", "content", disclosure_elements())]
    pages += [(f"{n:02d}-{s['id']}", s.get("bg", "content"), s["els"]) for n, s in enumerate(spec, 3)]
    for name, bg, els in pages:
        im = Image.open(bg_title if bg == "title" else bg_content).convert("RGB").resize((1920, 1080), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        for el in els:
            k = el["kind"]
            if k == "img":
                x, y, w, h = contain(el["path"], el["x"], el["y"], el["w"], el["h"], el["align"])
                pic = Image.open(el["path"]).convert("RGB").resize((max(1, int(w * PX_IN)), max(1, int(h * PX_IN))),
                                                                   Image.LANCZOS)
                im.paste(pic, (int(x * PX_IN), int(y * PX_IN)))
            elif k == "rect":
                box = [el["x"] * PX_IN, el["y"] * PX_IN, (el["x"] + el["w"]) * PX_IN, (el["y"] + el["h"]) * PX_IN]
                d.rectangle(box, fill=("#" + el["fill"]) if el["fill"] else None,
                            outline=("#" + el["line"]) if el["line"] else None, width=max(1, int(el["lw"] * scale_px)))
            elif k == "line":
                y = el["y"] * PX_IN
                d.line([el["x"] * PX_IN, y, (el["x"] + el["w"]) * PX_IN, y], fill="#" + el["color"],
                       width=max(1, int(el["lw"] * scale_px)))
            elif k == "table":
                draw_table(d, el, scale_px)
        for el in els:
            if el["kind"] == "text":
                draw_text(d, el, scale_px)
        d.line([8.3 * PX_IN, 0, 8.3 * PX_IN, 1080], fill="#ffd0d0") if bg == "content" else None
        im.save(out_dir / f"{name}.png")


def make_qr(url: str, path: Path):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=20, border=2)
    q.add_data(url)
    q.make(fit=True)
    q.make_image(fill_color="black", back_color="white").convert("RGB").save(path, quality=95)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--figures", type=Path, required=True, help="folder of white-background JPG dashboard exports")
    ap.add_argument("--slides", type=Path, required=True, help="talk/deck/project/slides (speaker notes come from here)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--preview-dir", type=Path)
    ap.add_argument("--bg-title", type=Path, help="PNG render of the template's title background (preview only)")
    ap.add_argument("--bg-content", type=Path, help="PNG render of the template's content background (preview only)")
    args = ap.parse_args()

    qr_dir = args.out.parent / "qr"
    qr_dir.mkdir(parents=True, exist_ok=True)
    qr = {"dashboard": qr_dir / "qr_dashboard.jpg", "repo": qr_dir / "qr_repo.jpg"}
    make_qr("https://friseeb.github.io/stroke_open_science_outputs/", qr["dashboard"])
    make_qr("https://github.com/Friseeb/stroke_open_science", qr["repo"])

    spec = deck_spec(args.figures, qr)
    problems = fit_report(spec)
    for p in problems:
        print("FIT", p)
    build_pptx(args.template, spec, args.out, args.slides)
    print("wrote", args.out)
    if args.preview_dir and args.bg_title and args.bg_content:
        render_preview(spec, args.bg_title, args.bg_content, args.preview_dir)
        print("previews in", args.preview_dir)


if __name__ == "__main__":
    main()
