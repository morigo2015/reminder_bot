# app/scenarios.py
"""
Hardcoded PoC scenarios (no YAML yet).
Each scenario is a tiny unit: trigger -> prompt -> expected labels -> fallbacks.
We keep only what's needed for PoC; final project will lift this shape into YAML+Jinja2.
"""

from __future__ import annotations
from typing import Callable, Dict, List, Literal, TypedDict
from . import prompts
from .regex_bank import (
    LABEL_PILL_TAKEN,
    LABEL_PILL_NEGATE,
    LABEL_MEAS_BP,
    LABEL_MEAS_TEMP,
    LABEL_SYMPTOM,
)

TriggerKind = Literal["med_due", "measure_due"]

class Scenario(TypedDict, total=False):
    id: str
    trigger: Dict[str, str]         # {"type":"med_due"} or {"type":"measure_due","kind":"bp"}
    prompt_fn: Callable[..., str]   # functions from prompts.py
    expected_labels: List[str]      # allowed classification labels
    fallback_prompt_fn: Callable[..., str]

SCENARIOS: Dict[str, Scenario] = {
    # 1) Medication reminder
    "meds.reminder.take_pill": {
        "id": "meds.reminder.take_pill",
        "trigger": {"type": "med_due"},
        "prompt_fn": prompts.med_due,
        "expected_labels": [
            LABEL_PILL_TAKEN,    # "прийняв/прийняла/так/да/є"
            LABEL_PILL_NEGATE,   # negation (we still wait for nags/escalation rules)
        ],
        "fallback_prompt_fn": prompts.med_reprompt,
    },

    # 2) Blood pressure measurement
    "measure.collect.bp": {
        "id": "measure.collect.bp",
        "trigger": {"type": "measure_due", "kind": "bp"},
        "prompt_fn": prompts.measure_bp_prompt,
        "expected_labels": [LABEL_MEAS_BP],
        "fallback_prompt_fn": prompts.measure_recorded_ack,  # not really used; re-prompt handled in policy
    },

    # 3) Temperature measurement
    "measure.collect.temp": {
        "id": "measure.collect.temp",
        "trigger": {"type": "measure_due", "kind": "temp"},
        "prompt_fn": prompts.measure_temp_prompt,
        "expected_labels": [LABEL_MEAS_TEMP],
        "fallback_prompt_fn": prompts.measure_recorded_ack,
    },

    # 4) Simple symptom intake (catch-all)
    "symptom.intake.simple": {
        "id": "symptom.intake.simple",
        "trigger": {"type": "user_text"},
        "prompt_fn": lambda patient_name: prompts.ok_ack(),
        "expected_labels": [LABEL_SYMPTOM],
        "fallback_prompt_fn": prompts.ask_clarify_yes_no,
    },
}
