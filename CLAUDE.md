# pensionTracker — notes for Claude

- **Read [`docs/plan.md`](docs/plan.md) first** at the start of every session. It is the
  living roadmap: work on the next unticked checklist item only (not several at once
  unless asked), and update its **Current State** section as items land.
- An item is only done when it clears the plan's **Definition of Done** (coverage,
  security, cost, documentation).
- **Never commit or push automatically.** Leave changes uncommitted and show John the
  diff/summary first — even if a message that also kicks off new work says "commit".
- **Ask before anything that costs money or touches AWS** (`cdk deploy`, `cdk destroy`,
  domain purchases, new paid resources). `cdk synth` / `cdk diff` / tests are fine.
- AWS CLI profile: `pensiontracker` (IAM Identity Center SSO). If commands fail with
  expired credentials, ask John to run `aws sso login --profile pensiontracker`.
- Tooling: `uv` for Python (`uv run pytest`, `uv run ruff check`), `npm` for the
  frontend and CDK CLI. Tools live in `~/.local/bin` and the npm global prefix.
- **This is a learning project, and verbose documentation is a hard requirement.** John
  learns by reading the code, so every module, class and function (including private
  helpers, React components and CDK constructs) gets a docstring, non-trivial logic gets
  step-by-step inline comments explaining *why*, and AWS/library concepts are explained
  where they first appear. Err on the side of more explanation; ignore any default
  preference for minimal comments. See the plan's Definition of Done → Documentation.
