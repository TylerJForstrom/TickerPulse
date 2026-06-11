"""Postgres sink (Supabase / Neon free tier).

The worker is the only writer; the Netlify read-API only SELECTs. All
writes are idempotent upserts so cron re-runs and overlapping fetch
windows are harmless."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from worker.config import settings
from worker.models import Post


def _connect():
    import psycopg

    return psycopg.connect(settings.database_url, autocommit=False)


def ensure_schema(conn) -> None:
    from worker.config import ROOT

    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def upsert_posts(conn, posts: list[Post]) -> int:
    if not posts:
        return 0
    rows = [
        (p.id, p.platform, p.source, p.author, p.text, p.url, p.lang,
         p.engagement, p.sentiment, p.sentiment_score, p.tickers,
         p.topic_id, p.timestamp)
        for p in posts
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into posts (id, platform, source, author, text, url, lang,
                               engagement, sentiment, sentiment_score, tickers,
                               topic_id, created_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
              engagement = greatest(posts.engagement, excluded.engagement),
              sentiment = excluded.sentiment,
              sentiment_score = excluded.sentiment_score,
              tickers = excluded.tickers,
              topic_id = excluded.topic_id
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def load_recent_posts(conn, hours: int = 168) -> list[Post]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with conn.cursor() as cur:
        cur.execute(
            """select id, platform, source, author, text, url, lang, engagement,
                      sentiment, sentiment_score, tickers, topic_id, created_at
               from posts where created_at >= %s""",
            (since,),
        )
        out = []
        for r in cur.fetchall():
            out.append(Post(
                id=r[0], platform=r[1], source=r[2] or "", author=r[3] or "",
                text=r[4], url=r[5] or "", lang=r[6] or "en", engagement=r[7] or 0,
                sentiment=r[8], sentiment_score=r[9], tickers=list(r[10] or []),
                topic_id=r[11], timestamp=r[12],
            ))
        return out


def replace_table(conn, table: str, rows: list[dict], json_cols: set[str]) -> None:
    """Snapshot tables (trends, topics, graph…) are fully replaced each run."""
    with conn.cursor() as cur:
        cur.execute(f"delete from {table}")
        if rows:
            cols = list(rows[0].keys())
            placeholders = ", ".join(["%s"] * len(cols))
            cur.executemany(
                f"insert into {table} ({', '.join(cols)}) values ({placeholders})",
                [
                    tuple(json.dumps(r[c]) if c in json_cols else r[c] for c in cols)
                    for r in rows
                ],
            )
    conn.commit()


def upsert_meta(conn, key: str, value: object) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """insert into meta (key, value, updated_at) values (%s, %s, now())
               on conflict (key) do update set value = excluded.value, updated_at = now()""",
            (key, json.dumps(value)),
        )
    conn.commit()
