import os
from dataclasses import dataclass


DEFAULT_RSS_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"
DEFAULT_FILTER_CONFIG_PARAM = "/whatsnew-agent/filter/config"


@dataclass(frozen=True)
class Config:
    table_name: str
    bedrock_model_id: str
    line_token_param: str
    line_user_id_param: str
    filter_config_param: str
    seed_mode: bool
    rss_url: str
    ttl_days: int = 90


def load_config(environ: dict[str, str] | None = None) -> Config:
    values = environ if environ is not None else os.environ

    return Config(
        table_name=values.get("TABLE_NAME", "aws-whatsnew-agent-sent"),
        bedrock_model_id=values.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        line_token_param=values.get(
            "LINE_TOKEN_PARAM",
            "/whatsnew-agent/line/channel_token",
        ),
        line_user_id_param=values.get(
            "LINE_USER_ID_PARAM",
            "/whatsnew-agent/line/user_id",
        ),
        filter_config_param=values.get(
            "FILTER_CONFIG_PARAM",
            DEFAULT_FILTER_CONFIG_PARAM,
        ),
        seed_mode=values.get("SEED_MODE", "false").lower() == "true",
        rss_url=values.get("RSS_URL", DEFAULT_RSS_URL),
    )
