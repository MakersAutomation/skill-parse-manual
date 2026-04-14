#!/usr/bin/env python3
"""Validate device_registers.yaml for ParseManual."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set

import yaml


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


def _load_knowledge_frontmatters(knowledge_dir: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not knowledge_dir.exists():
        return out
    for md in knowledge_dir.rglob("*.md"):
        if md.name == "_index.md":
            continue
        raw = md.read_text(encoding="utf-8", errors="ignore")
        fm = _split_frontmatter(raw) or {}
        out[md.relative_to(knowledge_dir).as_posix()] = fm
    return out


def validate(
    data: Dict[str, Any],
    phase: int,
    *,
    knowledge_dir: Optional[Path] = None,
    index_path: Optional[Path] = None,
    rules_dir: Optional[Path] = None,
) -> tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    parameters = data.get("parameters")
    if not isinstance(parameters, list):
        errors.append("`parameters` must be a list.")
        return errors, warnings

    groups = data.get("groups", [])
    group_ids: Set[str] = set()
    if isinstance(groups, list):
        for item in groups:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                group_ids.add(item["id"])

    # Uniqueness of parameter IDs and minimum shape checks.
    ids_seen: Set[str] = set()
    modbus_addresses: Set[int] = set()
    for idx, param in enumerate(parameters):
        if not isinstance(param, dict):
            errors.append(f"parameters[{idx}] must be a mapping.")
            continue

        pid = param.get("id")
        if not isinstance(pid, str) or not pid.strip():
            errors.append(f"parameters[{idx}].id must be a non-empty string.")
            continue
        if pid in ids_seen:
            errors.append(f"Duplicate parameter id: {pid}")
        ids_seen.add(pid)

        group = param.get("group")
        if isinstance(group, str) and group_ids and group not in group_ids:
            errors.append(f"Parameter {pid} references unknown group: {group}")

        dtype = param.get("data_type")
        if dtype == "bitfield":
            bl = param.get("bit_layout")
            if not isinstance(bl, dict) or not bl:
                errors.append(f"Parameter {pid} has data_type bitfield but missing or empty bit_layout.")
            if param.get("value_map"):
                warnings.append(f"Parameter {pid} is bitfield but has value_map; prefer bit_layout only.")

        value_map = param.get("value_map")
        rng = param.get("range")
        if value_map and isinstance(rng, dict):
            mn = rng.get("min")
            mx = rng.get("max")
            if mn == 0 and mx == 1:
                warnings.append(
                    f"Parameter {pid} has both value_map and range 0..1; check bool/enum classification."
                )

        protocols = param.get("protocols", {})
        if isinstance(protocols, dict):
            modbus = protocols.get("modbus")
            if isinstance(modbus, dict):
                address = modbus.get("address")
                if isinstance(address, int):
                    if address in modbus_addresses:
                        errors.append(f"Duplicate Modbus address: {address}")
                    modbus_addresses.add(address)

        if phase >= 2:
            kref = param.get("knowledge_ref")
            if kref is not None and not isinstance(kref, str):
                errors.append(f"Parameter {pid} has invalid knowledge_ref type.")

    # Completeness heuristic
    total = len(parameters)
    if total < 10:
        warnings.append(
            f"Only {total} parameters extracted. This is suspiciously low for an industrial manual."
        )

    knowledge_frontmatters: Dict[str, Dict[str, Any]] = {}
    if knowledge_dir:
        knowledge_frontmatters = _load_knowledge_frontmatters(knowledge_dir)

    # Phase-2 checks only
    if phase >= 2:
        knowledge_paths = set(knowledge_frontmatters.keys())
        related_ids: Set[str] = set()

        # check that knowledge refs are plausible paths and exist when provided
        for param in parameters:
            if not isinstance(param, dict):
                continue
            pid = str(param.get("id", "?"))
            kref = param.get("knowledge_ref")
            if kref is not None and isinstance(kref, str) and not kref.strip():
                errors.append(f"Parameter {pid} has empty knowledge_ref string.")
            if isinstance(kref, str) and kref.strip() and knowledge_paths and f"{kref}.md" not in knowledge_paths:
                warnings.append(f"Parameter {pid} knowledge_ref points to missing file: {kref}.md")

        for rel_path, fm in knowledge_frontmatters.items():
            related = fm.get("related_parameters", [])
            if isinstance(related, list):
                for item in related:
                    if isinstance(item, dict):
                        rid = item.get("id")
                        if isinstance(rid, str):
                            related_ids.add(rid)

            for list_key in ("prerequisites", "see_also"):
                refs = fm.get(list_key, [])
                if not isinstance(refs, list):
                    continue
                for ref in refs:
                    if not isinstance(ref, str):
                        continue
                    if f"{ref}.md" not in knowledge_paths:
                        warnings.append(f"{rel_path} {list_key} references missing section: {ref}.md")

            diagrams = fm.get("diagrams", [])
            if not isinstance(diagrams, list):
                continue
            for diagram in diagrams:
                if not isinstance(diagram, dict):
                    continue
                filename = diagram.get("filename")
                if not isinstance(filename, str) or not filename.strip():
                    continue
                image_path = (knowledge_dir.parent / "images" / filename) if knowledge_dir else None
                if image_path and not image_path.exists():
                    warnings.append(f"{rel_path} diagram file missing in images/: {filename}")

        for rid in sorted(related_ids):
            if rid not in ids_seen:
                warnings.append(f"Knowledge related parameter missing from Type 1 register list: {rid}")

        if index_path and index_path.exists():
            try:
                idx = _load_yaml(index_path)
                total_idx = idx.get("total_parameters")
                if isinstance(total_idx, int) and total_idx != total:
                    errors.append(
                        f"_index.yaml total_parameters mismatch: index={total_idx}, registers={total}"
                    )
            except Exception as exc:
                warnings.append(f"Failed to read _index.yaml for validation: {exc}")
        elif index_path and not index_path.exists():
            warnings.append(f"_index.yaml not found: {index_path}")

        if rules_dir:
            if not rules_dir.exists():
                warnings.append(f"Rules directory not found: {rules_dir}")
            else:
                mdc_files = list(rules_dir.glob("device-*.mdc"))
                if not mdc_files:
                    warnings.append("No device-*.mdc rule found in rules directory.")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ParseManual Type 1 register file.")
    parser.add_argument("--registers", required=True, help="Path to device_registers.yaml")
    parser.add_argument("--phase", type=int, default=1, choices=[1, 2, 3, 4])
    parser.add_argument("--knowledge-dir", default=None, help="Optional path to knowledge directory.")
    parser.add_argument("--index", default=None, help="Optional path to knowledge/_index.yaml.")
    parser.add_argument("--rules-dir", default=None, help="Optional path to .cursor/rules for rule checks.")
    args = parser.parse_args()

    register_path = Path(args.registers).expanduser().resolve()
    if not register_path.exists():
        print(f"ERROR: file not found: {register_path}", file=sys.stderr)
        return 2

    try:
        data = _load_yaml(register_path)
    except Exception as exc:
        print(f"ERROR: failed to load YAML: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate(
        data,
        args.phase,
        knowledge_dir=Path(args.knowledge_dir).expanduser().resolve() if args.knowledge_dir else None,
        index_path=Path(args.index).expanduser().resolve() if args.index else None,
        rules_dir=Path(args.rules_dir).expanduser().resolve() if args.rules_dir else None,
    )

    print(f"Validated: {register_path}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    for msg in warnings:
        print(f"WARN: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
