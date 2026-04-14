# Changelog

Notable changes to **parse-manual** are listed here. Entries are grouped by date (newest first). Within a date, changes are summarized in rough implementation order.

## 2026-04-13

### Added

- **Knowledge-only devices:** `--skip-registers` on `run_skill.py` skips register extraction, knowledge ref linking, validation, and spot-check when a manual has no addressable registers. `run_phase2_only.py` treats `device_registers.yaml` as optional and skips register-dependent stages when it is absent.
- **`generate_index.py`:** Optional `--registers`; without it, index uses `register_file: null`, `total_parameters: 0`, and empty groups. `--manufacturer` and `--model` for metadata when no register file exists.
- **`generate_rules.py`:** Optional `--registers`; knowledge-only device rules omit the register lookup block and inventory notes "knowledge only." `--manufacturer` and `--model`. Device root inferred from `knowledge_dir` when registers are omitted.
- **`refine_knowledge.py`:** Optional pass over low-confidence or stub knowledge files (`--dry-run`, `--force-all`, `--prompt-path`).
- **`link_knowledge_refs.py`:** Populates `knowledge_ref` in `device_registers.yaml` (related-parameter matching, group hints, pass-2 group propagation, `--dry-run`).
- **Curated images:** `extract_knowledge.py` copies diagrams from `.parse-cache/images` to device `images/` with `--parse-cache-images-dir` and `--output-images-dir`; diagram frontmatter from page HTML.
- **`generate_rules.py`:** Optional `--agents-path`; updates `.cursor/AGENTS.md` inside a marked block for device inventory.

### Changed

- **`classify_sections.py`:** Page-level classification (one entry per page) with improved merges and additional section groups (e.g. installation, wiring, commissioning, tuning)—fewer, coarser sections than node-level classification.
- **`extract_knowledge.py`:** Full-page content via `--parsed-json` and HTML-to-text (headings, tables, lists, images) instead of short excerpt stubs; expanded knowledge types (e.g. `specifications`); semantic path normalization, bounded topic slugs, duplicate-path handling; frontmatter `section` aligned to output path.
- **`generate_rules.py`:** Device-specific globs only; inventory rule without broad protocol globs; relative doc paths via repo root inference.
- **`run_skill.py`:** Renamed from `run_phase1.py`. Full pipeline orchestration; requires `.parse-cache/extract_registers_generated.py` (or `--extractor-script`)—no silent fallback to the reference extractor. Forwards manufacturer/model and image paths; runs `link_knowledge_refs.py`; optional `--refine-knowledge`.
- **`run_phase2_only.py`:** Renamed from `run_phase2.py`. Phase-2-only entry point when parse (and optional register extraction) already exists; register file optional; `--refine-knowledge` support.
- **`generate_index.py`:** By default, normalizes knowledge `section` paths and prunes stale `prerequisites` / `see_also` references; `--no-prune-stale-refs` for debugging.
- **`SKILL.md`:** Step 3 no longer offers a runtime fallback to `scripts/extract_registers.py` (Option C)—agents generate a per-manual extractor when missing. Steps renumbered after adding link/refine stages; image flags, AGENTS path, fallbacks for classification and register gap-fill, knowledge-only acceptance criteria, and orchestrator renames documented.

### Removed

- **`prompts/summarize_diagram.md`:** Diagram summaries use Marker alt-text; separate vision summarization dropped from the workflow.
- **Reference extractor as runtime fallback:** `scripts/extract_registers.py` remains a reference implementation only, not a default execution path.

### Fixed

- **`run_phase1.py` / orchestrators:** `parse_quality_score` / `None` handling and forwarding of `--parsed-json` to knowledge extraction (as applicable before renames).

## 2026-04-12

### Added

- Initial **Phase 2** knowledge pipeline delivery: classification, full-content knowledge extraction, index and rules generation, validation and spot-check integration, and `SKILL.md` workflow through the phase-2 orchestrator.

### Changed

- **`extract_knowledge.py`:** Replaced stub excerpt-only outputs with full-document extraction.
- **`generate_rules.py`:** Replaced broad protocol globs and absolute doc paths with device-scoped globs and relative paths.

### Fixed

- **`classify_sections.py`:** Over-granular node-level classification (1871 sections) replaced with page-level classification (219 sections on the A6-RS reference run).
