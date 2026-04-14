#!/usr/bin/env python3
"""Build Type 2 knowledge files from classified sections and parsed manual content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

import yaml


PARAM_ID_RE = re.compile(r"\b[CFRU][0-9A-F]{2}\.[0-9A-F]{2}\b", flags=re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
IMG_ALT_RE = re.compile(r'<img[^>]*alt="([^"]*)"[^>]*/?\s*>', flags=re.IGNORECASE)
IMG_TAG_RE = re.compile(r"<img[^>]*>", flags=re.IGNORECASE)
IMG_SRC_RE = re.compile(r'src="([^"]+)"', flags=re.IGNORECASE)
IMG_ALT_ATTR_RE = re.compile(r'alt="([^"]*)"', flags=re.IGNORECASE)
TABLE_RE = re.compile(r"<table.*?</table>", flags=re.DOTALL | re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"<li[^>]*>(.*?)</li>", flags=re.DOTALL | re.IGNORECASE)
HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", flags=re.DOTALL | re.IGNORECASE)
PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", flags=re.DOTALL | re.IGNORECASE)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.DOTALL | re.IGNORECASE)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", flags=re.DOTALL | re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
MAX_TOPIC_SLUG_LEN = 60


def _clean(text: str) -> str:
    return WS_RE.sub(" ", TAG_RE.sub("", text)).strip()


def _html_to_text(html: str) -> str:
    """Convert HTML content to readable plain text with basic structure."""
    if not html:
        return ""

    lines: List[str] = []

    for m in HEADING_RE.finditer(html):
        level = int(m.group(1))
        text = _clean(m.group(2))
        if text:
            prefix = "#" * min(level + 1, 4)
            lines.append(f"\n{prefix} {text}\n")

    working = html
    working = HEADING_RE.sub("", working)

    for m in IMG_ALT_RE.finditer(working):
        alt = m.group(1).strip()
        if alt:
            lines.append(f"\n[Image: {alt}]\n")

    for m in TABLE_RE.finditer(working):
        table_lines = _table_to_text(m.group(0))
        if table_lines:
            lines.append("\n" + table_lines + "\n")

    remaining = TABLE_RE.sub("", working)
    remaining = IMG_ALT_RE.sub("", remaining)

    for m in PARA_RE.finditer(remaining):
        text = m.group(1)
        text = BR_RE.sub("\n", text)
        text = _clean(text)
        if text and len(text) > 3:
            lines.append(text)

    for m in LIST_ITEM_RE.finditer(remaining):
        text = _clean(m.group(1))
        if text:
            lines.append(f"- {text}")

    remaining_text = _clean(remaining)
    if not lines and remaining_text:
        lines.append(remaining_text)

    return "\n\n".join(lines).strip()


def _table_to_text(table_html: str) -> str:
    """Convert an HTML table to a simple text table."""
    rows = ROW_RE.findall(table_html)
    if not rows:
        return ""

    parsed_rows: List[List[str]] = []
    for row_html in rows:
        cells = [_clean(c) for c in CELL_RE.findall(row_html)]
        if any(cells):
            parsed_rows.append(cells)

    if not parsed_rows:
        return ""

    if len(parsed_rows) <= 1:
        return " | ".join(parsed_rows[0]) if parsed_rows else ""

    col_count = max(len(r) for r in parsed_rows)
    for row in parsed_rows:
        while len(row) < col_count:
            row.append("")

    widths = [max(len(row[c]) for row in parsed_rows) for c in range(col_count)]
    widths = [max(w, 3) for w in widths]

    out: List[str] = []
    for i, row in enumerate(parsed_rows):
        line = " | ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        out.append(line)
        if i == 0:
            out.append(" | ".join("-" * widths[j] for j in range(col_count)))

    return "\n".join(out)


def _slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return out or "section"


def _sanitize_path_segment(value: str) -> str:
    return _slug(value)


def _normalize_group_path(group: str) -> str:
    parts = [p for p in group.replace("\\", "/").split("/") if p.strip()]
    normalized = [_sanitize_path_segment(p) for p in parts if _sanitize_path_segment(p)]
    return "/".join(normalized) if normalized else "misc"


def _bounded_topic_slug(topic_seed: str, index: int) -> str:
    slug = _slug(topic_seed)
    if not slug:
        slug = f"section_{index:03d}"
    if len(slug) > MAX_TOPIC_SLUG_LEN:
        slug = slug[:MAX_TOPIC_SLUG_LEN].rstrip("_")
    return slug or f"section_{index:03d}"


def _title(section: Dict[str, Any]) -> str:
    heading = str(section.get("section_heading") or "").strip()
    if not heading:
        return "Untitled Knowledge Section"
    return heading[:96]


def _pages(section: Dict[str, Any]) -> List[int]:
    page_range = section.get("page_range", [None, None])
    if not isinstance(page_range, list) or len(page_range) != 2:
        return []
    start, end = page_range
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return list(range(start, end + 1))
    if isinstance(start, int):
        return [start]
    return []


def _path_from_topic(group: str, topic: str, heading: str, index: int) -> str:
    normalized_group = _normalize_group_path(group)
    topic_seed = ""

    if topic:
        clean = topic.strip().replace("\\", "/")
        parts = [p for p in clean.split("/") if p.strip()]
        if parts:
            topic_seed = parts[-1]
            if not group and len(parts) > 1:
                normalized_group = "/".join(_sanitize_path_segment(p) for p in parts[:-1] if _sanitize_path_segment(p)) or "misc"

    if not topic_seed:
        topic_seed = heading or f"section_{index:03d}"

    topic_slug = _bounded_topic_slug(topic_seed, index=index)
    return f"{normalized_group}/{topic_slug}.md"


def _dedupe_rel_path(rel_path: str, used: set[str]) -> str:
    if rel_path not in used:
        used.add(rel_path)
        return rel_path
    stem, dot, suffix = rel_path.rpartition(".")
    if not dot:
        stem = rel_path
        suffix = "md"
    counter = 2
    while True:
        candidate = f"{stem}_{counter:02d}.{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def _extract_page_content(
    parsed_json: Dict[str, Any],
    page_range: List[Optional[int]],
) -> str:
    """Extract full text content from parsed.json for a given page range (1-based)."""
    children = parsed_json.get("children", [])
    if not isinstance(children, list):
        return ""

    start, end = page_range if len(page_range) == 2 else (None, None)
    if not isinstance(start, int) or not isinstance(end, int):
        return ""

    start_idx = start - 1
    end_idx = end

    parts: List[str] = []
    for idx in range(max(0, start_idx), min(end_idx, len(children))):
        page_node = children[idx]
        if not isinstance(page_node, dict):
            continue
        html = page_node.get("html", "")
        if isinstance(html, str) and html.strip():
            text = _html_to_text(html)
            if text:
                parts.append(text)

    return "\n\n---\n\n".join(parts)


def _extract_page_diagrams(
    parsed_json: Dict[str, Any],
    page_range: List[Optional[int]],
) -> List[Dict[str, Any]]:
    """Extract image references from parsed page HTML for a section."""
    children = parsed_json.get("children", [])
    if not isinstance(children, list):
        return []

    start, end = page_range if len(page_range) == 2 else (None, None)
    if not isinstance(start, int) or not isinstance(end, int):
        return []

    start_idx = start - 1
    end_idx = end
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, int]] = set()

    for idx in range(max(0, start_idx), min(end_idx, len(children))):
        page_node = children[idx]
        if not isinstance(page_node, dict):
            continue
        html = page_node.get("html", "")
        if not isinstance(html, str) or not html:
            continue

        for img_tag in IMG_TAG_RE.findall(html):
            src_match = IMG_SRC_RE.search(img_tag)
            alt_match = IMG_ALT_ATTR_RE.search(img_tag)
            if not src_match:
                continue
            src = src_match.group(1)
            alt = alt_match.group(1) if alt_match else ""
            filename = Path(src).name.strip()
            if not filename:
                continue
            key = (filename, idx + 1)
            if key in seen:
                continue
            seen.add(key)
            summary = alt.strip() or f"Diagram extracted from manual page {idx + 1}."
            out.append(
                {
                    "filename": filename,
                    "content_summary": summary[:400],
                    "source_page": idx + 1,
                }
            )
    return out


def _copy_diagrams(
    diagrams: List[Dict[str, Any]],
    *,
    parse_cache_images_dir: Optional[Path],
    output_images_dir: Optional[Path],
) -> int:
    """Copy referenced diagram files from parse-cache/images to output images directory."""
    if parse_cache_images_dir is None or output_images_dir is None:
        return 0
    if not parse_cache_images_dir.exists():
        return 0

    output_images_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in diagrams:
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            continue
        src = parse_cache_images_dir / filename
        dst = output_images_dir / filename
        if not src.exists():
            continue
        if dst.exists():
            continue
        shutil.copy2(src, dst)
        copied += 1
    return copied


def _frontmatter(
    section: Dict[str, Any],
    section_ref: str,
    device_name: str,
    idx: int,
    body: str,
    diagrams: List[Dict[str, Any]],
) -> Dict[str, Any]:
    related_ids = sorted({x.upper() for x in PARAM_ID_RE.findall(body)})
    related = [{"id": pid, "role": "Referenced in manual narrative"} for pid in related_ids[:30]]
    pages = _pages(section)

    body_len = len(body)
    confidence = "high" if body_len > 500 else "medium" if body_len > 150 else "low"
    completeness = "complete" if body_len > 800 else "partial" if body_len > 250 else "stub"

    return {
        "device": device_name,
        "section": section_ref,
        "title": _title(section),
        "source_pages": pages,
        "extraction_confidence": confidence,
        "content_completeness": completeness,
        "related_parameters": related,
        "prerequisites": [],
        "see_also": [],
        "diagrams": diagrams,
    }


def _write_knowledge_file(path: Path, frontmatter: Dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    markdown = f"---\n{yaml_text}\n---\n\n## {frontmatter['title']}\n\n{body}\n"
    path.write_text(markdown, encoding="utf-8")


KNOWLEDGE_TYPES = {
    "narrative_knowledge",
    "wiring_diagram",
    "block_diagram",
    "safety_warning",
    "fault_code_table",
    "specifications",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Type 2 knowledge markdown files from section map.")
    parser.add_argument("--sections-json", required=True)
    parser.add_argument("--parsed-json", required=True, help="Path to .parse-cache/parsed.json")
    parser.add_argument("--output-knowledge-dir", required=True)
    parser.add_argument("--parse-cache-images-dir", default=None, help="Optional path to .parse-cache/images")
    parser.add_argument("--output-images-dir", default=None, help="Optional path to output curated images directory")
    parser.add_argument("--device-name", required=True, help='Display name, e.g. "StepperOnline A6-RS"')
    args = parser.parse_args()

    sections_path = Path(args.sections_json).expanduser().resolve()
    parsed_json_path = Path(args.parsed_json).expanduser().resolve()
    out_dir = Path(args.output_knowledge_dir).expanduser().resolve()
    parse_cache_images_dir = Path(args.parse_cache_images_dir).expanduser().resolve() if args.parse_cache_images_dir else None
    output_images_dir = Path(args.output_images_dir).expanduser().resolve() if args.output_images_dir else None
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = json.loads(sections_path.read_text(encoding="utf-8"))
    if not isinstance(sections, list):
        raise ValueError("sections-json must contain a JSON array.")

    parsed_json = json.loads(parsed_json_path.read_text(encoding="utf-8"))

    kept = [
        s for s in sections
        if isinstance(s, dict) and s.get("content_type") in KNOWLEDGE_TYPES
    ]

    written = 0
    skipped = 0
    copied_images = 0
    used_paths: set[str] = set()
    for idx, section in enumerate(kept, start=1):
        group = str(section.get("suggested_group") or "").strip()
        topic = str(section.get("suggested_knowledge_topic") or "").strip()
        heading = str(section.get("section_heading") or "").strip()
        rel_path = _path_from_topic(group, topic, heading, idx)
        rel_path = _dedupe_rel_path(rel_path, used_paths)
        target = out_dir / rel_path
        section_ref = rel_path[:-3].replace("\\", "/")

        page_range = section.get("page_range", [None, None])
        body = _extract_page_content(parsed_json, page_range)
        diagrams = _extract_page_diagrams(parsed_json, page_range)
        copied_images += _copy_diagrams(
            diagrams,
            parse_cache_images_dir=parse_cache_images_dir,
            output_images_dir=output_images_dir,
        )

        if not body or len(body) < 20:
            excerpt = str(section.get("excerpt") or "")
            body = excerpt.strip() if excerpt.strip() else "Manual section has limited detail. See related parameters."
            skipped += 1

        fm = _frontmatter(
            section,
            section_ref=section_ref,
            device_name=args.device_name,
            idx=idx,
            body=body,
            diagrams=diagrams,
        )
        _write_knowledge_file(target, fm, body)
        written += 1

    print(f"Knowledge files written: {written}")
    print(f"  Full content: {written - skipped}")
    print(f"  Excerpt fallback: {skipped}")
    if output_images_dir is not None:
        print(f"Curated images copied: {copied_images}")
        print(f"Images dir: {output_images_dir}")
    print(f"Output dir: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
