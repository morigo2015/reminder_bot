# pillsbot/tests/unit/test_matcher.py
from pillsbot.core.matcher import Matcher
from pillsbot import config as cfg


def test_matcher_positive_cases():
    # Use the same patterns as production config to keep tests realistic
    m = Matcher(cfg.CONFIRM_PATTERNS)
    for txt in ["Ок", "все ок!", "+", "да", "вже"]:
        assert m.matches_confirmation(txt)


def test_matcher_negative_cases():
    # Narrow pattern to ensure boundaries work as intended
    m = Matcher([r"\bтак\b"])
    assert not m.matches_confirmation("також")  # word boundary prevents false positive
    assert not m.matches_confirmation("random text")
