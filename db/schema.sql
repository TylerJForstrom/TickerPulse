-- TickerPulse Postgres schema (Supabase / Neon free tier)
-- Normalized social posts + precomputed per-ticker / per-topic time-series.
-- The worker writes, the Netlify read-API only ever SELECTs.

create table if not exists posts (
  id              text primary key,          -- "<platform>:<native id>"
  platform        text not null,             -- reddit | stocktwits | bluesky | hackernews | rss | sample
  source          text,                      -- subreddit, feed name, etc.
  author          text,
  text            text not null,
  url             text,
  lang            text default 'en',
  engagement      integer default 0,         -- upvotes + likes + reposts (platform-weighted)
  sentiment       text,                      -- bull | bear | neutral
  sentiment_score real,                      -- -1 (bear) .. +1 (bull)
  tickers         text[] default '{}',
  topic_id        integer,
  created_at      timestamptz not null,
  ingested_at     timestamptz default now()
);
create index if not exists posts_created_idx on posts (created_at desc);
create index if not exists posts_tickers_idx on posts using gin (tickers);

-- Per-ticker time buckets: the workhorse time-series behind every chart.
create table if not exists ticker_buckets (
  ticker         text not null,
  bucket_start   timestamptz not null,
  bucket_minutes integer not null default 60,
  mentions       integer default 0,
  engagement     integer default 0,
  bull           integer default 0,
  bear           integer default 0,
  neutral        integer default 0,
  sentiment_avg  real,
  platforms      jsonb default '{}',         -- {"reddit": 12, "stocktwits": 30}
  primary key (ticker, bucket_start, bucket_minutes)
);
create index if not exists buckets_start_idx on ticker_buckets (bucket_start desc);

-- Snapshot of trending metrics per ticker — what the leaderboard reads.
create table if not exists ticker_trends (
  ticker                    text primary key,
  name                      text,
  window_hours              integer,
  mentions                  integer,
  mentions_prev             integer,          -- previous window, for rising/falling
  velocity                  real,             -- mentions/hour growth rate
  breakout_score            real,             -- spike z-score vs trailing baseline
  phase                     text,             -- emerging | peaking | fading | steady
  share_of_voice            real,
  sentiment_avg             real,
  bull                      integer,
  bear                      integer,
  neutral                   integer,
  bull_bear_ratio           real,
  engagement                integer,
  engagement_weighted_score real,
  platforms                 jsonb,
  top_posts                 jsonb,            -- [{id,text,author,platform,engagement,url,sentiment}]
  sparkline                 jsonb,            -- recent hourly mention counts
  updated_at                timestamptz default now()
);

-- Topic clusters from embeddings → UMAP → HDBSCAN → c-TF-IDF.
create table if not exists topics (
  id            integer primary key,
  label         text,
  terms         jsonb,                        -- top c-TF-IDF terms
  size          integer,
  sentiment_avg real,
  velocity      real,
  tickers       jsonb,                        -- top associated tickers
  updated_at    timestamptz default now()
);

-- 2-D landscape coordinates per post (the topic map scatter).
create table if not exists topic_points (
  post_id  text primary key references posts (id) on delete cascade,
  topic_id integer,
  x        real,
  y        real
);

-- Real OHLCV market data per tracked ticker (yfinance / Finnhub).
create table if not exists prices (
  ticker text not null,
  ts     timestamptz not null,
  open   real, high real, low real, close real,
  volume bigint,
  primary key (ticker, ts)
);

-- Social-buzz vs price-move correlation readouts (flagship feature).
create table if not exists correlations (
  ticker        text primary key,
  pearson_r     real,                         -- mentions vs |return|, aligned
  best_lag_hours integer,                     -- buzz leads price (+) or lags (-)
  best_lag_r    real,
  readout       text,                         -- human "buzz vs move" summary
  series        jsonb,                        -- aligned {ts, mentions, sentiment, close, volume}
  updated_at    timestamptz default now()
);

-- Unusual-activity alerts (abnormal mention spikes etc.)
create table if not exists alerts (
  id         bigserial primary key,
  ticker     text,
  kind       text,                            -- mention_spike | sentiment_flip | new_entrant
  message    text,
  score      real,
  created_at timestamptz default now()
);
create index if not exists alerts_created_idx on alerts (created_at desc);

-- Pipeline metadata: market mood, last refresh, run stats.
create table if not exists meta (
  key        text primary key,
  value      jsonb,
  updated_at timestamptz default now()
);
