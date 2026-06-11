"""Pipeline orchestrator.

    python -m worker.pipeline [--demo] [--skip-topics] [--skip-prices]
                              [--top-n 40] [--out DIR]

Demo mode (default when no DATABASE_URL): ingest the bundled sample set,
run the full NLP + metrics stack, and write JSON artifacts the dashboard
serves statically.

Live mode (DATABASE_URL set): fetch from every configured adapter, upsert
posts into Postgres, recompute metrics over the trailing week, and replace
the snapshot tables the Netlify read-API queries.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from worker.config import DATA_DIR, settings
from worker.models import Post, dedupe
from worker.brief import generate_brief
from worker.ingest.fileloader import FileLoader
from worker.ingest.market import fetch_prices, synthetic_prices
from worker.metrics.alerts import detect_alerts
from worker.metrics.correlation import compute_correlation
from worker.metrics.graph import compute_graph
from worker.metrics.trends import bucket_series, compute_ticker_trends, market_mood
from worker.nlp.sentiment import score_posts
from worker.nlp.tickers import tag_posts


def pgsink_load_meta(conn, key: str):
    with conn.cursor() as cur:
        cur.execute("select value from meta where key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def collect_posts(demo: bool) -> tuple[list[Post], list[str]]:
    """Run every available adapter; returns (posts, source names used)."""
    adapters = []
    if demo:
        adapters.append(FileLoader(DATA_DIR / "sample_posts.json", platform="sample"))
    else:
        from worker.ingest.reddit import RedditAdapter
        from worker.ingest.stocktwits import StockTwitsAdapter
        from worker.ingest.bluesky import BlueskyAdapter
        from worker.ingest.hackernews import HackerNewsAdapter
        from worker.ingest.rss import RSSAdapter
        from worker.ingest.edgar import EdgarAdapter
        from worker.ingest.gdelt import GdeltAdapter
        from worker.ingest.mastodon import MastodonAdapter
        from worker.ingest.finnhub import FinnhubAdapter

        adapters += [RedditAdapter(), StockTwitsAdapter(), BlueskyAdapter(),
                     HackerNewsAdapter(), RSSAdapter(), EdgarAdapter(),
                     GdeltAdapter(), MastodonAdapter(), FinnhubAdapter()]

    posts: list[Post] = []
    used: list[str] = []
    for a in adapters:
        if not a.available():
            print(f"  [skip] {a.name} (not configured)")
            continue
        t0 = time.time()
        try:
            fetched = list(a.fetch())
        except Exception as exc:
            print(f"  [fail] {a.name}: {exc}")
            continue
        posts.extend(fetched)
        used.append(a.name)
        print(f"  [ok]   {a.name}: {len(fetched)} posts in {time.time() - t0:.1f}s")
    return dedupe(posts), used


def run(demo: bool, skip_topics: bool, skip_prices: bool, top_n: int, out_dir=None) -> None:
    t_start = time.time()
    live = settings.has_db and not demo
    mode = "live" if live else "demo"
    print(f"TickerPulse pipeline — {mode} mode")

    print("[1/6] ingest")
    new_posts, sources = collect_posts(demo=not live)
    if not new_posts and not live:
        print("No posts ingested — generate the sample set first: python -m worker.sample_gen")
        sys.exit(1)

    print("[2/6] nlp: ticker extraction")
    tag_posts(new_posts)

    print("[3/6] nlp: sentiment")
    backend = score_posts(new_posts)
    print(f"  backend: {backend}")

    conn = None
    if live:
        from worker.sinks import pgsink

        conn = pgsink._connect()
        pgsink.ensure_schema(conn)
        n = pgsink.upsert_posts(conn, new_posts)
        print(f"  upserted {n} posts")
        posts = pgsink.load_recent_posts(conn, hours=168)
        print(f"  computing over {len(posts)} posts from the trailing week")
    else:
        posts = new_posts

    print("[4/6] metrics: trends, mood, graph, alerts")
    trends = compute_ticker_trends(posts, window_hours=settings.window_hours)
    mood = market_mood(posts, window_hours=settings.window_hours)
    graph = compute_graph(posts)
    alerts = detect_alerts(trends)
    ranked = sorted(trends.values(), key=lambda m: -m["mentions"])[:top_n]
    top_tickers = [m["ticker"] for m in ranked]
    print(f"  {len(trends)} tickers above floor; mood {mood['index']} ({mood['label']}); "
          f"{len(alerts)} alerts")

    print("[5/6] market data + correlation + flag backtest")
    from worker.metrics.backtest import replay_flags, score_events, summarize, HORIZONS

    flag_events = replay_flags(posts, window_hours=settings.window_hours)
    event_tickers = {e["ticker"] for e in flag_events}
    price_tickers = list(dict.fromkeys([*top_tickers, *sorted(event_tickers)]))

    buckets = {t: bucket_series(posts, t, settings.bucket_minutes) for t in top_tickers}
    if skip_prices:
        prices = {t: synthetic_prices(t) for t in price_tickers}
    else:
        prices = fetch_prices(price_tickers, days=30, interval="1h")
    correlations = {t: compute_correlation(t, buckets[t], prices[t]) for t in top_tickers}

    score_events(flag_events, prices)
    flag_events.sort(key=lambda e: e["flagged_at"], reverse=True)
    backtest_payload = {
        "summary": summarize(flag_events),
        "events": flag_events[:60],
        "params": {"window_hours": settings.window_hours,
                   "breakout_floor": 1.5, "horizons": list(HORIZONS)},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"  {len(flag_events)} historical flags replayed")

    topics_payload = {"topics": [], "points": [], "backend": "skipped"}
    if not skip_topics:
        print("[6/6] topic clustering")
        from worker.nlp.topics import compute_topics

        topics_payload = compute_topics(posts)
        print(f"  {len(topics_payload['topics'])} topics over "
              f"{len(topics_payload['points'])} posts ({topics_payload['backend']})")

    updated_at = datetime.now(timezone.utc).isoformat()
    brief_md = generate_brief(trends, mood, topics_payload["topics"], alerts, mode)
    meta = {
        "mode": mode,
        "updated_at": updated_at,
        "posts_processed": len(posts),
        "sources": sources,
        "sentiment_backend": backend,
        "embed_backend": topics_payload["backend"],
        "window_hours": settings.window_hours,
        "refresh_minutes": 15 if live else None,
        "mood": mood,
    }

    trending_payload = {
        "updated_at": updated_at,
        "window_hours": settings.window_hours,
        "mood": mood,
        "tickers": sorted(trends.values(), key=lambda m: -m["mentions"]),
    }

    if live:
        from worker.sinks import pgsink

        db_trends = []
        for m in trends.values():
            db_trends.append({k: v for k, v in m.items() if k not in ("sector", "origin_platform")})
        pgsink.replace_table(conn, "ticker_trends",
                             db_trends, {"platforms", "top_posts", "sparkline"})
        pgsink.replace_table(conn, "topics", [
            {k: t[k] for k in ("id", "label", "terms", "size", "sentiment_avg")}
            | {"tickers": t["tickers"]} for t in topics_payload["topics"]
        ], {"terms", "tickers"})
        pgsink.replace_table(conn, "correlations", [
            {"ticker": c["ticker"], "pearson_r": c["pearson_r"],
             "best_lag_hours": c["best_lag_hours"], "best_lag_r": c["best_lag_r"],
             "readout": c["readout"], "series": c["series"]}
            for c in correlations.values()
        ], {"series"})
        pgsink.replace_table(conn, "alerts", [
            {k: a[k] for k in ("ticker", "kind", "message", "score", "created_at")}
            for a in alerts
        ], set())
        # Notify on fresh alerts before overwriting the previous snapshot.
        from worker.notify import send_discord_alerts

        prev = pgsink_load_meta(conn, "alerts") or {}
        sent = send_discord_alerts(alerts, prev.get("alerts", []))
        if sent:
            print(f"  discord: sent {sent} new alerts")

        pruned = pgsink.prune(conn, days=30)
        if any(pruned.values()):
            print(f"  pruned: {pruned}")

        pgsink.upsert_meta(conn, "meta", meta)
        pgsink.upsert_meta(conn, "trending", trending_payload)
        pgsink.upsert_meta(conn, "alerts", {"alerts": alerts, "updated_at": updated_at})
        pgsink.upsert_meta(conn, "backtest", backtest_payload)
        pgsink.upsert_meta(conn, "graph", graph)
        pgsink.upsert_meta(conn, "topics_map", topics_payload)
        pgsink.upsert_meta(conn, "brief", {"markdown": brief_md})
        for t in top_tickers:
            pgsink.upsert_meta(conn, f"ticker:{t}", {
                "trend": trends[t], "buckets": buckets[t][-168:],
                "prices": prices[t], "correlation": correlations[t],
            })
        conn.close()
        print(f"done (live) in {time.time() - t_start:.1f}s")
    else:
        from worker.sinks.jsonsink import write_artifacts

        payloads = {
            "meta": meta,
            "trending": trending_payload,
            "topics": topics_payload,
            "graph": graph,
            "alerts": {"alerts": alerts, "updated_at": updated_at},
            "brief": {"markdown": brief_md, "updated_at": updated_at},
            "backtest": backtest_payload,
        }
        for t in top_tickers:
            payloads[f"tickers/{t}"] = {
                "trend": trends[t],
                "buckets": buckets[t][-168:],
                "prices": prices[t],
                "correlation": correlations[t],
            }
        write_artifacts(payloads, out_dir)
        print(f"done (demo) in {time.time() - t_start:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true", help="force demo mode even with a DB configured")
    ap.add_argument("--skip-topics", action="store_true")
    ap.add_argument("--skip-prices", action="store_true", help="synthetic prices (offline)")
    ap.add_argument("--top-n", type=int, default=40)
    args = ap.parse_args()
    run(args.demo, args.skip_topics, args.skip_prices, args.top_n)


if __name__ == "__main__":
    main()
