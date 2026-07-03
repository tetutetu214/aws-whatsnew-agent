import os
from dataclasses import dataclass


DEFAULT_RSS_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"


@dataclass(frozen=True)
class Config:
    table_name: str
    bedrock_model_id: str
    line_token_param: str
    line_user_id_param: str
    seed_mode: bool
    exclude_services: tuple[str, ...]
    rss_url: str
    max_articles_per_message: int
    ttl_days: int = 90


def load_config(environ: dict[str, str] | None = None) -> Config:
    values = environ if environ is not None else os.environ
    raw_exclude_services = values.get("EXCLUDE_SERVICES", "")
    max_articles = values.get("MAX_ARTICLES_PER_MESSAGE", "10")

    return Config(
        table_name=values.get("TABLE_NAME", "aws-whatsnew-agent-sent"),
        bedrock_model_id=values.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        line_token_param=values.get(
            "LINE_TOKEN_PARAM",
            "/aws-whatsnew-agent/line/channel_token",
        ),
        line_user_id_param=values.get(
            "LINE_USER_ID_PARAM",
            "/aws-whatsnew-agent/line/user_id",
        ),
        seed_mode=values.get("SEED_MODE", "false").lower() == "true",
        exclude_services=tuple(
            item.strip()
            for item in raw_exclude_services.split(",")
            if item.strip()
        ),
        rss_url=values.get("RSS_URL", DEFAULT_RSS_URL),
        max_articles_per_message=max(1, int(max_articles)),
    )
