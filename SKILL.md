---
name: parse-manual
description: >-
  Extracts structured device documentation from industrial PDF manuals into
  AI-readable outputs: Type 1 register YAML, Type 2 knowledge files, knowledge
  index, and Cursor rules. Use when creating or updating device register maps
  from manuals.
---

You are a **ParseManual Agent**. Your goal is to convert a device PDF manual into a complete structured documentation bundle with repeatable, validated outputs.

This skill is **model-agnostic**:
- Python scripts do mechanical work (parse API call, file I/O, classification, validation, spot-check).
- The running agent model does reasoning work (generating per-manual extractor scripts, refining knowledge content).

For register extraction specifically, treat scripts as **per-manual generated artifacts**.
Do not assume a single static extractor will fit all manuals.

**Not all devices have registers.** When a manual describes a device without addressable registers (e.g. a microcontroller reference manual, a general user guide), skip register extraction entirely. Pass `--skip-registers` to the orchestrator, or omit Step 3. The pipeline will produce knowledge files, index, rules, and images without a `device_registers.yaml`.

## Inputs

The user must provide (or the agent must resolve from context):

| Input | Example | Required |
|---|---|---|
| PDF path | `ref/stepper-online-modbus-test/doc/A6-RS_series_servo_drive_manual.pdf` | yes |
| Device output dir | `ref/devices/a6-rs` | yes |
| Manufacturer | `StepperOnline` | yes |
| Model | `A6-RS` | yes |
| Manual source filename | `A6-RS_series_servo_drive_manual.pdf` | yes |

If the user omits any of these, ask before proceeding.

## Agent Workflow — Mandatory Steps

When invoked (via `/parse-manual` or natural language), execute **all steps below in order**. Do not stop after register extraction — the full bundle is required.

### Step 1: Parse PDF

The script **automatically skips** the Datalab API call if `.parse-cache/parsed.json` and `.parse-cache/parsed.md` already exist in the device dir. Pass `--force` to re-parse anyway.

> **Agent note:** `.parse-cache/` is a dotfolder. Cursor's Glob tool and PowerShell `Get-ChildItem` may not list its contents reliably. Use `python -c "from pathlib import Path; print(Path('{device_dir}/.parse-cache/parsed.json').is_file())"` to verify cache existence, not Glob.

```
python ~/.cursor/skills/parse-manual/scripts/parse_pdf.py
  --pdf "{pdf_path}"
  --output-dir "{device_dir}"
```

### Step 2: Classify sections

```
python ~/.cursor/skills/parse-manual/scripts/classify_sections.py
  --parsed-json "{device_dir}/.parse-cache/parsed.json"
  --output-sections "{device_dir}/.parse-cache/sections.json"
```

Fallback path (when Python classification is clearly wrong for a new manual format):
- Use `prompts/classify_sections.md` to produce the same `sections.json` schema.
- Overwrite `{device_dir}/.parse-cache/sections.json` with the prompt output and continue.

### Step 3: Extract registers (skip for non-register devices)

**Skip this step** when the device manual does not contain addressable registers (servo parameters, Modbus registers, configuration tables with addresses). Pass `--skip-registers` to the orchestrator, or simply proceed to Step 4. No `device_registers.yaml` will be produced, and downstream register-dependent steps (5, 8, 9) are automatically skipped.

Option A — If `.parse-cache/extract_registers_generated.py` exists, use it.
Option B — Otherwise, generate a manual-specific extractor script first (read `prompts/extractor_guidelines.md` and use `scripts/extract_registers.py` as a reference implementation), save to `.parse-cache/extract_registers_generated.py`, then run it.

```
python "{extractor_script}"
  --parsed-md "{device_dir}/.parse-cache/parsed.md"
  --parsed-json "{device_dir}/.parse-cache/parsed.json"
  --output-registers "{device_dir}/device_registers.yaml"
  --manufacturer "{manufacturer}"
  --model "{model}"
  --manual-source "{manual_source}"
```

Fallback path (when generated extractor misses tables or count is suspiciously low):
- Use `prompts/extract_registers.md` for gap-filling extraction.
- Merge and deduplicate by `id`, then write final `{device_dir}/device_registers.yaml`.
- Re-run validation after merge.

### Step 4: Build knowledge files

```
python ~/.cursor/skills/parse-manual/scripts/extract_knowledge.py
  --sections-json "{device_dir}/.parse-cache/sections.json"
  --parsed-json "{device_dir}/.parse-cache/parsed.json"
  --output-knowledge-dir "{device_dir}/knowledge"
  --parse-cache-images-dir "{device_dir}/.parse-cache/images"
  --output-images-dir "{device_dir}/images"
  --device-name "{manufacturer} {model}"
```

