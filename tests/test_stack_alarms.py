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
