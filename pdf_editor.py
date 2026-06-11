"""
PDF editing utilities.
Strategy:
 1. Locate original spans via rawdict (gives exact per-character baseline origins).
 2. Redact with add_redact_annot (no fill) + apply_redactions(images=PDF_REDACT_IMAGE_NONE).
    → removes original text without white box, preserves background, keeps file size small.
 3. Re-insert replacement text at the exact baseline coordinates.
    Date is reconstructed in three parts to preserve the superscript ordinal suffix.
"""
import fitz
import os
import tempfile
from datetime import datetime
from config import TEMPLATE_PDF, OUTPUT_DIR, TEMPLATE_CLIENT_NAME, TEMPLATE_PRICE


# ── date helpers ──────────────────────────────────────────────────────────────

def _ordinal_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "TH"
    return {1: "ST", 2: "ND", 3: "RD"}.get(day % 10, "TH")


def format_proposal_date(dt: datetime | None = None) -> dict:
    """Return date components matching the template's three-span layout."""
    dt = dt or datetime.now()
    return {
        "day_str":    f"{dt.day:02d}",
        "suffix":     _ordinal_suffix(dt.day),
        "month_year": dt.strftime("%B %Y"),
    }


def _int_to_rgb(color_int: int) -> tuple:
    return (
        ((color_int >> 16) & 0xFF) / 255,
        ((color_int >> 8) & 0xFF) / 255,
        (color_int & 0xFF) / 255,
    )


# ── font extraction ───────────────────────────────────────────────────────────

def _format_price(price_str: str) -> str:
    """Turn "2400" or "3,600" into "2,400AED/Yearly"."""
    clean = price_str.replace(",", "").strip()
    try:
        return f"{int(clean):,}AED/Yearly"
    except ValueError:
        return f"{price_str}AED/Yearly"


def _extract_poppins(doc: fitz.Document) -> tuple[fitz.Font | None, str | None]:
    """
    Extract the WinAnsiEncoding Poppins-Medium font from the PDF.
    Returns (fitz.Font object, temp_file_path).
    Caller must delete the temp file.
    """
    for xref, ext, ftype, basename, name, enc in doc.get_page_fonts(0):
        if "Poppins" in basename and enc == "WinAnsiEncoding":
            try:
                _, _, _, font_bytes = doc.extract_font(xref)
                if font_bytes:
                    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
                    tmp.write(font_bytes)
                    tmp.close()
                    font_obj = fitz.Font(fontbuffer=font_bytes)
                    return font_obj, tmp.name
            except Exception:
                pass
    return None, None


def _extract_poppins_regular(doc: fitz.Document) -> tuple[fitz.Font | None, str | None]:
    """Extract the WinAnsiEncoding Poppins-Regular font from the PDF."""
    for xref, ext, ftype, basename, name, enc in doc.get_page_fonts(2):
        if "Poppins-Regular" in basename and enc == "WinAnsiEncoding":
            try:
                _, _, _, font_bytes = doc.extract_font(xref)
                if font_bytes:
                    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
                    tmp.write(font_bytes)
                    tmp.close()
                    return fitz.Font(fontbuffer=font_bytes), tmp.name
            except Exception:
                pass
    return None, None


# ── raw span analysis ─────────────────────────────────────────────────────────

