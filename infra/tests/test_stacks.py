"""Assertions against the synthesized CloudFormation templates.

These tests pin down the security and correctness properties we care about
(private bucket, HTTPS only, right certificate region...) so a future change
can't quietly weaken them.
"""

import pytest
from aws_cdk import App, Stack
from aws_cdk.assertions import Annotations, Match, Template

from pension_tracker_infra.app_builder import AppStacks, build_app
from tests.conftest import TEST_DOMAIN, TEST_EMAIL


def test_certificate_is_in_us_east_1_and_dns_validated(stacks: AppStacks) -> None:
    """CloudFront only accepts us-east-1 certificates; DNS validation auto-renews."""
    assert stacks.certificate.region == "us-east-1"
    Template.from_stack(stacks.certificate).has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {
            "DomainName": TEST_DOMAIN,
            "SubjectAlternativeNames": [f"www.{TEST_DOMAIN}"],
            "ValidationMethod": "DNS",
        },
    )


def test_site_lives_in_ireland(stacks: AppStacks) -> None:
    assert stacks.site.region == "eu-west-1"


def test_bucket_is_private_and_encrypted(stacks: AppStacks) -> None:
    template = Template.from_stack(stacks.site)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "BucketEncryption": Match.object_like({
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            }),
        },
    )


def test_bucket_policy_denies_plain_http(stacks: AppStacks) -> None:
    Template.from_stack(stacks.site).has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with([
                    Match.object_like({
                        "Effect": "Deny",
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    })
                ])
            }
        },
    )


def test_cloudfront_reads_bucket_via_origin_access_control(stacks: AppStacks) -> None:
    """The bucket policy may only grant read access to the CloudFront service."""
    template = Template.from_stack(stacks.site)
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with([
                    Match.object_like({
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                    })
                ])
            }
        },
    )


def test_distribution_forces_https_on_our_domain(stacks: AppStacks) -> None:
    Template.from_stack(stacks.site).has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like({
                "Aliases": [TEST_DOMAIN, f"www.{TEST_DOMAIN}"],
                "DefaultRootObject": "index.html",
                "DefaultCacheBehavior": Match.object_like({
                    "ViewerProtocolPolicy": "redirect-to-https",
                }),
                "ViewerCertificate": Match.object_like({
                    "MinimumProtocolVersion": "TLSv1.2_2021",
                    "SslSupportMethod": "sni-only",
                }),
            })
        },
    )


@pytest.mark.parametrize("record_type", ["A", "AAAA"])
def test_apex_and_www_point_at_cloudfront(stacks: AppStacks, record_type: str) -> None:
    template = Template.from_stack(stacks.site)
    for name in (f"{TEST_DOMAIN}.", f"www.{TEST_DOMAIN}."):
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Name": name,
                "Type": record_type,
                "AliasTarget": Match.object_like({
                    # The alias resolves to the distribution's *.cloudfront.net name.
                    "DNSName": {"Fn::GetAtt": [
                        Match.string_like_regexp("^Distribution"), "DomainName"]},
                }),
            },
        )


def test_site_content_is_uploaded(stacks: AppStacks) -> None:
    Template.from_stack(stacks.site).resource_count_is("Custom::CDKBucketDeployment", 1)


def test_budget_alerts_email_at_80_actual_and_100_forecast(stacks: AppStacks) -> None:
    Template.from_stack(stacks.budget).has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": Match.object_like({
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "BudgetLimit": {"Amount": 10, "Unit": "USD"},
            }),
            "NotificationsWithSubscribers": [
                {
                    "Notification": Match.object_like({
                        "NotificationType": "ACTUAL", "Threshold": 80}),
                    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": TEST_EMAIL}],
                },
                {
                    "Notification": Match.object_like({
                        "NotificationType": "FORECASTED", "Threshold": 100}),
                    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": TEST_EMAIL}],
                },
            ],
        },
    )


@pytest.mark.parametrize("name", ["certificate", "site", "budget"])
def test_no_unsuppressed_cdk_nag_findings(stacks: AppStacks, name: str) -> None:
    """Every AwsSolutions finding must be fixed or explicitly justified."""
    stack: Stack = getattr(stacks, name)
    annotations = Annotations.from_stack(stack)
    pattern = Match.string_like_regexp("AwsSolutions-.*")
    errors = annotations.find_error("*", pattern)
    warnings = annotations.find_warning("*", pattern)
    assert not errors, [e.entry.data for e in errors]
    assert not warnings, [w.entry.data for w in warnings]


@pytest.mark.parametrize(
    ("context", "account", "message"),
    [
        ({"alertEmail": TEST_EMAIL}, "123456789012", "domainName"),
        ({"domainName": TEST_DOMAIN}, "123456789012", "alertEmail"),
        ({"domainName": TEST_DOMAIN, "alertEmail": TEST_EMAIL}, None, "No AWS account"),
    ],
)
def test_missing_settings_fail_with_helpful_message(
    monkeypatch: pytest.MonkeyPatch, context: dict[str, str], account: str | None, message: str
) -> None:
    if account:
        monkeypatch.setenv("CDK_DEFAULT_ACCOUNT", account)
    else:
        monkeypatch.delenv("CDK_DEFAULT_ACCOUNT", raising=False)
    with pytest.raises(ValueError, match=message):
        build_app(App(context=context))


@pytest.mark.parametrize(
    "bad_email",
    ["john@jwparnell@hotmail.com", "no-at-sign.com", "spaces in@example.com", "user@nodot"],
)
def test_malformed_alert_email_fails_before_deploy(
    monkeypatch: pytest.MonkeyPatch, bad_email: str
) -> None:
    """A typo'd email must fail at synth, not as a Budgets error mid-deploy."""
    monkeypatch.setenv("CDK_DEFAULT_ACCOUNT", "123456789012")
    with pytest.raises(ValueError, match="doesn't look like an email address"):
        build_app(App(context={"domainName": TEST_DOMAIN, "alertEmail": bad_email}))
