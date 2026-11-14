"""Shared fixtures: build the real app for each stage, with fake settings.

Synthesizing is slow (several seconds), so each stage's app is built once per
test session. No AWS credentials are needed: when the hosted-zone lookup has no
cached answer, CDK substitutes a dummy zone and synthesis carries on.
"""

from collections.abc import Iterator

import pytest
from aws_cdk import App

from pension_tracker_infra.app_builder import AppStacks, build_app

TEST_DOMAIN = "pensiontracker.example"
TEST_EMAIL = "alerts@pensiontracker.example"
TEST_ACCOUNT = "123456789012"


def _build(context: dict[str, str]) -> Iterator[AppStacks]:
    """Build the app with ``context`` and a fake account ID, then yield its stacks."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CDK_DEFAULT_ACCOUNT", TEST_ACCOUNT)
        yield build_app(App(context=context))


@pytest.fixture(scope="session")
def prod_stacks() -> Iterator[AppStacks]:
    """The prod stage's stacks (apex + www, budget)."""
    yield from _build({"stage": "prod", "domainName": TEST_DOMAIN, "alertEmail": TEST_EMAIL})


@pytest.fixture(scope="session")
def dev_stacks() -> Iterator[AppStacks]:
    """The dev stage's stacks (dev.<domain>, noindex, no budget, no alert email)."""
    yield from _build({"stage": "dev", "domainName": TEST_DOMAIN})


@pytest.fixture(params=["prod", "dev"])
def stacks(request: pytest.FixtureRequest, prod_stacks: AppStacks,
           dev_stacks: AppStacks) -> AppStacks:
    """Each stage in turn: a test using this fixture runs once for prod, once for dev.

    Use it for properties *every* environment must have (private bucket, HTTPS
    only...), so dev can never quietly fall below prod's security standard.
    """
    return prod_stacks if request.param == "prod" else dev_stacks
