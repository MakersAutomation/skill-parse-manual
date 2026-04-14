# parse-manual (Cursor skill)

**parse-manual** is a Cursor Agent Skill that turns industrial device PDF manuals into structured, AI-friendly documentation: register maps (YAML), per-topic knowledge markdown, a knowledge index, diagram assets, and Cursor rules so agents can reason about the device consistently in your repo.

The skill is **model-agnostic**: Python scripts handle parsing, I/O, classification, validation, and spot-checks; the agent model handles judgment (e.g. generating a manual-specific register extractor when layouts differ).

## What it produces

For each device you process (under a directory you choose, e.g. `ref/devices/<model>/`):

| Output | Purpose |
|--------|---------|
| `device_registers.yaml` | Type 1 register/parameter map (only when the manual has addressable registers) |
| `knowledge/*.md` | Type 2 topic files with YAML frontmatter |
| `knowledge/_index.yaml` | Section inventory and extraction metadata |
| `images/` | Curated figures referenced from knowledge frontmatter |
| `.parse-cache/` | Parse and intermediate artifacts (typically gitignored) |

At the **repository** root (inferred from the device directory):

| Output | Purpose |
|--------|---------|
| `.cursor/rules/device-<model>.mdc` | Device-specific agent guidance |
| `.cursor/rules/device-inventory.mdc` | Inventory of parsed devices |
| `CLAUDE.md` / `.cursor/AGENTS.md` | Optional append-only device documentation sections |

Manuals **without** registers (e.g. general guides) are supported: use `--skip-registers` so the pipeline produces knowledge, index, rules, and images only.

## Install

### 1. Put the skill where Cursor loads skills

Place this folder at:

- **macOS / Linux:** `~/.cursor/skills/parse-manual`
- **Windows:** `%USERPROFILE%\.cursor\skills\parse-manual`

Example (SSH clone into the skills tree):

```bash
git clone git@github.com:MakersAutomation/skill-parse-manual.git ~/.cursor/skills/parse-manual
```

On Windows PowerShell, adjust the path, for example:

```powershell
git clone git@github.com:MakersAutomation/skill-parse-manual.git "$env:USERPROFILE\.cursor\skills\parse-manual"
```

Ensure the skill’s front matter and instructions are in `SKILL.md` at the root of that folder (this repository layout already matches that).

### 2. Python dependencies

Use Python 3 and install:

```bash
pip install datalab-python-sdk pyyaml
```

### 3. Datalab API key

PDF parsing uses [Datalab](https://documentation.datalab.to/docs/welcome/quickstart). Create an account and API key, then expose it to the shell that runs the scripts:

- **Windows (current session):** `$env:DATALAB_API_KEY = "your_key_here"`
- **macOS / Linux:** `export DATALAB_API_KEY="your_key_here"`

For persistence, set a user environment variable and restart Cursor so agent terminals inherit it. Cursor skills do not inject secrets for you.

## Use

### Invoke the skill in Cursor

- Reference **`@parse-manual`** (or your configured skills path) so the agent loads `SKILL.md`, **or**
- Ask in natural language to parse a manual / build device docs — if **parse-manual** is enabled for the agent, it should follow the workflow in `SKILL.md`.

The agent must collect or confirm:

| Input | Example |
|-------|---------|
| Path to the PDF | `path/to/manual.pdf` |
| Device output directory | `ref/devices/my-device` |
| Manufacturer | `Acme` |
| Model | `X-100` |
| Manual source filename | `X-100_user_manual.pdf` |

### Run the pipeline yourself (optional)

From a terminal, the orchestrator runs steps 1–9 (parse through spot-check) in one command. Paths below use the Unix skills location; on Windows, substitute `%USERPROFILE%\.cursor\skills\parse-manual` or an equivalent.

**Full run (register-capable device)** — requires a generated extractor at `{device_dir}/.parse-cache/extract_registers_generated.py` when the default flow expects it (see `SKILL.md` Step 3):

```bash
python ~/.cursor/skills/parse-manual/scripts/run_skill.py \
  --pdf "/path/to/manual.pdf" \
  --device-dir "/path/to/ref/devices/my-device" \
  --manufacturer "Acme" \
  --model "X-100" \
  --manual-source "manual.pdf"
```

**Knowledge-only device** (no registers):

```bash
python ~/.cursor/skills/parse-manual/scripts/run_skill.py \
  --pdf "/path/to/manual.pdf" \
  --device-dir "/path/to/ref/devices/my-device" \
  --manufacturer "Acme" \
  --model "X-100" \
  --manual-source "manual.pdf" \
  --skip-registers
```

Optional: add `--refine-knowledge` for a second pass on low-confidence knowledge files. Add `--force-parse` to re-run the Datalab parse even when `.parse-cache` exists.

**Phase 2 only** (parse already done; rebuild knowledge, index, rules):

```bash
python ~/.cursor/skills/parse-manual/scripts/run_phase2_only.py \
  --device-dir "/path/to/ref/devices/my-device" \
  --manufacturer "Acme" \
  --model "X-100" \
  --manual-source "manual.pdf"
```

For step-by-step commands, acceptance criteria, validation, and guardrails, see **`SKILL.md`** in this folder.
