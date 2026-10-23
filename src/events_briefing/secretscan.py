"""Pattern scan for committed secrets. Recall is not measured."""

from __future__ import annotations

import re
from pathlib import Path

from events_briefing.paths import find_repo_root

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github_fine_grained", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("xai_key", re.compile(r"xai-[A-Za-z0-9]{20,}")),
    ("openai_style", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_+\-/]{16,}['\"]"
        ),
    ),
)

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "out",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "dist",
    "build",
}


def scan_tree(root: Path | None = None) -> list[str]:
    start = root or find_repo_root()
    findings: list[str] = []
    for path in start.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(start)}:{line_no}: {name}")
    return findings


def main_scan(root: Path | None = None) -> int:
    findings = scan_tree(root)
    if not findings:
        print("secretscan: no findings")
        return 0
    print("secretscan findings:")
    for item in findings:
        print(item)
    return 1
