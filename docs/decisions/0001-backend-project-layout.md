# 0001. Backend as a separate uv project with a `src/` layout

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

The app needs Python code that runs inside AWS Lambda (the API handlers). The
repo already has `infra/`, a uv project holding the CDK app that *defines* the
AWS resources. We had to decide where the Lambda code lives and how it's laid
out, before writing any real handlers.

## Options considered

1. **Put the Lambda code inside `infra/`.**
   - Pro: one project, one virtualenv.
   - Con: mixes two different jobs. `infra/` depends on the CDK libraries
     (large, deploy-time only), which must never be bundled into a Lambda. It
     also blurs which tests cover infrastructure and which cover app logic.
2. **A separate `backend/` uv project with a flat layout** (package folder at
   `backend/pension_tracker_api/`, like `infra/` uses).
   - Pro: matches `infra/` exactly.
   - Con: when CDK packages the Lambda code from `backend/`, it would need
     careful exclude rules to keep `tests/`, `.venv/` and config files out of
     the deployment package.
3. **A separate `backend/` uv project with a `src/` layout** (package at
   `backend/src/pension_tracker_api/`).
   - Pro: CDK can bundle exactly `backend/src/`, which contains runtime code
     and nothing else. Tests and dev tooling *can't* leak into a deployment.
   - Pro: tests import the package the same way Lambda will, rather than
     accidentally picking up files from the project root.
   - Con: slightly different from `infra/`'s layout; pytest and mypy each need
     one line of config to find `src/`.

## Decision

Option 3: `backend/` is its own uv project (Python 3.13, matching the Lambda
runtime and `infra/`), with the code in `src/pension_tracker_api/` and tests in
`tests/`. It uses the same tooling and standards as `infra/`: ruff, mypy
(strict), pytest with a 90% coverage gate (branch coverage too), and pip-audit.
moto fakes AWS in tests, and an autouse fixture forces fake credentials so no
test can ever reach the real AWS account.

## Consequences

- Lambda packages stay small and contain only runtime code.
- Runtime dependencies (`[project] dependencies`) are kept separate from
  dev-only tools (`[dependency-groups] dev`), so only the former are bundled.
- Two Python projects to keep in step (Python version, tool versions). CI will
  run the checks for both.
