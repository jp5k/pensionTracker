# 0002. Dev and prod stages, with prod keeping its original names

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

Milestone 1 deployed a single environment: three stacks named
`PensionTracker-Certificate`, `PensionTracker-Site` and `PensionTracker-Budget`,
serving the live site at `pensiontrackerapp.com` and `www.`. Before building the
backend we want a separate **dev** copy to try changes on, at
`dev.pensiontrackerapp.com`, without ever risking the live site. Three things
needed deciding: how a command picks its environment, what the stacks are
called, and what differs between the two.

## Options considered

**Choosing the environment** (`-c stage=...` on every `cdk` command):

1. **Required, no default.** A forgotten flag is an error.
2. **Default to dev.** Convenient, and a mistake only affects dev, but it's easy
   to lose track of which environment a command really targeted.
3. **Default to prod.** A forgotten flag goes straight to the live site.

**Naming the stacks:**

1. **Prefix both stages** (`PensionTracker-Prod-Site`, `PensionTracker-Dev-Site`).
   Symmetrical, but to CloudFormation a renamed stack is a *new* stack. It would
   try to create a second set of DNS records for the live domain (which fails,
   since the old stack still owns them), or force a delete-and-recreate of the
   live site.
2. **Keep prod's original names, prefix only dev.** Slightly asymmetrical, but
   prod's stacks are untouched.

## Decision

- The stage is **required** (option 1): no default, so nothing reaches prod by
  accident. Unknown values, including near misses like `Prod`, are rejected.
- **Prod keeps its original stack names**, and dev's are
  `PensionTracker-Dev-Certificate` and `PensionTracker-Dev-Site`. Inside the
  stacks, prod's resources also keep their original *construct IDs* (`ApexA`,
  `WwwAaaa`, `SiteBucket`...). CloudFormation tracks each resource by a logical
  ID derived from its construct ID, so a changed ID would also mean
  replacement. Tests pin prod's stack names and exact logical IDs.
- Everything that differs between stages lives in one place,
  `infra/pension_tracker_infra/stages.py`:

  | | prod | dev |
  |---|---|---|
  | Domains | apex + `www.` | `dev.` only |
  | Response headers | AWS-managed security headers policy (unchanged) | the same headers + `X-Robots-Tag: noindex` |
  | Budget stack | yes (the budget is account-wide, so it lives in one stage) | no, and so no `alertEmail` needed |

- Both stages use the same hosted zone and region layout, so `dev.` costs
  nothing extra beyond a free certificate and a free-tier CloudFront
  distribution.

Verified before accepting: `cdk diff -c stage=prod` against the live stacks
reported **no differences** in all three stacks, and `cdk diff -c stage=dev`
showed only two new stacks.

## Consequences

- Every `cdk` command (including `cdk bootstrap` run inside `infra/`) needs
  `-c stage=...`. That's slightly more typing in exchange for never deploying
  to the wrong place.
- Stack names are asymmetric (no "Prod" in prod's names). The asymmetry is
  documented in `stages.py` and pinned by tests, so it can't be "tidied up" by
  accident.
- Dev uses the custom headers policy and prod the managed one. When the planned
  CSP work changes prod's headers, both stages will move to custom policies,
  and that change will be reviewed with a prod `cdk diff`.
