"""Phase2: 記事を「グラフィカルに解説した自己完結 HTML」に変換して LINE に届けるエージェント本体。

framework 非依存の純粋関数＋クライアント注入で書く（既存モジュールの DI 規約に合わせる）。
AgentCore Runtime（agent/agent_runtime.py）からも、テストからも同じ関数を呼べる。

処理: mapping 取得 → (AWS MCP でサービス詳細) → Bedrock の OpenAI モデルで HTML 生成
      → S3 に put → presigned URL 発行 → LINE Push で「📊 図解を開く」リンク。
"""

from dataclasses import dataclass
from typing import Any
import logging
import os
import re

try:
    from . import line, store
except ImportError:
    import line
    import store


LOGGER = logging.getLogger(__name__)

# 図解の密度・品質は Claude が突出（GPT-5.5 はこのアカウントの Bedrock 未提供、gpt-oss は情報量が薄い）。
# 既定を Claude Sonnet 4.6（us-east-1 推論プロファイル）にする。EXPLAINER_MODEL_ID で切替可。
DEFAULT_EXPLAINER_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
DEFAULT_EXPLAINER_REGION = "us-east-1"
DEFAULT_KEY_PREFIX = "explainer/"
DEFAULT_LINE_TOKEN_PARAM = "/whatsnew-agent/line/channel_token"
DEFAULT_LINE_USER_ID_PARAM = "/whatsnew-agent/line/user_id"

# AWS 公式ポスター級の密度を狙うプロンプト。HTML は縦に伸ばせるので「1画面に収める」で削らない。
HTML_SYSTEM_PROMPT = (
    "あなたは AWS の新機能を、日本語で、プロ品質の1枚インフォグラフィックにするデザイナーです。"
    "与えられた本文とサービス情報から、情報量の多い自己完結 HTML を作ってください。\n"
    "【言語】すべて日本語で書く。英語の語句・文は日本語に訳す（固有名詞・API名・製品名・技術名は原語のままでよい）。\n"
    "【出力形式】出力は HTML のみ。コードフェンス(```)や前後の説明文を付けない。"
    "外部 CSS/JS/画像/Webフォント/CDN を一切参照しない（アイコン・図形・矢印はインライン SVG で描く）。"
    "<head> に <meta charset=\"utf-8\"> と <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> を必ず入れる。\n"
    "【キャンバス】body 直下に <div class=\"canvas\"> を1つ置く。"
    "max-width:1600px; width:100%; margin:0 auto; padding:clamp(20px,4vw,48px); box-sizing:border-box; background:#fff; とし（固定幅にしない）、"
    "高さは内容に応じて縦に伸ばす（固定高・overflow:hidden にしない。縦に長くなってよい）。"
    "body には margin:0; overflow-x:hidden; を付け、ページ本体に横スクロールを出さない。\n"
    "【スマホ対応・最重要】PC でもスマホ（縦・幅約390px）でも読めるレスポンシブにする:\n"
    "  - カードのグリッドは display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:… とし、"
    "画面幅に応じて列数が自動で減る（スマホでは1〜2列になる）ようにする。固定の6列などにしない。\n"
    "  - 動作の流れ・アーキテクチャ図など横に長い図は、その図だけを <div style=\"overflow-x:auto\"> で包み、"
    "狭い画面では図の中を横スクロールで見られるようにする（ページ本体は横スクロールさせない）。\n"
    "  - フォントは固定px一辺倒でなく主要な見出しに clamp() を使い、スマホで極端に小さく/大きくならないようにする。\n"
    "  - @media (max-width:700px) で見出し・本文を一回り小さく、余白を詰める。\n"
    "【内容の主従・最重要】この図解の主役は「今回のアップデートで“既存がどう変わったか”」。"
    "入力の『今回のアップデート(What's New)』を主役として**約6割**、『前提となるサービスの背景』を補足として**約4割**の分量にする。"
    "背景（サービスの一般説明・API 仕様の羅列）で主役を埋もれさせない。\n"
    "【構成】スカスカ厳禁で密度は保ちつつ、次の主従で組む:\n"
    "  ① ヘッダー: 大タイトル＋『今回“何が”変わったか』を一言で表すタグライン＋2〜3行で変更の要点。\n"
    "  ②【主役・大きく】今回の変更点: 新しくできるようになったこと/変わった点を 3〜6 個、アイコン付きで具体的に。"
    "可能なら『従来 → 今回』の対比（従来はこうだった／今回こう変わった）を対で見せる。\n"
    "  ③【主役】使い方・動作の流れ: 今回の新機能を使う手順やライフサイクルを番号付きの横フロー図で。\n"
    "  ④【背景・控えめ】前提となるサービスの概要: そのサービスが元々何をするものか、関連する基本機能を"
    "箱と矢印の小さめの構成図＋短い補足で。API 仕様の詳細列挙で主役を食わない。\n"
    "  ⑤ 下部に『利用シーン』『メリット（今回の変更で何が嬉しいか）』を各3〜5項目、アイコン付きカードで。\n"
    "『今回のアップデート』の情報が薄い場合でも、背景で水増しせず、変更点を軸に構成する。事実に反することは書かない。\n"
    "【出典】最下部のフッターに『出典: AWS What's New（元記事）』として、与えられた出典URLを"
    "クリック可能な <a href=\"出典URL\" target=\"_blank\" rel=\"noopener\">元記事を開く</a> のリンクで必ず入れる。"
    "URL は与えられたものを一字一句そのまま使い、勝手に生成・改変しない。出典URLが与えられていない場合はリンクを省く。\n"
    "【デザイン】白背景＋AWSオレンジ#FF9900のアクセント＋濃紺#232F3Eの見出し＋淡いグレーの枠/カード。"
    "角丸・余白・整列を効かせ、各セクションに見出しを付けて視認性を高く。SVGアイコンは単色ラインで統一。"
    "日本語は system-ui / sans-serif、長い語は折り返す(word-break:break-word)。"
)


