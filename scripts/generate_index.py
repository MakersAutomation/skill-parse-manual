#!/usr/bin/env python3
"""Generate knowledge/_index.yaml for ParseManual outputs."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return data


def _split_frontmatter(markdown: str) -> Optional[Dict[str, Any]]:
    if not markdown.startswith("---\n"):
        return None
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return None
    raw = markdown[4:end]
    parsed = yaml.safe_load(raw)
    return parsed if isinstance(parsed, dict) else None


def _split_frontmatter_and_body(markdown: str) -> tuple[Optional[Dict[str, Any]], str]:
    if not markdown.startswith("---\n"):
        return None, markdown
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return None, markdown
    raw = markdown[4:end]
    body = markdown[end + 5 :]
    parsed = yaml.safe_load(raw)
    return (parsed if isinstance(parsed, dict) else None), body


def _render_markdown(frontmatter: Dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_text}\n---\n{body if body.startswith(chr(10)) else chr(10) + body}"


def _knowledge_files(knowledge_dir: Path) -> List[Path]:
    return sorted(
        [
            p
            for p in knowledge_dir.rglob("*.md")
            if p.is_file() and p.name != "_index.md"
        ]
    )


def _section_ref_from_path(knowledge_dir: Path, path: Path) -> str:
    return path.relative_to(knowledge_dir).as_posix()[:-3]


def _normalize_ref(ref: str) -> str:
    return ref.strip().replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ParseManual _index.yaml.")
    parser.add_argument("--registers", default=None, help="Path to device_registers.yaml (optional for knowledge-only devices)")
    parser.add_argument("--knowledge-dir", required=True)
    parser.add_argument("--output-index", required=True)
    parser.add_argument("--llm-model", default="unspecified")
    parser.add_argument("--parser-mode", default="accurate")
    parser.add_argument("--parse-quality-score", type=float, default=None)
    parser.add_argument("--manual-source", default=None)
    parser.add_argument("--manufacturer", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--no-prune-stale-refs",
        action="store_true",
        help="Disable automatic pruning of stale prerequisites/see_also references.",
    )
    args = parser.parse_args()

    knowledge_dir = Path(args.knowledge_dir).expanduser().resolve()
    output_path = Path(args.output_index).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reg: Dict[str, Any] = {}
    registers_path: Optional[Path] = None
    if args.registers:
        registers_path = Path(args.registers).expanduser().resolve()
        if registers_path.exists():
            reg = _load_yaml(registers_path)

    device = reg.get("device", {}) if isinstance(reg.get("device"), dict) else {}
    groups = reg.get("groups", []) if isinstance(reg.get("groups"), list) else []
    parameters = reg.get("parameters", []) if isinstance(reg.get("parameters"), list) else []
    total_parameters = len([p for p in parameters if isinstance(p, dict)])

    knowledge_paths = _knowledge_files(knowledge_dir)
    section_refs = {_section_ref_from_path(knowledge_dir, p) for p in knowledge_paths}
    prune_enabled = not args.no_prune_stale_refs
    pruned_total = 0
    rewritten_files = 0
    knowledge_sections: List[Dict[str, Any]] = []
    covered_groups: Set[str] = set()

    for path in knowledge_paths:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        fm, body = _split_frontmatter_and_body(raw)
        fm = fm or {}
        section_path = path.relative_to(knowledge_dir).as_posix()
        section_ref = _section_ref_from_path(knowledge_dir, path)
        changed = False

        # Keep section keys aligned to real file path to avoid stale index refs.
        if fm.get("section") != section_ref:
            fm["section"] = section_ref
            changed = True

        if prune_enabled:
            for key in ("prerequisites", "see_also"):
                refs = fm.get(key, [])
                if not isinstance(refs, list):
                    continue
                cleaned: List[str] = []
                for item in refs:
                    if not isinstance(item, str):
                        continue
                    normalized = _normalize_ref(item)
                    if normalized in section_refs:
                        cleaned.append(normalized)
                if cleaned != refs:
                    pruned_total += max(0, len(refs) - len(cleaned))
                    fm[key] = cleaned
                    changed = True

        if changed:
            path.write_text(_render_markdown(fm, body), encoding="utf-8")
            rewritten_files += 1

        related = fm.get("related_parameters", [])
        related_count = len(related) if isinstance(related, list) else 0
        knowledge_sections.append(
            {
                "path": section_path,
                "title": fm.get("title") or path.stem.replace("_", " ").title(),
                "completeness": fm.get("content_completeness") or "partial",
                "confidence": fm.get("extraction_confidence") or "medium",
                "parameter_count": related_count,
            }
        )

        section_name = fm.get("section")
        if isinstance(section_name, str) and section_name.strip():
            covered_groups.add(section_name.split("/")[0])

    uncovered_groups: List[Dict[str, Any]] = []
    group_ids = {
        g.get("id")
        for g in groups
        if isinstance(g, dict) and isinstance(g.get("id"), str) and g.get("id")
    }
    for gid in sorted(group_ids):
        base = gid.split("/")[0]
        if gid not in covered_groups and base not in covered_groups:
            count = len([p for p in parameters if isinstance(p, dict) and p.get("group") == gid])
            uncovered_groups.append(
                {
                    "group": gid,
                    "parameter_count": count,
                    "reason": "No knowledge section generated from narrative content.",
                }
            )

    manufacturer = args.manufacturer or device.get("manufacturer")
    model = args.model or device.get("model")

    index_doc: Dict[str, Any] = {
        "schema_version": "1.0",
        "device": {
            "manufacturer": manufacturer,
            "model": model,
            "firmware": device.get("firmware"),
        },
        "extraction_metadata": {
            "tool": "ParseManual",
            "tool_version": "0.1.0",
            "extraction_date": date.today().isoformat(),
            "parser": "marker",
            "parser_mode": args.parser_mode,
            "parse_quality_score": args.parse_quality_score,
            "llm_model": args.llm_model,
            "manual_source": args.manual_source or device.get("manual_source"),
            "writing_style": "caveman-lite",
        },
        "register_file": registers_path.name if registers_path and registers_path.exists() else None,
        "total_parameters": total_parameters,
        "knowledge_sections": knowledge_sections,
        "uncovered_groups": uncovered_groups,
    }

    output_path.write_text(yaml.safe_dump(index_doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote: {output_path}")
    print(f"Knowledge sections: {len(knowledge_sections)}")
    if prune_enabled:
        print(f"Stale references pruned: {pruned_total}")
        print(f"Knowledge files normalized: {rewritten_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
