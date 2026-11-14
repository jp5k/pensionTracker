"""Deployment stages (environments): what differs between ``dev`` and ``prod``.

The same CDK code builds both environments. Everything that differs between
them is decided *here*, in one small, readable place, instead of
``if stage == "prod"`` checks scattered through the stacks. The stacks just
receive a ``StageSettings`` and build what it describes.

The stage is chosen on the command line, and is **required**:

    cdk deploy --all --profile pensiontracker -c stage=dev
    cdk deploy --all --profile pensiontracker -c stage=prod -c alertEmail=you@example.com

There is deliberately no default. A forgotten ``-c stage=...`` fails with an
error instead of quietly deploying somewhere, so a command can never reach the
live site by accident (see docs/decisions/0002-dev-and-prod-stages.md).
"""

from dataclasses import dataclass

#: The valid stage names, in the order they appear in error messages.
STAGES = ("dev", "prod")


@dataclass(frozen=True)
class StageSettings:
    """Everything that differs between environments.

    ``frozen=True`` makes instances read-only, so no code can change a stage's
    settings halfway through building the app.

    Attributes:
        name: ``"dev"`` or ``"prod"``.
        stack_prefix: Start of every stack name in this stage. Prod keeps the
            original, unprefixed names (see ``settings_for``).
        site_domains: The domain names the website answers on. The first is the
            certificate's main name; any others become extra names on it.
        noindex: Whether to send ``X-Robots-Tag: noindex`` so search engines
            don't list the site. True for dev only.
        has_budget: Whether this stage deploys the cost budget. The budget
            watches the *whole AWS account*, so it belongs to exactly one stage.
    """

    name: str
    stack_prefix: str
    site_domains: tuple[str, ...]
    noindex: bool
    has_budget: bool


def settings_for(stage: str, domain_name: str) -> StageSettings:
    """Return the settings for ``stage``, with domains built from ``domain_name``.

    Args:
        stage: ``"dev"`` or ``"prod"``, exactly (lower case).
        domain_name: The registered apex domain, e.g. ``pensiontrackerapp.com``.

    Returns:
        The stage's settings.

    Raises:
        ValueError: If ``stage`` isn't one of ``STAGES``.
    """
    if stage == "prod":
        return StageSettings(
            name="prod",
            # Prod keeps the stack names it was first deployed with
            # ("PensionTracker-Certificate", "PensionTracker-Site"). Those
            # stacks already own the live DNS records: if they were renamed,
            # CloudFormation would treat them as brand-new stacks and try to
            # create a *second* set of records for the same names, which fails
            # (or, done the hard way, means deleting and re-creating the live
            # site). Only the new dev stage gets a "-Dev" prefix.
            stack_prefix="PensionTracker",
            site_domains=(domain_name, f"www.{domain_name}"),
            noindex=False,
            has_budget=True,
        )
    if stage == "dev":
        return StageSettings(
            name="dev",
            stack_prefix="PensionTracker-Dev",
            # A subdomain of the same registered domain: covered by the existing
            # registration and hosted zone, so it costs nothing extra.
            site_domains=(f"dev.{domain_name}",),
            # Dev is publicly reachable (fictional data only), but shouldn't
            # appear in search results next to the real site.
            noindex=True,
            has_budget=False,
        )
    raise ValueError(
        f"Unknown stage {stage!r}: choose one of {', '.join(STAGES)} "
        "(e.g. -c stage=dev)."
    )
