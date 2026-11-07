"""Wires the stacks into a CDK app.

Kept separate from ``app.py`` so tests can build the exact same app with test
settings and inspect the synthesized templates.
"""

import os
import re
from dataclasses import dataclass

from aws_cdk import App, Aspects, Environment
from cdk_nag import AwsSolutionsChecks

from pension_tracker_infra.budget_stack import BudgetStack
from pension_tracker_infra.certificate_stack import CertificateStack
from pension_tracker_infra.site_stack import SiteStack

#: Where the app lives (Ireland). Chosen over London (eu-west-2) because it is
#: slightly cheaper for most services and gets new AWS features first; the
#: extra ~10 ms from the UK is hidden behind CloudFront's edge caches, and the
#: EU is covered by the UK's data-adequacy rules.
APP_REGION = "eu-west-1"
#: CloudFront only accepts certificates from this region.
CERTIFICATE_REGION = "us-east-1"
#: Deliberately loose shape check for the alert email: exactly one "@", no
#: spaces, and a dot in the domain part. Full RFC 5322 validation is famously
#: hairy and not worth it here; the goal is to catch typos like
#: "john@jwparnell@hotmail.com" at synth time, rather than have AWS Budgets
#: reject them halfway through a deploy (forcing a CloudFormation rollback).
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class AppStacks:
    """The stacks that make up the app, returned for tests to inspect."""

    certificate: CertificateStack
    site: SiteStack
    budget: BudgetStack


def _require_context(app: App, key: str, hint: str) -> str:
    """Read a required setting from CDK context, failing with a helpful message.

    Context values come from ``cdk.json`` or ``-c key=value`` on the command line.
    """
    value = app.node.try_get_context(key)
    if not value:
        raise ValueError(f"Missing CDK context '{key}': {hint}")
    return str(value)


def build_app(app: App) -> AppStacks:
    """Add all stacks to ``app`` and switch on cdk-nag security checks.

    Args:
        app: The CDK app to populate.

    Returns:
        The created stacks.

    Raises:
        ValueError: If ``domainName`` / ``alertEmail`` context or the AWS account
            is missing, or ``alertEmail`` isn't shaped like an email address.
    """
    domain_name = _require_context(
        app, "domainName", "set it in infra/cdk.json to the domain registered in Route 53.")
    alert_email = _require_context(
        app, "alertEmail", "pass it on the command line: -c alertEmail=you@example.com")
    if not EMAIL_PATTERN.fullmatch(alert_email):
        raise ValueError(f"alertEmail {alert_email!r} doesn't look like an email address "
                         "(expected something like you@example.com).")

    # The CDK CLI sets this from the --profile in use. Hosted-zone lookups need
    # an explicit account, so we can't fall back to an "environment-agnostic" stack.
    account = os.environ.get("CDK_DEFAULT_ACCOUNT")
    if not account:
        raise ValueError("No AWS account: run cdk with --profile pensiontracker "
                         "(and `aws sso login` if the session expired).")

    certificate = CertificateStack(
        app,
        "PensionTracker-Certificate",
        domain_name=domain_name,
        env=Environment(account=account, region=CERTIFICATE_REGION),
        # Lets the site stack (another region) use this stack's certificate.
        # CDK implements it with SSM parameters + small custom resources.
        cross_region_references=True,
    )
    site = SiteStack(
        app,
        "PensionTracker-Site",
        domain_name=domain_name,
        certificate=certificate.certificate,
        env=Environment(account=account, region=APP_REGION),
        cross_region_references=True,
    )
    budget = BudgetStack(
        app,
        "PensionTracker-Budget",
        alert_email=alert_email,
        env=Environment(account=account, region=APP_REGION),
    )

    # cdk-nag inspects every resource at synth time against the AWS Solutions
    # rule pack; any unsuppressed finding makes the synth report an error.
    Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

    return AppStacks(certificate=certificate, site=site, budget=budget)