Optional refinement pass (targets low-confidence / stub files):

```
python ~/.cursor/skills/parse-manual/scripts/refine_knowledge.py
  --knowledge-dir "{device_dir}/knowledge"
  --prompt-path "~/.cursor/skills/parse-manual/prompts/extract_knowledge.md"
```

### Step 5: Link parameter knowledge refs (requires registers)

Skipped automatically when no `device_registers.yaml` exists.

```
python ~/.cursor/skills/parse-manual/scripts/link_knowledge_refs.py
  --registers "{device_dir}/device_registers.yaml"
  --knowledge-dir "{device_dir}/knowledge"
```

### Step 6: Generate knowledge index

`--registers` is optional. When omitted, register metrics are zeros and `register_file` is null.

```
python ~/.cursor/skills/parse-manual/scripts/generate_index.py
  --knowledge-dir "{device_dir}/knowledge"
  --output-index "{device_dir}/knowledge/_index.yaml"
  --manual-source "{manual_source}"
  --manufacturer "{manufacturer}"
  --model "{model}"
  --registers "{device_dir}/device_registers.yaml"   # omit for non-register devices
```

By default, index generation also normalizes each knowledge file's `section` to its actual path and prunes stale `prerequisites` / `see_also` references that point to missing files. Use `--no-prune-stale-refs` only when debugging.

### Step 7: Generate Cursor rules

Infer repo root from `{device_dir}` (walk up to `.git`). Write rules into `{repo_root}/.cursor/rules/`. If `CLAUDE.md` and/or `.cursor/AGENTS.md` exist, append device inventory.

`--registers` is optional. When omitted, the device rule omits the register lookup block and the inventory entry says "knowledge only."

```
python ~/.cursor/skills/parse-manual/scripts/generate_rules.py
  --knowledge-dir "{device_dir}/knowledge"
  --rules-dir "{repo_root}/.cursor/rules"
  --manufacturer "{manufacturer}"
  --model "{model}"
  --registers "{device_dir}/device_registers.yaml"   # omit for non-register devices
  --claude-path "{repo_root}/CLAUDE.md"
  --agents-path "{repo_root}/.cursor/AGENTS.md"
```

### Step 8: Validate (requires registers)

Skipped automatically when no `device_registers.yaml` exists.

```
python ~/.cursor/skills/parse-manual/scripts/validate_registers.py
  --registers "{device_dir}/device_registers.yaml"
  --phase 2
  --knowledge-dir "{device_dir}/knowledge"
  --index "{device_dir}/knowledge/_index.yaml"
  --rules-dir "{repo_root}/.cursor/rules"
```

### Step 9: Spot-check (requires registers)

Skipped automatically when no `device_registers.yaml` exists.

```
python ~/.cursor/skills/parse-manual/scripts/spot_check.py
  --registers "{device_dir}/device_registers.yaml"
  --sample-size 5
```

### Step 10: Present results

Show the user:
- Parameter count and group count from `device_registers.yaml` (if registers were extracted)
- Knowledge file count and section coverage
- Validation error/warning summary (if registers were extracted)
- Spot-check sample table (if registers were extracted)
- For non-register devices: knowledge section count, image count, and confidence distribution
- Prompt user to verify the sampled entries against the source PDF (register devices only)

### Alternative: one-command pipelines

All steps 1–9 via a single orchestrator. The parse step is automatically skipped if cache exists; add `--force-parse` to re-run the Datalab API call.

For **register devices**: requires a generated extractor script at `.parse-cache/extract_registers_generated.py` (see Step 3).
For **non-register devices**: pass `--skip-registers` to skip steps 3, 5, 8, 9.

```
python ~/.cursor/skills/parse-manual/scripts/run_skill.py
  --pdf "{pdf_path}"
  --device-dir "{device_dir}"
  --manufacturer "{manufacturer}"
  --model "{model}"
  --manual-source "{manual_source}"
  --skip-registers     # for non-register devices
  --refine-knowledge   # optional
```

Phase 2 only (steps 2, 4–7), when parse is already done. Register-dependent steps are automatically skipped when no `device_registers.yaml` exists:

```
python ~/.cursor/skills/parse-manual/scripts/run_phase2_only.py
  --device-dir "{device_dir}"
  --manufacturer "{manufacturer}"
  --model "{model}"
  --manual-source "{manual_source}"
  --refine-knowledge   # optional
```

