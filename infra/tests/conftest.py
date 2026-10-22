"""Shared fixtures: build the real app once, with fake settings, for every test.

Synthesizing is slow (several seconds), so the app is built once per test
session. No AWS credentials are needed: when the hosted-zone lookup has no
cached answer, CDK substitutes a dummy zone and synthesis carries on.
"""

from collections.abc import Iterator

import pytest
from aws_cdk import App

from pension_tracker_infra.app_builder import AppStacks, build_app

TEST_DOMAIN = "pensiontracker.example"
TEST_EMAIL = "alerts@pensiontracker.example"
TEST_ACCOUNT = "123456789012"


@pytest.fixture(scope="session")
def stacks() -> Iterator[AppStacks]:
    """The app's stacks, built with test context and a fake account ID."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CDK_DEFAULT_ACCOUNT", TEST_ACCOUNT)
        app = App(context={"domainName": TEST_DOMAIN, "alertEmail": TEST_EMAIL})
        yield build_app(app)
