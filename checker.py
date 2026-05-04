
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import List, Tuple, Optional, Dict
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import pytesseract
    HAS_OCR = True
except Exception:
    pytesseract = None
    HAS_OCR = False

# Current production rules:
# - Feed: 1:1 only
# - Reels: 9:16 only
# - Stories: 9:16 only
# - Text/logo/CTA/legal copy must stay inside safe zones.
# - Photography/background may bleed outside safe zones.
#
# Note on Meta CTA/UI overlaps:
# Reels and Stories can show native UI, captions, profile name, CTA buttons, and interaction controls.
# This checker uses a conservative bottom zone so your own text/logo/CTA avoids likely Meta CTA/UI overlap.
RULES = {
    "feed": {
        "label": "Feed 1:1",
        "target_ratio_name": "1:1",
        "target_ratio": 1.0,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1080,
        "safe": {"top": 0.10, "bottom": 0.10, "left": 0.10, "right": 0.10},
        "meta_cta_zone": None,
        "notes": "Feed 1:1: keep text, logo, CTA, and legal copy out of the outer 10% edge zone.",
    },
    "reels": {
        "label": "Reels 9:16",
        "target_ratio_name": "9:16",
        "target_ratio": 9 / 16,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1920,
        # Conservative Reels rule for expected native Meta CTA + caption + controls.
        "safe": {"top": 0.14, "bottom": 0.35, "left": 0.06, "right": 0.06},
        "meta_cta_zone": {"bottom": 0.35},
        "notes": "Reels 9:16: keep critical text/logo/CTA above the bottom 35% to avoid expected Meta CTA/UI overlap.",
    },
    "stories": {
        "label": "Stories 9:16",
        "target_ratio_name": "9:16",
        "target_ratio": 9 / 16,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1920,
        # Stories bottom CTA can vary. We use a slightly conservative bottom zone.
        "safe": {"top": 0.14, "bottom": 0.20, "left": 0.06, "right": 0.06},
        "meta_cta_zone": {"bottom": 0.20},
        "notes": "Stories 9:16: keep critical text/logo/CTA clear of the top 14% and bottom 20% expected Meta CTA/UI area.",
    },
}

STATUS_RANK = {"PASS": 0, "REVIEW": 1, "FAIL": 2}

@dataclass
class TextBox:
    text: str
    box: Tuple[int, int, int, int]
    confidence: float
    outside_safe_zone: bool
    in_meta_cta_zone: bool
    suggestions: List[str]

@dataclass
class CreativeResult:
    filename: str
    placement: str
    rule_label: str
    status: str
    width: int
    height: int
    aspect_ratio_status: str
    resolution_status: str
    text_logo_status: str
    meta_cta_status: str
    reason: str
    suggestions: List[str]
    text_boxes: List[TextBox]
    annotated_image: Image.Image

def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def infer_placement(filename: str, width: int, height: int) -> str:
    name = filename.lower()
    if "reel" in name:
        return "reels"
    if "stor" in name:
        return "stories"
    if "feed" in name:
        return "feed"
    ratio = width / height
    if abs(ratio - 1.0) <= 0.04:
        return "feed"
    if abs(ratio - (9 / 16)) <= 0.04 or ratio < 0.70:
        return "reels"
    return "feed"

def get_safe_box(width: int, height: int, placement: str) -> Tuple[int, int, int, int]:
    safe = RULES[placement]["safe"]
    left = round(width * safe["left"])
    top = round(height * safe["top"])
    right = width - round(width * safe["right"])
    bottom = height - round(height * safe["bottom"])
    return left, top, right, bottom

def get_meta_cta_box(width: int, height: int, placement: str) -> Optional[Tuple[int, int, int, int]]:
    zone = RULES[placement].get("meta_cta_zone")
    if not zone:
        return None
    bottom_pct = zone["bottom"]
    y1 = height - round(height * bottom_pct)
    return (0, y1, width, height)

