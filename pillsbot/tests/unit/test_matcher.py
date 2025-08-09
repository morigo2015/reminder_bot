from pillsbot.core.matcher import Matcher

def test_matcher_positive_cases():
    m = Matcher([r"OK", r"\bтак\b", r"\bвже\b", r"\bда\b", r"\+"])
    for txt in ["Ок", "все ок!", "+", "да", "вже"]:
        assert m.matches_confirmation(txt)

def test_matcher_negative_cases():
    m = Matcher([r"\bтак\b"])
    assert not m.matches_confirmation("також")  # word boundary prevents false positive
    assert not m.matches_confirmation("random text")
