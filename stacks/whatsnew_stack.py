import os

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
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

        line_token_param = "/whatsnew-agent/line/channel_token"
        line_user_id_param = "/whatsnew-agent/line/user_id"
        line_channel_secret_param = "/whatsnew-agent/line/channel_secret"
        filter_config_param = "/whatsnew-agent/filter/config"

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
                "FILTER_CONFIG_PARAM": filter_config_param,
                "SEED_MODE": "false",
                "RSS_URL": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
            },
        )

        webhook = lambda_.Function(
            self,
            "SettingsWebhook",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhook.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "TABLE_NAME": table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0",
                "LINE_TOKEN_PARAM": line_token_param,
                "LINE_USER_ID_PARAM": line_user_id_param,
                "LINE_CHANNEL_SECRET_PARAM": line_channel_secret_param,
                "FILTER_CONFIG_PARAM": filter_config_param,
            },
        )
        webhook_url = webhook.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
        )
        CfnOutput(
            self,
            "SettingsWebhookUrl",
            value=webhook_url.url,
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
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=filter_config_param.lstrip("/"),
                    ),
                ],
            )
        )
        webhook.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Scan",
                ],
                resources=[table.table_arn],
            )
        )
        webhook.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-*"
                ],
            )
        )
        webhook.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=line_channel_secret_param.lstrip("/"),
                    ),
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=line_user_id_param.lstrip("/"),
                    ),
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=line_token_param.lstrip("/"),
                    ),
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=filter_config_param.lstrip("/"),
                    ),
                ],
            )
        )
        webhook.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:PutParameter"],
                resources=[
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        resource_name=filter_config_param.lstrip("/"),
                    ),
                ],
            )
        )

        # --- Phase2: 図解エージェント（dispatcher Lambda が生成 + S3 presigned 配信） ---
        # 生成 HTML の置き場。presigned URL で配るので公開不要。7日で自動失効。
        explainer_bucket = s3.Bucket(
            self,
            "ExplainerBucket",
            # バケットは私有。閲覧用 Lambda(Function URL)が私有 S3 を短い URL で配る。
            # presigned URL は1600文字超で LINE の URI 上限(1000)を超えるための回避策。7日で自動失効。
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(7)),
            ],
        )

        # 閲覧用 Lambda: GET /?id=<short_id> で私有 S3 の explainer/<id>.html を text/html で返す。
        # LINE には presigned(長い)ではなくこの短い Function URL を渡す。
        viewer = lambda_.Function(
            self,
            "ExplainerViewer",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="viewer.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={"EXPLAINER_BUCKET": explainer_bucket.bucket_name},
        )
        explainer_bucket.grant_read(viewer)
        viewer_url = viewer.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
        )
        CfnOutput(self, "ExplainerViewerUrl", value=viewer_url.url)

        # webhook → dispatcher Lambda(Event 非同期) の2段構え。
        # 図解生成は数十秒かかり invoke 系は同期のため、webhook(60s)から直接やるとブロックして
        # タイムアウト→LINE 再送→二重生成を招く。投げっぱなしできる dispatcher を挟み webhook を即応させる。
        # v1 では dispatcher 自身が Bedrock(OpenAI)で HTML を生成し S3→presigned→Push する。
        # （AgentCore Runtime は将来 MCP 深掘りが要る段で載せる。成果物は agent/ にある）
        explainer_dispatcher = lambda_.Function(
            self,
            "ExplainerDispatcher",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="agent_trigger.lambda_handler",
            code=lambda_.Code.from_asset("src"),
            timeout=Duration.seconds(300),
            memory_size=512,
            environment={
                "TABLE_NAME": table.table_name,
                "EXPLAINER_BUCKET": explainer_bucket.bucket_name,
                # LINE に渡す短い閲覧 URL の土台（閲覧 Lambda の Function URL）
                "EXPLAINER_VIEWER_URL": viewer_url.url,
                # 既定は IAM だけで呼べる gpt-oss。GPT-5.5(us-east-2)へは env 差し替えで切替。
                "EXPLAINER_MODEL_ID": "openai.gpt-oss-120b-1:0",
                "EXPLAINER_BEDROCK_REGION": "us-east-1",
                "LINE_TOKEN_PARAM": line_token_param,
                "LINE_USER_ID_PARAM": line_user_id_param,
            },
        )
        explainer_bucket.grant_read_write(explainer_dispatcher)
        explainer_dispatcher.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                # GPT-5.5 は us-east-2、既定の gpt-oss は us-east-1。両リージョンの OpenAI 系を許可。
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/openai.*",
                    "arn:aws:bedrock:us-east-2::foundation-model/openai.*",
                ],
            )
        )
        explainer_dispatcher.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem"],
                resources=[table.table_arn],
            )
        )
        explainer_dispatcher.add_to_role_policy(
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
        # webhook は dispatcher を非同期(Event)起動するだけ（即応のため）
        webhook.add_environment(
            "EXPLAINER_DISPATCHER_FUNCTION",
            explainer_dispatcher.function_name,
        )
        explainer_dispatcher.grant_invoke(webhook)

        CfnOutput(self, "ExplainerBucketName", value=explainer_bucket.bucket_name)

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

        # 死活アラートの通知先 SNS トピック。
        # 配信先メールは環境変数 ALERT_EMAIL から受け取り、未設定ならトピックのみ作る。
        alert_topic = sns.Topic(
            self,
            "AlertTopic",
            display_name="aws-whatsnew-agent-alerts",
        )
        alert_email = os.environ.get("ALERT_EMAIL")
        if alert_email:
            alert_topic.add_subscription(
                sns_subscriptions.EmailSubscription(alert_email)
            )

        alarm_action = cloudwatch_actions.SnsAction(alert_topic)

        # アラーム1: Lambda がエラー終了したら通知する。
        # 5分粒度で1回でもエラーが出れば発報。エラー0件（データなし）は正常なので NOT_BREACHING。
        error_alarm = cloudwatch.Alarm(
            self,
            "WorkerErrorAlarm",
            metric=worker.metric_errors(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=(
                cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
            ),
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="WhatsNew Lambda がエラー終了した",
        )
        error_alarm.add_alarm_action(alarm_action)

        # アラーム2: デッドマンスイッチ。24時間で起動が1回未満なら通知する。
        # Scheduler 停止や設定ミスで一度も起動しない状態を検知するため、
        # データなし（＝起動記録が存在しない）を BREACHING として障害扱いにする。
        missing_invocation_alarm = cloudwatch.Alarm(
            self,
            "WorkerMissingInvocationAlarm",
            metric=worker.metric_invocations(period=Duration.hours(24)),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
            alarm_description="WhatsNew Lambda が24時間起動していない（Scheduler停止等）",
        )
        missing_invocation_alarm.add_alarm_action(alarm_action)
