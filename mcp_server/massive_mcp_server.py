"""Massive market-data MCP server.

Exposes the read-only market-data capabilities of the repository's canonical
``massive_client.MassiveClient`` over MCP (Model Context Protocol). This is a
standalone Databricks App entrypoint; it does not replace the Flask dashboard.

Run locally (after installing FastMCP and configuring Databricks credentials):
    python mcp_server/massive_mcp_server.py
"""

import os
import sys
from pathlib import Path

from fastmcp import FastMCP

# This script is normally executed from mcp_server/. Insert the repository root
# ahead of the script directory so ``massive_client`` always resolves to the
# one canonical implementation at the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
project_root_path = str(PROJECT_ROOT)
if project_root_path in sys.path:
    sys.path.remove(project_root_path)
sys.path.insert(0, project_root_path)

from massive_client import MassiveClient


mcp = FastMCP("massive-market-data")

_client: MassiveClient | None = None


def _get_client() -> MassiveClient:
    """Create the authenticated Massive client only when a tool is invoked."""
    global _client
    if _client is None:
        _client = MassiveClient()
    return _client


@mcp.tool
def get_latest_price(symbol: str) -> dict:
    """Fetch the previous-session aggregate data for one ticker symbol.

    Args:
        symbol: Stock ticker symbol, for example ``AAPL``.
    """
    return _get_client().get_latest_price(symbol)


@mcp.tool
def get_news(
    ticker: str,
    limit: int = 50,
    published_utc_gte: str | None = None,
) -> list[dict]:
    """Fetch recent news articles for one ticker symbol.

    Args:
        ticker: Stock ticker symbol, for example ``AAPL``.
        limit: Maximum number of articles to return.
        published_utc_gte: Optional inclusive ISO date or datetime filter.
    """
    return _get_client().get_news(ticker, limit, published_utc_gte)


@mcp.tool
def get_ticker_details(symbol: str) -> dict:
    """Fetch company and listing details for one ticker symbol.

    Args:
        symbol: Stock ticker symbol, for example ``AAPL``.
    """
    return _get_client().get_ticker_details(symbol)


@mcp.tool
def get_price_history(
    symbol: str,
    from_date: str,
    to_date: str,
    timespan: str = "day",
    multiplier: int = 1,
) -> list[dict]:
    """Fetch historical OHLC aggregate bars for one ticker.

    Args:
        symbol: Stock ticker symbol, for example ``AAPL``.
        from_date: Inclusive start date in ``YYYY-MM-DD`` format.
        to_date: Inclusive end date in ``YYYY-MM-DD`` format.
        timespan: Bar timespan accepted by Massive, default ``day``.
        multiplier: Size of each timespan interval, default 1.
    """
    return _get_client().get_price_history(
        symbol, from_date, to_date, timespan, multiplier
    )


@mcp.tool
def get_sma(
    symbol: str,
    window: int = 50,
    series_type: str = "close",
    timespan: str = "day",
    order: str = "desc",
    limit: int = 100,
) -> dict:
    """Fetch Simple Moving Average indicator values for one ticker."""
    return _get_client().get_sma(
        symbol, window, series_type, timespan, order, limit
    )


@mcp.tool
def get_ema(
    symbol: str,
    window: int = 50,
    series_type: str = "close",
    timespan: str = "day",
    order: str = "desc",
    limit: int = 100,
) -> dict:
    """Fetch Exponential Moving Average indicator values for one ticker."""
    return _get_client().get_ema(
        symbol, window, series_type, timespan, order, limit
    )


@mcp.tool
def get_macd(
    symbol: str,
    short_window: int = 12,
    long_window: int = 26,
    signal_window: int = 9,
    series_type: str = "close",
    timespan: str = "day",
    order: str = "desc",
    limit: int = 100,
) -> dict:
    """Fetch Moving Average Convergence/Divergence indicator values."""
    return _get_client().get_macd(
        symbol,
        short_window,
        long_window,
        signal_window,
        series_type,
        timespan,
        order,
        limit,
    )


@mcp.tool
def get_rsi(
    symbol: str,
    window: int = 14,
    series_type: str = "close",
    timespan: str = "day",
    order: str = "desc",
    limit: int = 100,
) -> dict:
    """Fetch Relative Strength Index indicator values for one ticker."""
    return _get_client().get_rsi(
        symbol, window, series_type, timespan, order, limit
    )


if __name__ == "__main__":
    # Databricks Apps routes external HTTP traffic to this port. Keep the same
    # transport and port precedence as the existing Alpaca MCP server.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
