from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import List, Tuple, Optional
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import pytesseract
    HAS_OCR = True
except Exception:
    pytesseract = None
    HAS_OCR = False

RULES = {
    "feed": {
        "label": "Feed 1:1",
        "ratio": 1.0,
        "ratio_name": "1:1",
        "ratio_tolerance": 0.02,
        "min_width": 1080,
        "min_height": 1080,
        "safe": {"top": 0.10, "bottom": 0.10, "left": 0.10, "right": 0.10},
    },
    "reels": {
        "label": "Reels 9:16",
        "ratio": 9 / 16,
        "ratio_name": "9:16",
        "ratio_tolerance": 0.02,
        "min_width": 1080,
        "min_height": 1920,
        "safe": {"top": 0.14, "bottom": 0.35, "left": 0.06, "right": 0.06},
    },
    "stories": {
        "label": "Stories 9:16",
        "ratio": 9 / 16,
        "ratio_name": "9:16",
        "ratio_tolerance": 0.02,
        "min_width": 1080,
        "min_height": 1920,
        "safe": {"top": 0.14, "bottom": 0.20, "left": 0.06, "right": 0.06},
    },
}

@dataclass
class TextBox:
    text: str
    box: Tuple[int, int, int, int]
    confidence: float
    outside_safe_zone: bool

@dataclass
class CreativeResult:
    filename: str
    placement: str
    status: str
    width: int
    height: int
    aspect_ratio_status: str
    resolution_status: str
    text_logo_status: str
    reason: str
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
    if "feed" in name or width == height:
        return "feed"
    if width / height < 0.7:
        return "reels"
    return "feed"

def get_safe_box(width: int, height: int, placement: str) -> Tuple[int, int, int, int]:
    safe = RULES[placement]["safe"]
    left = round(width * safe["left"])
    top = round(height * safe["top"])
    right = width - round(width * safe["right"])
    bottom = height - round(height * safe["bottom"])
    return left, top, right, bottom

def outside(box: Tuple[int, int, int, int], safe: Tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    sx1, sy1, sx2, sy2 = safe
    return x1 < sx1 or y1 < sy1 or x2 > sx2 or y2 > sy2

def ratio_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    ratio = width / height
    delta = abs(ratio - rule["ratio"]) / rule["ratio"]
    if delta <= rule["ratio_tolerance"]:
        return "PASS", f"Aspect ratio matches {rule['ratio_name']}."
    return "FAIL", f"Aspect ratio is {ratio:.3f}; expected {rule['ratio_name']}."

def resolution_status(width: int, height: int, placement: str) -> Tuple[str, str]:
    rule = RULES[placement]
    if width >= rule["min_width"] and height >= rule["min_height"]:
        return "PASS", f"Resolution {width}×{height} meets minimum."
    return "FAIL", f"Resolution {width}×{height} is below {rule['min_width']}×{rule['min_height']}."

def detect_text_boxes(image: Image.Image, safe_box: Tuple[int, int, int, int]) -> List[TextBox]:
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

        if w < 18 or h < 14:
            continue

        box = (x, y, x + w, y + h)
        boxes.append(TextBox(text=text, box=box, confidence=conf, outside_safe_zone=outside(box, safe_box)))

    return boxes

def annotate(
    image: Image.Image,
    filename: str,
    placement: str,
    status: str,
    reason: str,
    text_boxes: List[TextBox],
) -> Image.Image:
    img = image.convert("RGBA")
    width, height = img.size
    safe = get_safe_box(width, height, placement)
    sx1, sy1, sx2, sy2 = safe

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    red_fill = (225, 0, 0, 70)
    green = (0, 255, 120, 255)
    blue = (50, 160, 255, 255)
    red = (255, 70, 70, 255)
    white = (255, 255, 255, 235)
    black = (0, 0, 0, 175)
    amber = (255, 200, 0, 255)

    zones = [
        (0, 0, width, sy1),
        (0, sy2, width, height),
        (0, 0, sx1, height),
        (sx2, 0, width, height),
    ]
    for z in zones:
        d.rectangle(z, fill=red_fill, outline=white, width=max(2, width // 420))

    d.rectangle(safe, outline=green, width=max(5, width // 180))

    if placement in ("reels", "stories"):
        sq = min(width, height)
        y0 = (height - sq) // 2
        d.rectangle((0, y0, width, y0 + sq), outline=(60, 180, 255, 230), width=max(2, width // 320))

    for tb in text_boxes:
        col = red if tb.outside_safe_zone else blue
        d.rectangle(tb.box, outline=col, width=max(2, width // 420))

    panel_h = max(92, height // 16)
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
        "Photo/background bleed is acceptable; text/logo must stay inside green safe zone.",
        font=_font(max(13, width // 70), False),
        fill=white,
    )

    footer_h = max(74, height // 21)
    d.rectangle((0, height - footer_h, width, height), fill=black)
    d.multiline_text(
        (max(12, width // 60), height - footer_h + 8),
        reason[:240],
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

    aspect_status, aspect_reason = ratio_status(width, height, placement)
    res_status, res_reason = resolution_status(width, height, placement)
    boxes = detect_text_boxes(image, safe)

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

    statuses = [aspect_status, res_status, text_status]
    if "FAIL" in statuses:
        status = "FAIL"
    elif "REVIEW" in statuses:
        status = "REVIEW"
    else:
        status = "PASS"

    reason = " ".join([aspect_reason, res_reason, text_reason])
    annotated = annotate(image, filename, placement, status, reason, boxes)

    return CreativeResult(
        filename=filename,
        placement=placement,
        status=status,
        width=width,
        height=height,
        aspect_ratio_status=aspect_status,
        resolution_status=res_status,
        text_logo_status=text_status,
        reason=reason,
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
            "filename,placement,status,width,height,aspect_ratio_status,resolution_status,text_logo_status,reason\n"
        ]
        for r in results:
            safe_reason = r.reason.replace('"', '""')
            lines.append(
                f'"{r.filename}","{r.placement}","{r.status}",{r.width},{r.height},'
                f'"{r.aspect_ratio_status}","{r.resolution_status}","{r.text_logo_status}","{safe_reason}"\n'
            )
        z.writestr("meta_safezone_report.csv", "".join(lines))

        for r in results:
            safe_name = r.filename.replace(" ", "_")
            if "." in safe_name:
                safe_name = safe_name.rsplit(".", 1)[0]
            z.writestr(f"annotated/{safe_name}_annotated.jpg", image_to_bytes(r.annotated_image))

    return bio.getvalue()
