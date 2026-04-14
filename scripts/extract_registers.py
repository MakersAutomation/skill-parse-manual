#!/usr/bin/env python3
"""Extract Type 1 device_registers.yaml from parse-cache artifacts."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

PARAM_ID_RE = re.compile(r"^[CFRU][0-9A-F]{2}\.[0-9A-F]{2}$")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    # Preserve exponent notation from HTML superscripts (e.g., 2<sup>31</sup> -> 2^31)
    text = re.sub(r"<sup>\s*([+-]?\d+)\s*</sup>", r"^\1", value, flags=re.IGNORECASE)
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    return text


def parse_table_rows(table_html: str) -> Tuple[List[str], List[List[str]]]:
    row_chunks = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
    rows: List[List[str]] = []
    for row in row_chunks:
        cell_chunks = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
        cells = [clean_text(c) for c in cell_chunks]
        if cells:
            rows.append(cells)
    if not rows:
        return [], []
    header = [c.lower() for c in rows[0]]
    return header, rows[1:]


def header_index(header: List[str], candidates: List[str]) -> Optional[int]:
    for i, h in enumerate(header):
        for c in candidates:
            if c in h:
                return i
    return None


def parse_power_expr(value: str) -> Optional[int]:
    v = value.strip().replace(" ", "")
    if not v:
        return None
    if re.match(r"^-?\d+$", v):
        return int(v)
    # Handle forms like -2^31 or 2^31-1
    m = re.match(r"^(-?)2\^(\d+)(-1)?$", v)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        n = int(m.group(2))
        out = sign * (2**n)
        if m.group(3):
            out -= 1
        return out
    return None


def parse_number(value: str) -> Optional[Union[int, float]]:
    v = value.strip()
    if not v or v == "-":
        return None
    power_val = parse_power_expr(v)
    if power_val is not None:
        return power_val
    if re.match(r"^-?\d+(?:\.\d+)?$", v):
        if "." in v:
            return float(v)
        return int(v)
    return None


def parse_range(value: str) -> Optional[Dict[str, Union[int, float]]]:
    v = value.strip()
    if not v or v == "-":
        return None
    v_compact = v.replace(" ", "")
    # LaTeX / math cells: 2^{32} -> 2^32
    v_compact = re.sub(r"\^\{(\d+)\}", r"^\1", v_compact)
    # Forms like 0-(2^32-1) or 1-(2^32-1) (U32 full range in A6-RS tables / <math> cells)
    m_uint_span = re.match(r"^(\d+)-\((2\^\d+(?:-1)?)\)$", v_compact)
    if m_uint_span:
        lo = int(m_uint_span.group(1))
        hi = parse_power_expr(m_uint_span.group(2))
        if hi is not None:
            return {"min": lo, "max": hi}
    # Handle forms like -2^31-(2^31-1)
    m_power = re.match(r"^\(?(-?2\^\d+)\)?\s*-\s*\(?(-?2\^\d+(?:-1)?)\)?$", v_compact)
    if m_power:
        lo = parse_power_expr(m_power.group(1))
        hi = parse_power_expr(m_power.group(2))
        if lo is not None and hi is not None:
            return {"min": lo, "max": hi}
    # Common formats: "0-20000", "1 to 31", "-9999-9999"
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:to|-)\s*(-?\d+(?:\.\d+)?)\s*$", v.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    lo_raw = m.group(1)
    hi_raw = m.group(2)
    lo: Union[int, float] = float(lo_raw) if "." in lo_raw else int(lo_raw)
    hi: Union[int, float] = float(hi_raw) if "." in hi_raw else int(hi_raw)
    return {"min": lo, "max": hi}


def map_data_type(value: str) -> str:
    v = value.strip().lower()
    mapping = {
        "u16": "uint16",
        "i16": "int16",
        "u32": "uint32",
        "i32": "int32",
        "f32": "float32",
        "bool": "bool",
    }
    return mapping.get(v, "string")


def register_count_from_data_type(data_type: str) -> int:
    if data_type in ("uint32", "int32", "float32"):
        return 2
    return 1


def normalize_bool_like_register(rec: Dict[str, Any]) -> None:
    """Two-state 0/1 with labels -> bool, drop redundant range (Phase 1 validator)."""
    if rec.get("data_type") == "bitfield" or rec.get("bit_layout"):
        return
    vm = rec.get("value_map")
    if not isinstance(vm, dict) or not vm:
        return
    try:
        int_keys = {int(k) for k in vm.keys()}
    except (TypeError, ValueError):
        return
    if int_keys != {0, 1}:
        return
    rng = rec.get("range")
    if not isinstance(rng, dict) or rng.get("min") != 0 or rng.get("max") != 1:
        return
    rec["data_type"] = "bool"
    rec["range"] = None
    modbus = rec.get("protocols", {}).get("modbus")
    if isinstance(modbus, dict):
        modbus["register_count"] = register_count_from_data_type("bool")


def parse_unit_and_scale(unit_text: str) -> Tuple[Optional[str], Optional[float]]:
    unit = unit_text.strip()
    if not unit or unit == "-":
        return None, None
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.+)$", unit)
    if not m:
        return unit, None
    scale = float(m.group(1))
    normalized_unit = m.group(2).strip()
    if not normalized_unit:
        return unit, None
    return normalized_unit, scale


def parse_value_map(options_text: str) -> Optional[Dict[str, str]]:
    text = options_text.strip()
    if not text or text == "-":
        return None
    matches = re.findall(r"(-?\d+)\s*:\s*([^:]+?)(?=(?:\s+-?\d+\s*:)|$)", text)
    if not matches:
        return None
    mapped: Dict[str, str] = {}
    for key, label in matches:
        mapped[str(int(key))] = WS_RE.sub(" ", label).strip()
    return mapped if mapped else None


def parse_bit_layout(options_text: str) -> Optional[Dict[str, str]]:
    """Extract Bit00 / Bit01 / … labels from options text (bitfield registers)."""
    text = WS_RE.sub(" ", options_text.strip())
    if not text or text == "-":
        return None
    matches = list(re.finditer(r"Bit(\d+)\s*:\s*", text, flags=re.IGNORECASE))
    if not matches:
        return None
    out: Dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        idx = str(int(m.group(1)))
        desc = text[start:end].strip()
        if desc:
            out[idx] = desc
    return out if out else None


def map_write_condition(value: str) -> Optional[str]:
    v = value.strip().lower()
    if not v or v == "-":
        return None
    if "at stop" in v:
        return "stopped"
    if "during operation" in v:
        return "any_state"
    return None


def map_takes_effect(value: str) -> Optional[str]:
    v = value.strip().lower()
    if not v or v == "-":
        return None
    if "immediate" in v:
        return "immediate"
    if "power" in v:
        return "power_cycle"
    return None


def id_to_modbus_address(pid: str) -> int:
    """16-bit register address: high byte = group nibble pair (C00 -> 0x00), low = offset (C00.13 -> 0x13)."""
    group = pid[1:3]
    offset = pid[4:6]
    return int(group + offset, 16)


def pdf_page_index_to_source_page(page: Optional[int], *, delta: int) -> Optional[int]:
    """Map Marker 0-based PDF page index to manual `source_page` (printed footer).

    File page (1-based) is ``page + 1``. ``delta`` adjusts file index to printed numbering
    (A6-RS: ``-2`` matches footer vs Datalab page index).
    """
    if not isinstance(page, int):
        return None
    return max(1, page + 1 + delta)


def modbus_protocol_block(pid: str, data_type: str) -> Dict[str, Any]:
    addr = id_to_modbus_address(pid)
    return {
        "address": addr,
        "address_hex": f"0x{addr:04X}",
        "table": "holding",
        "register_count": register_count_from_data_type(data_type),
    }


def is_placeholder_brief(value: Optional[str]) -> bool:
    if not value:
        return True
    return value.strip().lower() == "no description in manual."


def extract_group_labels_from_markdown(parsed_md: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in parsed_md.splitlines():
        m = re.search(r"\|\s*8\.\d+\s*\|\s*([^|]+?)\s*\((?:[0-9A-Fa-f]+h/)?([CFRU][0-9A-Fa-f]{2})\)\s*\|", line)
        if m:
            out[m.group(2).lower()] = m.group(1).strip()
    return out


def iter_nodes_with_page(node: Any, inherited_page: Optional[int] = None) -> List[Tuple[Dict[str, Any], Optional[int]]]:
    out: List[Tuple[Dict[str, Any], Optional[int]]] = []
    if isinstance(node, dict):
        page = node.get("page", inherited_page)
        out.append((node, page if isinstance(page, int) else inherited_page))
        for v in node.values():
            if isinstance(v, dict):
                out.extend(iter_nodes_with_page(v, page if isinstance(page, int) else inherited_page))
            elif isinstance(v, list):
                for item in v:
                    out.extend(iter_nodes_with_page(item, page if isinstance(page, int) else inherited_page))
    elif isinstance(node, list):
        for item in node:
            out.extend(iter_nodes_with_page(item, inherited_page))
    return out


def merge_record(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    existing_priority = int(merged.get("__priority", 0))
    candidate_priority = int(candidate.get("__priority", 0))
    if candidate_priority > existing_priority:
        # Prefer source_page/name/brief from higher-priority tables (typically Chapter 8 master tables).
        for key in ("source_page", "name", "brief", "data_type", "access"):
            if candidate.get(key) not in (None, "", "-"):
                merged[key] = candidate[key]
        merged["__priority"] = candidate_priority

    for key in ("range", "default", "unit", "write_condition", "takes_effect", "source_page"):
        if merged.get(key) is None and candidate.get(key) is not None:
            merged[key] = candidate[key]

    if merged.get("name") in (None, "", merged["id"]) and candidate.get("name") not in (None, "", candidate["id"]):
        merged["name"] = candidate["name"]

    if merged.get("data_type") == "string" and candidate.get("data_type") not in (None, "string"):
        merged["data_type"] = candidate["data_type"]

    if is_placeholder_brief(merged.get("brief")) and not is_placeholder_brief(candidate.get("brief")):
        merged["brief"] = candidate["brief"]

    if merged.get("scale") is None and candidate.get("scale") is not None:
        merged["scale"] = candidate["scale"]

    if candidate.get("bit_layout"):
        merged["bit_layout"] = candidate["bit_layout"]
        merged["value_map"] = None
        merged["data_type"] = "bitfield"
        merged["protocols"] = merged.get("protocols") or {}
        merged["protocols"]["modbus"] = modbus_protocol_block(merged["id"], "bitfield")
    elif not merged.get("bit_layout"):
        if merged.get("value_map") is None and candidate.get("value_map") is not None:
            merged["value_map"] = candidate["value_map"]
    else:
        merged["value_map"] = None

    if merged.get("protocols", {}).get("modbus", {}).get("register_count") == 1:
        cand_count = candidate.get("protocols", {}).get("modbus", {}).get("register_count")
        if cand_count == 2:
            merged["protocols"]["modbus"]["register_count"] = 2

    # For equal-priority records, prefer later page entries (typically Chapter 8 tables)
    if candidate_priority == existing_priority:
        ex_page = merged.get("source_page")
        cand_page = candidate.get("source_page")
        if isinstance(ex_page, int) and isinstance(cand_page, int) and cand_page > ex_page:
            merged["source_page"] = cand_page

    return merged


def extract_records(
    parsed_json: Dict[str, Any],
    valid_groups: set[str],
    *,
    source_page_delta: int,
) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for node, inherited_page in iter_nodes_with_page(parsed_json):
        html_blob = node.get("html")
        page = node.get("page", inherited_page)
        if not isinstance(html_blob, str) or "<table" not in html_blob.lower():
            continue
        tables = re.findall(r"<table[^>]*>.*?</table>", html_blob, flags=re.IGNORECASE | re.DOTALL)
        for table in tables:
            header, rows = parse_table_rows(table)
            if not header:
                continue
            table_priority = 1
            if (
                header_index(header, ["index"]) is not None
                and header_index(header, ["data type", "datatype"]) is not None
                and header_index(header, ["modification mode"]) is not None
                and header_index(header, ["effective time"]) is not None
            ):
                table_priority = 3
            elif header_index(header, ["value range", "range"]) is not None and header_index(header, ["default"]) is not None:
                table_priority = 2

            parameter_idx = header_index(header, ["parameter"])
            name_idx = header_index(header, ["name"])
            range_idx = header_index(header, ["value range", "range"])
            default_idx = header_index(header, ["default"])
            unit_idx = header_index(header, ["unit"])
            options_idx = header_index(header, ["options", "description"])
            dtype_idx = header_index(header, ["data type", "datatype"])
            mod_idx = header_index(header, ["modification mode"])
            eff_idx = header_index(header, ["effective time"])

            if parameter_idx is None or name_idx is None:
                continue

            for row in rows:
                if parameter_idx >= len(row) or name_idx >= len(row):
                    continue
                pid = row[parameter_idx].strip().upper()
                if not PARAM_ID_RE.match(pid):
                    continue
                if pid.split(".")[0] not in valid_groups:
                    continue

                name = row[name_idx].strip()
                range_text = row[range_idx].strip() if range_idx is not None and range_idx < len(row) else ""
                default_text = row[default_idx].strip() if default_idx is not None and default_idx < len(row) else ""
                unit_text = row[unit_idx].strip() if unit_idx is not None and unit_idx < len(row) else ""
                options_text = row[options_idx].strip() if options_idx is not None and options_idx < len(row) else ""
                dtype_text = row[dtype_idx].strip() if dtype_idx is not None and dtype_idx < len(row) else ""
                mod_text = row[mod_idx].strip() if mod_idx is not None and mod_idx < len(row) else ""
                eff_text = row[eff_idx].strip() if eff_idx is not None and eff_idx < len(row) else ""
                unit, scale = parse_unit_and_scale(unit_text)
                base_dtype = map_data_type(dtype_text) if dtype_text else "uint16"
                bit_layout = parse_bit_layout(options_text)
                if bit_layout:
                    data_type = "bitfield"
                    value_map = None
                else:
                    data_type = base_dtype
                    value_map = parse_value_map(options_text)
                access = "read_only" if pid.startswith("U") else "read_write"

                rec = {
                    "id": pid,
                    "name": name or pid,
                    "group": pid.split(".")[0].lower(),
                    "brief": options_text if options_text and options_text != "-" else "No description in manual.",
                    "data_type": data_type,
                    "access": access,
                    "range": parse_range(range_text),
                    "default": parse_number(default_text),
                    "scale": scale,
                    "unit": unit,
                    "value_map": value_map,
                    "bit_layout": bit_layout,
                    "dependencies": [],
                    "write_condition": map_write_condition(mod_text),
                    "takes_effect": map_takes_effect(eff_text),
                    "knowledge_ref": None,
                    "source_page": pdf_page_index_to_source_page(page, delta=source_page_delta),
                    "__priority": table_priority,
                    "protocols": {"modbus": modbus_protocol_block(pid, data_type)},
                }
                if pid in records:
                    records[pid] = merge_record(records[pid], rec)
                else:
                    records[pid] = rec

    # Build first-seen page map for parameter mentions in non-table text.
    mention_page: Dict[str, int] = {}
    for node, inherited_page in iter_nodes_with_page(parsed_json):
        page = node.get("page", inherited_page)
        html_blob = node.get("html")
        if not isinstance(html_blob, str) or "<table" in html_blob.lower():
            continue
        if not isinstance(page, int):
            continue
        text = clean_text(html_blob)
        if not text:
            continue
        for m in re.finditer(r"\b([CFRU][0-9A-F]{2}\.[0-9A-F]{2})\b", text):
            pid = m.group(1).upper()
            if pid.split(".")[0] not in valid_groups:
                continue
            if pid not in mention_page:
                mention_page[pid] = pdf_page_index_to_source_page(page, delta=source_page_delta)

    # Fallback for IDs referenced in narrative text but not present in tables.
    for node, inherited_page in iter_nodes_with_page(parsed_json):
        page = node.get("page", inherited_page)
        html_blob = node.get("html")
        if not isinstance(html_blob, str) or "<table" in html_blob.lower():
            continue
        text = clean_text(html_blob)
        if not text:
            continue
        for m in re.finditer(r"\b([CFRU][0-9A-F]{2}\.[0-9A-F]{2})\b", text):
            pid = m.group(1).upper()
            if pid in records:
                continue
            if pid.split(".")[0] not in valid_groups:
                continue
            records[pid] = {
                "id": pid,
                "name": pid,
                "group": pid.split(".")[0].lower(),
                "brief": text[max(0, m.start() - 120): min(len(text), m.end() + 160)].strip(),
                "data_type": "uint16",
                "access": "read_only" if pid.startswith("U") else "read_write",
                "range": None,
                "default": None,
                "scale": None,
                "unit": None,
                "value_map": None,
                "bit_layout": None,
                "dependencies": [],
                "write_condition": None,
                "takes_effect": None,
                "knowledge_ref": None,
                "source_page": mention_page.get(pid)
                or pdf_page_index_to_source_page(page, delta=source_page_delta),
                "__priority": 0,
                "protocols": {"modbus": modbus_protocol_block(pid, "uint16")},
            }

    for rec in records.values():
        normalize_bool_like_register(rec)

    # Ensure brief is always meaningful even when table options are "-".
    for pid, rec in records.items():
        if not is_placeholder_brief(rec.get("brief")):
            continue
        parts: List[str] = []
        name = rec.get("name") or pid
        parts.append(str(name))
        rng = rec.get("range")
        if isinstance(rng, dict) and "min" in rng and "max" in rng:
            parts.append(f"Range {rng['min']} to {rng['max']}.")
        vm = rec.get("value_map")
        if rec.get("data_type") == "bool" and isinstance(vm, dict) and vm:
            ordered = sorted(vm.items(), key=lambda kv: int(kv[0]))
            parts.append("States: " + "; ".join(f"{k}={v}" for k, v in ordered) + ".")
        if rec.get("default") is not None:
            parts.append(f"Default {rec['default']}.")
        if rec.get("unit"):
            parts.append(f"Unit {rec['unit']}.")
        if rec.get("write_condition"):
            parts.append(f"Write condition {rec['write_condition']}.")
        if rec.get("takes_effect"):
            parts.append(f"Takes effect {rec['takes_effect']}.")
        rec["brief"] = " ".join(parts) if parts else "No description in manual."
        rec.pop("__priority", None)

    # Drop transient fields from non-placeholder records.
    for rec in records.values():
        rec.pop("__priority", None)
        if rec.get("bit_layout") is None:
            rec.pop("bit_layout", None)

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Type 1 device_registers.yaml from parse-cache.")
    parser.add_argument("--parsed-md", required=True)
    parser.add_argument("--parsed-json", required=True)
    parser.add_argument("--output-registers", required=True)
    parser.add_argument("--manufacturer", default="StepperOnline")
    parser.add_argument("--model", default="A6-RS")
    parser.add_argument("--manual-source", default="A6-RS_series_servo_drive_manual.pdf")
    parser.add_argument(
        "--source-page-delta",
        type=int,
        default=-2,
        help="Added to (PDF file page, 1-based) to get source_page (printed footer). "
        "A6-RS uses -2; use 0 if file page index already matches the manual.",
    )
    args = parser.parse_args()

    parsed_md = Path(args.parsed_md).expanduser().resolve().read_text(encoding="utf-8", errors="ignore")
    parsed_json = json.loads(Path(args.parsed_json).expanduser().resolve().read_text(encoding="utf-8"))
    out_path = Path(args.output_registers).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    group_labels = extract_group_labels_from_markdown(parsed_md)
    valid_groups = {k.upper() for k in group_labels.keys()}
    records = extract_records(parsed_json, valid_groups=valid_groups, source_page_delta=args.source_page_delta)

    parameters = sorted(records.values(), key=lambda p: p["id"])
    groups = [{"id": gid, "label": group_labels.get(gid, gid.upper())} for gid in sorted({p["group"] for p in parameters})]

    doc = {
        "schema_version": "1.0",
        "extraction_metadata": {
            "source_page_basis": "printed_manual_footer",
            "pdf_file_page_1based_to_source_page_delta": args.source_page_delta,
            "source_page_note": (
                "source_page matches the printed page number in the manual footer: "
                "(Marker 0-based page index) + 1 + source_page_delta (default -2 for A6-RS)."
            ),
            "scale_note": (
                "scale is null when the register value matches the manual's stated engineering value 1:1 "
                "(no leading numeric factor in the unit column). Use an explicit numeric scale only when "
                "the manual gives a factor (e.g. 0.1 Hz). Do not use scale: 1 for that case."
            ),
            "modbus_address_note": (
                "protocols.modbus.address is the 16-bit holding-register index derived from the parameter ID: "
                "C GG.OO -> 0xGG00 | 0xOO (e.g. C00.13 -> 0x0013 = 19 decimal). It is not the trailing OO alone."
            ),
        },
        "device": {
            "manufacturer": args.manufacturer,
            "model": args.model,
            "firmware": None,
            "manual_source": args.manual_source,
            "manual_revision": None,
            "manual_language": "en",
            "source_language": None,
            "device_type": "servo_drive",
            "communication": {
                "supported_protocols": ["modbus_rtu"],
                "modbus": {
                    "default_baud": None,
                    "default_slave_id": None,
                    "addressing": "1_based",
                    "byte_order": "big_endian",
                    "word_order": "big_endian",
                },
            },
        },
        "groups": groups,
        "parameters": parameters,
    }

    out_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(f"Groups: {len(groups)}")
    print(f"Parameters: {len(parameters)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
