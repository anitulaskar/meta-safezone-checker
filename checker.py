
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

# 2026-oriented best-practice rules based on vertical-first Meta guidance.
# This app is intentionally conservative for production QA.
RULESETS = {
    "unified_9x16_conservative": {
        "label": "Unified 9:16 Conservative",
        "description": "Best for assets that may run across Reels + Stories. Uses 14% top, 35% bottom, and center 80% horizontal safe zone.",
        "placements": {
            "reels": {
                "label": "Reels / Unified 9:16",
                "target_ratios": [{"name": "9:16", "ratio": 9 / 16, "severity": "FAIL"}],
                "ratio_tolerance": 0.025,
                "min_width": 1080,
                "min_height": 1920,
                "safe": {"top": 0.14, "bottom": 0.35, "left": 0.10, "right": 0.10},
                "notes": "Conservative rule: 14% top, 35% bottom, and middle 80% horizontally."
            },
            "stories": {
                "label": "Stories / Unified 9:16",
                "target_ratios": [{"name": "9:16", "ratio": 9 / 16, "severity": "FAIL"}],
                "ratio_tolerance": 0.025,
                "min_width": 1080,
                "min_height": 1920,
                "safe": {"top": 0.14, "bottom": 0.35, "left": 0.10, "right": 0.10},
                "notes": "Uses unified conservative rule so one asset can survive Stories + Reels."
            },
            "feed": {
                "label": "Feed Image 4:5 Preferred",
                "target_ratios": [
                    {"name": "4:5 preferred", "ratio": 4 / 5, "severity": "PASS"},
                    {"name": "1:1 legacy supported", "ratio": 1.0, "severity": "REVIEW"},
                    {"name": "3:4 supported preview", "ratio": 3 / 4, "severity": "REVIEW"},
                ],
                "ratio_tolerance": 0.025,
                "min_width": 1080,
                "min_height": 1080,
                "preferred_width": 1080,
                "preferred_height": 1350,
                "safe": {"top": 0.10, "bottom": 0.10, "left": 0.10, "right": 0.10},
                "notes": "4:5 is preferred for Feed images; 1:1 may still be supported but is not the recommended default."
            },
        },
    },
    "stories_only_relaxed": {
        "label": "Stories-only Relaxed",
        "description": "Use only when the asset is guaranteed to run in Stories only. Reels/broad placements should use the unified conservative rule.",
        "placements": {
            "stories": {
                "label": "Stories-only 9:16",
                "target_ratios": [{"name": "9:16", "ratio": 9 / 16, "severity": "FAIL"}],
                "ratio_tolerance": 0.025,
                "min_width": 1080,
                "min_height": 1920,
                "safe": {"top": 0.14, "bottom": 0.14, "left": 0.06, "right": 0.06},
                "notes": "Stories-only relaxed rule: 14% top and 14% bottom. Use unified rule for broad placements."
            }
        }
    }
}

STATUS_RANK = {"PASS": 0, "REVIEW": 1, "FAIL": 2}

@dataclass
class TextBox:
    text: str
    box: Tuple[int, int, int, int]
    confidence: float
    outside_safe_zone: bool
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
    if abs(ratio - 1.0) < 0.04 or abs(ratio - 0.8) < 0.04 or abs(ratio - 0.75) < 0.04:
        return "feed"
    if ratio < 0.7:
        return "reels"
    return "feed"

def get_rule(placement: str, ruleset_key: str) -> Dict:
    ruleset = RULESETS[ruleset_key]["placements"]
    if placement in ruleset:
        return ruleset[placement]
    return RULESETS["unified_9x16_conservative"]["placements"][placement]

def get_safe_box(width: int, height: int, placement: str, ruleset_key: str) -> Tuple[int, int, int, int]:
    rule = get_rule(placement, ruleset_key)
    safe = rule["safe"]
    left = round(width * safe["left"])
    top = round(height * safe["top"])
    right = width - round(width * safe["right"])
    bottom = height - round(height * safe["bottom"])
    return left, top, right, bottom

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

def outside(box: Tuple[int, int, int, int], safe: Tuple[int, int, int, int]) -> bool:
    return len(boundary_suggestions(box, safe)) > 0

def ratio_status(width: int, height: int, placement: str, ruleset_key: str) -> Tuple[str, str]:
    rule = get_rule(placement, ruleset_key)
    ratio = width / height
    tolerance = rule["ratio_tolerance"]
    matches = []
    for target in rule["target_ratios"]:
        delta = abs(ratio - target["ratio"]) / target["ratio"]
        if delta <= tolerance:
            matches.append((STATUS_RANK[target["severity"]], target))

    if matches:
        _, best = sorted(matches, key=lambda x: x[0])[0]
        if best["severity"] == "PASS":
            return "PASS", f"Aspect ratio matches recommended {best['name']}."
        return "REVIEW", f"Aspect ratio matches {best['name']}, but current best practice prefers 4:5 Feed or 9:16 vertical depending on placement."

    expected = ", ".join(t["name"] for t in rule["target_ratios"])
    return "FAIL", f"Aspect ratio is {ratio:.3f}; expected {expected}."

