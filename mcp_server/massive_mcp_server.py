"""Massive market-data MCP server.

Exposes the read-only market-data capabilities of the repository's canonical
``massive_client.MassiveClient`` over MCP (Model Context Protocol). This is a
standalone Databricks App entrypoint; it does not replace the Flask dashboard.

Run locally (after installing FastMCP and configuring Databricks credentials):
    python mcp_server/massive_mcp_server.py
"""

import os
import sys
import logging
from pathlib import Path

from fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

# This script is normally executed from mcp_server/. Insert the repository root
# ahead of the script directory so ``massive_client`` always resolves to the
# one canonical implementation at the project root.

from massive_client import MassiveClient
import lakebase
from datetime import datetime, timedelta
import statistics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("massive-mcp-server")

# Table names for vector search
NEWS_TABLE_NAME = os.environ.get("NEWS_TABLE_NAME", "ticker_news_documents")
EMBEDDINGS_TABLE_NAME = os.environ.get("EMBEDDINGS_TABLE_NAME", "ticker_news_embeddings")
CHUNK_EMBEDDINGS_TABLE_NAME = os.environ.get("CHUNK_EMBEDDINGS_TABLE_NAME", "ticker_news_chunk_embeddings")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# Load embedding model once at startup (lazy)
_embedding_model = None

def get_embedding_model():
    """Lazy-load the embedding model (expensive operation, only on first use)."""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


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
    """Fetch recent news articles for one ticker from the Polygon.io API (real-time).
    
    This pulls fresh news directly from the external API, not from local storage.
    For semantic search over previously indexed news in Lakebase, use vector_search instead.

    Args:
        ticker: Stock ticker symbol, for example ``AAPL``.
        limit: Maximum number of articles to return.
        published_utc_gte: Optional inclusive ISO date or datetime filter.
    
    Returns:
        List of news articles with title, description, sentiment, and article_url.
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


# ============================================================================
# Watchlist Management Tools
# ============================================================================

@mcp.tool
def get_watchlist(user_email: str) -> list[dict]:
    """Get user's watchlist with latest prices and last updated timestamps.
    
    Args:
        user_email: User's email address
    
    Returns:
        List of watchlist items with symbol, latest_price, and updated_at
    """
    return lakebase.run_query(
        "SELECT symbol, latest_price, updated_at FROM watchlist WHERE email = %s ORDER BY updated_at DESC",
        (user_email,)
    )


@mcp.tool
def add_to_watchlist(symbol: str, user_email: str, latest_price: float = None) -> dict:
    """Add a ticker to user's watchlist.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL)
        user_email: User's email address
        latest_price: Optional current price to store
    
    Returns:
        Confirmation dict with status
    """
    lakebase.run_write(
        """
        INSERT INTO watchlist (symbol, email, latest_price, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (symbol, email) DO UPDATE
            SET latest_price = EXCLUDED.latest_price,
                updated_at = EXCLUDED.updated_at
        """,
        (symbol.upper(), user_email, latest_price)
    )
    return {"status": "success", "message": f"Added {symbol} to watchlist"}


@mcp.tool
def remove_from_watchlist(symbol: str, user_email: str) -> dict:
    """Remove a ticker from user's watchlist.
    
    Args:
        symbol: Stock ticker symbol
        user_email: User's email address
    
    Returns:
        Confirmation dict with status
    """
    rows = lakebase.run_write(
        "DELETE FROM watchlist WHERE symbol = %s AND email = %s",
        (symbol.upper(), user_email)
    )
    if rows > 0:
        return {"status": "success", "message": f"Removed {symbol} from watchlist"}
    return {"status": "not_found", "message": f"{symbol} not in watchlist"}


# ============================================================================
# Research Notes Tools
# ============================================================================

@mcp.tool
def save_research_note(symbol: str, user_email: str, note: str) -> dict:
    """Save a research note or analysis for a ticker.
    
    Args:
        symbol: Stock ticker symbol
        user_email: User's email address
        note: Research note text
    
    Returns:
        Dict with note_id and confirmation
    """
    # INSERT with RETURNING needs manual connection handling to commit
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_notes (symbol, user_email, note, created_at, updated_at)
                VALUES (%s, %s, %s, now(), now())
                RETURNING id
                """,
                (symbol.upper(), user_email, note)
            )
            result = cur.fetchone()
            conn.commit()
            note_id = result['id'] if result else None
    
    return {
        "status": "success",
        "note_id": note_id,
        "message": f"Saved research note for {symbol}"
    }


