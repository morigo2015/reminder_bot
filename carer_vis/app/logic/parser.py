import re

CONFIRM_RE = re.compile(r"(?i)\b(випив|випила|прийняв|прийняла|прийнято|готово|ок|ok|done|taken)\b")
BP_RE = re.compile(r"(?i)^(left|right|ліва|права|ліворуч|праворуч)\s+(\d{2,3})[,|/\-\s]+(\d{2,3})[,|/\-\s]+(\d{2,3})$")

SIDE_MAP = {
    "ліва": "left",
    "ліворуч": "left",
    "права": "right",
    "праворуч": "right",
    "left": "left",
    "right": "right",
}


def is_confirm_text(text: str) -> bool:
    return bool(CONFIRM_RE.search(text))


def parse_bp(text: str):
    m = BP_RE.match(text.strip())
    if not m:
        return None
    side_raw, sys_s, dia_s, pulse_s = m.groups()
    side = SIDE_MAP.get(side_raw.lower())
    if side is None:
        return None
    try:
        sys_v = int(sys_s)
        dia_v = int(dia_s)
        pulse_v = int(pulse_s)
    except ValueError:
        return None
    # Hard limits
    if not (70 <= sys_v <= 260 and 40 <= dia_v <= 160 and 30 <= pulse_v <= 200):
        return (side, sys_v, dia_v, pulse_v, "hard_range_fail")
    return (side, sys_v, dia_v, pulse_v, None)
