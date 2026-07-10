import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.whatsnew_stack import WhatsNewStack


def _template(alert_email: str | None) -> Template:
    # ALERT_EMAIL はスタック構築時に os.environ から読むため、synth 前に環境を整える。
    # モックではなく、環境変数の有無で購読の生成が変わる本来の振る舞いを検証する。
    app = cdk.App()
    stack = WhatsNewStack(app, "TestStack")
    return Template.from_stack(stack)


@pytest.fixture
def template_without_email(monkeypatch: pytest.MonkeyPatch) -> Template:
    monkeypatch.delenv("ALERT_EMAIL", raising=False)
    return _template(None)


@pytest.fixture
def template_with_email(monkeypatch: pytest.MonkeyPatch) -> Template:
    monkeypatch.setenv("ALERT_EMAIL", "alerts@example.com")
    return _template("alerts@example.com")


def test_Lambdaエラー時に通知するアラームが作られる(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Errors",
            "Namespace": "AWS/Lambda",
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "Threshold": 1,
            "EvaluationPeriods": 1,
            "TreatMissingData": "notBreaching",
        },
    )


def test_エラーアラームはエラー0件を障害扱いしない(
    template_without_email: Template,
) -> None:
    # データなし（エラー0件）を発報させないため NOT_BREACHING であること。
    template_without_email.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Errors",
            "TreatMissingData": "notBreaching",
        },
    )


def test_24時間起動がない時に通知するデッドマンアラームが作られる(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Invocations",
            "Namespace": "AWS/Lambda",
            "ComparisonOperator": "LessThanThreshold",
            "Threshold": 1,
            "EvaluationPeriods": 1,
            "Period": 86400,
        },
    )


def test_デッドマンアラームはデータ欠損を障害扱いする(
    template_without_email: Template,
) -> None:
    # 一度も起動しない＝メトリクスが存在しない状態を検知するため BREACHING であること。
    template_without_email.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Invocations",
            "TreatMissingData": "breaching",
        },
    )


def test_アラームは死活通知用のSNSトピックへ発報する(
    template_without_email: Template,
) -> None:
    template_without_email.resource_count_is("AWS::SNS::Topic", 1)
    template_without_email.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmActions": Match.array_with([{"Ref": Match.any_value()}]),
        },
    )


def test_ALERT_EMAIL未設定時はメール購読を作らない(
    template_without_email: Template,
) -> None:
    template_without_email.resource_count_is("AWS::SNS::Subscription", 0)


def test_ALERT_EMAIL設定時は指定アドレスへメール購読を作る(
    template_with_email: Template,
) -> None:
    template_with_email.has_resource_properties(
        "AWS::SNS::Subscription",
        {
            "Protocol": "email",
            "Endpoint": "alerts@example.com",
        },
    )


def test_SettingsWebhook用のFunctionURLが作られる(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::Lambda::Url",
        {
            "AuthType": "NONE",
        },
    )


def test_Workerから旧フィルタ環境変数を除去してfilter_configを参照する(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "handler.lambda_handler",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "FILTER_CONFIG_PARAM": "/whatsnew-agent/filter/config",
                    }
                )
            },
        },
    )
    template_without_email.resource_properties_count_is(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "EXCLUDE_SERVICES": Match.any_value(),
                    }
                )
            }
        },
        0,
    )


def test_SettingsWebhookはwebhook_handlerで作られる(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "webhook.lambda_handler",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "LINE_CHANNEL_SECRET_PARAM": (
                            "/whatsnew-agent/line/channel_secret"
                        ),
                        "FILTER_CONFIG_PARAM": "/whatsnew-agent/filter/config",
                    }
                )
            },
        },
    )


def test_Phase2の図解HTML用S3バケットは7日失効で作られる(
    template_without_email: Template,
) -> None:
    template_without_email.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": Match.object_like(
                {
                    "Rules": Match.array_with(
                        [Match.object_like({"ExpirationInDays": 7})]
                    )
                }
            ),
        },
    )


def test_図解閲覧用のFunctionURL_Lambdaが作られる(
    template_without_email: Template,
) -> None:
    # 私有 S3 を短い URL で配るための閲覧 Lambda（presigned が長すぎる回避策）。
    template_without_email.has_resource_properties(
        "AWS::Lambda::Function",
        {"Handler": "viewer.lambda_handler"},
    )
    # webhook と viewer の2つの Function URL がある
    template_without_email.resource_count_is("AWS::Lambda::Url", 2)


def test_図解生成用の非同期dispatcher_Lambdaが作られる(
    template_without_email: Template,
) -> None:
    # webhook(60s) から同期実行するとブロックするため、投げっぱなしできる dispatcher を挟む。
    template_without_email.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "agent_trigger.lambda_handler",
            "Timeout": 300,
        },
    )


def test_dispatcherはAgentCoreRuntimeを起動する権限を持つ(
    template_without_email: Template,
) -> None:
    # 図解本体は AgentCore Runtime 側。dispatcher はそれを invoke するだけ。
    template_without_email.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {"Action": "bedrock-agentcore:InvokeAgentRuntime"}
                        )
                    ]
                )
            }
        },
    )
