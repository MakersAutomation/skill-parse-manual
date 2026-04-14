# Phase 2 — Build Log

## Update Order Policy

- Keep this file in strict chronological order: **oldest entries first, newest entries last**.
- Add new entries at the **bottom** of the file.
- If multiple updates happen on the same date, append new subsections under that date in the order they occurred.
- Do not reorder older entries unless explicitly doing a housekeeping pass like this one.

## 2026-04-12 — Session start

### State assessment

Phase 1 completed. Existing artifacts:

- `scripts/` — All 8 scripts present (parse_pdf, classify_sections, extract_registers, extract_knowledge, generate_index, generate_rules, validate_registers, spot_check, run_phase1)
- `prompts/` — 5 prompt files (classify_sections, extractor_guidelines, extract_knowledge, extract_registers, summarize_diagram)
- `schemas/` — type1_schema.yaml, type2_frontmatter.yaml
- `SKILL.md` — Full workflow with Steps 1–9

A6-RS Phase 1 outputs at `controller/ipp001-plugger/ref/devices/a6-rs/`:
- `device_registers.yaml` — 19080 lines, Type 1 register file (715 parameters)
- `.parse-cache/parsed.json` — 13MB, 363 pages
- `.parse-cache/parsed.md` — 1.2MB
- `.parse-cache/images/` — ~1800+ extracted images
- `.parse-cache/metadata.json`
- `.parse-cache/extract_registers_generated.py`

Missing Phase 2 outputs (before this session):
- No `sections.json`
- No `knowledge/` directory
- No `knowledge/_index.yaml`
- No `.cursor/rules/device-a6-rs.mdc`
- No `.cursor/rules/device-inventory.mdc`

### Issues found in existing Phase 2 scripts

1. **extract_knowledge.py** — Created stub knowledge files from 700-char excerpt text only.
2. **generate_rules.py** — Used broad protocol globs; used absolute path for doc_root_rel.
3. **classify_sections.py** — Classified at node level (1871 sections from 363 pages). Too granular.
4. **run_phase1.py / run_phase2.py** — No Phase 2 orchestrator existed. run_phase1 passed `None` as parse-quality-score.

### Changes made

#### classify_sections.py — rewritten
- Changed from node-level to page-level classification (one entry per page).
- Improved merge logic: adjacent narrative_knowledge pages merge even with different groups.
- Added more group categories (installation, wiring, commissioning, tuning).
- Result: 363 pages → 219 sections (was 1871 nodes before).

#### extract_knowledge.py — rewritten
- Added `--parsed-json` argument to read full page content.
- Replaced excerpt-only extraction with full HTML→text conversion.
- Added `_html_to_text()` with heading, table, list, image alt-text extraction.
- Added `_table_to_text()` for readable table rendering.
- Expanded knowledge types to include `specifications`.
- Increased related_parameters cap from 20 to 30.
- Adjusted confidence/completeness thresholds for full-content sizing.

#### generate_rules.py — fixed
- Device-specific globs only: `**/{model_glob}*`, `**/ref/devices/{model_slug}/**` (no broad protocol globs).
- Inventory rule: no globs at all (`alwaysApply: false` only).
- Added `_infer_repo_root()` to compute relative doc paths instead of absolute.

#### run_phase2.py — new
- Orchestrates Steps 2, 4–8 (classify, knowledge, index, rules, validate, spot-check).
- Checks Phase 1 prerequisites exist before running.
- Handles None quality_score gracefully (omits --parse-quality-score arg).

#### run_phase1.py — fixed
- Passes `--parsed-json` to extract_knowledge.py.
- Handles None quality_score gracefully.

#### SKILL.md — updated
- Step 4 now shows `--parsed-json` argument.
- Added Phase 2 orchestrator command in alternative pipelines section.

### Test results (A6-RS)

Pipeline: `run_phase2.py` against A6-RS device dir.

| Metric | Value |
|---|---|
| Sections classified | 219 (from 363 pages) |
| Knowledge files written | 108 (all full content, 0 excerpt fallback) |
| Knowledge sections indexed | 103 |
| Parameters | 715 |
| Validation errors | 0 |
| Validation warnings | 0 |
| Device rule | `device-a6-rs.mdc` (device-specific globs only) |
| Inventory rule | `device-inventory.mdc` (no globs) |

### Acceptance criteria

- [x] Validation reports zero errors
- [x] Spot-check of 5 parameters passes
- [x] Extracted parameter count >50 (715)
- [x] `knowledge/_index.yaml` exists and `total_parameters` matches register file (715)
- [x] At least one `device-*.mdc` rule exists in `.cursor/rules/`

## 2026-04-13 — SKILL.md removed Option C from Step 3

