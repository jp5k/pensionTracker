"""CDK (Python) infrastructure for pensionTracker.

Each module defines one CloudFormation stack; ``app_builder`` wires them together
into a CDK app. ``cdk synth`` turns this Python into CloudFormation templates
(under ``cdk.out/``), which ``cdk deploy`` then hands to CloudFormation.
"""
