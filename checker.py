
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import List, Tuple, Optional
import os
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import pytesseract
    HAS_OCR = True
except Exception:
    pytesseract = None
    HAS_OCR = False

# v5 rule:
# Safe-zone checks apply ONLY to 9:16 ads.
#
# For 9:16 ads in Stories, Reels, Feed, and Facebook in-stream reels:
# - Top guardrail: 14%
# - Side guardrails: 6% left and 6% right
# - Bottom guardrail: 35%
# - Additional lower-right guardrail from the supplied Meta template:
#   right 21% × bottom 40%
#
# For 1:1 and 4:5 Feed assets:
# - Do not fail safe-zone placement.
# - The app reports format support/review only.
#
# Background imagery can bleed. The 9:16 safe-zone pass/fail is focused on critical
# text/logo/CTA/legal-copy elements.

RULES = {
    "nine_sixteen": {
        "label": "9:16 Meta guardrail",
        "target_ratio_name": "9:16",
        "target_ratio": 9 / 16,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1920,
        "safe": {"top": 0.14, "bottom": 0.35, "left": 0.06, "right": 0.06},
        "extra_guardrail": {"name": "lower-right CTA/UI guardrail", "right": 0.21, "bottom": 0.40},
        "notes": "9:16: keep key text/logos outside top 14%, bottom 35%, side 6%, and lower-right guardrail.",
    },
    "feed_1x1": {
        "label": "Feed 1:1",
        "target_ratio_name": "1:1",
        "target_ratio": 1.0,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1080,
        "notes": "1:1 Feed: safe-zone check disabled per current workflow.",
    },
    "feed_4x5": {
        "label": "Feed 4:5",
        "target_ratio_name": "4:5",
        "target_ratio": 4 / 5,
        "ratio_tolerance": 0.025,
        "min_width": 1080,
        "min_height": 1350,
        "notes": "4:5 Feed: safe-zone check disabled per current workflow.",
    },
}

@dataclass
class TextBox:
    text: str
    box: Tuple[int, int, int, int]
    confidence: float
    outside_safe_zone: bool
    in_extra_guardrail: bool
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
    safe_zone_status: str
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
    ratio = width / height

    # Any explicit 9:16 placement goes to the 9:16 guardrail.
    if any(term in name for term in ["reel", "stor", "story", "9x16", "9_16", "vertical", "instream", "in-stream"]):
        if abs(ratio - (9 / 16)) <= 0.08 or ratio < 0.70:
            return "nine_sixteen"

    if abs(ratio - (9 / 16)) <= 0.04 or ratio < 0.70:
        return "nine_sixteen"
    if abs(ratio - (4 / 5)) <= 0.04:
        return "feed_4x5"
    return "feed_1x1"

def ratio_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    ratio = width / height
    delta = abs(ratio - rule["target_ratio"]) / rule["target_ratio"]
    if delta <= rule["ratio_tolerance"]:
        return "PASS", f"Aspect ratio matches {rule['target_ratio_name']}."
    return "FAIL", f"Aspect ratio is {ratio:.3f}; expected {rule['target_ratio_name']}."

def resolution_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    if width >= rule["min_width"] and height >= rule["min_height"]:
        return "PASS", f"Resolution {width}×{height} meets minimum."
    return "FAIL", f"Resolution {width}×{height} is below {rule['min_width']}×{rule['min_height']}."

def get_9x16_safe_box(width: int, height: int) -> Tuple[int, int, int, int]:
    safe = RULES["nine_sixteen"]["safe"]
    return (
        round(width * safe["left"]),
        round(height * safe["top"]),
        width - round(width * safe["right"]),
        height - round(height * safe["bottom"]),
    )

def get_extra_guardrail_box(width: int, height: int) -> Tuple[int, int, int, int]:
    guard = RULES["nine_sixteen"]["extra_guardrail"]
    x1 = width - round(width * guard["right"])
    y1 = height - round(height * guard["bottom"])
    return (x1, y1, width, height)

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

def is_probable_real_text(text: str, conf: float, w: int, h: int, image_w: int, image_h: int) -> bool:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", text)
    if len(cleaned) < 2:
        return False
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return False
    if conf < 55:
        return False
    if w < max(24, image_w * 0.018) or h < max(16, image_h * 0.008):
        return False
    aspect = w / max(1, h)
    if aspect < 0.15 or aspect > 18:
        return False
    return True

