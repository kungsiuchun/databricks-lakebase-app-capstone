# Agent Demo Transcript

This demonstrates the Massive Stock Research Agent end-to-end, showing:
- Vector search for relevant context
- News retrieval with citations
- Write actions (save_research_note, add_to_watchlist)
- Clear reasoning and source attribution

---

## Demo Session: AAPL Analysis

### User Query
```
User: What's the sentiment around AAPL lately? Should I be concerned about any recent developments?
```

### Agent Response

**Step 1: Vector Search for Context**

*Reasoning: First, I need to search our knowledge base for any existing research notes or embeddings about AAPL to understand historical context and recent technical indicators.*

🔍 **Tool Call**: `vector_search`
```json
{
  "query": "AAPL Apple recent sentiment analysis technical indicators news",
  "top_k": 5,
  "index_name": "ticker_news_embeddings"
}
```

**Results**:
- Found 5 relevant articles with similarity scores 0.85-0.92
- Key themes: iPhone sales concern, China market challenges, services growth
- Most recent: 2 days ago

---

**Step 2: Fetch Latest News**

*Reasoning: The vector search showed concerns about iPhone sales and China. Let me fetch the very latest news (last 7 days) to see if there are any breaking developments.*

📰 **Tool Call**: `get_news`
```json
{
  "ticker": "AAPL",
  "limit": 20,
  "published_utc_gte": "2026-08-02T00:00:00Z"
}
```

**Results**:
- 18 articles found
- **Key Headlines**:
  - "Apple Reports Strong Services Growth" (Aug 7, CNBC)
  - "iPhone 16 Pre-orders Beat Expectations" (Aug 6, Bloomberg)
  - "Analysts Upgrade AAPL on AI Momentum" (Aug 5, Reuters)

**Sentiment Analysis**:
- Positive: 72% (13 articles)
- Neutral: 22% (4 articles)
- Negative: 6% (1 article)

**Citations**:
1. https://cnbc.com/apple-services-growth-q3-2026
2. https://bloomberg.com/iphone-16-preorders-strong
3. https://reuters.com/apple-ai-upgrade-cycle

---

**Step 3: Synthesis & Research Note**

*Reasoning: The data shows a positive shift. Earlier concerns about China seem to be offset by strong services and AI-driven upgrade momentum. I should save this insight for future reference.*

💾 **Tool Call**: `save_research_note`
```json
{
  "symbol": "AAPL",
  "note_type": "sentiment",
  "title": "AAPL Sentiment Improved - AI & Services Driving Confidence",
  "content": "Recent sentiment analysis (Aug 2-9, 2026) shows 72% positive coverage, a significant improvement from prior concerns about China exposure and iPhone sales. Key drivers: (1) Services revenue growth exceeding expectations (Q3 2026), (2) iPhone 16 pre-orders beating analyst forecasts on AI features, (3) Multiple analyst upgrades citing AI monetization potential. Earlier China market headwinds appear to be priced in, with investors focusing on long-term AI positioning.",
  "sources": [
    "https://cnbc.com/apple-services-growth-q3-2026",
    "https://bloomberg.com/iphone-16-preorders-strong",
    "https://reuters.com/apple-ai-upgrade-cycle"
  ],
  "metadata": {
    "sentiment_score": 0.72,
    "article_count": 18,
    "analysis_date": "2026-08-09"
  }
}
```

✅ **Response**: Research note saved (ID: 1247)

---

**Step 4: Watchlist Update**

*Reasoning: Given the positive shift and strong fundamentals, I should ensure AAPL is on the user's watchlist for continued monitoring.*

⭐ **Tool Call**: `add_to_watchlist`
```json
{
  "symbol": "AAPL"
}
```

✅ **Response**: AAPL added to watchlist (current price: $182.45)

---

### Final Agent Response to User

