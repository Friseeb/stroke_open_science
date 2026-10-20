"""Build the World Stroke Congress 2026 talk as a .pptx in the talk's own design.

Every slide is the Slides deck (talk/deck/project) converted to native, editable PowerPoint shapes: text boxes,
filled and bordered boxes, rules and JPG pictures, at the positions Chrome measured with the congress fonts
(extract_slides.js). The HTML deck is the single source, so the two presentations always agree. Slide 1 (cover) carries
the name and title and slide 2 (disclosure) the congress's conflict-of-interest form, both in the deck's look.

With --template WSC-2026-PPT_w_disclosure_16_9.pptx the first two slides come from the official speaker template
instead (its title slide, and its disclosure rebuilt as editable tables with "No" ticked); the speaker chose the deck's
own look for all slides on 2026-10-14, so this is off by default.

Congress rules followed: 16:9; slide 1 = name and title; slide 2 = conflict-of-interest disclosure; common fonts only
(Arial, and Times New Roman for the big figures); pictures as JPG. The official WSC cover banner is included
at the speaker's request. Conceptual illustrations are separate from empirical evidence graphics.

Usage:
  NODE_PATH=<dir>/node_modules node talk/deck/congress/extract_slides.js talk/deck/project \
      talk/outputs/figures/dashboard /tmp/wsc_extract
  python talk/deck/congress/build_wsc_pptx.py --extract /tmp/wsc_extract \
      --out talk/deck/congress/Fridman_WSC2026_open_science.pptx --preview-dir /tmp/wsc_preview
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

SANS, SERIF = "Arial", "Times New Roman"
FONT_FILES = {
    (SANS, False, False): "/System/Library/Fonts/Supplemental/Arial.ttf",
    (SANS, True, False): "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    (SANS, False, True): "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    (SANS, True, True): "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    (SERIF, False, False): "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    (SERIF, True, False): "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    (SERIF, False, True): "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
    (SERIF, True, True): "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf",
}
EMU_PX = 914400 * 10 / 1920      # the 1920 x 1080 canvas onto a 10 x 5.625 in slide
PT_PX = 72 * 10 / 1920           # 0.375 pt per canvas pixel
WIDTH_SLACK = 0.03               # text boxes 3% wider than Chrome's, so PowerPoint never wraps a line earlier
TEMPLATE_IDS = {"cover", "disclosure"}  # replaced by the template's own slides when --template is given

WHITE, PALE = "FFFFFF", "DCE6F5"
INDIGO, GREEN = "2E247A", "52AE32"   # disclosure colours, sampled from the template's picture


# =============================================================================================
# helpers shared by the .pptx writer and the preview
# =============================================================================================
def css_rgb(value: str) -> str | None:
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", value or "")
    if not m or (m.group(4) is not None and float(m.group(4)) == 0):
        return None
    return "%02X%02X%02X" % tuple(int(m.group(i)) for i in (1, 2, 3))


_fonts: dict = {}


def font(face, size_px, bold, italic, scale=10):
    key = (face, round(size_px * scale), bold, italic)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_FILES[(face, bold, italic)], max(1, round(size_px * scale)))
    return _fonts[key]


def run_face(run):
    return SERIF if run.get("serif") else SANS


def text_w(piece, run):
    """Width in canvas px, measured on a 10x font, plus letter spacing."""
    w = font(run_face(run), run["size"], run["bold"], run["italic"]).getlength(piece) / 10
    return w + run.get("spacing", 0) * len(piece)


def wrap(item, width_px):
    """Greedy word wrap over styled runs and <br>s, as PowerPoint does. Returns lists of (piece, run)."""
    lines, cur, cur_w = [], [], 0.0
    for run in item["runs"]:
        if run.get("br"):
            lines.append(cur)
            cur, cur_w = [], 0.0
            continue
        for piece in re.split(r"( )", run["text"]):
            if not piece:
                continue
            w = text_w(piece, run)
            if piece != " " and cur and cur_w + w > width_px + 0.01:
                while cur and cur[-1][0] == " ":
                    cur_w -= text_w(" ", cur[-1][1])
                    cur.pop()
                lines.append(cur)
                cur, cur_w = [], 0.0
            if piece == " " and not cur:
                continue
            cur.append((piece, run))
            cur_w += w
    lines.append(cur)
    return lines


def box_geometry(item):
    """Text box rectangle on the canvas: Chrome's content box, widened by the slack on the side alignment allows."""
    indent = item.get("indent", 0) if item.get("bullet") else 0
    x, w = item["x"] - indent, item["w"] + indent
    extra = max(4.0, w * WIDTH_SLACK)
    align = item.get("align", "left")
    if align in ("right", "end"):
        x -= extra
    elif align == "center":
        x -= extra / 2
    return x, item["y"], w + extra, item["h"], indent


# =============================================================================================
# .pptx writing
# =============================================================================================
def rgb(h):
    return RGBColor.from_string(h)