## Acceptance Criteria

**All devices:**
- `knowledge/_index.yaml` exists.
- At least one `device-*.mdc` rule exists in `.cursor/rules/`.
- `images/` exists with curated diagram assets referenced by knowledge frontmatter when diagrams are present.

**Register devices only** (when `device_registers.yaml` is produced):
- Validation reports zero errors.
- Spot-check of 5 sampled parameters passes human review.
- Extracted parameter count is greater than 50.
- `total_parameters` in `_index.yaml` matches register file.
- `knowledge_ref` is populated for parameters with matching knowledge sections.

**Non-register (knowledge-only) devices:**
- No `device_registers.yaml` file is produced.
- `_index.yaml` shows `register_file: null` and `total_parameters: 0`.
- Knowledge sections are generated from the manual's narrative content.

## Feedback-Driven Self-Update

When the user reviews extracted registers and reports defects:

1. Map each defect to a parser rule gap (column mapping, type parsing, source page selection, enum handling, etc.).
2. Update the generated extractor script for that manual and rerun extraction.
3. If the defect reflects a reusable pattern, update:
   - `prompts/extractor_guidelines.md`
   - reference script `scripts/extract_registers.py`
   - schema files if output fields changed
4. Re-run validation and spot-check, then show the exact corrected rows to the user.

Do not patch `device_registers.yaml` manually to fix defects. Fix extraction logic and regenerate.

## Requirements

- **Datalab account and API key** (paid usage after free credits). Sign up at [datalab.to/auth/sign_up](https://datalab.to/auth/sign_up), then create a key at [datalab.to/app/keys](https://www.datalab.to/app/keys). Official docs: [documentation.datalab.to](https://documentation.datalab.to/docs/welcome/quickstart).
- Environment variable: `DATALAB_API_KEY` (read by `datalab-python-sdk` and by `parse_pdf.py` before calling the API).
- Python dependencies: `datalab-python-sdk`, `pyyaml`

### Making `DATALAB_API_KEY` available

Cursor skills do **not** inject secrets. The terminal running parse scripts must have the variable set.

**Windows (current PowerShell session):** `$env:DATALAB_API_KEY = "your_key_here"`

**Windows (persistent):** System Settings > Environment Variables > New user variable `DATALAB_API_KEY`.

**macOS/Linux:** `export DATALAB_API_KEY="your_key_here"` (add to shell profile for persistence).

After changing user-level env vars on Windows, restart Cursor so new agent terminals inherit them.

## Output Paths

Per-device outputs live under `ref/devices/{model}/`:

- `device_registers.yaml` — complete parameter register file (Type 1). **Only produced for register devices.**
- `.parse-cache/` — Marker parse artifacts (gitignored)
- `knowledge/` — per-topic markdown files with YAML frontmatter (Type 2)
- `knowledge/_index.yaml` — extraction metadata and section inventory
- `images/` — curated diagram/image assets referenced in knowledge frontmatter

Repo-level outputs:

- `.cursor/rules/device-{model}.mdc` — device-specific Cursor rule
- `.cursor/rules/device-inventory.mdc` — inventory of all parsed devices
- `CLAUDE.md` — device documentation section (appended if file exists)
- `.cursor/AGENTS.md` — device documentation section (appended if file exists)

## Prompt Files

- `prompts/classify_sections.md` — section classification guidance
- `prompts/extract_registers.md` — LLM-driven register extraction for gap-filling
- `prompts/extractor_guidelines.md` — rules for generating per-manual extractor scripts
- `prompts/extract_knowledge.md` — knowledge file writing guidance

## Guardrails

- Extract every documented parameter. Do not filter.
- Keep Type 1 entries dense and practical; no filler language.
- If uncertain about a field, use null/empty per schema rules instead of guessing.
- Keep parameter IDs, units, ranges, and addresses exact from source.
- Prefer deterministic `knowledge_ref` values produced by `link_knowledge_refs.py`; use null only when no reliable section match exists.
- Prefer Chapter 8 table columns when available:
  - `Parameter` -> `id`
  - `Name` -> `name`
  - `Value Range` -> `range`
  - `Default` -> `default`
  - `Unit` -> `unit`
  - `Modification Mode` -> `write_condition`
  - `Effective Time` -> `takes_effect`

## Reference Extractor

`scripts/extract_registers.py` is a reference implementation based on A6-RS.
Use it as a starting point, but adapt or regenerate for each new manual layout.
