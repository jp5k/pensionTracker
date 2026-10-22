"""Static website hosting: private S3 bucket behind CloudFront, on our domain.

Request path: browser → CloudFront (HTTPS, our certificate) → S3. The bucket is
completely private; CloudFront reads it using Origin Access Control (OAC), so
the S3 URL itself returns "Access Denied" and the domain is the only way in.
"""

from pathlib import Path
from typing import Any

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from cdk_nag import NagSuppressions
from constructs import Construct

#: Folder whose contents are uploaded to the bucket (the hello-world page for
#: now; the React build output later).
SITE_DIR = Path(__file__).resolve().parent.parent / "site"


class SiteStack(Stack):
    """Bucket + CloudFront distribution + DNS records + content upload.

    Attributes:
        bucket: The private S3 bucket holding the site's files.
        distribution: The CloudFront distribution serving them.
    """

    def __init__(self, scope: Construct, construct_id: str, *, domain_name: str,
                 certificate: acm.ICertificate, **kwargs: Any) -> None:
        """Create the hosting resources.

        Args:
            scope: Parent construct (the CDK app).
            construct_id: Logical name of this stack.
            domain_name: The apex domain, e.g. ``pensiontracker.uk``.
            certificate: us-east-1 ACM certificate covering the apex and ``www``.
            **kwargs: Standard ``Stack`` options.
        """
        super().__init__(scope, construct_id, **kwargs)

        zone = route53.HostedZone.from_lookup(self, "Zone", domain_name=domain_name)

        self.bucket = s3.Bucket(
            self,
            "SiteBucket",
            # No public access of any kind; CloudFront gets in via OAC instead.
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            # Bucket policy denies any non-HTTPS request.
            enforce_ssl=True,
            # The contents are rebuilt from the repo on every deploy, so nothing
            # is lost by deleting the bucket. DESTROY + auto-delete lets
            # `cdk destroy` tear everything down cleanly (cost guardrail).
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                # Origin Access Control: CDK also adds a bucket-policy statement
                # allowing *only this distribution* to read objects.
                origin=origins.S3BucketOrigin.with_origin_access_control(self.bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                # AWS-managed policy adding HSTS, X-Content-Type-Options,
                # X-Frame-Options, Referrer-Policy and X-XSS-Protection headers.
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
            ),
            domain_names=[domain_name, f"www.{domain_name}"],
            certificate=certificate,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_root_object="index.html",
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            # Cheapest tier: edge locations in Europe and North America only,
            # which is fine for a UK audience.
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        # Point both the apex and www at CloudFront. Alias records are a Route 53
        # feature: like a CNAME, but allowed at the zone apex and free to query.
        alias = route53.RecordTarget.from_alias(targets.CloudFrontTarget(self.distribution))
        for record_name, suffix in ((None, "Apex"), ("www", "Www")):
            route53.ARecord(self, f"{suffix}A", zone=zone, record_name=record_name, target=alias)
            route53.AaaaRecord(self, f"{suffix}Aaaa", zone=zone, record_name=record_name,
                               target=alias)

        # Upload the site folder on every deploy, then invalidate CloudFront's
        # cache so visitors see the new version immediately.
        s3deploy.BucketDeployment(
            self,
            "DeploySite",
            sources=[s3deploy.Source.asset(str(SITE_DIR))],
            destination_bucket=self.bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
        )

        self._add_nag_suppressions()

    def _add_nag_suppressions(self) -> None:
        """Record why each cdk-nag finding in this stack is accepted for now.

        Each suppression is a conscious, documented decision rather than a
        silenced warning; several are revisited by Stretch items in docs/plan.md.
        """
        NagSuppressions.add_resource_suppressions(
            self.bucket,
            [{"id": "AwsSolutions-S1",
              "reason": "Static public content; server access logging deferred "
                        "(Stretch: CloudFront + S3 access logging)."}],
        )
        NagSuppressions.add_resource_suppressions(
            self.distribution,
            [
                {"id": "AwsSolutions-CFR1",
                 "reason": "No geo restriction needed: a public demo site."},
                {"id": "AwsSolutions-CFR2",
                 "reason": "WAF deferred to keep costs at zero (Stretch: AWS WAF)."},
                {"id": "AwsSolutions-CFR3",
                 "reason": "Access logging deferred (Stretch: CloudFront + S3 access logging)."},
            ],
        )
        # The remaining findings are on Lambda functions and IAM roles that CDK
        # itself generates for its built-in custom resources (uploading the site
        # files, emptying the bucket on destroy, reading the cross-region
        # certificate reference). We don't write that code, so we can't change
        # its runtime or policies; CDK scopes them to this stack's resources.
        NagSuppressions.add_stack_suppressions(
            self,
            [
                {"id": "AwsSolutions-IAM4",
                 "reason": "CDK-generated custom resource roles use "
                           "AWSLambdaBasicExecutionRole for CloudWatch logging."},
                {"id": "AwsSolutions-IAM5",
                 "reason": "CDK-generated BucketDeployment / cross-region reader roles "
                           "need object-level wildcards (bucket/*) and SSM parameter paths."},
                {"id": "AwsSolutions-L1",
                 "reason": "Runtime of CDK-managed custom resource Lambdas is set by CDK."},
            ],
        )
