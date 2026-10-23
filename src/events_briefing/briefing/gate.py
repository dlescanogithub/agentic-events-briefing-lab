"""DRAFT -> PENDING_APPROVAL -> APPROVED or REJECTED -> PUBLISHED (local outbox).

This is an approval gate (simulated actor). The state file is HMAC-signed with
APPROVAL_STATE_KEY and the actor must be on the config allowlist. The signature
covers the program id, the approved segments, a one-time approval nonce, and
the nonce-ledger head. Load rejects a file whose signed program id does not
match the requested id. Load also rejects a missing or tampered nonce ledger
when program state exists. Publish consumes the nonce. Deleting the ledger and
restoring an old APPROVED file does not publish again. Restoring that ledger
file together with the old APPROVED file still does: the same key signs both.
It is not an authenticated channel. Production needs one. The public lab
fixture key is refused outside demo mode and must be rotated before then.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from events_briefing.briefing.writer import dumps, render_markdown
from events_briefing.paths import find_repo_root

_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
GATE_NAME = "approval gate (simulated actor)"
# Public on purpose. Demo and eval may use it. Any other run must rotate it.
PUBLIC_LAB_APPROVAL_KEY = "lab-simulated-not-a-secret"

TRANSITIONS: dict[tuple[str, str], str] = {
    ("DRAFT", "submit"): "PENDING_APPROVAL",
    ("PENDING_APPROVAL", "approve"): "APPROVED",
    ("PENDING_APPROVAL", "reject"): "REJECTED",
    ("APPROVED", "publish"): "PUBLISHED",
}


class GateError(RuntimeError):
    pass


def approval_key_for_run(key: str, *, demo: bool) -> str:
    """Return the key to sign with.

    Demo mode (``demo --offline``, eval) may use the public lab fixture, including
    when the variable is unset. Every other run fails if that fixture is still set.
    """
    cleaned = key.strip()
    if not cleaned and demo:
        return PUBLIC_LAB_APPROVAL_KEY
    if cleaned == PUBLIC_LAB_APPROVAL_KEY and not demo:
        raise GateError(
            "APPROVAL_STATE_KEY is the public lab fixture; rotate it before use outside demo mode"
        )
    return cleaned


def load_approvers(path: Path | None = None) -> frozenset[str]:
    target = path or (find_repo_root() / "config" / "approvers.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    raw = payload.get("approvers")
    if not isinstance(raw, list):
        raise GateError(f"approvers file has no list: {target}")
    names = frozenset(str(item).strip() for item in raw if str(item).strip())
    if not names:
        raise GateError(f"approvers allowlist is empty: {target}")
    return names


class BriefingStore:
    def __init__(
        self,
        out_dir: Path,
        *,
        state_key: str | None = None,
        approvers: frozenset[str] | None = None,
        approvers_path: Path | None = None,
        demo: bool = False,
    ) -> None:
        self.out_dir = out_dir
        self.state_dir = out_dir / "state"
        self.outbox_dir = out_dir / "outbox"
        self.demo = demo
        if state_key is None:
            state_key = os.environ.get("APPROVAL_STATE_KEY", "")
        self.state_key = state_key.strip()
        if self.state_key == PUBLIC_LAB_APPROVAL_KEY and not demo:
            raise GateError(
                "APPROVAL_STATE_KEY is the public lab fixture; rotate it before use "
                "outside demo mode"
            )
        self.approvers = approvers if approvers is not None else load_approvers(approvers_path)

    def create(
        self,
        *,
        program_id: str,
        model_leg: str,
        rubric_version: str,
        segments: list[dict[str, object]],
        inputs_hash: str,
        created_at: datetime | None = None,
    ) -> dict[str, object]:
        self._require_key()
        self._check_id(program_id)
        self._ensure_ledger()
        moment = created_at or datetime.now(timezone.utc)
        document: dict[str, object] = {
            "program_id": program_id,
            "status": "DRAFT",
            "model_leg": model_leg,
            "rubric_version": rubric_version,
            "inputs_hash": inputs_hash,
            "created_at": moment.isoformat(),
            "approval_gate": GATE_NAME,
            "simulated_approval": False,
            "approver": None,
            "decision_note": "not decided",
            "approval_nonce": secrets.token_hex(16),
            "segments": segments,
        }
        self._write_state(document)
        return document

    def submit(self, program_id: str) -> dict[str, object]:
        return self._transition(program_id, "submit")

    def decide(
        self,
        program_id: str,
        decision: str,
        *,
        actor: str,
        simulated: bool,
        note: str,
    ) -> dict[str, object]:
        if decision not in {"approve", "reject"}:
            raise GateError("decision must be approve or reject")
        if not simulated:
            raise GateError(
                "approval gate (simulated actor) cannot record an authenticated approval; "
                "production needs an authenticated channel"
            )
        cleaned = actor.strip()
        if not cleaned:
            raise GateError("actor is empty")
        if cleaned not in self.approvers:
            raise GateError("actor is not on the approvers allowlist")
        document = self._transition(program_id, decision)
        document["approver"] = cleaned
        document["simulated_approval"] = True
        document["approval_gate"] = GATE_NAME
        document["decision_note"] = note
        self._write_state(document)
        return document

    def publish(self, program_id: str) -> dict[str, object]:
        document = self.load(program_id)
        if document.get("status") != "APPROVED":
            raise GateError(
                f"publish refused from status {document.get('status')}; approval is required"
            )
        nonce = document.get("approval_nonce")
        if not isinstance(nonce, str) or not nonce:
            raise GateError("approval nonce is missing")
        consumed = self._load_consumed()
        if any(item["nonce"] == nonce for item in consumed):
            raise GateError("approval nonce already used")
        self._require_ledger_head(document)
        self._consume_nonce(nonce, program_id)
        document = self._transition(program_id, "publish")
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        markdown = render_markdown(
            program_id=program_id,
            status="PUBLISHED",
            model_leg=str(document["model_leg"]),
            rubric_version=str(document["rubric_version"]),
            segments=_segments(document),
            simulated_note=_simulated_line(document),
        )
        (self.outbox_dir / f"{program_id}.json").write_text(dumps(document), encoding="utf-8")
        (self.outbox_dir / f"{program_id}.md").write_text(markdown, encoding="utf-8")
        return document

    def load(self, program_id: str) -> dict[str, object]:
        self._require_key()
        self._check_id(program_id)
        path = self.state_dir / f"{program_id}.json"
        if not path.is_file():
            raise GateError(f"unknown program {program_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise GateError("state file is not an object")
        self._verify(payload)
        signed_id = payload.get("program_id")
        if not isinstance(signed_id, str) or signed_id != program_id:
            raise GateError("program id does not match the signed state")
        if not self._ledger_path().is_file():
            raise GateError("nonce ledger is missing")
        self._load_consumed()
        return payload

    def outbox_count(self) -> int:
        if not self.outbox_dir.is_dir():
            return 0
        return len(list(self.outbox_dir.glob("*.json")))

    def _transition(self, program_id: str, action: str) -> dict[str, object]:
        document = self.load(program_id)
        status = str(document.get("status"))
        nxt = TRANSITIONS.get((status, action))
        if nxt is None:
            raise GateError(f"illegal transition {status} -- {action}")
        document["status"] = nxt
        self._write_state(document)
        return document

    def _write_state(self, document: dict[str, object]) -> None:
        self._require_key()
        program_id = str(document["program_id"])
        self._check_id(program_id)
        document["ledger_head"] = self._current_ledger_mac()
        document["state_mac"] = _mac(document, self.state_key, exclude="state_mac")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / f"{program_id}.json"
        path.write_text(dumps(document), encoding="utf-8")

    def _verify(self, document: dict[str, object]) -> None:
        self._verify_mac(document, exclude="state_mac")

    def _verify_mac(self, document: dict[str, object], *, exclude: str) -> None:
        found = document.get(exclude)
        if not isinstance(found, str) or not found:
            raise GateError("tampered state")
        expected = _mac(document, self.state_key, exclude=exclude)
        if not hmac.compare_digest(found, expected):
            raise GateError("tampered state")

    def _ledger_path(self) -> Path:
        return self.state_dir / "nonce-ledger.json"

    def _ensure_ledger(self) -> None:
        self._require_key()
        path = self._ledger_path()
        if path.is_file():
            self._load_consumed()
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        others = [item for item in self.state_dir.glob("*.json") if item.name != path.name]
        if others:
            raise GateError("nonce ledger is missing")
        document: dict[str, object] = {"consumed": []}
        document["ledger_mac"] = _mac(document, self.state_key, exclude="ledger_mac")
        path.write_text(dumps(document), encoding="utf-8")

    def _current_ledger_mac(self) -> str:
        return _mac({"consumed": self._load_consumed()}, self.state_key, exclude="ledger_mac")

    def _require_ledger_head(self, document: dict[str, object]) -> None:
        head = document.get("ledger_head")
        current = self._current_ledger_mac()
        if not isinstance(head, str) or not hmac.compare_digest(head, current):
            raise GateError("nonce ledger does not match the signed state")

    def _load_consumed(self) -> list[dict[str, str]]:
        path = self._ledger_path()
        if not path.is_file():
            raise GateError("nonce ledger is missing")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise GateError("tampered state")
        self._verify_mac(payload, exclude="ledger_mac")
        raw = payload.get("consumed")
        if not isinstance(raw, list):
            raise GateError("tampered state")
        rows: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise GateError("tampered state")
            nonce = item.get("nonce")
            program = item.get("program_id")
            if not isinstance(nonce, str) or not isinstance(program, str):
                raise GateError("tampered state")
            rows.append({"nonce": nonce, "program_id": program})
        return rows

    def _consume_nonce(self, nonce: str, program_id: str) -> None:
        self._require_key()
        consumed = self._load_consumed()
        if any(item["nonce"] == nonce for item in consumed):
            raise GateError("approval nonce already used")
        consumed.append({"nonce": nonce, "program_id": program_id})
        document: dict[str, object] = {"consumed": consumed}
        document["ledger_mac"] = _mac(document, self.state_key, exclude="ledger_mac")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._ledger_path().write_text(dumps(document), encoding="utf-8")

    def _require_key(self) -> None:
        if not self.state_key:
            raise GateError("APPROVAL_STATE_KEY is empty")

    def _check_id(self, program_id: str) -> None:
        if _ID_RE.fullmatch(program_id) is None:
            raise GateError("program id is not a safe filename")
        if ".." in program_id:
            raise GateError("program id is not a safe filename")


def _mac(document: dict[str, object], key: str, *, exclude: str) -> str:
    body = {field: value for field, value in document.items() if field != exclude}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _segments(document: dict[str, object]) -> list[dict[str, object]]:
    raw = document.get("segments")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _simulated_line(document: dict[str, object]) -> str:
    actor = document.get("approver") or "unspecified"
    return (
        f"Approval gate (simulated actor): SIMULATED by {actor}. "
        "Production needs an authenticated channel; this lab does not have one."
    )