def emu(px):
    return Emu(int(round(px * EMU_PX)))


def set_bullet(paragraph, indent_px):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", str(int(round(indent_px * EMU_PX))))
    pPr.set("indent", str(-int(round(indent_px * EMU_PX))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont"):
        for old in pPr.findall(qn(tag)):
            pPr.remove(old)
    etree.SubElement(pPr, qn("a:buFont")).set("typeface", SANS)
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def style_run(r, face, size_pt, bold, italic, color, underline=False, spacing_pt=0.0):
    f = r.font
    f.name = face
    f.size = Pt(round(size_pt * 100) / 100)
    f.bold = bold
    f.italic = italic
    f.underline = underline
    f.color.rgb = rgb(color)
    rPr = r._r.get_or_add_rPr()
    if spacing_pt:
        rPr.set("spc", str(int(round(spacing_pt * 100))))
    for tag in ("a:latin", "a:ea", "a:cs"):
        node = rPr.find(qn(tag))
        if node is None:
            node = etree.SubElement(rPr, qn(tag))
        node.set("typeface", face)


def prepare_frame(tf, anchor=MSO_ANCHOR.TOP):
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor


def write_item(slide, item, use_title):
    x, y, w, h, indent = box_geometry(item)
    if use_title and slide.shapes.title is not None:
        shp = slide.shapes.title
        shp.left, shp.top, shp.width, shp.height = emu(x), emu(y), emu(w), emu(h)
        shp.text_frame.clear()
    else:
        shp = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = shp.text_frame
    prepare_frame(tf, {"bottom": MSO_ANCHOR.BOTTOM, "middle": MSO_ANCHOR.MIDDLE}.get(item.get("valign"), MSO_ANCHOR.TOP))
    p = tf.paragraphs[0]
    p.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "end": PP_ALIGN.RIGHT}.get(item.get("align"), PP_ALIGN.LEFT)
    p.line_spacing = Pt(round(item["lineHeight"] * PT_PX * 100) / 100)
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    if item.get("bullet"):
        set_bullet(p, indent)
    for run in item["runs"]:
        if run.get("br"):
            p.add_line_break()
            continue
        r = p.add_run()
        r.text = run["text"]
        style_run(r, run_face(run), run["size"] * PT_PX, run["bold"], run["italic"], css_rgb(run["color"]) or "000000",
                  run.get("underline", False), run.get("spacing", 0) * PT_PX)
    return shp


def add_box(slide, b):
    fill = css_rgb(b["fill"]) if b.get("fill") else None
    if fill:
        shp = slide.shapes.add_shape(MSO_SHAPE.OVAL if b.get("round") else MSO_SHAPE.RECTANGLE,
                                     emu(b["x"]), emu(b["y"]), emu(b["w"]), emu(b["h"]))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
        shp.line.fill.background()
        shp.shadow.inherit = False
    for side, spec in (b.get("borders") or {}).items():
        color = css_rgb(spec["color"])
        if not color:
            continue
        lw = spec["w"]
        x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
        seg = {"top": (x0, y0 + lw / 2, x1, y0 + lw / 2), "bottom": (x0, y1 - lw / 2, x1, y1 - lw / 2),
               "left": (x0 + lw / 2, y0, x0 + lw / 2, y1), "right": (x1 - lw / 2, y0, x1 - lw / 2, y1)}[side]
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, emu(seg[0]), emu(seg[1]), emu(seg[2]), emu(seg[3]))
        ln.line.color.rgb = rgb(color)
        ln.line.width = Pt(max(0.5, lw * PT_PX))


def to_jpg(src: Path, media: Path, background=(255, 255, 255)) -> Path:
    media.mkdir(parents=True, exist_ok=True)
    out = media / (src.stem + ".jpg")
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        im = Image.open(src)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            base = Image.new("RGB", im.size, background)
            base.paste(im, mask=im.split()[-1])
            im = base
        im.convert("RGB").save(out, quality=93, optimize=True)
    return out


def cell_border(cell, color, width_pt=0.75):
    tcPr = cell._tc.get_or_add_tcPr()
    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for old in tcPr.findall(qn(side)):
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, qn(side))
        ln.set("w", str(int(Pt(width_pt))))
        etree.SubElement(etree.SubElement(ln, qn("a:solidFill")), qn("a:srgbClr")).set("val", color)
    for fnode in [c for c in tcPr if c.tag in (qn("a:solidFill"), qn("a:noFill"))]:
        tcPr.remove(fnode)
        tcPr.append(fnode)   # borders must precede the fill


