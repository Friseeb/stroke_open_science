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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", type=Path, help="optional: open with the official WSC title and disclosure slides")
    ap.add_argument("--extract", type=Path, required=True, help="output folder of extract_slides.js (slides.json)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--media", type=Path, help="JPG cache (default: <out dir>/media)")
    ap.add_argument("--preview-dir", type=Path)
    ap.add_argument("--bg-title", type=Path, help="PNG render of the template's title background (preview only)")
    args = ap.parse_args()

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