def resolution_status(width: int, height: int, placement: str, ruleset_key: str) -> Tuple[str, str]:
    rule = get_rule(placement, ruleset_key)
    if width >= rule["min_width"] and height >= rule["min_height"]:
        if placement == "feed" and rule.get("preferred_width") and (width, height) != (rule["preferred_width"], rule["preferred_height"]):
            return "REVIEW", f"Resolution meets minimum, but preferred Feed export is {rule['preferred_width']}×{rule['preferred_height']} for 4:5."
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

        # Ignore tiny OCR noise.
        if w < 18 or h < 14:
            continue

        box = (x, y, x + w, y + h)
        sugg = boundary_suggestions(box, safe_box)
        boxes.append(TextBox(text=text, box=box, confidence=conf, outside_safe_zone=bool(sugg), suggestions=sugg))

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
    all_suggestions = []
    for tb in text_boxes:
        if tb.outside_safe_zone:
            all_suggestions.extend(tb.suggestions)

    all_suggestions = dedupe_suggestions(all_suggestions)

    if not all_suggestions:
        if placement in ("reels", "stories"):
            return ["Keep headline, logo, CTA, price, and legal copy inside the green zone; allow only photography/background to bleed."]
        return ["For Feed, prefer a 4:5 export and keep headline/logo/CTA away from the outer 10% edges."]

    return all_suggestions

def wrap_text(text: str, width: int = 80) -> str:
    words = text.split()
    lines = []
    line = []
    for w in words:
        if sum(len(x) for x in line) + len(line) + len(w) > width:
            lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))
    return "\n".join(lines)

def annotate(
    image: Image.Image,
    filename: str,
    placement: str,
    ruleset_key: str,
    status: str,
    reason: str,
    suggestions: List[str],
    text_boxes: List[TextBox],
) -> Image.Image:
    img = image.convert("RGBA")
    width, height = img.size
    safe = get_safe_box(width, height, placement, ruleset_key)
    sx1, sy1, sx2, sy2 = safe
    rule = get_rule(placement, ruleset_key)

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
        d.text((sx1 + 8, y0 + 8), "center 1:1 crop guide", font=_font(max(13, width // 78), True), fill=(210,245,255,255), stroke_width=2, stroke_fill=(0,0,0,180))

    for tb in text_boxes:
        col = red if tb.outside_safe_zone else blue
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

def check_creative(file_bytes: bytes, filename: str, placement: Optional[str] = None, ruleset_key: str = "unified_9x16_conservative") -> CreativeResult:
    image = Image.open(BytesIO(file_bytes)).convert("RGB")
    width, height = image.size
    placement = placement or infer_placement(filename, width, height)
    safe = get_safe_box(width, height, placement, ruleset_key)

    aspect_status, aspect_reason = ratio_status(width, height, placement, ruleset_key)
    res_status, res_reason = resolution_status(width, height, placement, ruleset_key)
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

    suggestions = consolidate_suggestions(boxes, placement)
    if aspect_status == "FAIL":
        suggestions.insert(0, "resize/re-export to the recommended placement ratio")
    elif aspect_status == "REVIEW" and placement == "feed":
        suggestions.insert(0, "consider converting Feed image to 4:5, e.g. 1080×1350 or 1440×1800")
    if res_status == "FAIL":
        suggestions.insert(0, "export at a higher resolution")

    reason = " ".join([aspect_reason, res_reason, text_reason])
    annotated = annotate(image, filename, placement, ruleset_key, status, reason, suggestions, boxes)

    return CreativeResult(
        filename=filename,
        placement=placement,
        rule_label=get_rule(placement, ruleset_key)["label"],
        status=status,
        width=width,
        height=height,
        aspect_ratio_status=aspect_status,
        resolution_status=res_status,
        text_logo_status=text_status,
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
            "filename,placement,rule,status,width,height,aspect_ratio_status,resolution_status,text_logo_status,reason,suggestions\n"
        ]
        for r in results:
            safe_reason = r.reason.replace('"', '""')
            safe_suggestions = "; ".join(r.suggestions).replace('"', '""')
            lines.append(
                f'"{r.filename}","{r.placement}","{r.rule_label}","{r.status}",{r.width},{r.height},'
                f'"{r.aspect_ratio_status}","{r.resolution_status}","{r.text_logo_status}","{safe_reason}","{safe_suggestions}"\n'
            )
        z.writestr("meta_safezone_report.csv", "".join(lines))

        for r in results:
            safe_name = r.filename.replace(" ", "_")
            if "." in safe_name:
                safe_name = safe_name.rsplit(".", 1)[0]
            z.writestr(f"annotated/{safe_name}_annotated.jpg", image_to_bytes(r.annotated_image))

    return bio.getvalue()