Step 3 (Extract registers) previously offered three options:
- **Option A** — Reuse `.parse-cache/extract_registers_generated.py` if it exists.
- **Option B** — Generate a manual-specific extractor script, save to `.parse-cache/`, then run it.
- **Option C** — Fall back to the reference extractor `scripts/extract_registers.py`.

Removed Option C. The agent must now always generate a per-manual extractor script (Option B) when one doesn't already exist, using the reference script and `prompts/extractor_guidelines.md` as guidance. The reference script remains in `scripts/` as a starting-point implementation but is no longer a runtime fallback.

**Rationale:** Each manual has its own table layout and quirks. Generating a dedicated script per manual forces the agent to inspect the parsed content and adapt, rather than silently falling back to a generic extractor that may not fit.

## 2026-04-13 — Phase 2 gap closure

### Goal

Complete remaining Phase 2 items:

- Curated diagram/image output under `ref/devices/{model}/images/`
- Append ParseManual device inventory to `.cursor/AGENTS.md`

### Changes made

#### `scripts/extract_knowledge.py`
- Added image extraction from page HTML (`<img src=... alt=...>`).
- Added diagram frontmatter population (`filename`, `content_summary`, `source_page`).
- Added curated image copy from `.parse-cache/images` to device `images/`.
- New args:
  - `--parse-cache-images-dir`
  - `--output-images-dir`

#### `scripts/generate_rules.py`
- Added optional `--agents-path`.
- Added `_upsert_agents()` with marker block:
  - `<!-- parse-manual-device-docs:start -->`
  - `<!-- parse-manual-device-docs:end -->`
- Script now updates `.cursor/AGENTS.md` when path is provided.

#### `scripts/run_phase1.py` and `scripts/run_phase2.py`
- Auto-detect `.cursor/AGENTS.md` at repo root.
- Pass `--agents-path` to `generate_rules.py`.
- Pass image args to `extract_knowledge.py`:
  - `--parse-cache-images-dir {device_dir}/.parse-cache/images`
  - `--output-images-dir {device_dir}/images`

#### `SKILL.md`
- Step 4 now includes image curation flags.
- Step 6 now includes `--agents-path`.
- Output paths and acceptance criteria updated for curated images and AGENTS append behavior.

## 2026-04-13 — Phase 2/3 gap review and cleanup

### Context

Reviewed all scripts, artifacts, and plan against the A6-RS test output. Phase 1 and Phase 2 are complete. Identified and resolved gaps before moving to Phase 3.

### Changes made

#### `scripts/run_phase1.py` → `scripts/run_skill.py` (renamed)
- Removed silent fallback to reference extractor (`scripts/extract_registers.py`). The orchestrator now errors out if `.parse-cache/extract_registers_generated.py` (or `--extractor-script`) doesn't exist. Agent must generate a per-manual extractor first (SKILL.md Step 3).
- Updated docstring and CLI description to reflect "full pipeline" role.
- Renamed from `run_phase1.py` to `run_skill.py` since it runs all steps (1–8), not just Phase 1.

#### `scripts/run_phase2.py` → `scripts/run_phase2_only.py` (renamed)
- Renamed for clarity: this runs Phase 2-only steps (2, 4–8) when parse + register extraction already done.

#### `prompts/summarize_diagram.md` — deleted
- Marker already provides descriptive alt-text for diagrams (e.g. "Three different models of the A6-RS Servo Drive units showing front panel interfaces"). A separate vision-model summarization pass adds marginal value over what Marker supplies. Diagram `content_summary` in knowledge frontmatter uses Marker alt-text directly.

#### `SKILL.md`
- Removed `prompts/summarize_diagram.md` from prompt file listing.
- Updated orchestrator commands: `run_phase1.py` → `run_skill.py`, `run_phase2.py` → `run_phase2_only.py`.
- Added note that `run_skill.py` requires a generated extractor script.

#### Plan file updated
- Corrected `classify-prompt` and `extract-prompt` todo status from `cancelled` to `completed` (files exist and were delivered with a different implementation approach than originally envisioned).
- Added Phase 3 todos: wire prompts into workflow, knowledge file refinement, naming cleanup.
- Updated Phase 3 scope: removed Docling fallback and prompt tuning. Added: prompt-as-alternative-path for classification and extraction, agent-driven knowledge refinement, knowledge file naming cleanup with `_index.yaml` regeneration.
- Updated file layout section to reflect all current scripts.
- Marked Phase 1 and Phase 2 as complete with metrics.

## 2026-04-13 — Phase 3 implementation pass (partial)

### Goal

Implement concrete Phase 3 items approved after critique:
- Prompt fallback workflow wiring
- Knowledge naming cleanup logic
- Initial `knowledge_ref` linking automation