def add_table(slide, x, y, col_w, row_h, rows, fills, styles, grid):
    """A native table (inches). fills: per row, one colour or a per-column list; styles: one dict per row."""
    gf = slide.shapes.add_table(len(rows), len(col_w), Inches(x), Inches(y), Inches(sum(col_w)), Inches(sum(row_h)))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    sid = tblPr.find(qn("a:tableStyleId"))
    if sid is not None:
        tblPr.remove(sid)
    for j, w in enumerate(col_w):
        tbl.columns[j].width = Inches(w)
    for i, h in enumerate(row_h):
        tbl.rows[i].height = Inches(h)
    for i, row in enumerate(rows):
        st = styles[i]
        for j, txt in enumerate(row):
            cell = tbl.cell(i, j)
            fill = fills[i][j] if isinstance(fills[i], (list, tuple)) else fills[i]
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(fill)
            cell.margin_left = cell.margin_right = Inches(0.03)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text_frame.word_wrap = True
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j in st.get("left_cols", ()) else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = txt
            style_run(r, SANS, st["size"], st.get("bold", False), st.get("italic", False),
                      st.get("col_colors", {}).get(j, st["color"]))
            cell_border(cell, grid)


DISCLOSURE_HEADER = ["Company Name", "Honoraria/ Expenses", "Consulting/ Advisory Board", "Funded Research",
                     "Royalties/ Patent", "Stock Options", "Ownership/ Equity Position", "Employee",
                     "Other (please specify)"]
DISCLOSURE_COLS = [342, 122, 146, 109, 110, 118, 110, 123, 224]  # pixel widths in the template's own picture


def build_disclosure(slide):
    """The template's disclosure, rebuilt editable. The speaker has nothing to disclose (confirmed 2026-10-13)."""
    for shp in list(slide.shapes):
        if shp.shape_type == 13:
            shp._element.getparent().remove(shp._element)
    box_style = {"size": 15, "color": "000000", "left_cols": (1,), "col_colors": {0: WHITE}}
    add_table(slide, 0.34, 0.31, [0.48, 4.25], [0.4, 0.4],
              [["x", "No, nothing to disclose"], ["", "Yes, please specify:"]],
              [[INDIGO, GREEN], [INDIGO, GREEN]], [box_style, box_style], "000000")
    scale = 8.51 / sum(DISCLOSURE_COLS)
    head = {"size": 9, "italic": True, "color": WHITE}
    body = {"size": 11, "color": "000000", "left_cols": (0,)}
    add_table(slide, 0.30, 1.63, [c * scale for c in DISCLOSURE_COLS], [0.75, 0.48, 0.48, 0.48, 0.48],
              [DISCLOSURE_HEADER] + [[""] * 9 for _ in range(4)], [INDIGO] + [GREEN] * 4, [head] + [body] * 4, "808080")
    slide.notes_slide.notes_text_frame.text = "Nothing to disclose. Required by the congress; a second, then move on."


TITLE_LINES = [  # (x, y, w, h in inches), text, size pt, bold, colour; the first goes in the title placeholder
    ((0.6, 1.72, 5.3, 1.25), "Open science in stroke research", 32, True, WHITE),
    ((0.6, 2.98, 5.2, 0.62), "Measuring reproducibility and transparency, and what to do with the numbers", 16, False, PALE),
    ((0.6, 3.95, 5.2, 0.32), "Sebastian Fridman, MD", 16, True, WHITE),
    ((0.6, 4.27, 5.2, 0.3), "Western University · London Health Sciences Centre · Canada", 12, False, PALE),
    ((0.6, 4.8, 5.2, 0.42), "The latest in stroke implementation science · Thursday 22 October 2026", 11, False, PALE),
]


def build_title(slide, notes):
    """Slide 1: name and title on the official title background (Arial, white, left of the photograph)."""
    for i, (geom, text, size, bold, color) in enumerate(TITLE_LINES):
        if i == 0:
            shp = slide.shapes.title
            shp.left, shp.top, shp.width, shp.height = (Inches(v) for v in geom)
            shp.text_frame.clear()
        else:
            shp = slide.shapes.add_textbox(*(Inches(v) for v in geom))
        prepare_frame(shp.text_frame)
        r = shp.text_frame.paragraphs[0].add_run()
        r.text = text
        style_run(r, SANS, size, bold, False, color)
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def delete_slide(prs, slide):
    lst = prs.slides._sldIdLst
    for sldId in list(lst):
        if prs.part.related_part(sldId.rId) is slide.part:
            prs.part.drop_rel(sldId.rId)
            lst.remove(sldId)
            return


