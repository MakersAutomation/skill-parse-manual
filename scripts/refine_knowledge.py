#!/usr/bin/env python3
"""Prepare and apply a light refinement pass for low-confidence knowledge files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

WS_RE = re.compile(r"[ \t]+")
BLANKS_RE = re.compile(r"\n{3,}")


def _split_frontmatter(markdown: str) -> Tuple[Optional[Dict[str, Any]], str]:
    if not markdown.startswith("---\n"):
        return None, markdown
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return None, markdown
    payload = markdown[4:end]
    fm = yaml.safe_load(payload)
    body = markdown[end + 5 :]
    return (fm if isinstance(fm, dict) else None), body


def _normalize_body(body: str) -> str:
    lines = []
    prev = None
    for raw in body.splitlines():
        line = WS_RE.sub(" ", raw).rstrip()
        # preserve markdown tables and list markers exactly-ish
        if line.startswith("|") or line.startswith("- ") or line.startswith("#"):
            pass
        if prev is not None and line == prev and line.strip():
            continue
        lines.append(line)
        prev = line
    text = "\n".join(lines).strip()
    text = BLANKS_RE.sub("\n\n", text)
    return text + "\n"


def _render_markdown(fm: Dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    title = str(fm.get("title") or "Knowledge Section").strip()
    # Ensure body starts with title heading once.
    content = body.strip()
    if not content.startswith("## "):
        content = f"## {title}\n\n{content}"
    return f"---\n{yaml_text}\n---\n\n{content}\n"


def _is_target(fm: Dict[str, Any], force: bool) -> bool:
    if force:
        return True
    confidence = str(fm.get("extraction_confidence", "")).lower()
    completeness = str(fm.get("content_completeness", "")).lower()
    return confidence == "low" or completeness == "stub"


def main() -> int:
    parser = argparse.ArgumentParser(description="Refine low-confidence knowledge markdown files.")
    parser.add_argument("--knowledge-dir", required=True)
    parser.add_argument("--prompt-path", default=None, help="Optional prompt file path for agent reference")
    parser.add_argument("--force-all", action="store_true", help="Refine all knowledge files, not only low/stub")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    knowledge_dir = Path(args.knowledge_dir).expanduser().resolve()
    files = sorted([p for p in knowledge_dir.rglob("*.md") if p.is_file() and p.name != "_index.md"])

    scanned = 0
    targets = 0
    updated = 0
    for md in files:
        scanned += 1
        raw = md.read_text(encoding="utf-8", errors="ignore")
        fm, body = _split_frontmatter(raw)
        if fm is None:
            continue
        if not _is_target(fm, force=args.force_all):
            continue
        targets += 1
        new_body = _normalize_body(body)
        if new_body == body:
            continue
        updated += 1
        if not args.dry_run:
            md.write_text(_render_markdown(fm, new_body), encoding="utf-8")

    mode = "DRY RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: {knowledge_dir}")
    print(f"Files scanned: {scanned}")
    print(f"Refinement targets: {targets}")
    print(f"Files changed: {updated}")
    if args.prompt_path:
        print(f"Prompt reference: {Path(args.prompt_path).expanduser().resolve()}")
    if targets == 0:
        print("No low-confidence/stub files detected. Refinement pass is a no-op.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
