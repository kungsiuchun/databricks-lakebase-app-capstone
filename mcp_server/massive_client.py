"""
Client for the Massive API.

The API key is stored in a Databricks secret scope (see setup_secrets.py) and
resolved at runtime via the Databricks SDK - it is never stored in code, env
files, or app.yaml.
"""

import base64
import os
import time
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

_w = WorkspaceClient()

_SCOPE = os.environ.get("MASSIVE_SECRET_SCOPE", "massive")
_KEY = os.environ.get("MASSIVE_SECRET_KEY", "api-key")
_BASE_URL = os.environ.get("MASSIVE_API_BASE_URL", "https://api.polygon.io")

_DEFAULT_TIMEOUT = 30


def _get_api_key() -> str:
    """Fetch and decode the Massive API key from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")


class MassiveClient:
    """Thin wrapper around the Massive API with auth + retry-friendly session.
    
    Rate Limiting:
    - Enforces a rate limit of 5 requests per minute (Polygon free tier)
    - Spaces requests evenly: 12 seconds between calls
    - Sleeps BEFORE each request to avoid exceeding the API limit
    """
    
    # Class-level rate limiting state (shared across all instances)
    _last_request_time = 0.0
    _requests_per_minute = int(os.environ.get("MASSIVE_RATE_LIMIT", "5"))
    _seconds_between_requests = 60.0 / _requests_per_minute

    def __init__(self, base_url: str | None = None, timeout: int = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or _BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {_get_api_key()}",
                "Content-Type": "application/json",
            }
        )

    def _enforce_rate_limit(self):
        """Sleep if needed to enforce rate limit (5 requests per minute).
        
        Calculates time since last request and sleeps if we're making requests
        too quickly. This prevents hitting Polygon's free tier rate limits.
        """
        current_time = time.time()
        time_since_last = current_time - MassiveClient._last_request_time
        
        if time_since_last < MassiveClient._seconds_between_requests:
            sleep_time = MassiveClient._seconds_between_requests - time_since_last
            time.sleep(sleep_time)
        
        MassiveClient._last_request_time = time.time()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._enforce_rate_limit()  # Sleep if needed to avoid rate limits
        resp = self._session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        self._enforce_rate_limit()  # Sleep if needed to avoid rate limits
        resp = self._session.post(f"{self.base_url}{path}", json=json, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def paginated_get(self, path: str, params: dict[str, Any] | None = None, page_size: int = 200):
        """
        Generator that yields items across all pages of a "massive" (large)
        paginated dataset. Assumes a cursor-based API shape:
        {"items": [...], "next_cursor": "..." | null}
        Adjust to match the real Massive API pagination contract.
        """
        cursor = None
        params = dict(params or {})
        params["page_size"] = page_size

        while True:
            if cursor:
                params["cursor"] = cursor
            data = self.get(path, params=params)
            items = data.get("items", [])
            for item in items:
                yield item

            cursor = data.get("next_cursor")
            if not cursor:
                break

    def get_latest_price(self, symbol: str) -> dict:
        """
        Fetch the latest traded price for a single symbol in a SINGLE API
        call (no pagination). Use this instead of paginated_get() whenever
        the caller needs to stay within tight API rate limits (e.g.
        classroom/student accounts), at the cost of only being able to
        request one symbol per request.
        """
        data = self.get(f"/v2/aggs/ticker/{symbol}/prev")
        return data

    def get_news(
        self,
        ticker: str,
        limit: int = 50,
        published_utc_gte: str | None = None,
    ) -> list[dict]:
        """
        Fetch recent news articles for a single ticker in a SINGLE API call
        (GET /v2/reference/news). Returns just the "results" list - each
        item has: id, title, description, author, article_url, publisher,
        tickers, keywords, insights (sentiment), published_utc.

        published_utc_gte: optional ISO date/datetime string to only fetch
        articles published on/after this date (maps to the API's
        "published_utc.gte" filter).
        """
        params: dict[str, Any] = {
            "ticker": ticker,
            "limit": limit,
            "order": "desc",
            "sort": "published_utc",
        }
        if published_utc_gte:
            params["published_utc.gte"] = published_utc_gte

        data = self.get("/v2/reference/news", params=params)
        return data.get("results", [])

    def get_ticker_details(self, symbol: str) -> dict:
        """
        Fetch company details for a single ticker (GET /v3/reference/tickers/{symbol}).
        Returns comprehensive company information including name, description,
        market cap, logo URL, homepage, industry, sector, employees, etc.

        Free tier: ✅ Available

        Example response shape:
        {
            "status": "OK",
            "results": {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
                "active": true,
                "currency_name": "usd",
                "cik": "0000320193",
                "composite_figi": "BBG000B9XRY4",
                "share_class_figi": "BBG001S5N8V8",
                "market_cap": 2771126040000,
                "phone_number": "(408) 996-1010",
                "address": {...},
                "description": "Apple Inc. designs, manufactures...",
                "sic_code": "3571",
                "sic_description": "ELECTRONIC COMPUTERS",
                "ticker_root": "AAPL",
                "homepage_url": "https://www.apple.com",
                "total_employees": 164000,
                "list_date": "1980-12-12",
                "branding": {
                    "logo_url": "https://api.polygon.io/v1/reference/company-branding/...",
                    "icon_url": "https://api.polygon.io/v1/reference/company-branding/..."
                },
                "share_class_shares_outstanding": 15204100000,
                "weighted_shares_outstanding": 15204100000
            }
        }
        """
        data = self.get(f"/v3/reference/tickers/{symbol}")
        return data.get("results", {})

    def get_price_history(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        timespan: str = "day",
        multiplier: int = 1,
    ) -> list[dict]:
        """
        Fetch historical aggregate bars (OHLC data) for a ticker over a date range
        (GET /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}).

        Free tier: ✅ Available (limited to last 2 years of data)

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            from_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
            to_date: End date in YYYY-MM-DD format (e.g., "2024-12-31")
            timespan: Bar timespan - "minute", "hour", "day", "week", "month", "quarter", "year"
                      Default: "day" (free tier works best with day/week/month)
            multiplier: Size of the timespan multiplier (e.g., 1 for 1-day bars, 5 for 5-minute bars)

        Returns:
            List of aggregate bars, each containing:
            {
                "v": volume,
                "vw": volume_weighted_price,
                "o": open,
                "c": close,
                "h": high,
                "l": low,
                "t": timestamp_ms,
                "n": number_of_transactions
            }

        Example:
            # Get last 90 days of daily bars
            history = client.get_price_history(
                "AAPL",
                "2024-10-01",
                "2024-12-31",
                timespan="day"
            )
        """
        path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        data = self.get(path)
        return data.get("results", [])

    def get_sma(self, symbol: str, window: int = 50, series_type: str = "close",
                timespan: str = "day", order: str = "desc", limit: int = 100) -> dict:
        """
        Retrieve the Simple Moving Average (SMA) for a ticker.
        GET /v1/indicators/sma/{symbol}

        Free tier: ✅ Available

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            window: Size of the moving average window (default: 50)
            series_type: Price type to calculate on - "close", "open", "high", "low" (default: "close")
            timespan: Timespan of the aggregates - "day", "week", "month" (default: "day")
            order: Order of results - "asc" or "desc" (default: "desc")
            limit: Number of results to return (default: 100, max: 5000)

        Returns:
            Dict with:
            {
                "status": "OK",
                "results": {
                    "values": [{"timestamp": ms, "value": float}, ...]
                }
            }
        """
        params = {
            "window": window,
            "series_type": series_type,
            "timespan": timespan,
            "order": order,
            "limit": limit,
        }
        return self.get(f"/v1/indicators/sma/{symbol}", params=params)

    def get_ema(self, symbol: str, window: int = 50, series_type: str = "close",
                timespan: str = "day", order: str = "desc", limit: int = 100) -> dict:
        """
        Retrieve the Exponential Moving Average (EMA) for a ticker.
        GET /v1/indicators/ema/{symbol}

        Free tier: ✅ Available

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            window: Size of the moving average window (default: 50)
            series_type: Price type to calculate on - "close", "open", "high", "low" (default: "close")
            timespan: Timespan of the aggregates - "day", "week", "month" (default: "day")
            order: Order of results - "asc" or "desc" (default: "desc")
            limit: Number of results to return (default: 100, max: 5000)

        Returns:
            Dict with:
            {
                "status": "OK",
                "results": {
                    "values": [{"timestamp": ms, "value": float}, ...]
                }
            }
        """
        params = {
            "window": window,
            "series_type": series_type,
            "timespan": timespan,
            "order": order,
            "limit": limit,
        }
        return self.get(f"/v1/indicators/ema/{symbol}", params=params)

    def get_macd(self, symbol: str, short_window: int = 12, long_window: int = 26,
                 signal_window: int = 9, series_type: str = "close",
                 timespan: str = "day", order: str = "desc", limit: int = 100) -> dict:
        """
        Retrieve the Moving Average Convergence/Divergence (MACD) for a ticker.
        GET /v1/indicators/macd/{symbol}

        Free tier: ✅ Available

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            short_window: Short EMA window (default: 12)
            long_window: Long EMA window (default: 26)
            signal_window: Signal line window (default: 9)
            series_type: Price type to calculate on - "close", "open", "high", "low" (default: "close")
            timespan: Timespan of the aggregates - "day", "week", "month" (default: "day")
            order: Order of results - "asc" or "desc" (default: "desc")
            limit: Number of results to return (default: 100, max: 5000)

        Returns:
            Dict with:
            {
                "status": "OK",
                "results": {
                    "values": [{"timestamp": ms, "value": float, "signal": float, "histogram": float}, ...]
                }
            }
        """
        params = {
            "short_window": short_window,
            "long_window": long_window,
            "signal_window": signal_window,
            "series_type": series_type,
            "timespan": timespan,
            "order": order,
            "limit": limit,
        }
        return self.get(f"/v1/indicators/macd/{symbol}", params=params)

    def get_rsi(self, symbol: str, window: int = 14, series_type: str = "close",
                timespan: str = "day", order: str = "desc", limit: int = 100) -> dict:
        """
        Retrieve the Relative Strength Index (RSI) for a ticker.
        GET /v1/indicators/rsi/{symbol}

        Free tier: ✅ Available

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            window: RSI window/period (default: 14)
            series_type: Price type to calculate on - "close", "open", "high", "low" (default: "close")
            timespan: Timespan of the aggregates - "day", "week", "month" (default: "day")
            order: Order of results - "asc" or "desc" (default: "desc")
            limit: Number of results to return (default: 100, max: 5000)

        Returns:
            Dict with:
            {
                "status": "OK",
                "results": {
                    "values": [{"timestamp": ms, "value": float}, ...]
                }
            }
        """
        params = {
            "window": window,
            "series_type": series_type,
            "timespan": timespan,
            "order": order,
            "limit": limit,
        }
        return self.get(f"/v1/indicators/rsi/{symbol}", params=params)
