import json

from src.filter_config import (
    DEFAULT_FILTER_CONFIG,
    Category,
    FilterConfig,
    add_category,
    delete_category,
    load_filter_config,
    parse_filter_config,
    toggle_category,
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
