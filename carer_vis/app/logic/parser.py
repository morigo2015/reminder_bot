import re

BP_RE = re.compile(
    r"(?i)^(мама|надя|надія|папа|сергій|сергей)\s+(\d{2,3})[,|/\-\s]+(\d{2,3})[,|/\-\s]+(\d{2,3})$"
)

SIDE_MAP = {
    "мама": "мама",
    "надя": "мама",
    "надія": "мама",
    "папа": "папа",
    "сергій": "папа",
    "сергей": "папа",
}


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
    # Accept any positive integers
    if sys_v <= 0 or dia_v <= 0 or pulse_v <= 0:
        return None
    return (side, sys_v, dia_v, pulse_v, None)
