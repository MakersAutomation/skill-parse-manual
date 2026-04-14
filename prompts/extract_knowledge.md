Rewrite this manual section as a Type 2 knowledge markdown file.

Input:
- Narrative section text
- Related parameter IDs
- Type 2 frontmatter schema from `schemas/type2_frontmatter.yaml`

Output:
- Markdown file with YAML frontmatter + body

Writing style:
- Direct, precise, no filler.
- Keep exact parameter IDs, values, units, and procedure ordering.
- Preserve all warnings and safety statements.
- If source text is unclear/translated poorly, rewrite for clarity and reduce confidence.

Body rules:
- Lead with what the section does.
- Use parameter IDs inline.
- Include procedures as ordered steps when available.
- Add cross-references to related sections when useful.