def detect_text_boxes(
    image: Image.Image,
    safe_box: Tuple[int, int, int, int],
    extra_guardrail_box: Tuple[int, int, int, int],
) -> List[TextBox]:
    if not HAS_OCR:
        return []

    gray = ImageOps.autocontrast(image.convert("L"))
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config="--psm 11")
    boxes: List[TextBox] = []
    image_w, image_h = image.size

    for i, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        if not is_probable_real_text(text, conf, w, h, image_w, image_h):
            continue

        box = (x, y, x + w, y + h)
        suggestions = boundary_suggestions(box, safe_box)
        in_extra = intersects(box, extra_guardrail_box)

        if in_extra:
            suggestions.append("move out of lower-right CTA/UI guardrail")

        boxes.append(
            TextBox(
                text=text,
                box=box,
                confidence=conf,
                outside_safe_zone=bool(boundary_suggestions(box, safe_box)),
                in_extra_guardrail=in_extra,
                suggestions=list(dict.fromkeys(suggestions)),
            )
        )

    return boxes

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

def consolidate_suggestions(text_boxes: List[TextBox], placement: str) -> List[str]:
    if placement != "nine_sixteen":
        return ["Safe-zone pass/fail is disabled for 1:1 and 4:5 Feed assets."]

    suggestions = []
    for tb in text_boxes:
        if tb.outside_safe_zone or tb.in_extra_guardrail:
            suggestions.extend(tb.suggestions)

    # De-dupe while preserving order.
    suggestions = list(dict.fromkeys(suggestions))

    if suggestions:
        return suggestions

    return ["Keep key text/logos inside the green 9:16 safe zone and outside the lower-right guardrail."]