def _find_rawspans(page: fitz.Page, search_text: str) -> list[dict]:
    """Find spans containing search_text, with per-char origin data from rawdict."""
    result = []
    for block in page.get_text("rawdict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = "".join(c.get("c", "") for c in span["chars"])
                if search_text in text:
                    result.append(span)
    return result


def _span_origin(span: dict) -> fitz.Point:
    """Baseline origin of the first character of a span."""
    ox, oy = span["chars"][0]["origin"]
    return fitz.Point(ox, oy)


def _combined_bbox(spans: list[dict]) -> fitz.Rect:
    rect = fitz.Rect(spans[0]["bbox"])
    for s in spans[1:]:
        rect |= fitz.Rect(s["bbox"])
    return rect


# ── replacement builders ──────────────────────────────────────────────────────

def _build_name_edit(page: fitz.Page, new_name: str, font_obj: fitz.Font | None = None) -> dict:
    name_spans = _find_rawspans(page, TEMPLATE_CLIENT_NAME)
    if not name_spans:
        rects = page.search_for(TEMPLATE_CLIENT_NAME)
        if not rects:
            raise ValueError(f"Could not find '{TEMPLATE_CLIENT_NAME}' on page 1")
        return {
            "redact_rects": [rects[0]],
            "inserts": [{"origin": fitz.Point(rects[0].x0, rects[0].y1 - 2),
                         "text": new_name.upper(), "fontsize": 26.0,
                         "color": _int_to_rgb(0x806000)}],
        }

    name_span = name_spans[0]
    name_bbox  = name_span["bbox"]
    baseline_y = _span_origin(name_span).y
    name_size  = name_span["size"]
    name_color = _int_to_rgb(name_span["color"])

    # Find the "M/S" span on the same baseline
    ms_spans = [s for s in _find_rawspans(page, "M/S")
                if abs(_span_origin(s).y - baseline_y) < 2]

    if ms_spans and font_obj:
        ms_span  = ms_spans[0]
        ms_bbox  = ms_span["bbox"]
        ms_size  = ms_span["size"]
        ms_color = _int_to_rgb(ms_span["color"])

        # Original group center (M/S + WECARE CLINIC combined)
        group_x0    = min(ms_bbox[0], name_bbox[0])
        group_x1    = max(ms_bbox[2], name_bbox[2])
        group_cx    = (group_x0 + group_x1) / 2

        # Measure new group: "M/S " at ms_size  +  new_name at name_size
        ms_w      = font_obj.text_length("M/S ", fontsize=ms_size)
        name_upper = new_name.upper()
        name_w    = font_obj.text_length(name_upper, fontsize=name_size)
        total_w   = ms_w + name_w

        # Available width = page width minus symmetric margins
        available_w = page.rect.width - 2 * 36  # 36pt ≈ 0.5 inch margin

        pad         = 4
        line_height = name_size * 1.4

        if total_w <= available_w:
            # ── Single line ──────────────────────────────────────────────────
            new_ms_x   = group_cx - total_w / 2
            new_name_x = new_ms_x + ms_w
            redact_rect = fitz.Rect(
                min(group_x0, new_ms_x) - pad,   ms_bbox[1],
                max(group_x1, new_name_x + name_w) + pad, name_bbox[3],
            )
            return {
                "redact_rects": [redact_rect],
                "inserts": [
                    {"origin": fitz.Point(new_ms_x,   baseline_y), "text": "M/S ",
                     "fontsize": ms_size,  "color": ms_color, "bold": True},
                    {"origin": fitz.Point(new_name_x, baseline_y), "text": name_upper,
                     "fontsize": name_size, "color": name_color},
                ],
            }

        # ── Multi-line: wrap at word boundaries ──────────────────────────────
        words = name_upper.split()
        line1_words: list[str] = []
        split_idx = len(words)

        for i, word in enumerate(words):
            test_w = font_obj.text_length(" ".join(line1_words + [word]), fontsize=name_size)
            if ms_w + test_w <= available_w:
                line1_words.append(word)
            else:
                split_idx = i
                break

        line1 = " ".join(line1_words)
        line2 = " ".join(words[split_idx:])

        # Center line 1 (M/S + line1)
        l1_name_w = font_obj.text_length(line1, fontsize=name_size)
        l1_total  = ms_w + l1_name_w
        l1_ms_x   = group_cx - l1_total / 2
        l1_name_x = l1_ms_x + ms_w

        # Center line 2 (name continuation only)
        l2_w = font_obj.text_length(line2, fontsize=name_size)
        l2_x = group_cx - l2_w / 2

        redact_rect = fitz.Rect(
            min(group_x0, l1_ms_x, l2_x) - pad,   ms_bbox[1],
            max(group_x1, l1_name_x + l1_name_w, l2_x + l2_w) + pad,
            name_bbox[3] + line_height,
        )

        inserts = [
            {"origin": fitz.Point(l1_ms_x,  baseline_y),             "text": "M/S ",
             "fontsize": ms_size,  "color": ms_color, "bold": True},
            {"origin": fitz.Point(l1_name_x, baseline_y),            "text": line1,
             "fontsize": name_size, "color": name_color},
        ]
        if line2:
            inserts.append(
                {"origin": fitz.Point(l2_x, baseline_y + line_height), "text": line2,
                 "fontsize": name_size, "color": name_color}
            )
        return {"redact_rects": [redact_rect], "inserts": inserts}

    # Fallback: no M/S found — just keep name at its original x
    return {
        "redact_rects": [fitz.Rect(name_bbox)],
        "inserts": [{"origin": fitz.Point(name_bbox[0], baseline_y),
                     "text": new_name.upper(), "fontsize": name_size,
                     "color": name_color}],
    }


def _build_date_edit(page: fitz.Page, date: dict, font_obj: fitz.Font | None) -> dict | None:
    """
    Reconstruct 'On DD<sup>TH</sup> Month YYYY' using correct baseline origins.
    date = {"day_str": "10", "suffix": "TH", "month_year": "June 2026"}
    """
    month_names = ("January","February","March","April","May","June",
                   "July","August","September","October","November","December")

    # Collect all date-related spans
    date_spans: list[dict] = []
    for frag in [f"On {d}" for d in ("0","1","2","3")] + list(month_names):
        date_spans.extend(_find_rawspans(page, frag))
    for frag in ("TH", "ST", "ND", "RD"):
        for s in _find_rawspans(page, frag):
            if s["size"] < 12:
                date_spans.append(s)

    # Deduplicate
    seen: set = set()
    unique = []
    for s in date_spans:
        key = tuple(round(x, 1) for x in s["bbox"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    if not unique:
        return None

    # Collect per-span info
    main_spans   = [s for s in unique if s["size"] > 10]   # "On DD" and "Month YYYY"
    suffix_spans = [s for s in unique if s["size"] <= 10]  # "TH"/"ST" superscript

    if not main_spans:
        return None

    # Main baseline (shared by "On DD" and "Month YYYY")
    main_origin = _span_origin(main_spans[0])
    main_size   = main_spans[0]["size"]
    main_color  = _int_to_rgb(main_spans[0]["color"])

    # Superscript baseline (higher on the page = smaller y)
    if suffix_spans:
        sup_origin = _span_origin(suffix_spans[0])
        sup_size   = suffix_spans[0]["size"]
    else:
        # fallback: raise by ~1/3 of main font size
        sup_origin = fitz.Point(main_origin.x, main_origin.y - main_size / 3)
        sup_size   = main_size * 0.55

    # Calculate x positions using font metrics
    on_day_text = f"On {date['day_str']}"
    if font_obj:
        on_day_w  = font_obj.text_length(on_day_text, fontsize=main_size)
        suffix_w  = font_obj.text_length(date["suffix"], fontsize=sup_size)
    else:
        # rough fallback: 0.55 * fontsize per char
        on_day_w = len(on_day_text) * main_size * 0.55
        suffix_w = len(date["suffix"]) * sup_size * 0.55

    x0 = main_origin.x
    suffix_x = x0 + on_day_w
    month_x  = suffix_x + suffix_w

    inserts = [
        {"origin": fitz.Point(x0,      main_origin.y),  "text": on_day_text,        "fontsize": main_size, "color": main_color},
        {"origin": fitz.Point(suffix_x, sup_origin.y),  "text": date["suffix"],     "fontsize": sup_size,  "color": main_color},
        {"origin": fitz.Point(month_x,  main_origin.y), "text": f" {date['month_year']}", "fontsize": main_size, "color": main_color},
    ]

    return {
        "redact_rects": [fitz.Rect(s["bbox"]) for s in unique],
        "inserts": inserts,
    }


def _build_price_edit(page: fitz.Page, new_price: str) -> dict | None:
    """Find the price span on page 3 and replace it."""
    spans = _find_rawspans(page, TEMPLATE_PRICE)
    if not spans:
        rects = page.search_for(TEMPLATE_PRICE)
        if not rects:
            return None
        return {
            "redact_rects": [rects[0]],
            "inserts": [{"origin": fitz.Point(rects[0].x0, rects[0].y1 - 2),
                         "text": new_price, "fontsize": 12.0,
                         "color": (0, 0, 0), "bold": False}],
        }

    span = spans[0]
    origin = _span_origin(span)
    return {
        "redact_rects": [fitz.Rect(span["bbox"])],
        "inserts": [{"origin": origin, "text": new_price,
                     "fontsize": span["size"], "color": _int_to_rgb(span["color"]),
                     "bold": False}],
    }


# ── public API ────────────────────────────────────────────────────────────────

def update_proposal(client_name: str, price: str | None = None, output_filename: str | None = None) -> str:
    """
    Open the template PDF, replace client name and date on page 1,
    optionally replace price on page 3, save to output/.
    Returns the absolute path to the generated PDF.
    """
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_PDF)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not output_filename:
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in client_name)
        today = datetime.now().strftime("%Y%m%d")
        output_filename = f"Proposal_{safe}_{today}.pdf"

    output_path = os.path.join(OUTPUT_DIR, output_filename)

    doc = fitz.open(template_path)
    font_obj, font_file = _extract_poppins(doc)
    reg_font_obj, reg_font_file = _extract_poppins_regular(doc)

    try:
        page = doc[0]
        date = format_proposal_date()

        name_edit = _build_name_edit(page, client_name, font_obj)
        date_edit = _build_date_edit(page, date, font_obj)

        edits = [name_edit]
        if date_edit:
            edits.append(date_edit)

        # Page 3 price edit
        price_edit = None
        if price:
            formatted_price = _format_price(price)
            price_edit = _build_price_edit(doc[2], formatted_price)

        # Step 1: redact page 1 spans
        for edit in edits:
            for rect in edit["redact_rects"]:
                page.add_redact_annot(rect)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # Step 2: re-insert page 1 text
        font_kwargs: dict = {"fontfile": font_file} if font_file else {"fontname": "helv"}
        for edit in edits:
            for ins in edit["inserts"]:
                extra: dict = {}
                if ins.get("bold"):
                    extra = {"render_mode": 2, "border_width": 0.4}
                page.insert_text(
                    ins["origin"],
                    ins["text"],
                    fontsize=ins["fontsize"],
                    color=ins["color"],
                    **font_kwargs,
                    **extra,
                )

        # Step 3: redact + re-insert page 3 price
        if price_edit:
            page3 = doc[2]
            for rect in price_edit["redact_rects"]:
                page3.add_redact_annot(rect)
            page3.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            reg_kwargs: dict = {"fontfile": reg_font_file} if reg_font_file else {"fontname": "helv"}
            for ins in price_edit["inserts"]:
                page3.insert_text(
                    ins["origin"],
                    ins["text"],
                    fontsize=ins["fontsize"],
                    color=ins["color"],
                    **reg_kwargs,
                )

        doc.save(output_path, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
        if font_file and os.path.exists(font_file):
            os.unlink(font_file)
        if reg_font_file and os.path.exists(reg_font_file):
            os.unlink(reg_font_file)

    return os.path.abspath(output_path)
