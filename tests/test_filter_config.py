from dataclasses import replace
import json

import pytest

from src.filter_config import (
    DEFAULT_FILTER_CONFIG,
    DEFAULT_FOCUS,
    Category,
    FilterConfig,
    Focus,
    add_category,
    delete_category,
    load_filter_config,
    merge_with_builtin,
    parse_filter_config,
    toggle_category,
    to_json,
)


# 実 AWS 未認証環境のため SSM は fake client で代替する。
class ParameterNotFound(Exception):
    pass


class MissingSsmClient:
    def get_parameter(self, Name: str, WithDecryption: bool) -> object:
        del Name, WithDecryption
        raise ParameterNotFound()


def test_SSMパラメータ未作成時は既定カテゴリを返す() -> None:
    loaded = load_filter_config("/filter", MissingSsmClient())

    assert loaded == DEFAULT_FILTER_CONFIG


def test_既定カテゴリは設定値のenabledを保持してbuiltinに補正される() -> None:
    raw = json.dumps(
        {
            "categories": [
                {
                    "id": "region_expansion",
                    "label": "変更される値",
                    "description": "変更される説明",
                    "enabled": False,
                    "builtin": False,
                }
            ]
        }
    )

    loaded = parse_filter_config(raw)

    assert loaded.categories[0].id == "region_expansion"
    assert loaded.categories[0].label == "リージョン拡大"
    assert loaded.categories[0].enabled is False
    assert loaded.categories[0].builtin is True


def test_カテゴリのON_OFFを切り替えられる() -> None:
    updated = toggle_category(DEFAULT_FILTER_CONFIG, "region_expansion")

    assert updated.categories[0].enabled is False


def test_ユーザー定義カテゴリを追加できる() -> None:
    updated = add_category(
        DEFAULT_FILTER_CONFIG,
        "pricing_noise",
        "価格系",
        "小さな価格改定。",
    )

    assert updated.categories[-1].id == "pricing_noise"
    assert updated.categories[-1].builtin is False


def test_builtinカテゴリは削除されない() -> None:
    updated = delete_category(DEFAULT_FILTER_CONFIG, "region_expansion")

    assert updated == DEFAULT_FILTER_CONFIG


def test_ユーザー定義カテゴリは削除できる() -> None:
    current = FilterConfig(
        categories=(
            *DEFAULT_FILTER_CONFIG.categories,
            Category(
                id="pricing_noise",
                label="価格系",
                description="小さな価格改定。",
                enabled=True,
                builtin=False,
            ),
        )
    )

    updated = delete_category(current, "pricing_noise")

    assert all(category.id != "pricing_noise" for category in updated.categories)


@pytest.fixture
def custom_filter_config() -> FilterConfig:
    return replace(
        DEFAULT_FILTER_CONFIG,
        categories=(
            *DEFAULT_FILTER_CONFIG.categories,
            Category("pricing_noise", "価格系", "小さな価格改定。", True, False),
        ),
        focus=Focus(
            enabled=False,
            label="分析",
            product_slugs=("amazon-athena",),
            title_keywords=("analytics", "athena"),
        ),
    )


def test_カテゴリ切り替え後に保存して読み直してもfocus設定を保持する(
    custom_filter_config: FilterConfig,
) -> None:
    updated = toggle_category(custom_filter_config, "region_expansion")

    assert parse_filter_config(to_json(updated)).focus == custom_filter_config.focus


def test_カテゴリ追加後に保存して読み直してもfocus設定を保持する(
    custom_filter_config: FilterConfig,
) -> None:
    updated = add_category(custom_filter_config, "noise", "対象外", "対象外の記事。")

    assert parse_filter_config(to_json(updated)).focus == custom_filter_config.focus


def test_カテゴリ削除後に保存して読み直してもfocus設定を保持する(
    custom_filter_config: FilterConfig,
) -> None:
    updated = delete_category(custom_filter_config, "pricing_noise")

    assert parse_filter_config(to_json(updated)).focus == custom_filter_config.focus


def test_既定カテゴリとの統合後も指定したfocus設定を保持する(
    custom_filter_config: FilterConfig,
) -> None:
    merged = merge_with_builtin(
        custom_filter_config.categories,
        focus=custom_filter_config.focus,
    )

    assert parse_filter_config(to_json(merged)).focus == custom_filter_config.focus


def test_focus設定は指定形式のJSONに保存される(
    custom_filter_config: FilterConfig,
) -> None:
    payload = json.loads(to_json(custom_filter_config))

    assert payload["focus"] == {
        "enabled": False,
        "label": "分析",
        "product_slugs": ["amazon-athena"],
        "title_keywords": ["analytics", "athena"],
    }


def test_focusキーのない旧形式JSONは既定のfocus設定になる() -> None:
    loaded = parse_filter_config('{"categories":[]}')

    assert loaded.focus == DEFAULT_FOCUS


@pytest.mark.parametrize(
    "raw_focus",
    [
        None,
        False,
        "serverless",
        [],
        1,
        {"enabled": "false"},
        {"enabled": 0},
        {"label": None},
        {"product_slugs": "aws-lambda"},
        {"product_slugs": [1]},
        {"title_keywords": [None]},
        {"enabled": False, "title_keywords": "serverless"},
    ],
)
def test_focusの型が不正なら全体を既定値に戻す(raw_focus: object) -> None:
    loaded = parse_filter_config(json.dumps({"categories": [], "focus": raw_focus}))

    assert loaded.focus == DEFAULT_FOCUS


@pytest.mark.parametrize(
    ("raw_focus", "expected"),
    [
        ({}, DEFAULT_FOCUS),
        ({"enabled": False}, replace(DEFAULT_FOCUS, enabled=False)),
        ({"label": "分析"}, replace(DEFAULT_FOCUS, label="分析")),
        ({"product_slugs": []}, replace(DEFAULT_FOCUS, product_slugs=())),
        ({"title_keywords": []}, replace(DEFAULT_FOCUS, title_keywords=())),
    ],
)
def test_focusの欠けたキーだけを既定値で補う(
    raw_focus: dict[str, object],
    expected: Focus,
) -> None:
    loaded = parse_filter_config(json.dumps({"categories": [], "focus": raw_focus}))

    assert loaded.focus == expected
