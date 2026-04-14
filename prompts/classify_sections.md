Classify each section of this industrial device manual parse.

Input:
- Parsed markdown from Marker (`parsed.md`)
- Optional structured JSON blocks (`parsed.json`)

Output:
- JSON array of section objects:
  - `section_heading` (string)
  - `page_range` ([start_page, end_page])
  - `content_type` (one of: `parameter_table`, `narrative_knowledge`, `wiring_diagram`, `block_diagram`, `specifications`, `fault_code_table`, `safety_warning`, `table_of_contents`, `cover_page`, `appendix`, `revision_history`)
  - `suggested_group` (string or null)
  - `suggested_knowledge_topic` (string path or null)

Rules:
- Prefer Marker structured JSON boundaries when available.
- If parsed markdown is too large for context, classify by chapter chunks and merge.
- Mark parameter and fault-code tables as `parameter_table` / `fault_code_table`.
- Keep output deterministic and concise.

Output constraints:
- Return valid JSON only (no prose, no markdown fence).
- Use 1-based page numbers in `page_range`.
- Keep `suggested_group` in slug form (examples: `communication`, `tuning/velocity`, `diagnostics`).
- Keep `suggested_knowledge_topic` as `{group}/{short_topic_slug}` or null.

Example output object:
{
  "section_heading": "Communication Parameters",
  "page_range": [241, 247],
  "content_type": "parameter_table",
  "suggested_group": "communication",
  "suggested_knowledge_topic": "communication/modbus_settings"
}
