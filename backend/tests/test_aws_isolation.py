"""Prove the test setup itself: AWS is faked, and real credentials are never used.

These tests don't exercise app code. They check the safety net in
``conftest.py``, so a future change to it can't silently start sending test
traffic to the real AWS account.
"""

import os

from mypy_boto3_dynamodb import DynamoDBClient


def test_tests_run_with_fake_credentials_and_no_profile() -> None:
    """The autouse fixture must replace any real credentials and SSO profile."""
    assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"
    assert "AWS_PROFILE" not in os.environ


def test_moto_fakes_dynamodb(dynamodb: DynamoDBClient) -> None:
    """A table created inside moto works like DynamoDB but exists only in memory.

    The key schema mirrors the app's planned single table (``PK`` + ``SK``
    strings; see the plan's data model), so this also documents how later tests
    will create it.
    """
    dynamodb.create_table(
        TableName="test-table",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},  # partition key
            {"AttributeName": "SK", "KeyType": "RANGE"},  # sort key
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",  # on-demand, as the real table will be
    )
    dynamodb.put_item(
        TableName="test-table",
        Item={"PK": {"S": "USER#abc"}, "SK": {"S": "PROFILE"}},
    )

    item = dynamodb.get_item(
        TableName="test-table",
        Key={"PK": {"S": "USER#abc"}, "SK": {"S": "PROFILE"}},
    )["Item"]

    assert item["SK"] == {"S": "PROFILE"}


def test_each_test_starts_with_an_empty_account(dynamodb: DynamoDBClient) -> None:
    """Tables from other tests must not leak in: every test gets a fresh fake account."""
    assert dynamodb.list_tables()["TableNames"] == []