> **No major concerns - sentiment has actually improved!** 📈
> 
> Here's what I found:
> 
> **Recent Sentiment: 72% Positive** (18 articles analyzed, Aug 2-9)
> 
> The narrative has shifted positively over the past week:
> 1. **Services Growth**: Q3 services revenue exceeded expectations, showing strength beyond hardware ([CNBC](https://cnbc.com/apple-services-growth-q3-2026))
> 2. **iPhone 16 Momentum**: Pre-orders are beating forecasts, driven by AI features that are resonating with consumers ([Bloomberg](https://bloomberg.com/iphone-16-preorders-strong))
> 3. **Analyst Confidence**: Multiple upgrades citing long-term AI monetization potential ([Reuters](https://reuters.com/apple-ai-upgrade-cycle))
> 
> **Earlier China concerns seem to be priced in** - the focus has moved to Apple's AI positioning and ecosystem monetization.
> 
> I've saved this analysis as a research note and added AAPL to your watchlist for tracking. Current price: **$182.45**
> 
> **Bottom Line**: No red flags. The recent developments are positive, and sentiment has improved from earlier cautious tones.

---

## Demo Session 2: Multi-Stock Comparison

### User Query
```
User: Compare MSFT and GOOGL - which has better momentum right now?
```

### Agent Response

**Step 1: Parallel Vector Search**

*Reasoning: Search for recent technical analysis and price momentum indicators for both stocks.*

🔍 **Tool Calls** (parallel):
1. `vector_search` - MSFT technical momentum indicators
2. `vector_search` - GOOGL technical momentum indicators

**Results**:
- **MSFT**: Strong RSI (64), positive MACD crossover (3 days ago), above 20/50/200 MA
- **GOOGL**: Moderate RSI (52), neutral MACD, consolidating near 50 MA

---

**Step 2: Parallel News Retrieval**

📰 **Tool Calls** (parallel):
1. `get_news` - MSFT (last 7 days)
2. `get_news` - GOOGL (last 7 days)

**Results**:

**MSFT**:
- 22 articles, 77% positive sentiment
- Key themes: Azure growth, AI Copilot adoption, enterprise wins
- Citations: WSJ, FT, TechCrunch

**GOOGL**:
- 16 articles, 56% positive sentiment
- Key themes: Cloud competition, AI search updates, regulatory headwinds
- Citations: NYT, Bloomberg, Verge

---

**Step 3: Comparative Research Note**

💾 **Tool Call**: `save_research_note`
```json
{
  "symbol": "MSFT",
  "note_type": "technical",
  "title": "MSFT vs GOOGL Momentum - MSFT Shows Stronger Near-Term Setup",
  "content": "Comparative analysis (Aug 2-9, 2026) shows MSFT with superior momentum: (1) Technical: MSFT RSI 64 vs GOOGL 52, MSFT recent MACD bullish crossover vs GOOGL neutral. (2) Sentiment: MSFT 77% positive (22 articles) vs GOOGL 56% positive (16 articles). (3) Catalysts: MSFT Azure/AI adoption driving confidence; GOOGL facing cloud competition and regulatory uncertainty. Short-term edge to MSFT, though GOOGL consolidation could set up next leg.",
  "sources": [
    "Technical indicators from ticker_details_embeddings",
    "News sentiment from ticker_news_embeddings"
  ],
  "metadata": {
    "comparison_stocks": ["MSFT", "GOOGL"],
    "msft_sentiment": 0.77,
    "googl_sentiment": 0.56,
    "recommendation": "MSFT near-term momentum advantage"
  }
}
```

✅ **Response**: Research note saved (ID: 1248)

---

### Final Agent Response to User

> **MSFT has stronger momentum right now** 🚀
> 
> Here's the breakdown:
> 
> | Metric | MSFT | GOOGL | Winner |
> |--------|------|-------|--------|
> | **Recent Sentiment** | 77% positive (22 articles) | 56% positive (16 articles) | ✅ MSFT |
> | **Technical (RSI)** | 64 (strong) | 52 (neutral) | ✅ MSFT |
> | **Price Trend** | MACD bullish crossover (3d ago) | Consolidating near 50 MA | ✅ MSFT |
> | **Key Catalysts** | Azure growth + AI Copilot adoption | Cloud competition + regulatory concerns | ✅ MSFT |
> 
> **MSFT** is showing better momentum across both technical and fundamental factors. Azure and AI Copilot are driving positive sentiment, and the recent MACD bullish crossover suggests near-term strength.
> 
> **GOOGL** is consolidating and facing headwinds from cloud competition and regulatory scrutiny. However, this consolidation could set up the next leg higher once resolved.
> 
> **Recommendation**: For near-term momentum, MSFT has the edge. GOOGL might offer value if you're patient.
> 
> I've saved this comparative analysis for future reference.

---

## Key Agent Capabilities Demonstrated

✅ **Vector Search**: Efficient retrieval of relevant historical research and technical data  
✅ **News Retrieval**: Real-time sentiment analysis with proper source attribution  
✅ **Write Actions**: Persistent research notes for future reference  
✅ **Watchlist Management**: Automatic tracking of analyzed stocks  
✅ **Multi-Tool Orchestration**: Parallel tool calls for comparative analysis  
✅ **Clear Reasoning**: Each tool call includes explicit reasoning about why it's needed  
✅ **Source Citations**: All claims backed by specific URLs and data sources  
✅ **Structured Output**: Organized responses with tables, summaries, and actionable insights

---

## Running the Agent

### Prerequisites
1. Complete all SQL setup steps (01-12) in `/sql` folder
2. Set up Databricks secrets scope with MASSIVE API key
3. Configure MCP server environment variables
4. Create embeddings for news and technical data (see notebooks)

### Configuration

The agent connects to your deployed MCP server:

```yaml
# agent-config.yaml
name: massive-stock-research-agent
description: AI stock research assistant with vector search, news analysis, and persistent notes
mcp_server:
  url: https://your-workspace.cloud.databricks.com/apps/massive-mcp-server
  authentication: databricks-oauth
tools:
  - vector_search
  - get_news
  - get_ticker_details
  - save_research_note
  - add_to_watchlist
  - get_price_history
system_prompt: |
  You are a stock research assistant. Always cite sources, explain your reasoning,
  and use vector search + news retrieval before making recommendations.
```

### Test the Agent

```python
from databricks.agents import Agent

agent = Agent.from_config("agent-config.yaml")

# Test basic query
response = agent.query("What's the latest on AAPL?")
print(response.content)

# Test multi-tool workflow
response = agent.query("Compare MSFT and GOOGL momentum, and save a research note")
print(response.content)
print(f"Tools used: {[t.name for t in response.tool_calls]}")
```

---

## Expected Output Quality

✅ **Grounded in data**: Every claim has a specific source (URL, table, vector search result)  
✅ **Transparent reasoning**: Each step explains why that tool was chosen  
✅ **Persistent insights**: Research notes saved to Lakebase for future sessions  
✅ **Actionable**: Clear recommendations with supporting evidence  
✅ **Multi-source**: Combines vector search, live news, price data, and technical indicators

This agent architecture ensures all analysis is:
- **Traceable** (citations + reasoning)
- **Reproducible** (saved research notes)
- **Comprehensive** (multiple data sources)
- **Actionable** (clear recommendations)

---

## Next Steps

1. ✅ Deploy the MCP server as a Databricks App
2. ✅ Run all SQL setup scripts (01-12)
3. ✅ Generate embeddings via notebooks
4. ✅ Configure agent with your MCP server URL
5. ✅ Test with the sample queries above
6. 📊 Monitor agent performance via `user_activity` table
7. 🔧 Tune vector search parameters based on result quality