def add_native_evidence_svg(slide, sv):
    """Keep the OA time series editable; QR paths still export as pictures."""
    if not sv.get("markup") or "<polyline" not in sv["markup"]:
        return False
    root = etree.fromstring(sv["markup"].encode())
    view = list(map(float, root.get("viewBox").split()))
    sx, sy = sv["w"] / view[2], sv["h"] / view[3]
    X = lambda value: sv["x"] + float(value) * sx
    Y = lambda value: sv["y"] + float(value) * sy
    def segment(x1, y1, x2, y2, node):
        shp = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, emu(X(x1)), emu(Y(y1)), emu(X(x2)), emu(Y(y2)))
        shp.line.color.rgb = rgb(css_rgb(node.get("stroke")) or "000000")
        shp.line.width = Pt(float(node.get("stroke-width", 1)) * sx * PT_PX)
    for node in root:
        kind = etree.QName(node).localname
        if kind == "line":
            segment(node.get("x1"), node.get("y1"), node.get("x2"), node.get("y2"), node)
        elif kind == "polyline":
            points = [list(map(float, pair.split(","))) for pair in node.get("points").split()]
            for first, second in zip(points, points[1:]):
                segment(*first, *second, node)
        elif kind == "text":
            size = float(node.get("font-size", 32)) * sx
            anchor, width = node.get("text-anchor", "start"), 380
            x = X(node.get("x")) - (width if anchor == "end" else width / 2 if anchor == "middle" else 0)
            item = {"tag": "SVG", "x": x, "y": Y(node.get("y")) - size, "w": width, "h": size * 1.3,
                    "lineHeight": size * 1.3, "align": {"end": "right", "middle": "center"}.get(anchor, "left"),
                    "runs": [{"text": "".join(node.itertext()), "size": size,
                              "bold": int(node.get("font-weight", "400")) >= 600, "italic": False,
                              "color": node.get("fill", "#000000"), "serif": False, "spacing": 0}]}
            write_item(slide, item, False)
    return True


def build_pptx(template: Path | None, extract: dict, out: Path, media: Path):
    by_id = {s["id"]: s for s in extract["slides"]}
    skip, protos = set(), []
    if template:
        prs = Presentation(str(template))
        title_slide, disc_slide = prs.slides[0], prs.slides[1]
        protos = [prs.slides[i] for i in range(2, len(prs.slides))]
        layout = protos[0].slide_layout if protos else title_slide.slide_layout
        build_title(title_slide, by_id.get("cover", {}).get("notes", ""))
        build_disclosure(disc_slide)
        skip = TEMPLATE_IDS
    else:
        prs = Presentation()                         # python-pptx's blank template, set to 16:9
        prs.slide_width, prs.slide_height = Emu(9144000), Emu(5143500)
        layout = next(l for l in prs.slide_layouts if l.name == "Title Only")
    core = prs.core_properties
    core.title, core.author = "Open science in stroke research", "Sebastian Fridman"
    core.subject = "World Stroke Congress 2026, Seoul: The latest in stroke implementation science"

    for sid in extract["order"]:
        if sid in skip:
            continue
        s = by_id[sid]
        slide = prs.slides.add_slide(layout)
        bg = slide.background.fill        # a solid slide background replaces the layout's 4:3 picture
        bg.solid()
        bg.fore_color.rgb = rgb(css_rgb(s["bg"]) or "F1F1EF")
        for ph in list(slide.placeholders):
            if ph.placeholder_format.idx != 0:
                ph._element.getparent().remove(ph._element)
        for b in s["boxes"]:
            add_box(slide, b)
        for im in s["images"]:
            jpg = to_jpg(Path(im["src"]), media)
            slide.shapes.add_picture(str(jpg), emu(im["x"]), emu(im["y"]), emu(im["w"]), emu(im["h"]))
        for sv in s["svgs"]:
            if add_native_evidence_svg(slide, sv):
                continue
            jpg = to_jpg(Path(sv["file"]), media)
            slide.shapes.add_picture(str(jpg), emu(sv["x"]), emu(sv["y"]), emu(sv["w"]), emu(sv["h"]))
        title_done = False
        for item in s["texts"]:
            use_title = not title_done and item["tag"] in ("H1", "H2")
            write_item(slide, item, use_title)
            title_done = title_done or use_title
        if not title_done and slide.shapes.title is not None:
            t = slide.shapes.title
            t._element.getparent().remove(t._element)
        if s.get("notes"):
            slide.notes_slide.notes_text_frame.text = s["notes"]

    for proto in protos:
        delete_slide(prs, proto)
    prs.save(str(out))


# =============================================================================================
# checks and preview
# =============================================================================================
def fit_report(extract, skip=frozenset()):
    """Lines PowerPoint will need (Arial / Times metrics, widened box) against the lines Chrome laid out."""
    problems = []
    for s in extract["slides"]:
        if s["id"] in skip:
            continue
        for item in s["texts"]:
            x, y, w, h, indent = box_geometry(item)
            n = len(wrap(item, w - indent))
            label = "".join(r.get("text", "") for r in item["runs"])[:48]
            if n > item["lines"]:
                problems.append(f"{s['id']}: {n} lines vs Chrome {item['lines']}: {label!r}")
            if y + h > 1080 or x + w > 1921:
                problems.append(f"{s['id']}: off the canvas: {label!r}")
            if y < 925 and y + h > 925:
                problems.append(f"{s['id']}: runs past y 920 into the footer band: {label!r}")
        for im in s["images"]:
            if im["y"] + im["h"] > 925:
                problems.append(f"{s['id']}: picture runs past y 920 ({im['y'] + im['h']:.0f})")
    return problems


