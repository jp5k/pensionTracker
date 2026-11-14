# AWS services used by pensionTracker

A quick reference: every AWS service the project uses or plans to use, what the
service *is* in general, what *we* use it for, and roughly what it costs. For
the full design see [`plan.md`](plan.md). For how a request travels through these
services, see [`how-it-works.md`](how-it-works.md).

**Status key:** ✅ in use now · 🔜 planned (in the roadmap) · 💡 stretch / later

> Keep this file current: when a new AWS service is added, add it here, along
> with its cost note in the plan (Definition of Done → Cost).

## How they fit together

```
Browser ──HTTPS──▶ CloudFront ──▶ S3 (React app files)
                       │
                       └─ /api/* ──▶ API Gateway (checks Cognito sign-in token)
                                         │
                                         ▼
                                      Lambda ──▶ DynamoDB
Browser ──sign in──▶ Cognito

EventBridge Scheduler ──▶ Lambda (demo clean-up, daily prices)
Budgets ──▶ SNS ──▶ Lambda (kill switch flag in Parameter Store)
```

---

## Website and domain

| Service | What it is | What we use it for | Status | Cost |
|---|---|---|---|---|
| **Route 53** | AWS's DNS service and domain registrar | Registered `pensiontrackerapp.com`; its hosted zone holds the DNS records for the prod site (apex and `www.`) and the dev site (`dev.`) | ✅ | ~$16/year domain + $0.50/month hosted zone; alias lookups to CloudFront are free |
| **Certificate Manager (ACM)** | Issues and auto-renews TLS (HTTPS) certificates | Certificates for the site's domains. CloudFront requires them in us-east-1, hence a separate small stack there | ✅ | Free (public certificates) |
| **CloudFront** | Global content delivery network (CDN): servers worldwide that cache and serve content close to users | Serves the site over HTTPS, redirects `http://` to `https://`; later routes `/api/*` to the API and adds security headers (CSP, HSTS...) | ✅ | Always-free tier: 1 TB transfer + 10M requests/month |
| **S3** | Object storage ("buckets" of files) | Private bucket holding the built React app; only CloudFront can read it (Origin Access Control) | ✅ | A few KB stored: pennies at most |
| **Shield Standard** | Automatic protection against network-level DDoS attacks | Comes with CloudFront; nothing to configure | ✅ | Free |

## Application backend

| Service | What it is | What we use it for | Status | Cost |
|---|---|---|---|---|
| **API Gateway (HTTP API)** | Managed "front door" for APIs: routing, auth checks, throttling | Checks each request's Cognito sign-in token *before* any code runs, routes paths to Lambdas, throttles per route. Lives behind CloudFront at `/api/*` | 🔜 | $1.00 per million requests. Its old "12 months free" allowance doesn't apply to accounts created after July 2025 (AWS moved new accounts to a credits-based free plan), but at our volume it's pennies |
| **Lambda** | Runs code on demand without managing servers; you pay per request and per millisecond | The app's Python logic: pots, holdings, summary, demo accounts, clean-up, price fetching. Code in [`backend/`](../backend/) | 🔜 (health handler written) | Free tier: 1M requests + 400,000 GB-seconds/month |
| **DynamoDB** | Serverless NoSQL key-value database | Single table for all user data; point-in-time recovery; TTL auto-deletes demo data | 🔜 | On-demand, pennies at our scale; PITR ~$0.20/GB-month |
| **Cognito** | User sign-up/sign-in service; issues JWTs | Accounts, email verification, MFA (authenticator apps) and passkeys. Never SMS (cost-safety rule) | 🔜 | Essentials tier free up to 10,000 monthly active users |
| **EventBridge Scheduler** | Runs targets (e.g. Lambdas) on a timetable | Daily demo-user clean-up; daily fund-price and exchange-rate fetch (phase 2) | 🔜 | Free tier: 14M invocations/month |
| **Systems Manager Parameter Store** | Stores configuration values and secrets | Price API key (encrypted SecureString, phase 2); budget kill-switch flag | 🔜 | Standard parameters free |
| **KMS** | Manages encryption keys | Behind Parameter Store's SecureString; we use the free AWS-managed `aws/ssm` key | 🔜 | Free (AWS-managed key) |

## Infrastructure and deployment

| Service | What it is | What we use it for | Status | Cost |
|---|---|---|---|---|
| **CloudFormation** | Deploys AWS resources from templates, as "stacks" | Everything CDK defines (in [`infra/`](../infra/)) is deployed as CloudFormation stacks; failed changes roll back automatically | ✅ | Free |
| **ECR** | Container image registry | Created by `cdk bootstrap` in case container images are used; empty and unused for now | ✅ | Free while empty |
| **IAM** | Users, roles and permissions | Least-privilege roles for each Lambda and service; later the GitHub Actions deploy role via OIDC (no long-lived keys) | ✅ | Free |

## Account and access

| Service | What it is | What we use it for | Status | Cost |
|---|---|---|---|---|
| **IAM Identity Center** | Single sign-on for AWS accounts, with short-lived credentials | John's `john` login for the console and CLI (`pensiontracker` profile); single-Region instance in eu-west-1 | ✅ | Free |
| **Organizations** | Groups AWS accounts under one management account | Created alongside Identity Center; could later hold a separate prod account | ✅ | Free |

## Cost and monitoring

| Service | What it is | What we use it for | Status | Cost |
|---|---|---|---|---|
| **Budgets** | Cost budgets with alerts | $10/month budget emailing at 80% actual and 100% forecast; later also triggers the kill switch | ✅ | First two budgets free |
| **Cost Anomaly Detection** | Machine-learning alerts for unusual spending | `Default-Services-Monitor`, emailing on per-service spending anomalies | ✅ | Free |
| **SNS** | Pub/sub notifications | Carries the budget alert to the kill-switch Lambda | 🔜 | Free tier covers it |
| **CloudWatch Logs** | Stores and searches logs | Logs from every Lambda, for debugging | 🔜 | 5 GB/month ingestion free |

## Stretch / later

| Service | What it is | What we'd use it for | Status | Cost |
|---|---|---|---|---|
| **Bedrock** | Access to foundation models (including Claude) via API | AI insights: plain-English explanations of a portfolio (education, not advice) | 💡 | Pay per token; capped in code (see plan → Cost safety) |
| **AWS Backup** | Scheduled, retained backups across services | Longer-term DynamoDB backups beyond PITR's 35 days | 💡 | Per GB stored: check before enabling |
| **CloudWatch alarms & dashboards, X-Ray** | Metrics alarms, dashboards and request tracing | Monitoring and tracing requests through CloudFront → API → Lambda → DynamoDB | 💡 | Small free tiers; check before enabling |
| **WAF** | Web application firewall (rules, per-IP rate limits) | Considered, **not planned**: ~$6+/month, and in-code limits cover our needs | 💡 | ~$5/month per web ACL + per rule + per request |
