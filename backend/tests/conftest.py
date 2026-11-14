"""Shared pytest fixtures, including the safety net that keeps tests off real AWS.

pytest loads this file automatically before any test runs. A *fixture* is a
function that prepares something a test needs (and cleans it up afterwards);
tests ask for one by naming it as a parameter.
"""

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_dynamodb import DynamoDBClient

#: Region for every faked AWS call; matches the app's real region (eu-west-1).
TEST_REGION = "eu-west-1"


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every test onto fake AWS credentials, so no test can touch real AWS.

    ``autouse=True`` means this runs for *every* test without being asked for.

    Why it matters: boto3 finds credentials automatically, from environment
    variables, ``~/.aws/config`` (your ``pensiontracker`` SSO profile!) and so
    on. If a test forgot to fake AWS, it could quietly read or write your real
    account, costing money or damaging data. Setting obviously fake keys here,
    and removing any ``AWS_PROFILE``, means a test that escapes moto fails with
    an authentication error instead of succeeding against the real account.

    ``monkeypatch`` changes environment variables for one test only and
    restores them afterwards, so nothing leaks between tests.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")  # noqa: S105 (fake, by design)
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", TEST_REGION)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def dynamodb() -> Iterator[DynamoDBClient]:
    """A DynamoDB client whose every call is answered by moto's in-memory fake.

    Inside ``mock_aws()``, moto intercepts boto3's HTTP requests before they
    leave the machine and answers them from an in-memory model of AWS. Tables
    created here exist only for the duration of one test, so each test starts
    from a clean, empty "account".

    ``yield`` hands the client to the test; code after it (none needed here)
    would run as clean-up. Leaving the ``with`` block switches moto off.

    The client is typed as ``DynamoDBClient`` (from ``boto3-stubs``), so mypy
    checks every method name and argument in tests that use it.
    """
    with mock_aws():
        yield boto3.client("dynamodb", region_name=TEST_REGION)