def annotate_non_9x16(image: Image.Image, placement: str, status: str, reason: str, suggestions: List[str]) -> Image.Image:
    img = image.convert("RGBA")
    width, height = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    black = (0, 0, 0, 175)
    green = (0, 255, 120, 255)
    amber = (255, 200, 0, 255)
    white = (255, 255, 255, 235)

    panel_h = max(104, height // 15)
    d.rectangle((0, 0, width, panel_h), fill=black)
    status_col = green if status == "PASS" else amber
    d.text(
        (max(12, width // 60), max(8, height // 180)),
        f"{status} · {placement.upper()} · SAFE-ZONE DISABLED",
        font=_font(max(22, width // 34), True),
        fill=status_col,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 180),
    )
    d.text(
        (max(12, width // 60), max(50, height // 40)),
        RULES[placement]["notes"],
        font=_font(max(13, width // 70), False),
        fill=white,
    )

    footer_h = max(88, height // 18)
    d.rectangle((0, height - footer_h, width, height), fill=black)
    sug = "Suggestions: " + "; ".join(suggestions[:3])
    d.multiline_text(
        (max(12, width // 60), height - footer_h + 8),
        wrap_text(sug, 80),
        font=_font(max(13, width // 70), False),
        fill=white,
        spacing=2,
    )
    return Image.alpha_composite(img, overlay).convert("RGB")

def annotate_9x16(
    image: Image.Image,
    status: str,
    reason: str,
    suggestions: List[str],
    text_boxes: List[TextBox],
) -> Image.Image:
    img = image.convert("RGBA")
    width, height = img.size
    safe = get_9x16_safe_box(width, height)
    extra = get_extra_guardrail_box(width, height)
    sx1, sy1, sx2, sy2 = safe

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    red_fill = (225, 0, 0, 56)
    yellow_fill = (255, 185, 0, 58)
    green = (0, 255, 120, 255)
    blue = (50, 160, 255, 255)
    red = (255, 70, 70, 255)
    yellow = (255, 205, 0, 255)
    white = (255, 255, 255, 235)
    black = (0, 0, 0, 175)
    amber = (255, 200, 0, 255)

    zones = [
        (0, 0, width, sy1),          # top 14%
        (0, sy2, width, height),     # bottom 35%
        (0, 0, sx1, height),         # left 6%
        (sx2, 0, width, height),     # right 6%
    ]
    for z in zones:
        d.rectangle(z, fill=red_fill, outline=white, width=max(2, width // 420))

    d.rectangle(extra, fill=yellow_fill, outline=yellow, width=max(2, width // 420))
    ex1, ey1, _, _ = extra
    d.text(
        (ex1 + 8, ey1 + 8),
        "lower-right 21% × bottom 40% guardrail",
        font=_font(max(13, width // 78), True),
        fill=yellow,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 185),
    )

    d.rectangle(safe, outline=green, width=max(5, width // 180))

    for tb in text_boxes:
        if tb.outside_safe_zone:
            col = red
        elif tb.in_extra_guardrail:
            col = yellow
        else:
            col = blue
        d.rectangle(tb.box, outline=col, width=max(2, width // 420))

    panel_h = max(108, height // 15)
    d.rectangle((0, 0, width, panel_h), fill=black)
    status_col = {"PASS": green, "FAIL": red, "REVIEW": amber}.get(status, white)
    d.text(
        (max(12, width // 60), max(8, height // 180)),
        f"{status} · 9:16 · TEXT/LOGO ONLY",
        font=_font(max(22, width // 34), True),
        fill=status_col,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 180),
    )
    d.text(
        (max(12, width // 60), max(50, height // 40)),
        RULES["nine_sixteen"]["notes"],
        font=_font(max(13, width // 70), False),
        fill=white,
    )

    footer_h = max(88, height // 18)
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

    aspect_status, aspect_reason = ratio_status(width, height, placement)
    res_status, res_reason = resolution_status(width, height, placement)

    text_boxes: List[TextBox] = []

    if placement != "nine_sixteen":
        safe_zone_status = "PASS" if aspect_status == "PASS" and res_status == "PASS" else "REVIEW"
        status = "PASS" if aspect_status == "PASS" and res_status == "PASS" else "REVIEW"
        reason = f"{aspect_reason} {res_reason} Safe-zone pass/fail is disabled for this non-9:16 Feed format."
        suggestions = consolidate_suggestions(text_boxes, placement)
        annotated = annotate_non_9x16(image, placement, status, reason, suggestions)
    else:
        safe = get_9x16_safe_box(width, height)
        extra = get_extra_guardrail_box(width, height)
        text_boxes = detect_text_boxes(image, safe, extra)

        if not HAS_OCR:
            safe_zone_status = "REVIEW"
            safe_zone_reason = "OCR is not available, so text/logo containment needs visual review."
        elif not text_boxes:
            safe_zone_status = "REVIEW"
            safe_zone_reason = "No reliable text detected by OCR. Review logo and small copy manually."
        elif any(tb.outside_safe_zone or tb.in_extra_guardrail for tb in text_boxes):
            safe_zone_status = "FAIL"
            count = sum(1 for tb in text_boxes if tb.outside_safe_zone or tb.in_extra_guardrail)
            safe_zone_reason = f"{count} reliable detected text element(s) cross the 9:16 safe-zone or lower-right guardrail."
        else:
            safe_zone_status = "PASS"
            safe_zone_reason = "Reliable detected text appears inside the 9:16 safe-zone guardrail."

        if "FAIL" in [aspect_status, res_status, safe_zone_status]:
            status = "FAIL"
        elif "REVIEW" in [aspect_status, res_status, safe_zone_status]:
            status = "REVIEW"
        else:
            status = "PASS"

        suggestions = consolidate_suggestions(text_boxes, placement)
        if aspect_status == "FAIL":
            suggestions.insert(0, "resize/re-export to 9:16")
        if res_status == "FAIL":
            suggestions.insert(0, "export at a higher resolution")

        reason = f"{aspect_reason} {res_reason} {safe_zone_reason}"
        annotated = annotate_9x16(image, status, reason, suggestions, text_boxes)

    return CreativeResult(
        filename=filename,
        placement=placement,
        rule_label=RULES[placement]["label"],
        status=status,
        width=width,
        height=height,
        aspect_ratio_status=aspect_status,
        resolution_status=res_status,
        safe_zone_status=safe_zone_status,
        reason=reason,
        suggestions=suggestions,
        text_boxes=text_boxes,
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
            "filename,placement,rule,status,width,height,aspect_ratio_status,resolution_status,safe_zone_status,reason,suggestions\n"
        ]
        for r in results:
            safe_reason = r.reason.replace('"', '""')
            safe_suggestions = "; ".join(r.suggestions).replace('"', '""')
            lines.append(
                f'"{r.filename}","{r.placement}","{r.rule_label}","{r.status}",{r.width},{r.height},'
                f'"{r.aspect_ratio_status}","{r.resolution_status}","{r.safe_zone_status}",'
                f'"{safe_reason}","{safe_suggestions}"\n'
            )
        z.writestr("meta_safezone_report.csv", "".join(lines))

        for r in results:
            safe_name = r.filename.replace(" ", "_")
            if "." in safe_name:
                safe_name = safe_name.rsplit(".", 1)[0]
            z.writestr(f"annotated/{safe_name}_annotated.jpg", image_to_bytes(r.annotated_image))

    return bio.getvalue()
