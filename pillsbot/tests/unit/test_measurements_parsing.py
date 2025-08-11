# pillsbot/tests/unit/test_measurements_parsing.py
from pillsbot.core.measurements import MeasurementRegistry
from pillsbot import config as cfg


def make_registry():
    return MeasurementRegistry(cfg.TZ, cfg.MEASURES)


def test_pressure_positive_cases():
    reg = make_registry()
    mid, body = reg.match("тиск 120 80 60")
    assert mid == "pressure"
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("BP 118/79/62")
    assert mid == "pressure"
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("давление 125,85,59")
    assert mid == "pressure"
    assert reg.parse(mid, body)["ok"]

    # NEW: punctuation after keyword
    mid, body = reg.match("BP: 120/80/60")
    assert mid == "pressure"
    assert reg.parse(mid, body)["ok"]


def test_pressure_negative_cases():
    reg = make_registry()
    mid, body = reg.match("pressure 120/80")  # missing one
    assert mid == "pressure"
    assert not reg.parse(mid, body)["ok"]

    mid, body = reg.match("давление 120.5/80/60")  # decimal not allowed
    assert mid == "pressure"
    assert not reg.parse(mid, body)["ok"]


def test_weight_positive_cases():
    reg = make_registry()
    mid, body = reg.match("вага 102,4")
    assert mid == "weight"
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("weight 73.0")
    assert mid == "weight"
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("вес 80")
    assert mid == "weight"
    assert reg.parse(mid, body)["ok"]

    # NEW: boundaries
    mid, body = reg.match("weight 0")
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("weight 0.0")
    assert reg.parse(mid, body)["ok"]

    mid, body = reg.match("weight 350.1234")
    assert reg.parse(mid, body)["ok"]


def test_weight_negative_cases():
    reg = make_registry()
    mid, body = reg.match("weight -5")
    r = reg.parse(mid, body)
    assert not r["ok"]

    mid, body = reg.match("взвешивание 80 кг")
    r = reg.parse(mid, body)
    assert not r["ok"]


def test_start_anchored():
    reg = make_registry()
    assert reg.match("моє давление 120 80 60") is None