def render_preview(extract, out_dir: Path, bg_title: Path | None, skip=frozenset()):
    """Draw each converted slide from the extracted layout with PIL: what the .pptx contains, not Chrome's render."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 3 if skip else 1
    for s in extract["slides"]:
        if s["id"] in skip:
            continue
        im = Image.new("RGB", (1920, 1080), "#" + (css_rgb(s["bg"]) or "F1F1EF"))
        d = ImageDraw.Draw(im)
        for b in s["boxes"]:
            if b.get("fill") and css_rgb(b["fill"]):
                draw_mark = d.ellipse if b.get("round") else d.rectangle
                draw_mark([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], fill="#" + css_rgb(b["fill"]))
            for side, spec in (b.get("borders") or {}).items():
                c = css_rgb(spec["color"])
                if not c:
                    continue
                x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
                seg = {"top": (x0, y0, x1, y0), "bottom": (x0, y1 - 1, x1, y1 - 1), "left": (x0, y0, x0, y1),
                       "right": (x1 - 1, y0, x1 - 1, y1)}[side]
                d.line(seg, fill="#" + c, width=max(1, round(spec["w"])))
        for pic in s["images"] + s["svgs"]:
            src = pic.get("src") or pic.get("file")
            p = Image.open(src).convert("RGB").resize((max(1, round(pic["w"])), max(1, round(pic["h"]))), Image.LANCZOS)
            im.paste(p, (round(pic["x"]), round(pic["y"])))
        for item in s["texts"]:
            x, y, w, h, indent = box_geometry(item)
            lh = item["lineHeight"]
            lines = wrap(item, w - indent)
            y += {"bottom": h - lh * len(lines), "middle": (h - lh * len(lines)) / 2}.get(item.get("valign"), 0)
            for li, line in enumerate(lines):
                lw = sum(text_w(p_, r) for p_, r in line)
                align = item.get("align", "left")
                cx = x + indent + {"center": (w - indent - lw) / 2, "right": w - indent - lw,
                                   "end": w - indent - lw}.get(align, 0)
                if item.get("bullet") and li == 0 and line:
                    r0 = line[0][1]
                    d.text((x, y + (lh - r0["size"] * 1.15) / 2), "•", font=font(SANS, r0["size"], False, False, scale=1),
                           fill="#" + (css_rgb(r0["color"]) or "000000"))
                for piece, r in line:
                    f = font(run_face(r), r["size"], r["bold"], r["italic"], scale=1)
                    d.text((cx, y + (lh - r["size"] * 1.15) / 2), piece, font=f, fill="#" + (css_rgb(r["color"]) or "000000"))
                    cx += text_w(piece, r)
                y += lh
        im.save(out_dir / f"{n:02d}-{s['id']}.png")
        n += 1
    if bg_title and skip:
        t = Image.open(bg_title).convert("RGB").resize((1920, 1080))
        d = ImageDraw.Draw(t)
        for (x, y, w, h), text, size, bold, color in TITLE_LINES:
            d.text((x * 192, y * 192), text, font=font(SANS, size / PT_PX, bold, False, scale=1), fill="#" + color)
        t.save(out_dir / "01-title.png")


def rebuild_existing_package(source, extract_dir, destination, animate=False):
    """Rebuild slide contents while retaining the existing congress package and masters."""
    from io import BytesIO
    import hashlib
    import zipfile
    from lxml import etree as E
    SOURCE, OUT = source, destination
    layout = json.loads((extract_dir / "slides.json").read_text())
    P='http://schemas.openxmlformats.org/presentationml/2006/main'
    A='http://schemas.openxmlformats.org/drawingml/2006/main'
    R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    REL='http://schemas.openxmlformats.org/package/2006/relationships'
    NS={'p':P,'a':A,'r':R}
    EMU=9144000/1920
    def tag(ns,name):return '{'+ns+'}'+name
    def sub(parent,ns,element_name,**attrs):return E.SubElement(parent,tag(ns,element_name),{k:str(v) for k,v in attrs.items()})
    def val(x):return max(1,round(x*EMU))
    def xy(x):return round(x*EMU)
    def color(css):
        if not css or css in ('none','transparent'):return None
        if css.startswith('#'):return css.lstrip('#').upper()
        nums=re.findall(r'[\d.]+',css)
        return ''.join(f'{int(float(n)):02X}' for n in nums[:3]) if len(nums)>=3 else None
    def solid(parent,css):
        c=color(css)
        if c:sub(sub(parent,A,'solidFill'),A,'srgbClr',val=c)
        else:sub(parent,A,'noFill')
    def xfrm(parent,x,y,w,h):
        xf=sub(parent,A,'xfrm');sub(xf,A,'off',x=xy(x),y=xy(y));sub(xf,A,'ext',cx=val(w),cy=val(h))
    def base_shape(tree,idx,name,x,y,w,h,geometry='rect',fill=None):
        sp=sub(tree,P,'sp');nv=sub(sp,P,'nvSpPr');sub(nv,P,'cNvPr',id=idx,name=name)
        sub(nv,P,'cNvSpPr',txBox='1' if geometry=='textbox' else '0');sub(nv,P,'nvPr')
        pr=sub(sp,P,'spPr');xfrm(pr,x,y,w,h)
        geom=sub(pr,A,'prstGeom',prst='rect' if geometry=='textbox' else geometry);sub(geom,A,'avLst')
        solid(pr,fill);sub(sub(pr,A,'ln'),A,'noFill')
        return sp
    def text(tree,idx,item,name=None):
        w=item['w']+8
        x=item['x']-(8 if item.get('align') in ('right','end') else 4 if item.get('align')=='center' else 0)
        sp=base_shape(tree,idx,name or 'Text '+str(idx),x,item['y'],w,item['h']+4,'textbox')
        # a line Chrome laid out on one line never wraps in PowerPoint (its metrics can run slightly wider and would
        # break a tight word such as "Value" across two lines)
        body=sub(sp,P,'txBody');sub(body,A,'bodyPr',wrap='none' if item.get('lines',1)==1 else 'square',lIns=0,rIns=0,tIns=0,bIns=0,anchor='t');sub(body,A,'lstStyle')
        p=sub(body,A,'p');pr=sub(p,A,'pPr',algn={'center':'ctr','right':'r','end':'r'}.get(item.get('align'),'l'))
        sub(sub(pr,A,'lnSpc'),A,'spcPts',val=round(item['lineHeight']*37.5))
        sub(sub(pr,A,'spcBef'),A,'spcPts',val=0);sub(sub(pr,A,'spcAft'),A,'spcPts',val=0)
        sub(pr,A,'buNone')
        for q in item['runs']:
            if q.get('br'):sub(p,A,'br');continue
            r=sub(p,A,'r');rp=sub(r,A,'rPr',lang='en-US',sz=round(q['size']*37.5),b='1' if q.get('bold') else '0',i='1' if q.get('italic') else '0',spc=round(q.get('spacing',0)*37.5))
            if q.get('underline'):rp.set('u','sng')
            solid(rp,q.get('color') or '#000000')
            face=q.get('family') or ('Instrument Serif' if q.get('serif') else 'Instrument Sans')
            if face == 'Instrument Sans':
                weight=q.get('weight',400)
                face={400:'Instrument Sans',500:'Instrument Sans Medium',600:'Instrument Sans SemiBold',700:'Instrument Sans Bold'}.get(weight,'Instrument Sans')
                rp.set('b','0')
            for family in ('latin','ea','cs'):sub(rp,A,family,typeface=face)
            t=sub(r,A,'t');t.text=q['text'];t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        sub(p,A,'endParaRPr',lang='en-US')
        return idx+1
    with zipfile.ZipFile(SOURCE) as z:files={n:z.read(n) for n in z.namelist()}
    pres=E.fromstring(files['ppt/presentation.xml'])
    rels=E.fromstring(files['ppt/_rels/presentation.xml.rels'])
    by_rid={r.get('Id'):r.get('Target') for r in rels}
    parts=['ppt/'+by_rid[s.get(tag(R,'id'))] for s in pres.find(tag(P,'sldIdLst'))]
    assert len(parts)==len(layout['slides']), 'The source package and deck must have the same slide count'
    prev_id=None
    for part,data in zip(parts,layout['slides']):
        roles={'title':[],'big':[],'pic':[],'foot':[]}
        xml=E.fromstring(files[part]); xml.find('p:cSld',NS).set('name', data['id']); tree=xml.find('p:cSld/p:spTree',NS)
        for el in list(tree):
            if E.QName(el).localname not in ('nvGrpSpPr','grpSpPr'):tree.remove(el)
        relname=part.replace('/slides/','/slides/_rels/')+'.rels'
        sr=E.fromstring(files[relname])
        for r in list(sr):
            if r.get('Type').endswith('/image'):sr.remove(r)
        idx=2
        for b in data['boxes']:
            if b.get('fill'):
                base_shape(tree,idx,'Data mark '+str(idx),b['x'],b['y'],b['w'],b['h'],'ellipse' if b.get('round') else 'rect',b['fill']);idx+=1
            for side,br in b.get('borders',{}).items():
                x,y,w,h=b['x'],b['y'],b['w'],b['h'];th=br['w']
                rect={'top':(x,y,w,th),'bottom':(x,y+h-th,w,th),'left':(x,y,th,h),'right':(x+w-th,y,th,h)}[side]
                base_shape(tree,idx,'Rule '+str(idx),*rect,fill=br['color']);idx+=1
        images=list(data['images'])
        for sv in data['svgs']:
            images.append({'src':sv['file'],'x':sv['x'],'y':sv['y'],'w':sv['w'],'h':sv['h'],'alt':sv.get('label','')})
        for im in images:
            path=Path(im['src'])
            if path.suffix.lower() in ('.jpg','.jpeg'):raw=path.read_bytes()
            else:
                buf=BytesIO();Image.open(path).convert('RGB').save(buf,'JPEG',quality=95);raw=buf.getvalue()
            name='wsc_fig_'+hashlib.sha256(raw).hexdigest()[:16]+'.jpg';files['ppt/media/'+name]=raw
            rid='rIdFigure'+str(idx);sub(sr,REL,'Relationship',Id=rid,Type=R+'/image',Target='../media/'+name)
            pic=sub(tree,P,'pic');nv=sub(pic,P,'nvPicPr');sub(nv,P,'cNvPr',id=idx,name='Illustration '+str(idx),descr=im.get('alt',''));roles['pic'].append(idx)
            sub(sub(nv,P,'cNvPicPr'),A,'picLocks',noChangeAspect='1');sub(nv,P,'nvPr')
            bf=sub(pic,P,'blipFill');blip=sub(bf,A,'blip');blip.set(tag(R,'embed'),rid);sub(sub(bf,A,'stretch'),A,'fillRect')
            pr=sub(pic,P,'spPr');xfrm(pr,im['x'],im['y'],im['w'],im['h']);sub(sub(pr,A,'prstGeom',prst='rect'),A,'avLst');idx+=1
        for item in data['texts']:
            role,name=motion_role(item,data['id'])
            if role:roles[role].append(idx)
            idx=text(tree,idx,item,name)
        for r in sr:
            if r.get('Type').endswith('/notesSlide'):
                target=str((Path(part).parent/r.get('Target')).as_posix());target=re.sub(r'slides/\.\./','',target)
                nx=E.fromstring(files[target])
                for sp in nx.findall('.//p:sp',NS):
                    ph=sp.find('p:nvSpPr/p:nvPr/p:ph',NS)
                    if ph is not None and ph.get('type')=='body':
                        old=sp.find('p:txBody',NS)
                        if old is not None:sp.remove(old)
                        tb=sub(sp,P,'txBody');sub(tb,A,'bodyPr');sub(tb,A,'lstStyle');p=sub(tb,A,'p');r=sub(p,A,'r');sub(r,A,'t').text=data['notes']
                files[target]=E.tostring(nx,xml_declaration=True,encoding='UTF-8',standalone=True)
        if animate:add_motion(xml,data['id'],roles,prev_id)
        prev_id=data['id']
        files[part]=E.tostring(xml,xml_declaration=True,encoding='UTF-8',standalone=True)
        files[relname]=E.tostring(sr,xml_declaration=True,encoding='UTF-8',standalone=True)
    # Remove media orphaned by replacement; the source package remains untouched.
    # Remove only media unreferenced by every part, including masters and layouts.
    import posixpath
    referenced=set()
    for relpath, raw in files.items():
        if not relpath.endswith('.rels'): continue
        base=posixpath.dirname(posixpath.dirname(relpath))
        for relation in E.fromstring(raw):
            if relation.get('TargetMode') == 'External': continue
            target=relation.get('Target','')
            resolved=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(base,target))
            referenced.add(resolved)
    for filename in list(files):
        if filename.startswith('ppt/media/') and filename not in referenced: del files[filename]
    with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in files.items():z.writestr(name,raw)



# =============================================================================================
# motion (with --package-source --animate): Morph between slides, then automatic entrance effects
# =============================================================================================
PML, MCN, P159 = ("http://schemas.openxmlformats.org/presentationml/2006/main", "http://schemas.openxmlformats.org/markup-compatibility/2006",
                  "http://schemas.microsoft.com/office/powerpoint/2015/09/main")
STATIC_SLIDES = {"cover", "disclosure"}   # the required opening stays still


def motion_role(item, slide_id):
    """(role, shape name) for one extracted text item. Names starting with !! are what Morph matches across slides."""
    size = max((r.get("size", 0) for r in item.get("runs", [])), default=0)
    words = "".join(r.get("text", "") for r in item.get("runs", [])).strip()
    if item["y"] < 80 and "CONGRESS" in words.upper():
        return None, "!!wsc-header"
    if 100 < item["y"] < 160 and size <= 26 and item.get("runs") and item["runs"][0].get("weight", 400) >= 500 and words[:2].isdigit():
        return None, "!!eyebrow"
    if slide_id == "purpose" and words == "Reproducibility":
        return "big", "!!purpose-reproducibility"
    if item["tag"] in ("H1", "H2"):
        if slide_id == "crisis":
            return None, "!!purpose-reproducibility"      # the big word on Purpose morphs into this title
        return "title", None
    if item["y"] >= 960:
        return "foot", None
    if size >= 64:
        return "big", None
    return None, None


def add_motion(sld, slide_id, roles, prev_id):
    """Morph transition (fade where Morph is unsupported) and, except on the opening slides, one automatic group of
    entrance effects: the title settles from 1.3x (anchored at its lower left), big numbers fade in one after another,
    pictures wipe in from the left, the source line fades in last. One click per slide, as before."""
    ns = {"p": PML}
    for old in sld.findall("p:transition", ns) + sld.findall("p:timing", ns) + sld.findall("{%s}AlternateContent" % MCN):
        sld.remove(old)
    alt = etree.fromstring(
        f'<mc:AlternateContent xmlns:mc="{MCN}" xmlns:p="{PML}"><mc:Choice xmlns:p159="{P159}" Requires="p159">'
        '<p:transition spd="med"><p159:morph option="byObject"/></p:transition></mc:Choice>'
        '<mc:Fallback><p:transition spd="med"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>')
    anchor = sld.find("p:clrMapOvr", ns)
    if anchor is None:
        anchor = sld.find("p:cSld", ns)
    anchor.addnext(alt)
    if slide_id in STATIC_SLIDES or not any(roles.values()):
        return
    effects, n = [], [4]

    def cid():
        n[0] += 1
        return n[0]

    def visible(spid):
        return (f'<p:set><p:cBhvr><p:cTn id="{cid()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
                '<p:to><p:strVal val="visible"/></p:to></p:set>')

    def effect(spid, delay, preset, subtype, body):
        head = f'<p:par><p:cTn id="{cid()}" presetID="{preset}" presetClass="entr" presetSubtype="{subtype}" fill="hold" grpId="0" nodeType="withEffect">'
        effects.append(head + f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{visible(spid)}{body}</p:childTnLst></p:cTn></p:par>')

    def fade(spid, delay, dur):
        effect(spid, delay, 10, 0, f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{cid()}" dur="{dur}"/>'
                                    f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')

    def anim(spid, attr, start, end, dur):
        return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="{cid()}" dur="{dur}" fill="hold"/>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr>'
                f'<p:tavLst><p:tav tm="0"><p:val><p:strVal val="{start}"/></p:val></p:tav>'
                f'<p:tav tm="100000"><p:val><p:strVal val="{end}"/></p:val></p:tav></p:tavLst></p:anim>')

    for spid in roles["title"]:   # zoom in from 1.3x, lower-left edge held
        body = (anim(spid, "ppt_w", "#ppt_w*1.3", "#ppt_w", 700) + anim(spid, "ppt_h", "#ppt_h*1.3", "#ppt_h", 700)
                + anim(spid, "ppt_x", "#ppt_x+#ppt_w*0.15", "#ppt_x", 700) + anim(spid, "ppt_y", "#ppt_y-#ppt_h*0.15", "#ppt_y", 700)
                + f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{cid()}" dur="450"/>'
                  f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')
        effect(spid, 0, 53, 16, body)
    last = 200
    for k, spid in enumerate(roles["big"]):
        last = 250 + k * 110
        fade(spid, last, 450)
    for spid in roles["pic"]:
        effect(spid, 300, 22, 8, f'<p:animEffect transition="in" filter="wipe(left)"><p:cBhvr><p:cTn id="{cid()}" dur="900"/>'
                                  f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')
        last = max(last, 700)
    for spid in roles["foot"]:
        fade(spid, last + 300, 500)
    text_ids = roles["title"] + roles["big"] + roles["foot"]
    timing = (f'<p:timing xmlns:p="{PML}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
              '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
              '<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
              '<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
              + "".join(effects) +
              '</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>'
              '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
              '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
              '</p:childTnLst></p:cTn></p:par></p:tnLst>'
              + ("<p:bldLst>" + "".join(f'<p:bldP spid="{s}" grpId="0"/>' for s in text_ids) + "</p:bldLst>" if text_ids else "")
              + '</p:timing>')
    alt.addnext(etree.fromstring(timing))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package-source", type=Path, help="retain this existing congress PPTX package and rebuild its slide contents")
    ap.add_argument("--template", type=Path, help="optional: open with the official WSC title and disclosure slides")
    ap.add_argument("--extract", type=Path, required=True, help="output folder of extract_slides.js (slides.json)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--media", type=Path, help="JPG cache (default: <out dir>/media)")
    ap.add_argument("--preview-dir", type=Path)
    ap.add_argument("--bg-title", type=Path, help="PNG render of the template's title background (preview only)")
    ap.add_argument("--animate", action="store_true", help="with --package-source: add the subtle motion (Morph between slides, titles settle, numbers fade in, charts wipe)")
    args = ap.parse_args()

    if args.package_source:
        rebuild_existing_package(args.package_source, args.extract, args.out, animate=args.animate)
        print("wrote", args.out)
        return

    extract = json.loads((args.extract / "slides.json").read_text())
    skip = TEMPLATE_IDS if args.template else frozenset()
    for p in fit_report(extract, skip):
        print("FIT", p)
    build_pptx(args.template, extract, args.out, args.media or args.out.parent / "media")
    print("wrote", args.out)
    if args.preview_dir:
        render_preview(extract, args.preview_dir, args.bg_title, skip)
        print("previews in", args.preview_dir)


if __name__ == "__main__":
    main()
