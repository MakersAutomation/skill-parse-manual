#!/usr/bin/env python3
"""Populate parameter knowledge_ref fields from generated knowledge files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

GROUP_CODE_RE = re.compile(r"\b([cfru][0-9a-f]{2})\b", flags=re.IGNORECASE)


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("Top-level YAML must be a mapping.")
    return data


def _split_frontmatter(markdown: str) -> Optional[Dict[str, Any]]:
    if not markdown.startswith("---\n"):
        return None
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return None
    payload = markdown[4:end]
    parsed = yaml.safe_load(payload)
    return parsed if isinstance(parsed, dict) else None


def _section_ref(knowledge_dir: Path, md_path: Path, fm: Dict[str, Any]) -> str:
    section = fm.get("section")
    if isinstance(section, str) and section.strip():
        return section.strip().replace("\\", "/")
    return md_path.relative_to(knowledge_dir).as_posix()[:-3]


def _score_frontmatter(fm: Dict[str, Any]) -> Tuple[int, int]:
    completeness_rank = {"stub": 0, "partial": 1, "complete": 2}
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    completeness = completeness_rank.get(str(fm.get("content_completeness", "")).lower(), 0)
    confidence = confidence_rank.get(str(fm.get("extraction_confidence", "")).lower(), 0)
    return completeness, confidence


def _best_entry(entries: List[Tuple[Tuple[int, int], str]]) -> str:
    entries_sorted = sorted(entries, key=lambda e: (e[0][0], e[0][1], -len(e[1])), reverse=True)
    return entries_sorted[0][1]


def _dominant_ref(refs: List[str], min_support: int = 2) -> Optional[str]:
    counts: Dict[str, int] = {}
    for ref in refs:
        counts[ref] = counts.get(ref, 0) + 1
    if not counts:
        return None
    best_ref, best_count = sorted(counts.items(), key=lambda kv: (kv[1], -len(kv[0])), reverse=True)[0]
    if best_count < min_support:
        return None
    return best_ref


def main() -> int:
    parser = argparse.ArgumentParser(description="Link Type 1 parameters to Type 2 knowledge files.")
    parser.add_argument("--registers", required=True, help="Path to device_registers.yaml")
    parser.add_argument("--knowledge-dir", required=True, help="Path to knowledge directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registers_path = Path(args.registers).expanduser().resolve()
    knowledge_dir = Path(args.knowledge_dir).expanduser().resolve()

    registers = _load_yaml(registers_path)
    parameters = registers.get("parameters")
    if not isinstance(parameters, list):
        raise ValueError("register file missing parameters list.")

    id_to_refs: Dict[str, List[Tuple[Tuple[int, int], str]]] = {}
    group_to_refs: Dict[str, List[Tuple[Tuple[int, int], str]]] = {}

    for md in sorted(knowledge_dir.rglob("*.md")):
        if md.name == "_index.md":
            continue
        raw = md.read_text(encoding="utf-8", errors="ignore")
        fm = _split_frontmatter(raw) or {}
        ref = _section_ref(knowledge_dir, md, fm)
        score = _score_frontmatter(fm)

        related = fm.get("related_parameters", [])
        if isinstance(related, list):
            for item in related:
                if not isinstance(item, dict):
                    continue
                pid = item.get("id")
                if isinstance(pid, str) and pid.strip():
                    key = pid.strip().upper()
                    id_to_refs.setdefault(key, []).append((score, ref))

        if "/" in ref:
            group = ref.split("/", 1)[0]
            if group:
                group_to_refs.setdefault(group, []).append((score, ref))

        # Group-code hint mapping (for register groups like c00, c06, u42).
        title = str(fm.get("title", ""))
        hint_source = f"{ref} {title}"
        hinted_groups = {m.group(1).lower() for m in GROUP_CODE_RE.finditer(hint_source)}
        for hinted_group in hinted_groups:
            group_to_refs.setdefault(hinted_group, []).append((score, ref))

    updated = 0
    non_null = 0
    group_assigned_refs: Dict[str, List[str]] = {}
    first_pass_matches = 0

    # Pass 1: explicit id/group hint matches from knowledge frontmatter and group-code hints.
    for param in parameters:
        if not isinstance(param, dict):
            continue
        pid = str(param.get("id", "")).strip().upper()
        group = str(param.get("group", "")).strip()
        chosen: Optional[str] = None

        if pid and pid in id_to_refs:
            chosen = _best_entry(id_to_refs[pid])
        elif group and group in group_to_refs:
            chosen = _best_entry(group_to_refs[group])

        old = param.get("knowledge_ref")
        if chosen is None:
            chosen_val: Any = None
        else:
            chosen_val = chosen

        if old != chosen_val:
            param["knowledge_ref"] = chosen_val
            updated += 1
        if chosen:
            first_pass_matches += 1
            if group:
                group_assigned_refs.setdefault(group, []).append(chosen)
        if param.get("knowledge_ref"):
            non_null += 1

    # Pass 2: if a group has a dominant reference, apply it to remaining null rows in that group.
    propagated = 0
    for param in parameters:
        if not isinstance(param, dict):
            continue
        if param.get("knowledge_ref"):
            continue
        group = str(param.get("group", "")).strip()
        if not group:
            continue
        dominant = _dominant_ref(group_assigned_refs.get(group, []), min_support=2)
        if dominant is None:
            continue
        param["knowledge_ref"] = dominant
        updated += 1
        propagated += 1
        non_null += 1

    total = len([p for p in parameters if isinstance(p, dict)])
    coverage = (non_null / total * 100.0) if total else 0.0

    if not args.dry_run:
        registers_path.write_text(
            yaml.safe_dump(registers, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    mode = "DRY RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: {registers_path}")
    print(f"Parameters total: {total}")
    print(f"knowledge_ref non-null: {non_null} ({coverage:.1f}%)")
    print(f"Explicit matches (pass 1): {first_pass_matches}")
    print(f"Group-propagated matches (pass 2): {propagated}")
    print(f"Rows changed: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
