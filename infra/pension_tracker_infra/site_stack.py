"""Static website hosting: private S3 bucket behind CloudFront, on our domain.

Request path: browser → CloudFront (HTTPS, our certificate) → S3. The bucket is
completely private; CloudFront reads it using Origin Access Control (OAC), so
the S3 URL itself returns "Access Denied" and the domain is the only way in.

One copy of this stack is deployed per stage: prod serves the apex domain and
``www``; dev serves ``dev.<domain>`` and adds a ``noindex`` header.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aws_cdk import Duration, RemovalPolicy, Stack
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


def record_name_and_id(domain: str, zone_domain: str) -> tuple[str | None, str]:
    """Work out a site domain's DNS record name and construct-ID prefix.

    Route 53 record names are given *relative to the hosted zone*: ``None``
    means the zone apex itself (``pensiontrackerapp.com``), and ``"www"``
    means ``www.pensiontrackerapp.com``.

    The construct-ID prefix must reproduce the IDs prod was first deployed with
    (``Apex`` and ``Www``), because CloudFormation identifies each resource by a
    *logical ID* derived from its construct ID. Change the ID and CloudFormation
    sees a different resource: it would create a new DNS record and delete the
    old one. For live DNS that's at best a pointless change and at worst a
    brief outage, so these IDs are pinned by tests.

    Args:
        domain: A site domain, e.g. ``www.pensiontrackerapp.com``.
        zone_domain: The hosted zone's apex, e.g. ``pensiontrackerapp.com``.

    Returns:
        ``(record_name, id_prefix)``, e.g. ``(None, "Apex")``,
        ``("www", "Www")`` or ``("dev", "Dev")``.

    Raises:
        ValueError: If ``domain`` isn't the zone apex or a subdomain of it.
    """
    if domain == zone_domain:
        return None, "Apex"
    suffix = f".{zone_domain}"
    if not domain.endswith(suffix):
        raise ValueError(f"{domain!r} is not inside the hosted zone {zone_domain!r}.")
    label = domain.removesuffix(suffix)
    return label, label.capitalize()


class SiteStack(Stack):
    """Bucket + CloudFront distribution + DNS records + content upload.

    Attributes:
        bucket: The private S3 bucket holding the site's files.
        distribution: The CloudFront distribution serving them.
    """

    def __init__(self, scope: Construct, construct_id: str, *, zone_domain: str,
                 site_domains: Sequence[str], certificate: acm.ICertificate,
                 noindex: bool = False, **kwargs: Any) -> None:
        """Create the hosting resources.

        Args:
            scope: Parent construct (the CDK app).
            construct_id: Logical name of this stack.
            zone_domain: The apex domain whose Route 53 hosted zone holds the
                records, e.g. ``pensiontrackerapp.com`` (same for every stage).
            site_domains: The names the site answers on, e.g. the apex and
                ``www`` for prod, or ``dev.<domain>`` for dev.
            certificate: us-east-1 ACM certificate covering ``site_domains``.
            noindex: Send ``X-Robots-Tag: noindex`` so search engines don't
                list the site (dev only).
            **kwargs: Standard ``Stack`` options.
        """
        super().__init__(scope, construct_id, **kwargs)

        zone = route53.HostedZone.from_lookup(self, "Zone", domain_name=zone_domain)

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
                response_headers_policy=self._response_headers_policy(noindex),
            ),
            domain_names=list(site_domains),
            certificate=certificate,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_root_object="index.html",
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            # Cheapest tier: edge locations in Europe and North America only,
            # which is fine for a UK audience.
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        # Point every site domain at CloudFront, over IPv4 (A) and IPv6 (AAAA).
        # Alias records are a Route 53 feature: like a CNAME, but allowed at the
        # zone apex and free to query. Construct IDs come out as ApexA, WwwAaaa,
        # DevA... (see record_name_and_id for why they must stay stable).
        alias = route53.RecordTarget.from_alias(targets.CloudFrontTarget(self.distribution))
        for domain in site_domains:
            record_name, id_prefix = record_name_and_id(domain, zone_domain)
            route53.ARecord(self, f"{id_prefix}A", zone=zone, record_name=record_name,
                            target=alias)
            route53.AaaaRecord(self, f"{id_prefix}Aaaa", zone=zone, record_name=record_name,
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

    def _response_headers_policy(self, noindex: bool) -> cloudfront.IResponseHeadersPolicy:
        """Choose the HTTP headers CloudFront adds to every response.

        Without ``noindex`` (prod) this is AWS's managed "SecurityHeadersPolicy",
        exactly as prod was first deployed, so prod's template doesn't change.

        With ``noindex`` (dev) we need one extra header, but a CloudFront
        behaviour can have only *one* response headers policy, and AWS's managed
        policies can't be extended. So dev gets its own policy that repeats the
        managed policy's security headers, value for value, and adds
        ``X-Robots-Tag: noindex``, which tells search engines not to list
        the page. (Header values below mirror the managed policy; see
        https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-response-headers-policies.html)

        Args:
            noindex: Whether to add ``X-Robots-Tag: noindex``.

        Returns:
            The policy to attach to the distribution's default behaviour.
        """
        if not noindex:
            # AWS-managed policy adding HSTS, X-Content-Type-Options,
            # X-Frame-Options, Referrer-Policy and X-XSS-Protection headers.
            return cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS
        return cloudfront.ResponseHeadersPolicy(
            self,
            "NoIndexSecurityHeaders",
            comment="Managed SecurityHeadersPolicy values plus X-Robots-Tag: noindex",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                # HSTS: browsers must use HTTPS for this site for the next year.
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365), override=False),
                # Stop browsers guessing ("sniffing") a file's type, which can
                # turn an innocent upload into executable script.
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(
                    override=False),
                # Only our own pages may embed this one in a frame
                # (clickjacking protection).
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.SAMEORIGIN, override=False),
                # Send only the origin, not the full URL, to other sites.
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=False),
                # Legacy XSS filter in older browsers.
                xss_protection=cloudfront.ResponseHeadersXSSProtection(
                    protection=True, mode_block=True, override=False),
            ),
            custom_headers_behavior=cloudfront.ResponseCustomHeadersBehavior(
                custom_headers=[cloudfront.ResponseCustomHeader(
                    header="X-Robots-Tag", value="noindex", override=True)],
            ),
        )

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
