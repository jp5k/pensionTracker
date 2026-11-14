"""Assertions against the synthesized CloudFormation templates.

These tests pin down the security and correctness properties we care about
(private bucket, HTTPS only, right certificate region...) so a future change
can't quietly weaken them.

Tests taking the ``stacks`` fixture run once per stage (prod and dev). Tests
taking ``prod_stacks`` or ``dev_stacks`` check what's specific to one stage.
"""

import pytest
from aws_cdk import Stack
from aws_cdk.assertions import Annotations, Match, Template

from pension_tracker_infra.app_builder import AppStacks
from tests.conftest import TEST_DOMAIN, TEST_EMAIL

#: The ID of AWS's managed "SecurityHeadersPolicy" response headers policy. It's
#: the same in every AWS account; prod's distribution references it by this ID.
MANAGED_SECURITY_HEADERS_POLICY_ID = "67f7725c-6f97-4210-82d7-5512b31e9d03"


# --- Every stage ------------------------------------------------------------


def test_certificate_is_in_us_east_1_and_dns_validated(stacks: AppStacks) -> None:
    """CloudFront only accepts us-east-1 certificates; DNS validation auto-renews."""
    assert stacks.certificate.region == "us-east-1"
    Template.from_stack(stacks.certificate).has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {"DomainName": stacks.stage.site_domains[0], "ValidationMethod": "DNS"},
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


def test_distribution_forces_https_on_the_stage_domains(stacks: AppStacks) -> None:
    Template.from_stack(stacks.site).has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like({
                "Aliases": list(stacks.stage.site_domains),
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
def test_every_site_domain_points_at_cloudfront(stacks: AppStacks, record_type: str) -> None:
    template = Template.from_stack(stacks.site)
    for domain in stacks.stage.site_domains:
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Name": f"{domain}.",  # DNS names are fully qualified (trailing dot)
                "Type": record_type,
                "AliasTarget": Match.object_like({
                    # The alias resolves to the distribution's *.cloudfront.net name.
                    "DNSName": {"Fn::GetAtt": [
                        Match.string_like_regexp("^Distribution"), "DomainName"]},
                }),
            },
        )
    # Exactly one A and one AAAA record per domain: no strays from another stage.
    template.resource_properties_count_is(
        "AWS::Route53::RecordSet", {"Type": record_type}, len(stacks.stage.site_domains))


def test_site_content_is_uploaded(stacks: AppStacks) -> None:
    Template.from_stack(stacks.site).resource_count_is("Custom::CDKBucketDeployment", 1)


def test_no_unsuppressed_cdk_nag_findings(stacks: AppStacks) -> None:
    """Every AwsSolutions finding must be fixed or explicitly justified, in every stack."""
    all_stacks: list[Stack] = [stacks.certificate, stacks.site]
    if stacks.budget is not None:
        all_stacks.append(stacks.budget)
    pattern = Match.string_like_regexp("AwsSolutions-.*")
    for stack in all_stacks:
        annotations = Annotations.from_stack(stack)
        errors = annotations.find_error("*", pattern)
        warnings = annotations.find_warning("*", pattern)
        assert not errors, [e.entry.data for e in errors]
        assert not warnings, [w.entry.data for w in warnings]


# --- Prod: must stay exactly as originally deployed ------------------------


def test_prod_keeps_its_original_stack_names(prod_stacks: AppStacks) -> None:
    """Renamed stacks would be *new* stacks to CloudFormation, clashing with the live ones."""
    assert prod_stacks.certificate.stack_name == "PensionTracker-Certificate"
    assert prod_stacks.site.stack_name == "PensionTracker-Site"
    assert prod_stacks.budget is not None
    assert prod_stacks.budget.stack_name == "PensionTracker-Budget"