@mcp.tool
def get_research_notes(symbol: str, user_email: str) -> list[dict]:
    """Get all research notes for a specific ticker.
    
    Args:
        symbol: Stock ticker symbol
        user_email: User's email address
    
    Returns:
        List of research notes with id, note, created_at, updated_at
    """
    return lakebase.run_query(
        """
        SELECT id, symbol, note, created_at, updated_at 
        FROM research_notes 
        WHERE symbol = %s AND user_email = %s 
        ORDER BY created_at DESC
        """,
        (symbol.upper(), user_email)
    )


@mcp.tool
def list_all_notes(user_email: str, limit: int = 50) -> list[dict]:
    """List all research notes across all tickers for a user.
    
    Args:
        user_email: User's email address
        limit: Maximum number of notes to return (default 50)
    
    Returns:
        List of all research notes ordered by creation date
    """
    return lakebase.run_query(
        """
        SELECT id, symbol, note, created_at, updated_at 
        FROM research_notes 
        WHERE user_email = %s 
        ORDER BY created_at DESC 
        LIMIT %s
        """,
        (user_email, limit)
    )


@mcp.tool
def delete_research_note(note_id: int, user_email: str) -> dict:
    """Delete a research note.
    
    Args:
        note_id: ID of the note to delete
        user_email: User's email (for authorization)
    
    Returns:
        Confirmation dict
    """
    rows = lakebase.run_write(
        "DELETE FROM research_notes WHERE id = %s AND user_email = %s",
        (note_id, user_email)
    )
    if rows > 0:
        return {"status": "success", "message": "Note deleted"}
    return {"status": "not_found", "message": "Note not found or unauthorized"}


# ============================================================================
# Price Analysis Tools
# ============================================================================

@mcp.tool
def analyze_price_performance(symbol: str, days: int = 30) -> dict:
    """Analyze recent price performance with key statistics.
    
    Args:
        symbol: Stock ticker symbol
        days: Number of days to analyze (default 30)
    
    Returns:
        Dict with price statistics: change_pct, high, low, avg_volume, volatility
    """
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")
    
    history = _get_client().get_price_history(symbol, from_date, to_date)
    
    if not history:
        return {"error": f"No price data available for {symbol}"}
    
    closes = [bar['c'] for bar in history]
    volumes = [bar['v'] for bar in history]
    
    first_close = closes[0]
    last_close = closes[-1]
    change_pct = ((last_close - first_close) / first_close) * 100
    
    high = max([bar['h'] for bar in history])
    low = min([bar['l'] for bar in history])
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    volatility = statistics.stdev(closes) if len(closes) > 1 else 0
    
    return {
        "symbol": symbol,
        "period_days": days,
        "first_price": first_close,
        "last_price": last_close,
        "change_pct": round(change_pct, 2),
        "high": high,
        "low": low,
        "avg_volume": int(avg_volume),
        "volatility": round(volatility, 2),
        "data_points": len(history)
    }


