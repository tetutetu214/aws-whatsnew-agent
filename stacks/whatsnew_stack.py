from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_scheduler as scheduler
from constructs import Construct


class WhatsNewStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table = dynamodb.Table(
            self,
            "SentArticlesTable",
            table_name="aws-whatsnew-agent-sent",
            partition_key=dynamodb.Attribute(
                name="article_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expire_at",
            removal_policy=RemovalPolicy.DESTROY,
        )

        line_token_param = "/aws-whatsnew-agent/line/channel_token"
        line_user_id_param = "/aws-whatsnew-agent/line/user_id"

        worker = lambda_.Function(
            self,
            "WhatsNewWorker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            timeout=Duration.seconds(300),
            memory_size=256,
            environment={
                "TABLE_NAME": table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0",
                "LINE_TOKEN_PARAM": line_token_param,
                "LINE_USER_ID_PARAM": line_user_id_param,
                "SEED_MODE": "false",
                "RSS_URL": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
                "MAX_ARTICLES_PER_MESSAGE": "10",
                "EXCLUDE_SERVICES": "",
            },
        )

        worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                ],
                resources=[table.table_arn],
            )
        )
        worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-*"
                ],
            )
        )
        worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=line_token_param.lstrip("/"),
                    ),
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=line_user_id_param.lstrip("/"),
                    ),
                ],
            )
        )

        scheduler_role = iam.Role(
            self,
            "SchedulerInvokeRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        scheduler_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[worker.function_arn],
            )
        )

        scheduler.CfnSchedule(
            self,
            "DailySchedule",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF",
            ),
            schedule_expression="cron(0 7 * * ? *)",
            schedule_expression_timezone="Asia/Tokyo",
            target=scheduler.CfnSchedule.TargetProperty(
                arn=worker.function_arn,
                role_arn=scheduler_role.role_arn,
            ),
        )
