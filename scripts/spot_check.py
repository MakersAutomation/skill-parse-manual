#!/usr/bin/env python3
"""Select random parameter entries for human PDF spot-check."""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys
from typing import Any, Dict, List

import yaml


def _load_parameters(register_path: Path) -> List[Dict[str, Any]]:
    with register_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("Top-level YAML must be a mapping.")
    params = data.get("parameters")
    if not isinstance(params, list):
        raise ValueError("`parameters` must be a list.")
    cleaned: List[Dict[str, Any]] = [p for p in params if isinstance(p, dict)]
    return cleaned


def _safe_address(param: Dict[str, Any]) -> str:
    protocols = param.get("protocols")
    if isinstance(protocols, dict):
        modbus = protocols.get("modbus")
        if isinstance(modbus, dict):
            address = modbus.get("address")
            if isinstance(address, int):
                return hex(address)
            if address is not None:
                return str(address)
    return "-"


def _safe_source_page(param: Dict[str, Any]) -> str:
    # Optional field if extraction process carries page metadata.
    value = param.get("source_page")
    return str(value) if value is not None else "-"


def main() -> int:
    parser = argparse.ArgumentParser(description="Select random parameters for manual spot-check.")
    parser.add_argument("--registers", required=True, help="Path to device_registers.yaml")
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip manual review prompt and only print sample output.",
    )
    args = parser.parse_args()

    register_path = Path(args.registers).expanduser().resolve()
    if not register_path.exists():
        print(f"ERROR: file not found: {register_path}", file=sys.stderr)
        return 2

    try:
        params = _load_parameters(register_path)
    except Exception as exc:
        print(f"ERROR: failed to load parameter list: {exc}", file=sys.stderr)
        return 2

    if not params:
        print("ERROR: no parameters found in register file.", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    k = min(args.sample_size, len(params))
    sample = rng.sample(params, k=k)

    print(f"Spot-check sample from: {register_path}")
    print(f"Total parameters: {len(params)}")
    print(f"Sample size: {k}")
    print("")
    print("Verify each sampled parameter against the source PDF:")
    print("- Parameter ID")
    print("- Modbus address")
    print("- Data type")
    print("- Range")
    print("- Source page (if available)")
    print("")

    for idx, param in enumerate(sample, start=1):
        pid = param.get("id", "-")
        name = param.get("name", "-")
        dtype = param.get("data_type", "-")
        rng_val = param.get("range", "-")
        print(f"[{idx}] {pid} - {name}")
        print(f"    address: {_safe_address(param)}")
        print(f"    data_type: {dtype}")
        print(f"    range: {rng_val}")
        print(f"    source_page: {_safe_source_page(param)}")
        print("")

    if args.no_review:
        print("Review skipped (--no-review).")
        return 0

    print("Manual review required: confirm sampled entries match the PDF before approving extraction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