@mcp.tool
def get_technical_summary(symbol: str) -> dict:
    """Get combined technical analysis with trading signals from Lakebase (FAST - no API calls).
    
    Fetches pre-computed technical indicators from the technical_indicators table in Lakebase.
    Much faster than get_technical_summary_api since it's a single local database query.
    
    Args:
        symbol: Stock ticker symbol
    
    Returns:
        Dict with SMA, RSI, MACD indicators and interpretation
    """
    try:
        # Fetch latest indicators from Lakebase in a single query
        # Get the most recent value for each indicator type
        results = lakebase.run_query(
            """
            WITH latest_indicators AS (
                SELECT 
                    ticker,
                    indicator_type,
                    window_size,
                    value,
                    signal_value,
                    timestamp_utc,
                    ROW_NUMBER() OVER (PARTITION BY ticker, indicator_type, window_size ORDER BY timestamp_utc DESC) as rn
                FROM technical_indicators
                WHERE ticker = %s
                    AND timestamp_utc >= NOW() - INTERVAL '7 days'
            )
            SELECT 
                ticker,
                indicator_type,
                window_size,
                value,
                signal_value
            FROM latest_indicators
            WHERE rn = 1
            """,
            (symbol.upper(),)
        )
        
        if not results:
            return {"error": f"No technical indicator data available for {symbol}"}
        
        # Extract values from results
        indicators = {}
        for row in results:
            key = f"{row['indicator_type']}_{row['window_size']}" if row['window_size'] else row['indicator_type']
            indicators[key] = {
                'value': float(row['value']) if row['value'] else 0,
                'signal': float(row['signal_value']) if row.get('signal_value') else None
            }
        
        # Get current price (1 API call - lightweight)
        client = _get_client()
        price_data = client.get_latest_price(symbol)
        current_price = price_data.get('results', [{}])[0].get('c', 0) if price_data.get('results') else 0
        
        # Extract specific indicators
        sma_50_val = indicators.get('SMA_50', {}).get('value', 0)
        sma_200_val = indicators.get('SMA_200', {}).get('value', 0)
        rsi_val = indicators.get('RSI_14', {}).get('value', 50)
        macd_val = indicators.get('MACD_12', {}).get('value', 0)
        macd_signal = indicators.get('MACD_12', {}).get('signal', 0)
        
        # Simple interpretations
        trend = "bullish" if current_price > sma_50_val > sma_200_val else "bearish" if current_price < sma_50_val < sma_200_val else "neutral"
        rsi_signal = "oversold" if rsi_val < 30 else "overbought" if rsi_val > 70 else "neutral"
        macd_signal_str = "bullish" if macd_val > macd_signal else "bearish"
        
        return {
            "symbol": symbol,
            "current_price": current_price,
            "sma_50": round(sma_50_val, 2),
            "sma_200": round(sma_200_val, 2),
            "rsi": round(rsi_val, 2),
            "rsi_signal": rsi_signal,
            "macd": round(macd_val, 4),
            "macd_signal": round(macd_signal, 4) if macd_signal else 0,
            "macd_signal_str": macd_signal_str,
            "overall_trend": trend,
            "source": "lakebase"
        }
        
    except Exception as e:
        logger.exception("Failed to fetch technical summary from Lakebase")
        return {"error": str(e)}


# ============================================================================
# Multi-Ticker Comparison Tools
# ============================================================================

@mcp.tool
def compare_tickers(symbols: list[str], days: int = 30) -> dict:
    """Compare multiple tickers on price performance.
    
    Args:
        symbols: List of ticker symbols (max 5 to respect rate limits)
        days: Period for comparison (default 30 days)
    
    Returns:
        Dict with comparison data for each ticker
    """
    if len(symbols) > 5:
        return {"error": "Maximum 5 tickers allowed for comparison (rate limit protection)"}
    
    results = {}
    for symbol in symbols:
        try:
            perf = analyze_price_performance(symbol, days)
            results[symbol] = perf
        except Exception as e:
            results[symbol] = {"error": str(e)}
    
    return {
        "period_days": days,
        "tickers": results
    }


# ============================================================================
# News Intelligence Tools
# ============================================================================

@mcp.tool
def get_news_summary(symbol: str, days: int = 7, limit: int = 20) -> dict:
    """Get structured news summary with sentiment analysis.
    
    Args:
        symbol: Stock ticker symbol
        days: Number of days to look back (default 7)
        limit: Maximum number of articles (default 20)
    
    Returns:
        Dict with news count, sentiment breakdown, and articles
    """
    published_gte = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    news = _get_client().get_news(symbol, limit=limit, published_utc_gte=published_gte)
    
    if not news:
        return {
            "symbol": symbol,
            "period_days": days,
            "total_articles": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "articles": []
        }
    
    # Count sentiment
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    for article in news:
        insights = article.get('insights', [])
        if insights:
            sentiment = insights[0].get('sentiment', 'neutral').lower()
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        else:
            sentiment_counts['neutral'] += 1
    
    # Extract key info
    articles = []
    for article in news[:10]:  # Top 10 most recent
        insights = article.get('insights', [])
        sentiment = insights[0].get('sentiment', 'neutral') if insights else 'neutral'
        
        articles.append({
            "title": article.get('title', ''),
            "published_utc": article.get('published_utc', ''),
            "article_url": article.get('article_url', ''),
            "publisher": article.get('publisher', {}).get('name', ''),
            "sentiment": sentiment
        })
    
    return {
        "symbol": symbol,
        "period_days": days,
        "total_articles": len(news),
        "sentiment": sentiment_counts,
        "articles": articles
    }


# ============================================================================
# Price Alerts and Notable Changes Tools
# ============================================================================

