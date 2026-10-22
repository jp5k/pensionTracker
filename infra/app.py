#!/usr/bin/env python3
"""Entry point the CDK CLI runs (see "app" in cdk.json)."""

from aws_cdk import App

from pension_tracker_infra.app_builder import build_app

app = App()
build_app(app)
app.synth()