@dataclass(frozen=True)
class ExplainerConfig:
    bucket: str
    model_id: str = DEFAULT_EXPLAINER_MODEL_ID
    bedrock_region: str = DEFAULT_EXPLAINER_REGION
    viewer_base_url: str = ""
    key_prefix: str = DEFAULT_KEY_PREFIX
    line_token_param: str = DEFAULT_LINE_TOKEN_PARAM
    line_user_id_param: str = DEFAULT_LINE_USER_ID_PARAM


def load_explainer_config(environ: dict[str, str] | None = None) -> ExplainerConfig:
    values = environ if environ is not None else os.environ
    return ExplainerConfig(
        bucket=values.get("EXPLAINER_BUCKET", ""),
        model_id=values.get("EXPLAINER_MODEL_ID", DEFAULT_EXPLAINER_MODEL_ID),
        bedrock_region=values.get("EXPLAINER_BEDROCK_REGION", DEFAULT_EXPLAINER_REGION),
        viewer_base_url=values.get("EXPLAINER_VIEWER_URL", ""),
        key_prefix=values.get("EXPLAINER_KEY_PREFIX", DEFAULT_KEY_PREFIX),
        line_token_param=values.get("LINE_TOKEN_PARAM", DEFAULT_LINE_TOKEN_PARAM),
        line_user_id_param=values.get("LINE_USER_ID_PARAM", DEFAULT_LINE_USER_ID_PARAM),
    )


def fetch_service_context(
    title: str,
    link: str,
    mcp_call: Any | None = None,
) -> str:
    """AWS Knowledge MCP でサービス詳細を取得（原型の手書き本文の本番代替）。

    mcp_call 未注入時は空文字を返す（グレースフル。記事 description で代替される）。
    本番の MCP 配線は AgentCore Runtime 側で mcp_call を渡して有効化する。
    """
    if mcp_call is None:
        return ""
    try:
        return str(mcp_call(title, link) or "").strip()
    except Exception as error:
        LOGGER.warning("MCP context fetch failed: %s", type(error).__name__)
        return ""


def build_html(
    title: str,
    description: str,
    service_context: str,
    model_id: str,
    bedrock_client: Any,
    link: str = "",
) -> str:
    # 役割を明示: What's New(=今回の変更) が主役6割、サービス背景(=MCP) が補足4割。
    user_text = (
        "# 今回のアップデート（What's New＝主役・約6割。既存がどう変わったかの中心情報）\n"
        f"タイトル: {title}\n\n本文:\n{description}"
    ).strip()
    if service_context:
        user_text += (
            "\n\n# 前提となるサービスの背景（AWS ドキュメント由来＝補足・約4割。"
            "主役を理解するための背景であり、これで主役を埋もれさせない）\n"
            f"{service_context}"
        )
    if link:
        # フッターの出典リンクに使う。改変せずそのまま <a> に入れさせる。
        user_text += f"\n\n# 出典URL（フッターに元記事リンクとして必ず入れる。改変禁止）\n{link}"

    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": HTML_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": 16000, "temperature": 0.4},
    )
    return _strip_code_fence(_extract_text(response))


