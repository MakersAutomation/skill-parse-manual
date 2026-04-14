Generate a **manual-specific** register extractor script from parse-cache artifacts.

Goal:
- Build `device_registers.yaml` (Type 1) from:
  - `parsed.md`
  - `parsed.json`
- Do not assume table layout matches previous manuals.

Required behavior:

1) Discover schema columns dynamically
- Detect table headers by normalized text.
- Support header variants (e.g., `Value Range`, `Range`, `RW Mode`, `Effective Time`, `Apply Time`).
- Ignore tables that do not contain both parameter ID and name columns.

2) Robust value parsing
- Numeric ranges:
  - `0-20000`
  - `1 to 31`
  - `-9999-9999`
  - power forms such as `-2^31-(2^31-1)`
  - U32 full-span cells: `0-(2^32-1)`, `1-(2^32-1)`, and LaTeX-style `1-(2^{32}-1)` after tag stripping
- Defaults:
  - integer defaults remain integers for integer data types.
  - float only when decimal is explicit.
- Unit scaling:
  - Parse leading numeric scales (`0.1Hz`, `0.01ms`, `0.1%`) into:
    - `scale` = numeric factor
    - `unit` = engineering unit without the scale prefix.
  - If the unit column has no leading factor (e.g. plain `ms`, `-`, or dimensionless), set `scale: null`
    (meaning 1:1 / identity). Do **not** emit `scale: 1` for that case.

3) Data semantics mapping
- `Parameter` -> `id`
- `Name` -> `name`
- `Value Range` -> `range`
- `Default` -> `default`
- `Unit` -> `unit` (+ `scale` when prefixed)
- `Modification Mode` -> `write_condition`
- `Effective Time` -> `takes_effect`
- `Data Type` -> `data_type`
- `Options` / enum text -> `value_map` when parseable as `0: label` style enums.
- Options that describe **bits** (`Bit00: …`, `Bit01: …`) -> `data_type: bitfield` and `bit_layout`
  (map bit index string -> description). Do **not** use `value_map` for bitmasks.

**Boolean / two-state (0/1) parameters**
- When the manual gives **Value range 0–1** (or `0-1`) **and** the Options column is parseable as
  **exactly two entries for `0` and `1`** (e.g. `0: Disable 1: Enable`), treat the register as semantic **`bool`**:
  - Set `data_type: bool` (even if the manual’s data-type column says `U16`; Modbus still uses one holding register).
  - Set **`range: null`** — the allowed values are fully described by `value_map`; keeping `range 0..1` together
    with `value_map` triggers Phase 1 validator noise and duplicates meaning.
  - **Keep `value_map`** with string keys `"0"` and `"1"` so labels (Disable/Enable, etc.) stay machine-readable.
- If the range is `0-1` but Options are **not** two labeled states (no usable `value_map`), emit **`data_type: bool`**,
  **`value_map: null`**, and **`range: {min: 0, max: 1}`** (or `range: null` if your schema allows and the validator
  is updated — prefer explicit `0..1` when there are no labels).
- Do **not** apply this rule when `bit_layout` is present (`bitfield` wins).

4) Protocol mapping
- For Modbus-addressable parameters:
  - derive `address` (decimal) and `address_hex` from ID when manual uses `C GG.OO` style IDs:
    combined 16-bit index = `0xGG00 | 0xOO` (e.g. `C00.13` -> `0x0013` -> address **19**, not 13).
  - set `register_count=2` for 32-bit types (`int32`, `uint32`, `float32`), else 1.

5) Access mapping
- Prefer explicit read/write metadata if present.
- If absent, use conservative heuristics (e.g., monitoring groups may be read-only), but keep this clearly marked heuristic.

6) Record merge strategy
- Same parameter may appear in multiple tables.
- Prefer richer records and higher-confidence chapter tables.
- Preserve the best `source_page`.
- Never duplicate IDs.

7) Brief quality
- Prefer descriptive text from manual options/description columns.
- If absent, synthesize a compact brief from known structured fields (name, range, default, unit, write/effect).
- Avoid filler language.

8) Source page handling
- Track source page from table nodes where possible.
- If missing, use best available mention page.
- Prefer **`source_page` = printed manual footer** when a stable delta from the Marker/Datalab 0-based page
  index is known (reference extractor: `--source-page-delta`, default **-2** for A6-RS:
  `source_page = max(1, page_index + 1 + delta)`).
- Emit `extraction_metadata.source_page_basis: printed_manual_footer` and record
  `pdf_file_page_1based_to_source_page_delta` for reproducibility. Use delta **0** when file pages already
  match the printed book.

9) Validation compatibility
- Output must satisfy `validate_registers.py`.
- Phase 1 warns on **`value_map` + `range` 0..1** together; use the boolean rules above so two-state labeled
  parameters are **`bool` + `value_map` + `range: null`**.
- Keep `knowledge_ref: null` in Phase 1.
- Emit complete `groups` and `parameters`.

Deliverables for each manual:
- `ref/devices/{model}/.parse-cache/extract_registers_generated.py`
- `ref/devices/{model}/device_registers.yaml`