def intersects(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1

def boundary_suggestions(box: Tuple[int, int, int, int], safe: Tuple[int, int, int, int]) -> List[str]:
    x1, y1, x2, y2 = box
    sx1, sy1, sx2, sy2 = safe
    suggestions = []
    buffer = 12
    if x1 < sx1:
        suggestions.append(f"move right at least {sx1 - x1 + buffer}px")
    if x2 > sx2:
        suggestions.append(f"move left at least {x2 - sx2 + buffer}px")
    if y1 < sy1:
        suggestions.append(f"move down at least {sy1 - y1 + buffer}px")
    if y2 > sy2:
        suggestions.append(f"move up at least {y2 - sy2 + buffer}px")
    return suggestions

def ratio_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    ratio = width / height
    delta = abs(ratio - rule["target_ratio"]) / rule["target_ratio"]
    if delta <= rule["ratio_tolerance"]:
        return "PASS", f"Aspect ratio matches required {rule['target_ratio_name']}."
    return "FAIL", f"Aspect ratio is {ratio:.3f}; expected {rule['target_ratio_name']}."

def resolution_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    if width >= rule["min_width"] and height >= rule["min_height"]:
        return "PASS", f"Resolution {width}×{height} meets minimum."
    return "FAIL", f"Resolution {width}×{height} is below {rule['min_width']}×{rule['min_height']}."

def detect_text_boxes(
    image: Image.Image,
    safe_box: Tuple[int, int, int, int],
    meta_cta_box: Optional[Tuple[int, int, int, int]],
) -> List[TextBox]:
    if not HAS_OCR:
        return []

    gray = ImageOps.autocontrast(image.convert("L"))
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config="--psm 11")
    boxes: List[TextBox] = []

    for i, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1
        if conf < 30:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        # Ignore tiny OCR noise.
        if w < 18 or h < 14:
            continue

        box = (x, y, x + w, y + h)
        suggestions = boundary_suggestions(box, safe_box)
        in_cta = bool(meta_cta_box and intersects(box, meta_cta_box))
        if in_cta and not any("move up" in s for s in suggestions):
            # If text is inside a separate CTA warning area, add a movement recommendation.
            suggestions.append("move up to avoid expected Meta CTA/UI overlap")

        boxes.append(
            TextBox(
                text=text,
                box=box,
                confidence=conf,
                outside_safe_zone=bool(boundary_suggestions(box, safe_box)),
                in_meta_cta_zone=in_cta,
                suggestions=suggestions,
            )
        )

    return boxes