@mcp.tool
def create_price_alert(
    symbol: str,
    user_email: str,
    alert_type: str,
    threshold: float
) -> dict:
    """Create a price alert for a ticker.
    
    Args:
        symbol: Stock ticker symbol
        user_email: User's email address
        alert_type: Type of alert - 'price_above', 'price_below', or 'change_pct'
        threshold: Price threshold or percentage change
    
    Returns:
        Dict with alert_id and confirmation
    """
    if alert_type not in ['price_above', 'price_below', 'change_pct']:
        return {"error": "Invalid alert_type. Use: price_above, price_below, or change_pct"}
    
    result = lakebase.run_query(
        """
        INSERT INTO price_alerts (symbol, user_email, alert_type, threshold, is_active, created_at)
        VALUES (%s, %s, %s, %s, TRUE, now())
        RETURNING id
        """,
        (symbol.upper(), user_email, alert_type, threshold)
    )
    
    return {
        "status": "success",
        "alert_id": result[0]['id'] if result else None,
        "message": f"Created {alert_type} alert for {symbol} at threshold {threshold}"
    }


@mcp.tool
def check_price_alerts(user_email: str) -> list[dict]:
    """Check all active price alerts for a user and evaluate them.
    
    Args:
        user_email: User's email address
    
    Returns:
        List of alerts with current status and whether they triggered
    """
    alerts = lakebase.run_query(
        """
        SELECT id, symbol, alert_type, threshold, last_triggered 
        FROM price_alerts 
        WHERE user_email = %s AND is_active = TRUE
        """,
        (user_email,)
    )
    
    results = []
    client = _get_client()
    
    for alert in alerts:
        symbol = alert['symbol']
        alert_type = alert['alert_type']
        threshold = float(alert['threshold'])
        
        try:
            # Get current price
            price_data = client.get_latest_price(symbol)
            current_price = price_data.get('results', [{}])[0].get('c', 0) if price_data.get('results') else 0
            
            triggered = False
            if alert_type == 'price_above' and current_price > threshold:
                triggered = True
            elif alert_type == 'price_below' and current_price < threshold:
                triggered = True
            elif alert_type == 'change_pct':
                # Check daily change
                prev_close = price_data.get('results', [{}])[0].get('pc', current_price) if price_data.get('results') else current_price
                if prev_close:
                    change_pct = abs(((current_price - prev_close) / prev_close) * 100)
                    if change_pct >= threshold:
                        triggered = True
            
            # Update last_triggered if triggered
            if triggered:
                lakebase.run_write(
                    "UPDATE price_alerts SET last_triggered = now() WHERE id = %s",
                    (alert['id'],)
                )
            
            results.append({
                "alert_id": alert['id'],
                "symbol": symbol,
                "alert_type": alert_type,
                "threshold": threshold,
                "current_price": current_price,
                "triggered": triggered,
                "last_triggered": alert['last_triggered']
            })
        
        except Exception as e:
            results.append({
                "alert_id": alert['id'],
                "symbol": symbol,
                "error": str(e)
            })
    
    return results


@mcp.tool
def get_notable_changes(user_email: str, since_hours: int = 24) -> dict:
    """Find notable price moves in user's watchlist.
    
    Args:
        user_email: User's email address
        since_hours: Look back period in hours (default 24)
    
    Returns:
        Dict with notable changes: large moves, volume spikes, news counts
    """
    # Get user's watchlist
    watchlist = get_watchlist(user_email)
    
    if not watchlist:
        return {"message": "No tickers in watchlist"}
    
    notable = []
    client = _get_client()
    
    # Check recent news count
    since_date = (datetime.now() - timedelta(hours=since_hours)).strftime("%Y-%m-%d")
    
    for item in watchlist[:10]:  # Limit to 10 to respect rate limits
        symbol = item['symbol']
        
        try:
            # Get latest price
            price_data = client.get_latest_price(symbol)
            if not price_data.get('results'):
                continue
                
            bar = price_data['results'][0]
            current_price = bar.get('c', 0)
            prev_close = bar.get('pc', current_price)
            volume = bar.get('v', 0)
            
            change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
            
            # Get news count
            news = client.get_news(symbol, limit=10, published_utc_gte=since_date)
            news_count = len(news) if news else 0
            
            # Flag as notable if:
            # - Large price change (>5%)
            # - Recent news articles
            is_notable = abs(change_pct) > 5 or news_count > 0
            
            if is_notable:
                notable.append({
                    "symbol": symbol,
                    "current_price": current_price,
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "news_count": news_count,
                    "reason": "Large price move" if abs(change_pct) > 5 else "Recent news"
                })
        
        except Exception:
            continue  # Skip tickers with errors
    
    return {
        "period_hours": since_hours,
        "watchlist_size": len(watchlist),
        "notable_count": len(notable),
        "notable_changes": notable
    }


