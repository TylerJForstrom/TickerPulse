# TickerPulse 📈

**Live social sentiment & trend radar for the stock market.**

TickerPulse ingests public social-media chatter (Reddit, StockTwits, Bluesky, Hacker News, finance RSS), figures out which tickers and themes people are talking about *right now*, measures how fast that chatter is growing, scores it with finance-tuned sentiment, and correlates the buzz against real market prices — all presented in an interactive dashboard.

**Live demo:** https://tickerpulse-demo.netlify.app
*(Demo runs on a bundled sample snapshot — zero credentials required. Wire in free-tier keys and it goes near-live.)*

> ⚠️ Not financial advice. TickerPulse is a research/portfolio project that aggregates public chatter.

---

## What it answers

| Feature | The real question it answers |
|---|---|
| Trending leaderboard (volume, velocity, breakout σ) | *"What is the crowd piling into right now, and is it accelerating?"* |
| Phase flags (emerging / peaking / fading) | *"Am I early, on time, or late to this story?"* |
| Bull:bear ratio + sentiment trajectory | *"Is this hype or fear — and is the mood shifting?"* |
| Engagement-weighted scores | *"Is this 1 viral post or a genuinely broad conversation?"* |
| Cross-platform diffusion | *"Where did this start, and has it escaped its bubble?"* (WSB-only ≠ mainstream) |
| **Buzz-vs-price overlay + lead/lag correlation** | *"Does chatter for this ticker actually precede the move, or just react to it?"* |
| Topic landscape map | *"What themes — not just tickers — dominate the conversation?"* |
| Unusual-activity alerts | *"What spiked out of nowhere in the last few hours?"* |
| Exportable brief | *"Give me the one-pager for the morning meeting."* |

## Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │            GitHub Actions (cron, free)       │
   Reddit API ──┐      │  Python worker, every 15 min:                │
   StockTwits ──┤      │  ingest → normalize → ticker extraction →    │
   Bluesky ─────┼─────▶│  FinBERT sentiment → topic clustering        │
   Hacker News ─┤      │  (MiniLM → UMAP → HDBSCAN → c-TF-IDF) →      │
   RSS feeds ───┘      │  trend metrics → buzz-vs-price correlation   │
   yfinance OHLCV ────▶│                                              │
                       └───────────────────┬──────────────────────────┘
                                           │ precomputed payloads
                                           ▼
                        ┌────────────────────────────────┐
                        │  Supabase Postgres (free tier) │
                        │  posts + time-series + meta    │
                        └───────────────┬────────────────┘
                                        │ indexed key lookups (read-only)
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │                  Netlify                      │
                 │  serverless functions (/api/*)  ←  React SPA │
                 │  demo fallback: static JSON artifacts (/data)│
                 └──────────────────────────────────────────────┘
```

**Design principles**

- **Free tier only.** GitHub Actions does the heavy lifting on a schedule (public repo = unlimited minutes); Netlify serves the SPA + a thin read API; Supabase stores results. No always-on server — but ingestion is adapter-based, so moving the worker to Render/Fly for true streaming is a config change, not a rewrite.
- **Precompute everything.** The worker writes final payloads; the read API is a single indexed lookup per request. The dashboard never makes the database think.
- **Zero-credential demo mode.** With no env vars at all, the pipeline processes a bundled 5k-post sample dataset with realistic narrative arcs, and the dashboard serves those artifacts statically. Every feature works.
- **ToS-compliant sources only.** Official APIs (Reddit OAuth, StockTwits public API, AT Protocol, Algolia HN, RSS), polite rate limits, aggressive caching.

## The NLP / metrics core

**Ticker extraction** — three confidence tiers: cashtags (`$NVDA`), a curated symbol dictionary for bare uppercase mentions, and company-name aliases ("nvidia" → NVDA). Junk disambiguation: `$5` isn't a ticker, neither is `YOLO`, and word-collision symbols (NOW, ARM, F, T…) only count as cashtags or full company names. *(Tested in `tests/test_tickers.py`.)*

**Sentiment** — [FinBERT](https://huggingface.co/ProsusAI/finbert) (finance-tuned BERT) classifies each post bull/bear/neutral, run locally in the Actions worker (or via HF Inference API). Demo mode falls back to a built-in weighted finance lexicon with negation handling, so the project runs with zero ML deps.

**Topics** — posts are embedded (all-MiniLM-L6-v2), projected to 2-D (UMAP; t-SNE fallback), density-clustered (HDBSCAN), and labeled by class-based TF-IDF. That gives the topic landscape map plus theme-level sentiment and velocity.

**Trend math** (tested in `tests/test_trends.py`):
- `velocity` = Δ mentions/hour between consecutive windows
- `breakout_score` = z-score of the current rate vs the trailing 7-day baseline
- `phase` = emerging / peaking / fading / steady from breakout × velocity × prior-window heat
- `bull_bear_ratio` = Laplace-smoothed bull/bear counts
- engagement-weighted scores use `Σ log1p(engagement)` so one viral post can't masquerade as a movement

**Buzz vs price (flagship)** — hourly mention counts are aligned with real OHLCV (yfinance) and correlated at lags −12h…+12h. The dashboard reports whether social buzz *leads* or *follows* the price action, with the full lag-correlation profile.

## Repo layout

```
worker/            Python pipeline
  ingest/          source adapters (reddit, stocktwits, bluesky, hn, rss, csv/json, market data)
  nlp/             ticker extraction · FinBERT/lexicon sentiment · topic clustering
  metrics/         trends · correlation · alerts · co-occurrence graph
  sinks/           Postgres writer · JSON artifact writer (demo)
  sample_gen.py    synthetic sample dataset generator
dashboard/         React + Vite SPA (Recharts, d3-force)
netlify/functions/ read-only API (Supabase meta lookups)
db/schema.sql      Postgres schema
.github/workflows/ pipeline cron + CI
tests/             ticker extraction + trend math
```

## Run it yourself

**Demo mode (no credentials):**

```bash
pip install -r requirements.txt
python -m worker.sample_gen          # generate the sample dataset
python -m worker.pipeline            # full pipeline → dashboard/public/data/
cd dashboard && npm install && npm run dev
```

**Live mode:**

1. Create a free Supabase (or Neon) project; run `db/schema.sql`.
2. Add repo secrets: `DATABASE_URL` (+ optional `REDDIT_CLIENT_ID/SECRET`, `BLUESKY_HANDLE/APP_PASSWORD`, `HF_TOKEN`). The Actions cron starts writing on the next tick.
3. On Netlify set `SUPABASE_URL` + `SUPABASE_ANON_KEY`; the same dashboard flips from demo to near-live automatically.

```bash
pytest        # ticker extraction + trend math tests
```

## Stack

Python (pandas, scikit-learn, transformers/FinBERT, sentence-transformers, UMAP, HDBSCAN, psycopg) · React + Vite · Recharts · d3-force · Netlify Functions · Supabase Postgres · GitHub Actions · yfinance
