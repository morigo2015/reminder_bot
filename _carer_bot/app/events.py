# app/events.py
from __future__ import annotations
from typing import Literal

# CSV "scenario" values
SC_MED: Literal["pill"] = "pill"
SC_MEASURE: Literal["measure"] = "measure"
SC_OTHER: Literal["other"] = "other"

# CSV "event" values
EV_DUE: Literal["due_sent"] = "due_sent"
EV_NAG: Literal["nag_sent"] = "nag_sent"
EV_CONFIRMED: Literal["confirmed"] = "confirmed"
EV_ESCALATED: Literal["escalated"] = "escalated"
EV_CLARIFY_REQUIRED: Literal["clarify_required"] = "clarify_required"
EV_CLARIFY_NAG: Literal["clarify_nag_sent"] = "clarify_nag_sent"
EV_BP_RECORDED: Literal["bp_recorded"] = "bp_recorded"
EV_ACK: Literal["ack"] = "ack"
EV_ACK_NEG: Literal["ack_negation"] = "ack_negation"
EV_DUPLICATE_IGNORE: Literal["duplicate_ignore"] = "duplicate_ignore"

# Kinds
BP_KIND: Literal["bp"] = "bp"
