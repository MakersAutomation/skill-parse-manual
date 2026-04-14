#!/usr/bin/env python3
"""Generate device rule, inventory rule, and optional doc index sections."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any, Dict, List

import yaml


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _safe_model_glob(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", model.lower())


def _load_registers(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("device_registers.yaml top-level must be mapping.")
    return data


def _key_topics(knowledge_dir: Path) -> List[str]:
    topics: List[str] = []
    for md in sorted(knowledge_dir.rglob("*.md")):
        if md.name == "_index.md":
            continue
        rel = md.relative_to(knowledge_dir).as_posix()
        topics.append(rel)
    return topics[:20]


def _device_rule_content(
    manufacturer: str,
    model: str,
    model_slug: str,
    doc_root_rel: str,
    topics: List[str],
    has_registers: bool,
) -> str:
    topic_lines = "\n".join(f"- `{doc_root_rel}/knowledge/{t}`" for t in topics) if topics else "- No knowledge files generated."
    model_glob = _safe_model_glob(model)

    register_block = ""
    if has_registers:
        register_block = f"""**Register Lookup**: `{doc_root_rel}/device_registers.yaml`
Complete parameter list with addresses, types, ranges, and defaults.

"""

    return f"""---
description: "{manufacturer} {model} device reference"
globs:
  - "**/{model_glob}*"
  - "**/ref/devices/{model_slug}/**"
alwaysApply: false
---

## {manufacturer} {model}

When writing code that communicates with or configures the {manufacturer} {model}, reference:

{register_block}**Knowledge Base**: `{doc_root_rel}/knowledge/`
See `_index.yaml` for coverage and confidence metadata.

Key topics:
{topic_lines}
"""


def _inventory_entry(manufacturer: str, model: str, doc_root_rel: str) -> str:
    return f"- **{manufacturer} {model}**: `{doc_root_rel}/device_registers.yaml` (knowledge: `{doc_root_rel}/knowledge/_index.yaml`)"


def _upsert_inventory(path: Path, entry: str) -> None:
    header = """---
description: "Device documentation inventory — lists all parsed device manuals"
alwaysApply: false
---

## Device Inventory
"""
    if not path.exists():
        path.write_text(f"{header}\n{entry}\n", encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    if entry in text:
        return
    if text.endswith("\n"):
        text += f"{entry}\n"
    else:
        text += f"\n{entry}\n"
    path.write_text(text, encoding="utf-8")


def _upsert_claude(path: Path, entry: str) -> None:
    begin = "<!-- parse-manual-device-docs:start -->"
    end = "<!-- parse-manual-device-docs:end -->"

    block = f"""## Device Documentation
{begin}
{entry}
{end}
"""
    if not path.exists():
        path.write_text(f"{block}\n", encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    if begin in text and end in text:
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), flags=re.DOTALL)
        existing = pattern.search(text)
        lines = []
        if existing:
            content = existing.group(0)
            lines = [ln for ln in content.splitlines()[1:-1] if ln.strip()]
        if entry not in lines:
            lines.append(entry)
        replacement = begin + "\n" + "\n".join(lines) + "\n" + end
        text = pattern.sub(replacement, text)
        path.write_text(text, encoding="utf-8")
        return

    if text.endswith("\n"):
        text += "\n"
    else:
        text += "\n\n"
    text += block + "\n"
    path.write_text(text, encoding="utf-8")


def _upsert_agents(path: Path, entry: str) -> None:
    begin = "<!-- parse-manual-device-docs:start -->"
    end = "<!-- parse-manual-device-docs:end -->"

    block = f"""## Device Documentation
{begin}
{entry}
{end}
"""
    if not path.exists():
        path.write_text(f"{block}\n", encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    if begin in text and end in text:
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), flags=re.DOTALL)
        existing = pattern.search(text)
        lines = []
        if existing:
            content = existing.group(0)
            lines = [ln for ln in content.splitlines()[1:-1] if ln.strip()]
        if entry not in lines:
            lines.append(entry)
        replacement = begin + "\n" + "\n".join(lines) + "\n" + end
        text = pattern.sub(replacement, text)
        path.write_text(text, encoding="utf-8")
        return

    if text.endswith("\n"):
        text += "\n"
    else:
        text += "\n\n"
    text += block + "\n"
    path.write_text(text, encoding="utf-8")


def _infer_repo_root(path: Path) -> Path:
    current = path.resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ParseManual rules and optional docs index sections.")
    parser.add_argument("--registers", default=None, help="Path to device_registers.yaml (optional for knowledge-only devices)")
    parser.add_argument("--knowledge-dir", required=True, help="Path to knowledge directory")
    parser.add_argument("--rules-dir", required=True, help="Path to .cursor/rules")
    parser.add_argument("--manufacturer", default=None, help="Device manufacturer (used when no registers file)")
    parser.add_argument("--model", default=None, help="Device model (used when no registers file)")
    parser.add_argument("--claude-path", default=None, help="Optional path to CLAUDE.md")
    parser.add_argument("--agents-path", default=None, help="Optional path to .cursor/AGENTS.md")
    args = parser.parse_args()

    knowledge_dir = Path(args.knowledge_dir).expanduser().resolve()
    rules_dir = Path(args.rules_dir).expanduser().resolve()
    rules_dir.mkdir(parents=True, exist_ok=True)

    registers_path: Path | None = None
    reg: Dict[str, Any] = {}
    if args.registers:
        registers_path = Path(args.registers).expanduser().resolve()
        if registers_path.exists():
            reg = _load_registers(registers_path)

    device = reg.get("device", {}) if isinstance(reg.get("device"), dict) else {}
    manufacturer = str(args.manufacturer or device.get("manufacturer") or "Unknown")
    model = str(args.model or device.get("model") or "Unknown")
    model_slug = _slug(model)

    device_root = knowledge_dir.parent
    repo_root = _infer_repo_root(device_root)
    try:
        doc_root_rel = device_root.relative_to(repo_root).as_posix()
    except ValueError:
        doc_root_rel = device_root.as_posix()
    topics = _key_topics(knowledge_dir)

    has_registers = registers_path is not None and registers_path.exists()

    device_rule_path = rules_dir / f"device-{model_slug}.mdc"
    device_rule_path.write_text(
        _device_rule_content(
            manufacturer=manufacturer,
            model=model,
            model_slug=model_slug,
            doc_root_rel=doc_root_rel,
            topics=topics,
            has_registers=has_registers,
        ),
        encoding="utf-8",
    )

    inventory_path = rules_dir / "device-inventory.mdc"
    if has_registers:
        inv_entry = _inventory_entry(manufacturer=manufacturer, model=model, doc_root_rel=doc_root_rel)
    else:
        inv_entry = f"- **{manufacturer} {model}**: `{doc_root_rel}/knowledge/_index.yaml` (knowledge only, no registers)"
    _upsert_inventory(inventory_path, inv_entry)

    if args.claude_path:
        _upsert_claude(Path(args.claude_path).expanduser().resolve(), inv_entry)
    if args.agents_path:
        _upsert_agents(Path(args.agents_path).expanduser().resolve(), inv_entry)

    print(f"Wrote: {device_rule_path}")
    print(f"Updated: {inventory_path}")
    if args.claude_path:
        print(f"Updated: {Path(args.claude_path).expanduser().resolve()}")
    if args.agents_path:
        print(f"Updated: {Path(args.agents_path).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