def test_prod_resources_keep_their_deployed_logical_ids(prod_stacks: AppStacks) -> None:
    """These IDs are what the live CloudFormation stacks track resources by.

    If one changed, CloudFormation would create a new resource and delete the
    old one: new DNS records, a new distribution, a new certificate, an emptied
    and recreated bucket. Every ID below is copied from prod's first deploy.
    """
    site = Template.from_stack(prod_stacks.site)
    assert set(site.find_resources("AWS::Route53::RecordSet")) == {
        "ApexACFD474A9", "ApexAaaaB007CDD0", "WwwA1EFC0D36", "WwwAaaaDBE5206D"}
    assert set(site.find_resources("AWS::S3::Bucket")) == {"SiteBucket397A1860"}
    assert set(site.find_resources("AWS::CloudFront::Distribution")) == {"Distribution830FAC52"}
    certificate = Template.from_stack(prod_stacks.certificate)
    assert set(certificate.find_resources("AWS::CertificateManager::Certificate")) == {
        "SiteCertificate38C247F6"}


def test_prod_certificate_covers_apex_and_www(prod_stacks: AppStacks) -> None:
    Template.from_stack(prod_stacks.certificate).has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {"DomainName": TEST_DOMAIN, "SubjectAlternativeNames": [f"www.{TEST_DOMAIN}"]},
    )


def test_prod_uses_the_managed_security_headers_and_no_noindex(prod_stacks: AppStacks) -> None:
    """Prod keeps AWS's managed policy (unchanged) and must stay visible to search engines."""
    site = Template.from_stack(prod_stacks.site)
    site.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {"DistributionConfig": Match.object_like({
            "DefaultCacheBehavior": Match.object_like({
                "ResponseHeadersPolicyId": MANAGED_SECURITY_HEADERS_POLICY_ID}),
        })},
    )
    site.resource_count_is("AWS::CloudFront::ResponseHeadersPolicy", 0)


def test_budget_alerts_email_at_80_actual_and_100_forecast(prod_stacks: AppStacks) -> None:
    assert prod_stacks.budget is not None
    Template.from_stack(prod_stacks.budget).has_resource_properties(
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


# --- Dev: a separate copy on dev.<domain> ----------------------------------


def test_dev_stacks_are_separately_named(dev_stacks: AppStacks) -> None:
    """Different names mean different CloudFormation stacks: dev can never overwrite prod."""
    assert dev_stacks.certificate.stack_name == "PensionTracker-Dev-Certificate"
    assert dev_stacks.site.stack_name == "PensionTracker-Dev-Site"


def test_dev_has_no_budget(dev_stacks: AppStacks) -> None:
    """The budget is account-wide and belongs to prod; dev deploys never touch it."""
    assert dev_stacks.budget is None


def test_dev_certificate_covers_only_the_dev_subdomain(dev_stacks: AppStacks) -> None:
    Template.from_stack(dev_stacks.certificate).has_resource_properties(
        "AWS::CertificateManager::Certificate",
        {"DomainName": f"dev.{TEST_DOMAIN}",
         "SubjectAlternativeNames": Match.absent()},
    )


def test_dev_sends_noindex_alongside_the_security_headers(dev_stacks: AppStacks) -> None:
    """Dev must not appear in search results, and must keep prod's security headers."""
    Template.from_stack(dev_stacks.site).has_resource_properties(
        "AWS::CloudFront::ResponseHeadersPolicy",
        {"ResponseHeadersPolicyConfig": Match.object_like({
            "CustomHeadersConfig": {"Items": [
                {"Header": "X-Robots-Tag", "Value": "noindex", "Override": True}]},
            "SecurityHeadersConfig": Match.object_like({
                "StrictTransportSecurity": Match.object_like(
                    {"AccessControlMaxAgeSec": 31536000}),
                "ContentTypeOptions": Match.any_value(),
                "FrameOptions": Match.object_like({"FrameOption": "SAMEORIGIN"}),
                "ReferrerPolicy": Match.object_like(
                    {"ReferrerPolicy": "strict-origin-when-cross-origin"}),
                "XSSProtection": Match.object_like({"Protection": True, "ModeBlock": True}),
            }),
        })},
    )
