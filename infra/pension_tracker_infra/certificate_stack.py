"""TLS certificate for the website, which must live in us-east-1.

CloudFront is a global service, but it only accepts ACM certificates issued in
the us-east-1 (N. Virginia) region. Everything else in the app lives in Ireland
(eu-west-1), so the certificate gets its own small stack pinned to us-east-1 and
is handed to the site stack through a cross-region reference.

Each stage has its own certificate: prod's covers ``<domain>`` and
``www.<domain>``; dev's covers ``dev.<domain>``.
"""

from collections.abc import Sequence
from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


class CertificateStack(Stack):
    """Issues a DNS-validated certificate for the stage's site domains.

    Attributes:
        certificate: The ACM certificate, for CloudFront to use.
    """

    def __init__(self, scope: Construct, construct_id: str, *, zone_domain: str,
                 site_domains: Sequence[str], **kwargs: Any) -> None:
        """Create the certificate.

        Args:
            scope: Parent construct (the CDK app).
            construct_id: Logical name of this stack.
            zone_domain: The apex domain registered in Route 53, e.g.
                ``pensiontrackerapp.com``. Used to find the hosted zone, which
                is the same for every stage (subdomains live in the same zone).
            site_domains: The names the certificate must cover, main name first,
                e.g. ``["pensiontrackerapp.com", "www.pensiontrackerapp.com"]``
                for prod or ``["dev.pensiontrackerapp.com"]`` for dev.
            **kwargs: Standard ``Stack`` options (``env``, ``cross_region_references``...).
        """
        super().__init__(scope, construct_id, **kwargs)

        # Find the hosted zone Route 53 created when the domain was registered.
        # This is a *lookup*, done at synth time using the CLI's credentials; the
        # result is cached in cdk.context.json so later synths don't need AWS.
        zone = route53.HostedZone.from_lookup(self, "Zone", domain_name=zone_domain)

        # A certificate has one main name plus optional extra names ("subject
        # alternative names", SANs). Dev has only one name, so it gets no SANs:
        # passing None (rather than an empty list) leaves the property out of
        # the template entirely.
        main_name, *extra_names = site_domains

        # DNS validation: ACM asks us to publish a CNAME record proving we own
        # the domain. Because we pass the hosted zone, CDK creates that record
        # for us and ACM renews the certificate automatically forever after.
        self.certificate = acm.Certificate(
            self,
            "SiteCertificate",
            domain_name=main_name,
            subject_alternative_names=extra_names or None,
            validation=acm.CertificateValidation.from_dns(zone),
        )