### Changes made

#### `scripts/extract_knowledge.py`
- Added semantic path normalization for knowledge files:
  - Normalizes group path segments.
  - Uses bounded topic slugs (max 60 chars).
  - Derives fallback topic from heading when suggested topic missing.
- Added duplicate path handling (`_dedupe_rel_path`) to prevent filename collisions after slug truncation.
- Frontmatter `section` now derives from final resolved output path (`rel_path` without `.md`) to keep index/cross-ref keys stable.

#### `scripts/link_knowledge_refs.py` (new)
- New script to populate `knowledge_ref` in `device_registers.yaml` from generated knowledge files.
- Matching strategy:
  - Primary: `related_parameters[].id` in knowledge frontmatter.
  - Fallback: section-group hints (including register-group tokens like `c06`, `u42` inferred from section path/title).
  - Chooses best candidate by completeness/confidence ranking.
- Supports `--dry-run` for safe evaluation before writing.

#### Pipeline wiring
- `scripts/run_skill.py` now runs `link_knowledge_refs.py` after `extract_knowledge.py`.
- `scripts/run_phase2_only.py` now includes an explicit “Link parameter knowledge refs” stage before index generation.

#### `SKILL.md`
- Added Step 2 fallback guidance using `prompts/classify_sections.md`.
- Added Step 3 fallback guidance using `prompts/extract_registers.md`.
- Added new Step 5 command for `link_knowledge_refs.py`.
- Renumbered downstream steps accordingly.
- Updated guardrail for `knowledge_ref` (prefer deterministic links, null only when no reliable mapping exists).
- Added acceptance criterion for `knowledge_ref` population.

#### Prompt updates
- `prompts/classify_sections.md` now includes output constraints and schema example object.
- `prompts/extract_registers.md` now includes full-document output constraints and explicit gap-fill behavior.

### Validation checks

- `python -m py_compile` passed for updated scripts:
  - `extract_knowledge.py`
  - `run_skill.py`
  - `run_phase2_only.py`
  - `link_knowledge_refs.py`
- `link_knowledge_refs.py --dry-run` on A6-RS:
  - Parameters: 715
  - Non-null `knowledge_ref`: 188 (26.3%)
  - Rows changed: 188

### Remaining Phase 3 work

- Knowledge refinement pass (`extract_knowledge.md`) still pending.
- Second-manual smoke test still pending.
- `knowledge_ref` coverage target (>=50%) not yet reached on A6-RS with current heuristic mapping.

## 2026-04-13 — Phase 3 implementation pass (continued)

### Goal

Finish the two remaining non-smoke-test Phase 3 items:
- knowledge refinement pass plumbing
- improved `knowledge_ref` linking coverage

### Changes made

#### `scripts/refine_knowledge.py` (new)
- Added a refinement stage targeting low-confidence/stub knowledge files.
- Reads knowledge markdown frontmatter, selects targets where:
  - `extraction_confidence == low` or
  - `content_completeness == stub`
- Applies light body normalization (whitespace/dedup cleanup) while preserving frontmatter and section title.
- Supports:
  - `--dry-run`
  - `--force-all`
  - `--prompt-path` (for traceability to `prompts/extract_knowledge.md`)
- No-op behavior is explicit when no files qualify.

#### `scripts/link_knowledge_refs.py` (enhanced)
- Added pass-2 group propagation:
  - pass-1: explicit matching by `related_parameters[].id` and group-code hints
  - pass-2: propagate dominant knowledge ref within each parameter group when support >=2
- Added diagnostics output:
  - explicit matches count
  - propagated matches count
- Result: substantial coverage increase on A6-RS dry-run.

#### Pipeline wiring
- `scripts/run_skill.py`
  - Added `--refine-knowledge` flag.
  - When enabled, runs `refine_knowledge.py` after `extract_knowledge.py` and before linking refs/index.
- `scripts/run_phase2_only.py`
  - Added `--refine-knowledge` flag and stage output banner.
  - Updated module docstring to include knowledge-ref linking stage.

#### `SKILL.md`
- Added optional refinement command after Step 4.
- Added `--refine-knowledge` examples in both orchestrator command blocks.

### Validation checks

- `python -m py_compile` passed for:
  - `link_knowledge_refs.py`
  - `refine_knowledge.py`
  - `run_skill.py`
  - `run_phase2_only.py`
- A6-RS dry-runs:
  - `link_knowledge_refs.py --dry-run`:
    - parameters: 715
    - non-null `knowledge_ref`: 556 (77.8%)
    - explicit matches: 188
    - group-propagated matches: 368
  - `refine_knowledge.py --dry-run`:
    - scanned: 103 knowledge files
    - targets: 0 (no low/stub files)
    - changed: 0