@mcp.tool
def update_user_activity(user_email: str, symbols_viewed: list[str] = None) -> dict:
    """Update user's last visit timestamp and recently viewed tickers.
    
    Args:
        user_email: User's email address
        symbols_viewed: Optional list of symbols viewed in this session
    
    Returns:
        Confirmation dict
    """
    import json
    
    if symbols_viewed:
        # Store as JSONB array of {symbol, viewed_at} objects
        viewed_data = json.dumps([
            {"symbol": s, "viewed_at": datetime.now().isoformat()}
            for s in symbols_viewed[:10]  # Keep last 10
        ])
        
        lakebase.run_write(
            """
            INSERT INTO user_activity (user_email, last_visit, last_symbols_viewed)
            VALUES (%s, now(), %s)
            ON CONFLICT (user_email) DO UPDATE
                SET last_visit = now(),
                    last_symbols_viewed = EXCLUDED.last_symbols_viewed
            """,
            (user_email, viewed_data)
        )
    else:
        lakebase.run_write(
            """
            INSERT INTO user_activity (user_email, last_visit)
            VALUES (%s, now())
            ON CONFLICT (user_email) DO UPDATE
                SET last_visit = now()
            """,
            (user_email,)
        )
    
    return {"status": "success", "message": "User activity updated"}


@mcp.tool
def vector_search(query: str, limit: int = 10, search_chunks: bool = True) -> dict:
    """
    Semantic search over ticker news stored in Lakebase using vector embeddings.
    
    USE THIS TOOL when you need to:
    - Search for news by meaning/topic (e.g., "AI chip announcements")
    - Find relevant historical news across multiple tickers
    - Query previously indexed news that's stored locally
    
    DO NOT use this for:
    - Fetching the latest breaking news (use get_news instead)
    - Getting news for a specific ticker in real-time (use get_news instead)
    
    This searches pre-indexed news documents and chunks stored in Lakebase 
    using pgvector's cosine similarity. The news was previously fetched from 
    the API and indexed with embeddings for semantic search.
    
    Args:
        query: Natural language search query describing what you're looking for.
               Examples: "tech company earnings", "AI chip shortage", 
               "electric vehicle production challenges"
        limit: Maximum number of results to return (default 10)
        search_chunks: Whether to search chunk-level embeddings in addition 
                       to full documents (default True)
    
    Returns:
        A dict with:
        - query: The search query
        - documents: List of matching documents with similarity scores
        - chunks: List of matching text chunks with similarity scores
        - model: The embedding model used
    
    Example:
        vector_search("semiconductor shortage impact", limit=5)
        # Returns news articles about chip shortages across all indexed tickers
    """
    if not query or not query.strip():
        return {"error": "Query text is required"}
    
    try:
        # Compute embedding for the query
        model = get_embedding_model()
        query_embedding = model.encode(query)
        
        # Convert to list for JSON serialization and postgres array format
        embedding_list = query_embedding.tolist()
        
        # Search document-level embeddings
        doc_results = lakebase.run_query(
            f"""
            SELECT 
                e.id,
                e.ticker,
                e.title,
                e.published_utc,
                e.model_name,
                1 - (e.embedding <=> %s::vector) as similarity,
                d.description,
                d.article_url,
                d.sentiment
            FROM {EMBEDDINGS_TABLE_NAME} e
            LEFT JOIN {NEWS_TABLE_NAME} d ON e.id = d.id
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (str(embedding_list), str(embedding_list), limit),
        )
        
        chunk_results = []
        if search_chunks:
            # Search chunk-level embeddings
            chunk_results = lakebase.run_query(
                f"""
                SELECT 
                    c.id,
                    c.article_id,
                    c.ticker,
                    c.chunk_index,
                    c.chunk_text,
                    c.model_name,
                    1 - (c.embedding <=> %s::vector) as similarity,
                    d.title,
                    d.article_url,
                    d.published_utc
                FROM {CHUNK_EMBEDDINGS_TABLE_NAME} c
                LEFT JOIN {NEWS_TABLE_NAME} d ON c.article_id = d.id
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (str(embedding_list), str(embedding_list), limit),
            )
        
        return {
            "query": query,
            "documents": doc_results,
            "chunks": chunk_results,
            "model": EMBEDDING_MODEL
        }
        
    except Exception as e:
        logger.exception("Vector search failed")
        return {"error": str(e)}


if __name__ == "__main__":
    # Databricks Apps routes external HTTP traffic to this port. Keep the same
    # transport and port precedence as the existing Alpaca MCP server.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
