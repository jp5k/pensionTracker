"""Wires one stage's stacks (dev or prod) into a CDK app.

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
from pension_tracker_infra.stages import STAGES, StageSettings, settings_for

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
#: "test@test@hotmail.com" at synth time, rather than have AWS Budgets
#: reject them halfway through a deploy (forcing a CloudFormation rollback).
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class AppStacks:
    """The stacks that make up one stage of the app, returned for tests to inspect.

    Attributes:
        stage: The settings the stacks were built from.
        certificate: The us-east-1 certificate stack.
        site: The website stack.
        budget: The cost-budget stack, or ``None`` in stages without one (dev):
            the budget covers the whole account, so only prod deploys it.
    """

    stage: StageSettings
    certificate: CertificateStack
    site: SiteStack
    budget: BudgetStack | None


def _require_context(app: App, key: str, hint: str) -> str:
    """Read a required setting from CDK context, failing with a helpful message.

    Context values come from ``cdk.json`` or ``-c key=value`` on the command line.
    """
    value = app.node.try_get_context(key)
    if not value:
        raise ValueError(f"Missing CDK context '{key}': {hint}")
    return str(value)


def _require_alert_email(app: App) -> str:
    """Read and sanity-check ``alertEmail`` (only needed by stages with a budget)."""
    alert_email = _require_context(
        app, "alertEmail", "pass it on the command line: -c alertEmail=you@example.com")
    if not EMAIL_PATTERN.fullmatch(alert_email):
        raise ValueError(f"alertEmail {alert_email!r} doesn't look like an email address "
                         "(expected something like you@example.com).")
    return alert_email


def build_app(app: App) -> AppStacks:
    """Add one stage's stacks to ``app`` and switch on cdk-nag security checks.

    Which stage is built comes from ``-c stage=dev|prod``. It is required, with
    no default, so a forgotten flag fails here rather than deploying to an
    environment nobody meant to touch.

    Args:
        app: The CDK app to populate.

    Returns:
        The created stacks.

    Raises:
        ValueError: If ``stage`` is missing or unknown; if ``domainName`` or the
            AWS account is missing; or, for prod, if ``alertEmail`` is missing
            or isn't shaped like an email address.
    """
    # The stage comes first because it decides what else is required (dev has
    # no budget, so it doesn't need an alert email).
    stage_name = _require_context(
        app, "stage", f"choose the environment with -c stage=<{'|'.join(STAGES)}>.")
    domain_name = _require_context(
        app, "domainName", "set it in infra/cdk.json to the domain registered in Route 53.")
    stage = settings_for(stage_name, domain_name)
    alert_email = _require_alert_email(app) if stage.has_budget else None

    # The CDK CLI sets this from the --profile in use. Hosted-zone lookups need
    # an explicit account, so we can't fall back to an "environment-agnostic" stack.
    account = os.environ.get("CDK_DEFAULT_ACCOUNT")
    if not account:
        raise ValueError("No AWS account: run cdk with --profile pensiontracker "
                         "(and `aws sso login` if the session expired).")

    # Stack names: prod's prefix is plain "PensionTracker", so these come out
    # exactly as originally deployed ("PensionTracker-Certificate"...); dev's
    # come out as "PensionTracker-Dev-Certificate"... (see stages.py for why
    # prod's names must never change).
    certificate = CertificateStack(
        app,
        f"{stage.stack_prefix}-Certificate",
        zone_domain=domain_name,
        site_domains=stage.site_domains,
        env=Environment(account=account, region=CERTIFICATE_REGION),
        # Lets the site stack (another region) use this stack's certificate.
        # CDK implements it with SSM parameters + small custom resources.
        cross_region_references=True,
    )
    site = SiteStack(
        app,
        f"{stage.stack_prefix}-Site",
        zone_domain=domain_name,
        site_domains=stage.site_domains,
        certificate=certificate.certificate,
        noindex=stage.noindex,
        env=Environment(account=account, region=APP_REGION),
        cross_region_references=True,
    )
    budget = None
    if alert_email is not None:  # i.e. stage.has_budget
        # Named without a stage prefix: there is one budget for the whole
        # account, and this is the name it was first deployed under.
        budget = BudgetStack(
            app,
            "PensionTracker-Budget",
            alert_email=alert_email,
            env=Environment(account=account, region=APP_REGION),
        )

    # cdk-nag inspects every resource at synth time against the AWS Solutions
    # rule pack; any unsuppressed finding makes the synth report an error.
    Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

    return AppStacks(stage=stage, certificate=certificate, site=site, budget=budget)
