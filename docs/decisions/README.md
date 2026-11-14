# Decision records

Short notes recording *why* a significant choice was made: the situation, the
options considered, what was chosen and the trade-offs accepted. Code shows
**what** was built. These records keep the **why**, so a later reader (or
future you) doesn't have to reconstruct the reasoning, or accidentally undo a
choice made for a good reason.

Each record is numbered and never rewritten after the fact. If a decision
changes, a new record supersedes the old one, which gets a "Superseded by" note.

## Template

```markdown
# NNNN. Title

- **Status:** Accepted (or Superseded by NNNN)
- **Date:** YYYY-MM-DD

## Context
What situation or problem prompted the decision?

## Options considered
The realistic alternatives, with their pros and cons.

## Decision
What was chosen.

## Consequences
What this makes easier, harder, or commits us to.
```

## Index

- [0001. Backend as a separate uv project with a `src/` layout](0001-backend-project-layout.md)
- [0002. Dev and prod stages, with prod keeping its original names](0002-dev-and-prod-stages.md)