### Remaining Phase 3 work

- Knowledge naming migration for already-generated legacy files remains in progress (new logic is in extractor; existing outputs need regeneration/migration to fully align).
- Second-manual smoke test intentionally deferred in this pass.

## 2026-04-13 — A6-RS Phase 2 clean regeneration for naming migration

### Goal

Apply the new knowledge naming scheme to existing A6-RS outputs by re-running Phase 2 on a clean `knowledge/` directory.

### Actions

- Ran `run_phase2_only.py` with `--refine-knowledge` for A6-RS.
- Observed mixed old/new filenames on first run (`knowledge_sections: 124` vs `Knowledge files written: 108`) because legacy files were not auto-pruned.
- Removed `ref/devices/a6-rs/knowledge/` and reran Phase 2 to force a clean output set.

### Results

- `Knowledge files written: 108`
- `_index.yaml` now reports `Knowledge sections: 108` (no stale legacy entries)
- `validate_registers.py` phase 2: `Errors: 0`, `Warnings: 0`
- `knowledge_ref` coverage after linking: `556/715` (`77.8%`)
- Naming constraints check:
  - knowledge files: 108
  - max filename stem length: 60
  - stems >60: 0

### Remaining Phase 3 work

- Second-manual smoke test intentionally deferred (per user instruction).

## 2026-04-13 — Auto-prune stale index references

### Goal

Ensure stale cross-references do not persist in knowledge metadata when files are renamed or removed.

### Changes made

#### `scripts/generate_index.py`
- Added automatic normalization and prune behavior during index generation:
  - Normalizes each knowledge file frontmatter `section` to match the file's real relative path.
  - Prunes stale `prerequisites` and `see_also` entries that point to missing knowledge sections.
- Added `--no-prune-stale-refs` flag to disable this behavior for debugging.
- Added summary metrics in script output:
  - stale references pruned count
  - knowledge files normalized count

#### `SKILL.md`
- Updated Step 6 notes to document that index generation now auto-prunes stale references by default.

### Validation checks

- `python -m py_compile scripts/generate_index.py` passed.
- A6-RS index regeneration completed successfully:
  - `Knowledge sections: 108`
  - `Stale references pruned: 0`
  - `Knowledge files normalized: 0`

---

## 2026-04-13 — Non-register (knowledge-only) device support

### Context

ClearCore smoke test revealed that the pipeline forced a `device_registers.yaml` even when the manual has no registers. The skill needs to handle knowledge-only devices cleanly.

### Changes made

#### `scripts/run_skill.py`
- Added `--skip-registers` flag. When passed, steps 3 (extract registers), 5 (link knowledge refs), 8 (validate), and 9 (spot-check) are skipped.
- `--registers` arg for downstream scripts is conditionally passed only when registers exist.
- `--manufacturer` and `--model` are now forwarded to `generate_index.py` and `generate_rules.py` so device metadata is available without a register file.

#### `scripts/run_phase2_only.py`
- Removed `device_registers.yaml` from the required-file check; only `parsed.json` is now required.
- Auto-detects `has_registers` from disk. Register-dependent steps are skipped when the file is absent.
- Passes `--manufacturer`, `--model` to `generate_index.py` and `generate_rules.py`.

#### `scripts/generate_index.py`
- `--registers` changed from required to optional. When absent, register metrics default to `register_file: null`, `total_parameters: 0`, empty groups.
- Added `--manufacturer` and `--model` CLI args as fallbacks when no register file provides device metadata.

#### `scripts/generate_rules.py`
- `--registers` changed from required to optional. When absent:
  - Device rule omits the "Register Lookup" block.
  - Inventory entry says "knowledge only, no registers."
- Added `--manufacturer` and `--model` CLI args.
- Device root is inferred from `knowledge_dir` parent instead of `registers_path` parent.

#### `SKILL.md`
- Added top-level note: "Not all devices have registers" with `--skip-registers` guidance.
- Step 3 marked as skippable; Steps 5, 8, 9 marked as "requires registers."
- Steps 6, 7 documented as accepting optional `--registers`.
- Step 10 updated to show non-register presentation format.
- Orchestrator docs updated with `--skip-registers`.
- Acceptance criteria split into "All devices", "Register devices only", and "Non-register devices."

#### ClearCore re-run
- Removed fake `device_registers.yaml` and `extract_registers_generated.py`.
- Re-ran pipeline with `--skip-registers`: 21 knowledge files, 56 images, 0 errors.
- `_index.yaml` correctly shows `register_file: null`, `total_parameters: 0`.
- Device rule omits register lookup block.
