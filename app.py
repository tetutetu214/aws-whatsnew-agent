#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.whatsnew_stack import WhatsNewStack


app = cdk.App()

WhatsNewStack(
    app,
    "AwsWhatsNewAgentStack",
    env=cdk.Environment(region="us-east-1"),
)

app.synth()
