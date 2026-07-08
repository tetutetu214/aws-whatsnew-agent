from dataclasses import asdict, dataclass
from typing import Any
import json
import logging


LOGGER = logging.getLogger(__name__)
DEFAULT_FILTER_CONFIG_PARAM = "/whatsnew-agent/filter/config"


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str
    enabled: bool
    builtin: bool


@dataclass(frozen=True)
class FilterConfig:
    categories: tuple[Category, ...]


DEFAULT_CATEGORIES = (
    Category(
        id="region_expansion",
        label="リージョン拡大",
        description="既存サービス・機能の他リージョン展開。",
        enabled=True,
        builtin=True,
    ),
    Category(
        id="instance_size",
        label="インスタンスサイズ追加",
        description="インスタンスタイプまたはサイズの追加・拡大。",
        enabled=True,
        builtin=True,
    ),
)
DEFAULT_FILTER_CONFIG = FilterConfig(categories=DEFAULT_CATEGORIES)


def load_filter_config(
    param_name: str = DEFAULT_FILTER_CONFIG_PARAM,
    ssm_client: Any | None = None,
) -> FilterConfig:
    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm")

    try:
        response = ssm_client.get_parameter(Name=param_name, WithDecryption=False)
    except Exception as error:
        if _is_parameter_not_found(error):
            return DEFAULT_FILTER_CONFIG
        raise

    return parse_filter_config(response["Parameter"]["Value"])


def save_filter_config(
    filter_config: FilterConfig,
    param_name: str = DEFAULT_FILTER_CONFIG_PARAM,
    ssm_client: Any | None = None,
) -> None:
    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm")

    ssm_client.put_parameter(
        Name=param_name,
        Value=to_json(filter_config),
        Type="String",
        Overwrite=True,
    )


def parse_filter_config(raw_json: str) -> FilterConfig:
    try:
        payload = json.loads(raw_json)
        raw_categories = payload.get("categories", [])
    except (TypeError, json.JSONDecodeError, AttributeError):
        LOGGER.warning("Invalid filter config JSON; using defaults")
        return DEFAULT_FILTER_CONFIG

    categories = [_category_from_dict(item) for item in raw_categories]
    valid_categories = tuple(item for item in categories if item is not None)
    return merge_with_builtin(valid_categories)


def to_json(filter_config: FilterConfig) -> str:
    payload = {
        "categories": [
            asdict(category)
            for category in filter_config.categories
        ]
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def enabled_categories(filter_config: FilterConfig) -> tuple[Category, ...]:
    return tuple(category for category in filter_config.categories if category.enabled)


def toggle_category(filter_config: FilterConfig, category_id: str) -> FilterConfig:
    categories = []
    for category in filter_config.categories:
        if category.id == category_id:
            categories.append(
                Category(
                    id=category.id,
                    label=category.label,
                    description=category.description,
                    enabled=not category.enabled,
                    builtin=category.builtin,
                )
            )
            continue
        categories.append(category)
    return FilterConfig(categories=tuple(categories))


def add_category(
    filter_config: FilterConfig,
    category_id: str,
    label: str,
    description: str,
) -> FilterConfig:
    new_category = Category(
        id=category_id,
        label=label,
        description=description,
        enabled=True,
        builtin=False,
    )
    remaining = tuple(
        category
        for category in filter_config.categories
        if category.id != category_id
    )
    return FilterConfig(categories=(*remaining, new_category))


def delete_category(filter_config: FilterConfig, category_id: str) -> FilterConfig:
    for category in filter_config.categories:
        if category.id == category_id and category.builtin:
            return filter_config

    return FilterConfig(
        categories=tuple(
            category
            for category in filter_config.categories
            if category.id != category_id
        )
    )


def merge_with_builtin(categories: tuple[Category, ...]) -> FilterConfig:
    by_id = {category.id: category for category in categories}
    merged: list[Category] = []

    for builtin in DEFAULT_CATEGORIES:
        configured = by_id.pop(builtin.id, None)
        if configured is None:
            merged.append(builtin)
            continue
        merged.append(
            Category(
                id=builtin.id,
                label=builtin.label,
                description=builtin.description,
                enabled=configured.enabled,
                builtin=True,
            )
        )

    merged.extend(
        category
        for category in categories
        if category.id in by_id and not category.builtin
    )
    return FilterConfig(categories=tuple(merged))


def _category_from_dict(payload: Any) -> Category | None:
    if not isinstance(payload, dict):
        return None
    category_id = str(payload.get("id", "")).strip()
    label = str(payload.get("label", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not category_id or not label or not description:
        return None
    return Category(
        id=category_id,
        label=label,
        description=description,
        enabled=bool(payload.get("enabled", True)),
        builtin=bool(payload.get("builtin", False)),
    )


def _is_parameter_not_found(error: Exception) -> bool:
    code = getattr(error, "response", {}).get("Error", {}).get("Code")
    return code == "ParameterNotFound" or type(error).__name__ == "ParameterNotFound"
