#!/usr/bin/env python3
"""Run ParseManual Phase 2 steps for one device.

Assumes Phase 1 is complete: parsed.json and parsed.md exist.
device_registers.yaml is optional — when absent, register-dependent steps are skipped.
Runs: classify -> knowledge extraction -> [link knowledge refs] -> index -> rules -> [validate] -> [spot-check].
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional


SCRIPT_DIR = Path(__file__).resolve().parent


def _run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.run(command, check=True)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _infer_repo_root(device_dir: Path) -> Optional[Path]:
    current = device_dir.resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ParseManual Phase 2 pipeline.")
    parser.add_argument("--device-dir", required=True, help="Device directory with Phase 1 outputs")
    parser.add_argument("--manufacturer", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--manual-source", required=True)
    parser.add_argument("--rules-dir", default=None, help="Optional output .cursor/rules path")
    parser.add_argument("--claude-path", default=None, help="Optional CLAUDE.md path")
    parser.add_argument("--agents-path", default=None, help="Optional .cursor/AGENTS.md path")
    parser.add_argument("--llm-model", default="unspecified")
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument(
        "--refine-knowledge",
        action="store_true",
        help="Run refine_knowledge.py after knowledge extraction.",
    )
    args = parser.parse_args()

    device_dir = Path(args.device_dir).expanduser().resolve()
    cache_dir = device_dir / ".parse-cache"
    parsed_json = cache_dir / "parsed.json"
    sections_json = cache_dir / "sections.json"
    registers_yaml = device_dir / "device_registers.yaml"
    knowledge_dir = device_dir / "knowledge"
    index_yaml = knowledge_dir / "_index.yaml"
    metadata_json = cache_dir / "metadata.json"

    if not parsed_json.exists():
        print(f"ERROR: Phase 1 output missing: {parsed_json}", file=sys.stderr)
        return 2

    has_registers = registers_yaml.exists()

    repo_root = _infer_repo_root(device_dir)
    rules_dir = Path(args.rules_dir).expanduser().resolve() if args.rules_dir else None
    claude_path = Path(args.claude_path).expanduser().resolve() if args.claude_path else None
    agents_path = Path(args.agents_path).expanduser().resolve() if args.agents_path else None
    if repo_root:
        if rules_dir is None:
            rules_dir = repo_root / ".cursor" / "rules"
        if claude_path is None and (repo_root / "CLAUDE.md").exists():
            claude_path = repo_root / "CLAUDE.md"
        if agents_path is None and (repo_root / ".cursor" / "AGENTS.md").exists():
            agents_path = repo_root / ".cursor" / "AGENTS.md"

    print("=== Phase 2: Classify sections ===")
    _run(
        [
            sys.executable,
            str(SCRIPT_DIR / "classify_sections.py"),
            "--parsed-json",
            str(parsed_json),
            "--output-sections",
            str(sections_json),
        ]
    )

    print("\n=== Phase 2: Extract knowledge ===")
    _run(
        [
            sys.executable,
            str(SCRIPT_DIR / "extract_knowledge.py"),
            "--sections-json",
            str(sections_json),
            "--parsed-json",
            str(parsed_json),
            "--output-knowledge-dir",
            str(knowledge_dir),
            "--parse-cache-images-dir",
            str(cache_dir / "images"),
            "--output-images-dir",
            str(device_dir / "images"),
            "--device-name",
            f"{args.manufacturer} {args.model}",
        ]
    )

    if args.refine_knowledge:
        print("\n=== Phase 2: Refine low-confidence knowledge files ===")
        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "refine_knowledge.py"),
                "--knowledge-dir",
                str(knowledge_dir),
                "--prompt-path",
                str(SCRIPT_DIR.parent / "prompts" / "extract_knowledge.md"),
            ]
        )

    if has_registers:
        print("\n=== Phase 2: Link parameter knowledge refs ===")
        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "link_knowledge_refs.py"),
                "--registers",
                str(registers_yaml),
                "--knowledge-dir",
                str(knowledge_dir),
            ]
        )
    else:
        print("\nSKIP: link_knowledge_refs (no device_registers.yaml).")

    print("\n=== Phase 2: Generate index ===")
    metadata = _read_json(metadata_json)
    index_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "generate_index.py"),
        "--knowledge-dir",
        str(knowledge_dir),
        "--output-index",
        str(index_yaml),
        "--llm-model",
        args.llm_model,
        "--parser-mode",
        str(metadata.get("mode", "accurate")),
        "--manual-source",
        args.manual_source,
        "--manufacturer",
        args.manufacturer,
        "--model",
        args.model,
    ]
    if has_registers:
        index_cmd.extend(["--registers", str(registers_yaml)])
    quality_score = metadata.get("quality_score")
    if quality_score is not None:
        index_cmd.extend(["--parse-quality-score", str(quality_score)])
    _run(index_cmd)

    print("\n=== Phase 2: Generate rules ===")
    if rules_dir is not None:
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "generate_rules.py"),
            "--knowledge-dir",
            str(knowledge_dir),
            "--rules-dir",
            str(rules_dir),
            "--manufacturer",
            args.manufacturer,
            "--model",
            args.model,
        ]
        if has_registers and registers_yaml.exists():
            cmd.extend(["--registers", str(registers_yaml)])
        if claude_path is not None:
            cmd.extend(["--claude-path", str(claude_path)])
        if agents_path is not None:
            cmd.extend(["--agents-path", str(agents_path)])
        _run(cmd)
    else:
        print("Skipped: no repo root / rules-dir found.")

    if has_registers:
        print("\n=== Phase 2: Validate (phase 2) ===")
        validate_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "validate_registers.py"),
            "--registers",
            str(registers_yaml),
            "--phase",
            "2",
            "--knowledge-dir",
            str(knowledge_dir),
            "--index",
            str(index_yaml),
        ]
        if rules_dir is not None:
            validate_cmd.extend(["--rules-dir", str(rules_dir)])
        _run(validate_cmd)

        print("\n=== Phase 2: Spot check ===")
        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "spot_check.py"),
                "--registers",
                str(registers_yaml),
                "--sample-size",
                str(args.sample_size),
                "--no-review",
            ]
        )
    else:
        print("\nSKIP: validate + spot_check (no device_registers.yaml).")

    print("\n=== Phase 2 pipeline complete ===")
    print(f"Knowledge dir: {knowledge_dir}")
    print(f"Knowledge index: {index_yaml}")
    if has_registers:
        print(f"Registers: {registers_yaml}")
    else:
        print("Registers: none (knowledge-only device)")
    if rules_dir is not None:
        print(f"Rules dir: {rules_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
