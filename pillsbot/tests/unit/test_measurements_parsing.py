# pillsbot/tests/unit/test_measurements_parsing.py
from pillsbot.core.measurements import MeasurementRegistry, parse_pressure_free, parse_weight_free
from pillsbot import config as cfg


def make_registry():
    return MeasurementRegistry(cfg.TZ, cfg.MEASURES)


def test_pressure_positive_cases():
    reg = make_registry()
    mid, body = reg.match("тиск 120 80")
    assert mid == "pressure"
    assert parse_pressure_free(body)["ok"]

    mid, body = reg.match("BP 118/79")
    assert mid == "pressure"
    assert parse_pressure_free(body)["ok"]

    mid, body = reg.match("давление 125,85")
    assert mid == "pressure"
    assert parse_pressure_free(body)["ok"]

    mid, body = reg.match("BP: 120/80")
    assert mid == "pressure"
    assert parse_pressure_free(body)["ok"]

    mid, body = reg.match("pressure 120-80 72")
    assert mid == "pressure"
    r = parse_pressure_free(body)
    assert r["ok"] and r.get("pulse") == 72


def test_pressure_negative_cases():
    reg = make_registry()
    mid, body = reg.match("pressure 120")
    assert mid == "pressure"
    r = parse_pressure_free(body)
    assert not r["ok"] and r["error"] in {"one_number", "unrecognized"}

    mid, body = reg.match("давление 120.5/80")
    assert mid == "pressure"
    r = parse_pressure_free(body)
    assert not r["ok"]


def test_weight_positive_cases():
    reg = make_registry()
    mid, body = reg.match("вага 102,4")
    assert mid == "weight"
    assert parse_weight_free(body)["ok"]

    mid, body = reg.match("weight 73.0")
    assert mid == "weight"
    assert parse_weight_free(body)["ok"]

    mid, body = reg.match("вес 80")
    assert mid == "weight"
    assert parse_weight_free(body)["ok"]


def test_weight_negative_cases_and_ranges():
    reg = make_registry()

    mid, body = reg.match("weight 120 80")
    assert mid == "weight"
    r = parse_weight_free(body)
    assert not r["ok"] and r["error"] == "likely_pressure"

    mid, body = reg.match("weight 7")
    assert mid == "weight"
    r = parse_weight_free(body)
    assert not r["ok"] and r["error"] == "range"

    mid, body = reg.match("weight 350.0")
    assert mid == "weight"
    r = parse_weight_free(body)
    assert not r["ok"] and r["error"] == "range"


def test_start_anchored():
    reg = make_registry()
    assert reg.match("моє давление 120 80") is None
