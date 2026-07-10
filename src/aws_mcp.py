"""AWS Knowledge MCP からサービス詳細を取得して図解を富化する。

創設時の設計の中核（「そのサービスにおける情報を MCP で取得」）。AWS 公式のリモート MCP
サーバ（認証不要）を公式 mcp クライアントで叩く。エンドポイントは **ベース URL**（`/mcp` を
付けると tool-call が gateway エラーで 400 になる。2026-07-11 に実測）。

同期の explainer から使えるよう asyncio.run で包む。`mcp` パッケージは AgentCore CodeZip の
依存として同梱する前提で、import は関数内（遅延）にする。テストは runner を注入して mock する。
"""

import asyncio
import logging

LOGGER = logging.getLogger(__name__)

# `/mcp` を付けると "Http operation is not supported for gateway protocol type MCP" で 400。
# プラグイン(deploy-on-aws)と同じくベース URL を使う。
DEFAULT_ENDPOINT = "https://knowledge-mcp.global.api.aws"
SEARCH_TOOL = "aws___search_documentation"
MAX_CONTEXT_CHARS = 2500


def fetch_service_context(
    service_name: str,
    endpoint: str = DEFAULT_ENDPOINT,
    runner=None,
) -> str:
    """サービス名で AWS ドキュメントを検索し、要点テキストを返す。失敗時は空文字（富化なしで続行）。"""
    if not service_name:
        return ""
    run = runner or _run_search
    try:
        text = run(service_name, endpoint)
    except Exception as error:
        LOGGER.warning("AWS MCP fetch failed: %s", type(error).__name__)
        return ""
    return (text or "")[:MAX_CONTEXT_CHARS]


def _run_search(service_name: str, endpoint: str) -> str:
    return asyncio.run(_search_async(service_name, endpoint))


async def _search_async(service_name: str, endpoint: str) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(endpoint) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                SEARCH_TOOL,
                {"search_phrase": service_name, "limit": 3},
            )
            return "".join(getattr(part, "text", "") for part in result.content)
