#!/usr/bin/env python3
"""Classify parsed manual pages into section types for knowledge extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
PARAM_ID_RE = re.compile(r"\b[CFRU][0-9A-F]{2}\.[0-9A-F]{2}\b", flags=re.IGNORECASE)


def _clean_text(value: str) -> str:
    text = TAG_RE.sub(" ", value)
    return WS_RE.sub(" ", text).strip()


def _collect_page_html(page_node: Dict[str, Any]) -> str:
    """Collect all HTML content from a Page-level node and its children."""
    parts: List[str] = []
    html = page_node.get("html")
    if isinstance(html, str):
        parts.append(html)
    children = page_node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                child_html = child.get("html")
                if isinstance(child_html, str):
                    parts.append(child_html)
    return "\n".join(parts)


def _page_number(page_node: Dict[str, Any]) -> Optional[int]:
    """Get 0-based page index from a page node or its first child."""
    p = page_node.get("page")
    if isinstance(p, int):
        return p
    children = page_node.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                cp = child.get("page")
                if isinstance(cp, int):
                    return cp
    return None


def _group_from_text(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in ("velocity", "speed loop")):
        return "tuning/velocity"
    if any(k in t for k in ("position loop", "positioning", "pulse", "electronic gear")):
        return "tuning/position"
    if any(k in t for k in ("torque", "current loop", "current limit")):
        return "tuning/current"
    if any(k in t for k in ("homing", "origin return", "home return")):
        return "motion/homing"
    if any(k in t for k in ("modbus", "communication", "baud", "station no", "slave id")):
        return "communication"
    if any(k in t for k in ("fault", "alarm", "diagnostic", "error code")):
        return "diagnostics"
    if any(k in t for k in ("input terminal", "digital input", "x0", "x1")):
        return "io/digital_inputs"
    if any(k in t for k in ("output terminal", "digital output", "y0", "y1")):
        return "io/digital_outputs"
    if any(k in t for k in ("protection", "overvoltage", "overcurrent", "limit")):
        return "protection"
    if any(k in t for k in ("motor", "encoder", "pole", "rated")):
        return "motor"
    if any(k in t for k in ("installation", "mounting", "dimension", "clearance")):
        return "installation"
    if any(k in t for k in ("wiring", "connector", "pin", "terminal", "cn1", "cn2", "cn3")):
        return "wiring"
    if any(k in t for k in ("trial run", "commissioning", "jog", "test run")):
        return "commissioning"
    if any(k in t for k in ("gain", "tuning", "pid", "filter", "bandwidth")):
        return "tuning"
    return None


def _slug(value: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return x or "section"


def _classify_page(text: str, html: str) -> str:
    t = text.lower()
    has_table = "<table" in html.lower()

    if "table of contents" in t or re.search(r"\.\.\.\s*\d+\b", t):
        return "table_of_contents"
    if any(k in t for k in ("revision history", "change history")):
        return "revision_history"
    if any(k in t for k in ("appendix", "annex")):
        return "appendix"
    if has_table and any(k in t for k in ("fault code", "alarm code", "error code")):
        return "fault_code_table"
    if has_table and (PARAM_ID_RE.search(text) or "parameter" in t):
        return "parameter_table"
    if any(k in t for k in ("wiring diagram", "terminal wiring", "connection diagram")):
        return "wiring_diagram"
    if any(k in t for k in ("block diagram", "control block", "signal flow")):
        return "block_diagram"
    if any(k in t for k in ("specification", "rated", "dimension")):
        return "specifications"

    has_safety = any(k in t for k in ("danger", "warning", "caution"))
    word_count = len(text.split())

    if has_safety and word_count < 200:
        return "safety_warning"

    if word_count < 15:
        return "cover_page"

    return "narrative_knowledge"


def _heading_from_html(html: str) -> str:
    """Extract the first heading from HTML, or first meaningful text."""
    heading_re = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", flags=re.DOTALL | re.IGNORECASE)
    for m in heading_re.finditer(html):
        text = _clean_text(m.group(1)).strip()
        if text and len(text) > 3:
            return text[:96]

    text = _clean_text(html)
    first_sentence = re.split(r"[.!?]\s+", text, maxsplit=1)[0].strip()
    if first_sentence and 4 < len(first_sentence) <= 96:
        return first_sentence
    words = text.split()
    if words:
        return " ".join(words[:10])
    return "Untitled section"


def classify(parsed_json: Any) -> List[Dict[str, Any]]:
    """Classify at the page level — one entry per page."""
    children = parsed_json.get("children", [])
    if not isinstance(children, list):
        return []

    out: List[Dict[str, Any]] = []
    for idx, page_node in enumerate(children):
        if not isinstance(page_node, dict):
            continue

        html = _collect_page_html(page_node)
        text = _clean_text(html)
        if not text:
            continue

        page_idx = _page_number(page_node)
        if page_idx is None:
            page_idx = idx
        page_num = page_idx + 1

        content_type = _classify_page(text, html)
        group = _group_from_text(text)
        heading = _heading_from_html(html)
        topic = f"{group}/{_slug(heading)}" if group else None

        out.append(
            {
                "section_heading": heading,
                "page_range": [page_num, page_num],
                "content_type": content_type,
                "suggested_group": group,
                "suggested_knowledge_topic": topic,
                "excerpt": text[:700],
            }
        )
    return out


def _merge_adjacent(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge consecutive pages with the same content_type and group into single sections."""
    if not sections:
        return []

    merged: List[Dict[str, Any]] = [dict(sections[0])]
    for section in sections[1:]:
        prev = merged[-1]
        prev_pages = prev.get("page_range") or [None, None]
        cur_pages = section.get("page_range") or [None, None]

        same_type = prev.get("content_type") == section.get("content_type")
        same_group = prev.get("suggested_group") == section.get("suggested_group")
        adjacent = (
            isinstance(prev_pages[1], int)
            and isinstance(cur_pages[0], int)
            and cur_pages[0] <= prev_pages[1] + 1
        )

        if same_type and same_group and adjacent:
            prev["page_range"] = [prev_pages[0], cur_pages[1]]
            continue

        if same_type and adjacent and prev.get("content_type") == "narrative_knowledge":
            prev["page_range"] = [prev_pages[0], cur_pages[1]]
            if section.get("suggested_group"):
                prev["suggested_group"] = section["suggested_group"]
                prev["suggested_knowledge_topic"] = section.get("suggested_knowledge_topic")
            continue

        merged.append(dict(section))
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify parsed manual content into section segments.")
    parser.add_argument("--parsed-json", required=True)
    parser.add_argument("--output-sections", required=True)
    args = parser.parse_args()

    parsed_json_path = Path(args.parsed_json).expanduser().resolve()
    output_path = Path(args.output_sections).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parsed_json = json.loads(parsed_json_path.read_text(encoding="utf-8"))
    raw = classify(parsed_json)
    sections = _merge_adjacent(raw)
    output_path.write_text(json.dumps(sections, indent=2), encoding="utf-8")

    from collections import Counter
    types = Counter(s.get("content_type") for s in sections)
    print(f"Wrote: {output_path}")
    print(f"Sections: {len(sections)} (from {len(raw)} pages)")
    for t, c in types.most_common():
        print(f"  {t}: {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
