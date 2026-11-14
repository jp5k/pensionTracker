# AWS setup (one-off)

Steps done once, by hand, to get an AWS account ready for CDK deployments.
Everything after this is created by code in `infra/`.

## 1. Secure the root user

The root user (the email address the account was created with) can do anything,
including close the account, so it is only used for rare account-level tasks.

1. Sign in as root → account menu (top right) → **Security credentials**.
2. **Assign MFA device** → an authenticator app (or passkey/security key).

## 2. Create an everyday admin user with IAM Identity Center

IAM Identity Center gives you a login with **short-lived credentials**: the CLI
gets temporary keys via a browser sign-in, so there are no long-lived access keys
sitting on disk to leak.

1. Console → **IAM Identity Center** → make sure the region selector says
   **Europe (Ireland) eu-west-1** → **Enable** → choose **Single-Region instance**.
   (Multi-Region replicates sign-in to a second region for resilience, but it
   needs a customer-managed KMS key at ~$1/month each and an external identity
   provider rather than Identity Center's own directory. Overkill for one user.)
2. **Users → Add user**: username `john`, your email. Accept the invitation email
   and set a password + MFA.
3. **Permission sets → Create permission set → Predefined → AdministratorAccess**.
   (Broad, but acceptable for a single-person learning account; tighten later.)
   - Name: keep `AdministratorAccess`. Description: optional.
   - **Session duration: 4 hours.** This is how long CLI credentials last before
     `aws sso login` is needed again. The 1-hour default interrupts long sessions,
     and the 12-hour maximum leaves a stolen session usable for longer.
   - Relay state: blank (the console page to land on after sign-in).
   - Tags: optional, e.g. `Project` = `pensiontracker` (free metadata).
4. **AWS accounts** → tick your account → **Assign users or groups** → `john` →
   `AdministratorAccess`.
5. Note the **AWS access portal URL** on the Identity Center dashboard — the CLI
   needs it. Use the **IPv4-only** one ending in `/start`
   (e.g. `https://d-xxxxxxxxxx.awsapps.com/start`): every CLI version accepts it.
   The dual-stack (`*.app.aws`) and Regional IPv4 (`*.portal.amazonaws.com`)
   URLs open the same portal; dual-stack only matters on IPv6-only networks.

## 3. Register the domain (Route 53)

1. Console → **Route 53 → Registered domains → Register domains**.
2. Search for the name, check the yearly price, and buy it (contact details
   privacy protection on).
3. Confirm the **registrant verification email** (the domain can be suspended if
   you don't).
4. Route 53 creates a **hosted zone** for the domain automatically ($0.50/month).
   CDK looks this zone up by name, so don't delete it.
5. Put the domain into `infra/cdk.json` as `domainName`.

## 4. Local tools

Installed into the user's home directory (no `sudo`):

```bash
# AWS CLI v2 → ~/.local/bin/aws
curl -sSfL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip awscliv2.zip && ./aws/install -i ~/.local/aws-cli -b ~/.local/bin

# uv (Python project/package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# AWS CDK CLI
npm install -g aws-cdk
```

## 5. Connect the CLI

```bash
aws configure sso
#   SSO session name:       pensiontracker
#   SSO start URL:          <access portal URL from step 2.5>
#   SSO region:             eu-west-1
#   SSO registration scopes: (accept default)
#   → browser opens, approve → choose the account and AdministratorAccess role
#   CLI default region:     eu-west-1
#   CLI default output:     json
#   Profile name:           pensiontracker

aws sts get-caller-identity --profile pensiontracker   # should print your account ID
```

Credentials expire after a few hours; renew with
`aws sso login --profile pensiontracker`.

## 6. Bootstrap CDK

CDK needs a small "bootstrap" stack (an S3 bucket + IAM roles for deployments)
in every account/region it deploys to. We use two regions: eu-west-1 (Ireland) for
the app, and us-east-1 because CloudFront only accepts certificates from there.

```bash
ACCOUNT=$(aws sts get-caller-identity --profile pensiontracker --query Account --output text)
cd infra
cdk bootstrap aws://$ACCOUNT/eu-west-1 aws://$ACCOUNT/us-east-1 \
  --profile pensiontracker -c stage=dev
```

Inside `infra/`, `cdk bootstrap` still runs the app first, even with the
environments given explicitly, and the app refuses to start without a `stage`
(see `stages.py`). Bootstrap is per account/region, not per stage, so either
stage works; `dev` is used because it doesn't need an `alertEmail`.
(Bootstrapping was originally done before stages existed, with
`-c alertEmail=...` instead; the result is identical.)
