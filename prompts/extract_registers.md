Extract every documented parameter into Type 1 YAML entries.

Input:
- Sections classified as parameter tables or inline parameter descriptions
- Type 1 schema reference from `schemas/type1_schema.yaml`

Output:
- YAML list entries for `parameters` and any needed `groups`

Rules:
- Include every parameter documented by the manual. Do not filter.
- Preserve exact parameter IDs, addresses, units, and numeric ranges.
- `brief` style: direct, precise, no filler text.
- If description is missing: `brief: "No description in manual."`
- If a field is unknown: use null or empty list/map (do not guess).
- In Phase 1: `knowledge_ref: null` for all parameters.
- Deduplicate by parameter ID. Merge repeated entries carefully.
- If conflicting values exist, choose best-supported value and note conflict in `brief`.

Chunking strategy:
- Primary split: by parameter group/section.
- If a group is still too large, split by subtable/page range.
- Include section heading and schema snippet with each chunk.
- Merge chunk outputs and deduplicate by parameter ID at the end.

Output constraints:
- Return a complete YAML document with top-level keys: `schema_version`, `extraction_metadata`, `device`, `groups`, `parameters`.
- Do not return partial snippets unless explicitly asked.
- Preserve existing parameters and only add/fix missing or incorrect rows when used as gap-fill mode.
- Keep `knowledge_ref` unchanged if already populated; otherwise set to null.

Gap-fill mode (fallback usage):
- Input may include an existing `device_registers.yaml`.
- Add missing parameters and improve weak fields (`brief`, `range`, `unit`, `data_type`) without regressing known-good rows.
- Always deduplicate by `id`.
