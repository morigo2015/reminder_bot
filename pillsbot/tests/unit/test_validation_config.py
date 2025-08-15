# tests/unit/test_validation_config.py
import pytest
from pillsbot.core.config_validation import validate_config
from zoneinfo import ZoneInfo


class CfgOk:
    TZ = ZoneInfo("Europe/Kyiv")
    MEASURES = {
        "pressure": {
            "label": "Тиск",
            "patterns": ["тиск", "давление", "BP", "pressure"],
            "csv_file": "pillsbot/logs/pressure_test.csv",
            "parser_kind": "int2",  # v4: two integers (systolic, diastolic)
            "separators": [" ", ",", "/"],
        }
    }
    PATIENTS = [
        {
            "patient_id": 1,
            "patient_label": "A",
            "group_id": -1,
            "nurse_user_id": 2,
            "doses": [{"time": "08:00", "text": "Med"}],
            "measurement_checks": [{"measure_id": "pressure", "time": "21:00"}],
        }
    ]


def test_validate_ok():
    validate_config(CfgOk)


def test_duplicate_measurement_check_times_raises():
    class CfgDup(CfgOk):
        PATIENTS = [
            {
                "patient_id": 1,
                "patient_label": "A",
                "group_id": -1,
                "nurse_user_id": 2,
                "doses": [{"time": "08:00", "text": "Med"}],
                "measurement_checks": [
                    {"measure_id": "pressure", "time": "21:00"},
                    {"measure_id": "pressure", "time": "21:00"},
                ],
            }
        ]

    with pytest.raises(ValueError):
        validate_config(CfgDup)
