"""Tests for choosing a stage and validating settings, before any stack is built.

The theme: a mistake on the command line (no stage, a typo'd stage, a missing
or malformed setting) must fail immediately with a clear message, never fall
back to a default that deploys somewhere unintended.
"""

import pytest
from aws_cdk import App

from pension_tracker_infra.app_builder import build_app
from pension_tracker_infra.site_stack import record_name_and_id
from pension_tracker_infra.stages import settings_for
from tests.conftest import TEST_ACCOUNT, TEST_DOMAIN, TEST_EMAIL


@pytest.fixture
def account(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the fake AWS account ID the CDK CLI would normally set."""
    monkeypatch.setenv("CDK_DEFAULT_ACCOUNT", TEST_ACCOUNT)


@pytest.mark.usefixtures("account")
def test_missing_stage_fails_instead_of_defaulting() -> None:
    """No `-c stage=...` must be an error: no command reaches prod by accident."""
    with pytest.raises(ValueError, match="stage"):
        build_app(App(context={"domainName": TEST_DOMAIN, "alertEmail": TEST_EMAIL}))


@pytest.mark.usefixtures("account")
@pytest.mark.parametrize("bad_stage", ["staging", "Prod", "PROD", "production", " dev"])
def test_unknown_stage_fails(bad_stage: str) -> None:
    """Only the exact names "dev" and "prod" are accepted; near misses are rejected."""
    with pytest.raises(ValueError, match="Unknown stage"):
        build_app(App(context={"stage": bad_stage, "domainName": TEST_DOMAIN}))


@pytest.mark.usefixtures("account")
def test_missing_domain_fails() -> None:
    with pytest.raises(ValueError, match="domainName"):
        build_app(App(context={"stage": "dev"}))


@pytest.mark.usefixtures("account")
def test_prod_requires_an_alert_email() -> None:
    """Prod deploys the budget, whose alerts need somewhere to go."""
    with pytest.raises(ValueError, match="alertEmail"):
        build_app(App(context={"stage": "prod", "domainName": TEST_DOMAIN}))


@pytest.mark.usefixtures("account")
def test_dev_needs_no_alert_email() -> None:
    """Dev has no budget, so it builds without one."""
    stacks = build_app(App(context={"stage": "dev", "domainName": TEST_DOMAIN}))
    assert stacks.budget is None


def test_missing_account_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CDK_DEFAULT_ACCOUNT", raising=False)
    with pytest.raises(ValueError, match="No AWS account"):
        build_app(App(context={"stage": "dev", "domainName": TEST_DOMAIN}))


@pytest.mark.usefixtures("account")
@pytest.mark.parametrize(
    "bad_email",
    ["john@jwparnell@hotmail.com", "no-at-sign.com", "spaces in@example.com", "user@nodot"],
)
def test_malformed_alert_email_fails_before_deploy(bad_email: str) -> None:
    """A typo'd email must fail at synth, not as a Budgets error mid-deploy."""
    with pytest.raises(ValueError, match="doesn't look like an email address"):
        build_app(App(context={"stage": "prod", "domainName": TEST_DOMAIN,
                               "alertEmail": bad_email}))


def test_stage_settings() -> None:
    """The per-stage differences, all in one place."""
    prod = settings_for("prod", TEST_DOMAIN)
    dev = settings_for("dev", TEST_DOMAIN)

    assert prod.site_domains == (TEST_DOMAIN, f"www.{TEST_DOMAIN}")
    assert (prod.stack_prefix, prod.noindex, prod.has_budget) == ("PensionTracker", False, True)
    assert dev.site_domains == (f"dev.{TEST_DOMAIN}",)
    assert (dev.stack_prefix, dev.noindex, dev.has_budget) == ("PensionTracker-Dev", True, False)


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        (TEST_DOMAIN, (None, "Apex")),
        (f"www.{TEST_DOMAIN}", ("www", "Www")),
        (f"dev.{TEST_DOMAIN}", ("dev", "Dev")),
    ],
)
def test_record_name_and_id(domain: str, expected: tuple[str | None, str]) -> None:
    """Record names are relative to the zone; ID prefixes match prod's originals."""
    assert record_name_and_id(domain, TEST_DOMAIN) == expected


@pytest.mark.parametrize("outside", ["example.com", f"evil{TEST_DOMAIN}"])
def test_domain_outside_the_zone_is_rejected(outside: str) -> None:
    """``evilpensiontracker.example`` ends with the zone name but isn't inside it."""
    with pytest.raises(ValueError, match="not inside the hosted zone"):
        record_name_and_id(outside, TEST_DOMAIN)
