# pensionTracker

A multi-user, UK-focused pension tracker: sign up, add your pension pots
(workplace, SIPP, personal, State Pension), record contributions and valuations,
and see how your pensions are growing and where they're heading at retirement.

Built as a learning and portfolio project for **AWS serverless** and
**infrastructure as code**. See [`docs/plan.md`](docs/plan.md) for the roadmap
and architecture, and [`docs/how-it-works.md`](docs/how-it-works.md) for a
plain-English walkthrough. [`docs/aws-services.md`](docs/aws-services.md) lists every AWS
service used, what it's for and what it costs.

## Stack

- **Frontend:** React + TypeScript (Vite), hosted on S3 + CloudFront _(planned; currently a static hello-world page)_
- **Backend:** Python 3.13 AWS Lambda functions behind API Gateway HTTP API, in [`backend/`](backend/) _(code started; not yet deployed)_
- **Auth:** Amazon Cognito _(planned)_
- **Data:** DynamoDB _(planned)_
- **Infrastructure:** AWS CDK (Python) → CloudFormation, in [`infra/`](infra/)

## Prerequisites

- AWS CLI v2, with an SSO profile named `pensiontracker` — see [`docs/aws-setup.md`](docs/aws-setup.md)
- [`uv`](https://docs.astral.sh/uv/) (Python tooling)
- Node.js + the AWS CDK CLI (`npm install -g aws-cdk`)

## Testing

Each Python project has the same checks. Run them from its folder:

```bash
cd backend             # Lambda code (or: cd infra, for the CDK app)
uv sync                # create/update the virtualenv from uv.lock
uv run pytest          # tests + the ≥90% coverage gate
uv run ruff check      # lint
uv run ruff format --check   # formatting
uv run mypy .          # strict type checking
uv run pip-audit       # known-vulnerability check on dependencies
```

`backend/` tests fake AWS with [moto](https://docs.getmoto.org/) and are forced
onto fake credentials, so they never touch the real AWS account. `infra/` tests
also run the cdk-nag security checks against the synthesized templates.

Significant design choices are recorded in [`docs/decisions/`](docs/decisions/).

## Deploying

```bash
aws sso login --profile pensiontracker
cd infra
cdk synth  --profile pensiontracker -c alertEmail=you@example.com   # inspect CloudFormation
cdk diff   --profile pensiontracker -c alertEmail=you@example.com
cdk deploy --all --profile pensiontracker -c alertEmail=you@example.com
```

The domain name is set in [`infra/cdk.json`](infra/cdk.json) (`domainName`).

## Features

_(documented here as they're added)_
