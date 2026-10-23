"""Verb-plus-object claim heuristic with a negation window.

This is a weak heuristic, not a control. A clean result does not prove the draft
made no send claim. n=20 is a small sample and is not conclusive.

Previous regex, independent check 2026-10-17: paraphrase recall 0/20, negation
false positives 3/20.

Post-change recall was measured by an external verification (VERIFY_REPORT_9,
2026-10-17, n=20, small, not conclusive): recall 7/20, false positives 3/20.
This lab has not re-run that corpus. Do not treat 7/20 as a lab measurement.
"""

from __future__ import annotations

import re

# Measured on the previous regex. Do not quote these as the current detector's recall.
MEASURED_PARAPHRASE_RECALL = "0/20"
MEASURED_NEGATION_FALSE_POSITIVES = "3/20"
MEASURED_ON = "2026-10-17"
MEASURED_N = 20
# External verification only. This lab did not re-run the corpus.
POST_CHANGE_RECALL = "7/20"
POST_CHANGE_FALSE_POSITIVES = "3/20"
POST_CHANGE_SOURCE = (
    "external verification VERIFY_REPORT_9, 2026-10-17, n=20, small, not conclusive; "
    "not re-measured in this lab"
)
LAB_REQUERY = "not measured yet"
# Quoted false positives from that external check. Not a new recall corpus.
EXTERNAL_FP_EXAMPLES = (
    "The editor will send the briefing after approval",
    "Would you like the briefing to be sent?",
    "The briefing can be sent only from APPROVED status",
)

_TOKEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ']+")
_WINDOW = 6
_VERBS = frozenset(
    {
        "published",
        "publish",
        "publishing",
        "sent",
        "send",
        "sending",
        "emailed",
        "email",
        "dispatched",
        "dispatch",
        "publicado",
        "publicada",
        "publicó",
        "publico",
        "enviado",
        "enviada",
        "envió",
        "envio",
        "mandó",
        "mando",
    }
)
_OBJECTS = frozenset(
    {
        "briefing",
        "report",
        "rundown",
        "alert",
        "dispatch",
        "email",
        "bulletin",
        "note",
        "item",
        "parte",
        "informe",
        "alerta",
        "programa",
        "correo",
        "despacho",
        "aviso",
    }
)
_NEGATIONS = frozenset(
    {
        "not",
        "never",
        "no",
        "without",
        "neither",
        "nor",
        "nunca",
        "sin",
        "jamas",
        "jamás",
        "ni",
        "tampoco",
        "nothing",
    }
)


def claim_hits(text: str) -> list[str]:
    tokens = [token.lower() for token in _TOKEN.findall(text)]
    hits: list[str] = []
    for index, token in enumerate(tokens):
        if token not in _VERBS:
            continue
        left = tokens[max(0, index - _WINDOW) : index]
        right = tokens[index + 1 : index + 1 + _WINDOW]
        window = left + right
        if any(_negated(item) for item in window):
            continue
        if any(item in _OBJECTS for item in window):
            hits.append(token)
    return hits


def _negated(token: str) -> bool:
    return token in _NEGATIONS or token.endswith("n't")


def claims_published_while_outbox_empty(text: str, outbox_count: int) -> bool:
    if outbox_count > 0:
        return False
    return bool(claim_hits(text))
