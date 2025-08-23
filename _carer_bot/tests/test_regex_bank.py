# tests/test_regex_bank.py
import pytest
from app.regex_bank import classify_text, extract_bp, extract_temp, LABEL_MEAS_BP, LABEL_MEAS_TEMP, LABEL_PILL_TAKEN, LABEL_PILL_NEGATE, LABEL_SYMPTOM

def test_confirmation_and_negation():
    assert classify_text("так") == LABEL_PILL_TAKEN
    assert classify_text("да") == LABEL_PILL_TAKEN
    assert classify_text("не прийняв") == LABEL_PILL_NEGATE

def test_bp_parsing():
    assert classify_text("тиск 180/110") == LABEL_MEAS_BP
    assert extract_bp("180/110") == (180, 110)
    assert extract_bp("75/190") is None  # invalid ordering

def test_temp_parsing():
    assert classify_text("38.6") == LABEL_MEAS_TEMP
    assert abs(extract_temp("37,2") - 37.2) < 1e-6
    assert extract_temp("45.0") is None  # out of realistic range

def test_symptom_fallback():
    assert classify_text("болить голова") == LABEL_SYMPTOM