def dedupe_suggestions(suggestions: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in suggestions:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out

def consolidate_suggestions(text_boxes: List[TextBox], placement: str) -> List[str]:
    all_suggestions: List[str] = []
    for tb in text_boxes:
        if tb.outside_safe_zone or tb.in_meta_cta_zone:
            all_suggestions.extend(tb.suggestions)

    all_suggestions = dedupe_suggestions(all_suggestions)

    if all_suggestions:
        return all_suggestions

    if placement == "feed":
        return ["Keep headline, logo, CTA, and legal copy inside the green 1:1 Feed safe zone."]
    if placement == "reels":
        return ["Keep all text/logo/CTA above the bottom 35% expected Meta CTA/UI overlap area."]
    return ["Keep all text/logo/CTA above the bottom 20% expected Meta CTA/UI overlap area."]

def wrap_text(text: str, width: int = 80) -> str:
    words = text.split()
    lines = []
    line = []
    for word in words:
        if sum(len(x) for x in line) + len(line) + len(word) > width:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return "\n".join(lines)

def annotate(
    image: Image.Image,
    filename: str,
    placement: str,
    status: str,
    reason: str,
    suggestions: List[str],
    text_boxes: List[TextBox],
) -> Image.Image:
    img = image.convert("RGBA")
    width, height = img.size
    safe = get_safe_box(width, height, placement)
    meta_cta = get_meta_cta_box(width, height, placement)
    sx1, sy1, sx2, sy2 = safe
    rule = RULES[placement]

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    red_fill = (225, 0, 0, 62)
    cta_fill = (255, 145, 0, 58)
    green = (0, 255, 120, 255)
    blue = (50, 160, 255, 255)
    red = (255, 70, 70, 255)
    orange = (255, 170, 0, 255)
    white = (255, 255, 255, 235)
    black = (0, 0, 0, 175)
    amber = (255, 200, 0, 255)

    # Unsafe zones for text/logo.
    zones = [
        (0, 0, width, sy1),
        (0, sy2, width, height),
        (0, 0, sx1, height),
        (sx2, 0, width, height),
    ]
    for z in zones:
        d.rectangle(z, fill=red_fill, outline=white, width=max(2, width // 420))

    # Extra callout for expected Meta CTA area.
    if meta_cta:
        d.rectangle(meta_cta, fill=cta_fill, outline=orange, width=max(2, width // 380))
        mx1, my1, _, _ = meta_cta
        d.text(
            (max(12, width // 60), my1 + 10),
            "expected Meta CTA / UI overlap area",
            font=_font(max(13, width // 72), True),
            fill=orange,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 180),
        )

    d.rectangle(safe, outline=green, width=max(5, width // 180))

    if placement in ("reels", "stories"):
        sq = min(width, height)
        y0 = (height - sq) // 2
        d.rectangle((0, y0, width, y0 + sq), outline=(60, 180, 255, 230), width=max(2, width // 320))

    # OCR boxes:
    # Blue = detected text safely inside.
    # Red = text crosses safe zone.
    # Orange = text intersects expected Meta CTA/UI zone.
    for tb in text_boxes:
        if tb.outside_safe_zone:
            col = red
        elif tb.in_meta_cta_zone:
            col = orange
        else:
            col = blue
        d.rectangle(tb.box, outline=col, width=max(2, width // 420))

    panel_h = max(104, height // 15)
    d.rectangle((0, 0, width, panel_h), fill=black)
    status_col = {"PASS": green, "FAIL": red, "REVIEW": amber}.get(status, white)
    d.text(
        (max(12, width // 60), max(8, height // 180)),
        f"{status} · {placement.upper()} · TEXT/LOGO ONLY",
        font=_font(max(22, width // 34), True),
        fill=status_col,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 180),
    )
    d.text(
        (max(12, width // 60), max(48, height // 40)),
        rule["notes"],
        font=_font(max(13, width // 70), False),
        fill=white,
    )

    footer_h = max(96, height // 17)
    d.rectangle((0, height - footer_h, width, height), fill=black)
    sug = "Suggestions: " + "; ".join(suggestions[:4])
    d.multiline_text(
        (max(12, width // 60), height - footer_h + 8),
        wrap_text(sug, 80),
        font=_font(max(13, width // 70), False),
        fill=white,
        spacing=2,
    )

    return Image.alpha_composite(img, overlay).convert("RGB")

def check_creative(file_bytes: bytes, filename: str, placement: Optional[str] = None) -> CreativeResult:
    image = Image.open(BytesIO(file_bytes)).convert("RGB")
    width, height = image.size
    placement = placement or infer_placement(filename, width, height)
    safe = get_safe_box(width, height, placement)
    meta_cta = get_meta_cta_box(width, height, placement)

    aspect_status, aspect_reason = ratio_status(width, height, placement)
    res_status, res_reason = resolution_status(width, height, placement)
    boxes = detect_text_boxes(image, safe, meta_cta)

    if not HAS_OCR:
        text_status = "REVIEW"
        text_reason = "OCR is not available, so text/logo containment needs visual review."
    elif not boxes:
        text_status = "REVIEW"
        text_reason = "No text detected by OCR. Review logo and small copy manually."
    elif any(tb.outside_safe_zone for tb in boxes):
        text_status = "FAIL"
        count = sum(1 for tb in boxes if tb.outside_safe_zone)
        text_reason = f"{count} detected text element(s) cross the safe-zone boundary."
    else:
        text_status = "PASS"
        text_reason = "Detected text appears inside the safe-zone boundary."

    if not HAS_OCR:
        meta_cta_status = "REVIEW"
        meta_cta_reason = "Expected Meta CTA/UI overlap needs visual review."
    elif any(tb.in_meta_cta_zone for tb in boxes):
        meta_cta_status = "FAIL"
        count = sum(1 for tb in boxes if tb.in_meta_cta_zone)
        meta_cta_reason = f"{count} detected text element(s) intersect the expected Meta CTA/UI overlap area."
    else:
        meta_cta_status = "PASS"
        meta_cta_reason = "Detected text is clear of the expected Meta CTA/UI overlap area."

    statuses = [aspect_status, res_status, text_status, meta_cta_status]
    if "FAIL" in statuses:
        status = "FAIL"
    elif "REVIEW" in statuses:
        status = "REVIEW"
    else:
        status = "PASS"

    suggestions = consolidate_suggestions(boxes, placement)
    if aspect_status == "FAIL":
        suggestions.insert(0, f"resize/re-export to {RULES[placement]['target_ratio_name']}")
    if res_status == "FAIL":
        suggestions.insert(0, "export at a higher resolution")

    reason = " ".join([aspect_reason, res_reason, text_reason, meta_cta_reason])
    annotated = annotate(image, filename, placement, status, reason, suggestions, boxes)

    return CreativeResult(
        filename=filename,
        placement=placement,
        rule_label=RULES[placement]["label"],
        status=status,
        width=width,
        height=height,
        aspect_ratio_status=aspect_status,
        resolution_status=res_status,
        text_logo_status=text_status,
        meta_cta_status=meta_cta_status,
        reason=reason,
        suggestions=suggestions,
        text_boxes=boxes,
        annotated_image=annotated,
    )

def image_to_bytes(image: Image.Image, fmt: str = "JPEG") -> bytes:
    bio = BytesIO()
    image.save(bio, format=fmt, quality=92)
    return bio.getvalue()

def make_zip(results: List[CreativeResult]) -> bytes:
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        lines = [
            "filename,placement,rule,status,width,height,aspect_ratio_status,resolution_status,text_logo_status,meta_cta_status,reason,suggestions\n"
        ]
        for r in results:
            safe_reason = r.reason.replace('"', '""')
            safe_suggestions = "; ".join(r.suggestions).replace('"', '""')
            lines.append(
                f'"{r.filename}","{r.placement}","{r.rule_label}","{r.status}",{r.width},{r.height},'
                f'"{r.aspect_ratio_status}","{r.resolution_status}","{r.text_logo_status}","{r.meta_cta_status}",'
                f'"{safe_reason}","{safe_suggestions}"\n'
            )
        z.writestr("meta_safezone_report.csv", "".join(lines))

        for r in results:
            safe_name = r.filename.replace(" ", "_")
            if "." in safe_name:
                safe_name = safe_name.rsplit(".", 1)[0]
            z.writestr(f"annotated/{safe_name}_annotated.jpg", image_to_bytes(r.annotated_image))

    return bio.getvalue()