def store_html(html: str, s3_client: Any, bucket: str, key: str) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )


def build_viewer_url(base_url: str, short_id: str) -> str:
    # presigned URL は SigV4 で1600文字超になり LINE の URI 上限(1000)を超える。
    # バケットは私有のままにし、閲覧用 Lambda(Function URL) が私有 S3 の HTML を返す。
    # LINE に渡すのはその短い URL（例: https://xxx.lambda-url.../?id=<short_id>）。
    return f"{base_url}?id={short_id}"


def build_link_message(url: str, title: str) -> dict[str, Any]:
    return {
        "type": "flex",
        "altText": f"図解ができました: {title}"[:400],
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "🎨 図解ができました",
                        "weight": "bold",
                    },
                    {"type": "text", "text": title, "wrap": True, "size": "sm"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "📊 図解を開く",
                            "uri": url,
                        },
                    }
                ],
            },
        },
    }


def generate_explainer(
    short_id: str,
    article_store: store.SentArticleStore,
    config: ExplainerConfig,
    mcp_call: Any | None = None,
    bedrock_client: Any | None = None,
    s3_client: Any | None = None,
    opener: Any | None = None,
    secrets_loader: Any | None = None,
) -> dict[str, Any]:
    # token/user_id が取れないと失敗通知すら送れないので最初に取得する（失敗時は素通しでログ）。
    token, user_id = (secrets_loader or _load_line_secrets)(
        config.line_token_param,
        config.line_user_id_param,
    )

    try:
        # DynamoDB 取得失敗も下の except で失敗通知できるよう try 内に入れる。
        mapping = article_store.get_feedback_mapping(short_id)
        if not mapping:
            line.push_messages(
                user_id,
                token,
                [{"type": "text", "text": "対象の記事が見つかりません"}],
                opener,
            )
            return {"status": "not_found", "short_id": short_id}

        bedrock_client = bedrock_client or _bedrock_client(config.bedrock_region)
        s3_client = s3_client or _s3_client()

        service_context = fetch_service_context(
            mapping.get("title", ""),
            mapping.get("link", ""),
            mcp_call,
        )
        html = build_html(
            mapping.get("title", ""),
            mapping.get("description", ""),
            service_context,
            config.model_id,
            bedrock_client,
            link=mapping.get("link", ""),
        )
        if not html:
            raise RuntimeError("empty HTML from model")

        key = f"{config.key_prefix}{short_id}.html"
        store_html(html, s3_client, config.bucket, key)
        url = build_viewer_url(config.viewer_base_url, short_id)
        line.push_messages(
            user_id,
            token,
            [build_link_message(url, mapping.get("title", ""))],
            opener,
        )
        return {"status": "sent", "short_id": short_id, "key": key, "url": url}
    except Exception as error:
        LOGGER.exception("Explainer failed: %s", type(error).__name__)
        line.push_messages(
            user_id,
            token,
            [{"type": "text", "text": "⚠️ 図解の生成に失敗しました"}],
            opener,
        )
        return {"status": "error", "short_id": short_id}


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    # モデルが ```html ... ``` で囲むことがあるため剥がす
    match = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts = [
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    return "\n".join(texts).strip()


def _load_line_secrets(token_param: str, user_id_param: str) -> tuple[str, str]:
    import boto3

    ssm_client = boto3.client("ssm")
    token = ssm_client.get_parameter(Name=token_param, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    user_id = ssm_client.get_parameter(Name=user_id_param, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    return token, user_id


def _bedrock_client(region: str) -> Any:
    import boto3
    from botocore.config import Config

    # 密度の高い図解生成(Claude, 数万字)は 2〜3 分かかる。既定 read_timeout(60s) だと
    # タイムアウト→リトライで多重生成・失敗になるため、長い read_timeout＋リトライ無しにする。
    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(read_timeout=300, connect_timeout=15, retries={"max_attempts": 1}),
    )


def _s3_client() -> Any:
    import boto3

    return boto3.client("s3")
