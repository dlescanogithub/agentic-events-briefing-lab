"""Doc contract tests.

Banned org names are not stored as plaintext. The check compares sha256 hashes
of lowercase word tokens and adjacent pairs with a stored hash list. Extra
phrases can be supplied at runtime through EVENTS_BANNED_TERMS or the untracked
file tests/banned-terms.local. Docs are also scanned for org-like CamelCase
tokens and legal-entity suffixes.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "README.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/HOW_IT_WORKS.md",
    "docs/BUSINESS_VALUE.md",
    "docs/BUSINESS_CASE.md",
    "docs/DISCOVERY.md",
    "docs/SCOPE.md",
    "docs/RISKS.md",
    "docs/METRICS.md",
    "docs/COST.md",
    "docs/RUNBOOK.md",
    "docs/architecture.md",
    "docs/ADAPT_TO_A_REAL_CLIENT.md",
    "docs/DATA_SOURCES.md",
    "docs/RUBRIC.md",
    "docs/PROVENANCE.md",
    "docs/adr/0001-offline-snapshots.md",
    "docs/adr/0007-invariant-evals.md",
]

# sha256 of lowercase unigrams or space-joined bigrams. Plaintext is not stored.
BANNED_HASHES = frozenset(
    {
        "358bfb6eea2eacdec7480c1fda994799523553c3a8e273c4d2020b267ded3e57",
        "89e20dd40115c29cf9c57393fa539063f8fa5209109a595a068d6ee921399ae4",
        "8b7a801b107e55e704286521141f47266dcdd3b35575abdff5dfefb7bf49fa26",
    }
)

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
CAMEL_RE = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z]+\b")
LEGAL_RE = re.compile(r"\b(?:Inc\.?|L\.L\.C\.|LLC|Ltd\.?|Corp\.?|GmbH|PLC)\b")
ALLOWED_CAMEL = frozenset({"OpenStreetMap", "OpenAI", "OpenData", "NonMedical", "GitHub"})
DOC_NAMES = ("README.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", "NOTICE")
LOCAL_BAN_FILE = ROOT / "tests" / "banned-terms.local"
REPO_VISIBILITY_PHRASES = (
    "stays private",
    "keep the repo private",
    "private lab repository",
    "private github repository",
    "this private repo",
    "private reference repo",
    "making this repository public",
    "does not make this repository public",
    "initial private lab",
    "interview walkthrough",
    "deployment strategist",
)


def _grams(text: str) -> set[str]:
    tokens = [tok.lower() for tok in TOKEN_RE.findall(text)]
    pairs = zip(tokens, tokens[1:], strict=False)
    pieces = tokens + [f"{left} {right}" for left, right in pairs]
    return {hashlib.sha256(piece.encode()).hexdigest() for piece in pieces}


def _extra_banned_hashes() -> set[str]:
    phrases: list[str] = []
    raw = os.environ.get("EVENTS_BANNED_TERMS", "")
    phrases.extend(part.strip().lower() for part in raw.split(",") if part.strip())
    if LOCAL_BAN_FILE.is_file():
        for line in LOCAL_BAN_FILE.read_text(encoding="utf-8").splitlines():
            phrase = line.strip().lower()
            if phrase and not phrase.startswith("#"):
                phrases.append(phrase)
    return {hashlib.sha256(phrase.encode()).hexdigest() for phrase in phrases}


def _tracked_texts() -> list[tuple[str, str]]:
    listing = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    rows: list[tuple[str, str]] = []
    for name in listing.decode().split("\0"):
        if not name:
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rows.append((name, text))
    return rows


def _doc_texts() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for name, text in _tracked_texts():
        if name.startswith("docs/") or name in DOC_NAMES:
            rows.append((name, text))
    return rows


def test_required_docs_exist() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    assert missing == []


def test_readme_disclaimer_and_section() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    head = text[:800]
    assert "Recreated scenario with public data, not a client deliverable." in head
    assert (
        "Architecture inspired by a team project; this is a personal recreation "
        "with public data, not a client deliverable."
    ) in head
    assert "PRIVATE" not in text
    assert "## Use cases, governance and business strategy" in text
    assert "not measured" in text.lower()
    assert "For engineers and buyers" in text
    assert "Walkthrough for engineers and buyers" in text
    assert "**Start here**" in text
    assert "## Proof" in text
    assert "## What this does NOT prove" in text
    assert "## Business value" in text
    assert "docs/BUSINESS_VALUE.md" in text
    assert "## Quickstart" in text
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    reporting = (
        'GitHub private vulnerability reporting ("Report a vulnerability" on the Security tab)'
    )
    assert reporting in security
    hits = [
        f"{name}:{phrase}"
        for name, body in _doc_texts()
        for phrase in REPO_VISIBILITY_PHRASES
        if phrase in body.lower()
    ]
    assert hits == []
    assert _grams(text).isdisjoint(BANNED_HASHES)


def test_license_is_standard_mit_and_notice_holds_data_terms() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License\n")
    assert "Copyright (c) 2026 Diego Lescano\n" in license_text
    assert "NYC" not in license_text
    assert "DATA_SOURCES" not in license_text
    assert license_text.rstrip().endswith("SOFTWARE.")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "NYC Open Data" in notice
    assert "docs/DATA_SOURCES.md" in notice


def test_how_it_works_walkthrough_is_english() -> None:
    text = (ROOT / "docs/HOW_IT_WORKS.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "look at where the data comes from" in lowered
    assert "see what is dropped" in lowered
    assert "life-safety above noise" in lowered
    assert "mirá" not in lowered
    assert "fijate" not in lowered


def test_no_banned_names_in_tracked_files() -> None:
    banned = set(BANNED_HASHES) | _extra_banned_hashes()
    hits = [name for name, text in _tracked_texts() if not _grams(text).isdisjoint(banned)]
    assert hits == []


def test_docs_have_no_org_like_names() -> None:
    camel_hits: list[str] = []
    legal_hits: list[str] = []
    for name, text in _doc_texts():
        for token in CAMEL_RE.findall(text):
            if token not in ALLOWED_CAMEL:
                camel_hits.append(f"{name}:{token}")
        if LEGAL_RE.search(text):
            legal_hits.append(name)
    assert camel_hits == []
    assert legal_hits == []


def test_hash_scanner_flags_a_bigram() -> None:
    sample = "Acme Widgets shipped a draft"
    digest = hashlib.sha256(b"acme widgets").hexdigest()
    assert digest in _grams(sample)
    assert digest not in BANNED_HASHES


def test_extra_banned_terms_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENTS_BANNED_TERMS", "acme widgets")
    digest = hashlib.sha256(b"acme widgets").hexdigest()
    assert digest in _extra_banned_hashes()
