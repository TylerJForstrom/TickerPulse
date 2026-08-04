"""Gap-tolerant pagination: drain_pages + the three paginating adapters.

GitHub's shared cron scheduler drops most of the pipeline's 15-min ticks
(measured 10-16 runs/day, gaps up to ~3h35m), so listing-based adapters walk
pages back through settings.ingest_lookback_hours instead of trusting one
fixed-depth page. These tests pin the stop conditions — horizon covered,
source exhausted, saturation budget cap — and the deterministic bluesky id."""

import datetime as dt

import worker.ingest.bluesky as bluesky_mod
import worker.ingest.mastodon as mastodon_mod
import worker.ingest.reddit as reddit_mod
from worker.config import settings
from worker.ingest.base import drain_pages
from worker.ingest.bluesky import BlueskyAdapter
from worker.ingest.mastodon import MastodonAdapter
from worker.ingest.reddit import RedditAdapter
from worker.models import Post


def _ago(hours: float) -> dt.datetime:
    return dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)


def post(pid: str, age_hours: float) -> Post:
    return Post(id=pid, platform="x", text="t", author="a", timestamp=_ago(age_hours))


class PageFeed:
    """Lazy page source that records how many pages were actually pulled."""

    def __init__(self, pages):
        self._pages = pages
        self.pulled = 0

    def __iter__(self):
        for page in self._pages:
            self.pulled += 1
            yield page


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


# --- drain_pages ------------------------------------------------------------

def test_drain_stops_once_horizon_is_covered(capsys):
    feed = PageFeed([[post("a", 1)], [post("b", 7)], [post("never", 9)]])
    items = drain_pages(iter(feed), lookback_hours=6, max_pages=10, label="x")
    assert [p.id for p in items] == ["a", "b"]
    assert feed.pulled == 2  # third page never fetched
    assert "[saturation]" not in capsys.readouterr().out


def test_drain_exhaustion_is_not_saturation(capsys):
    feed = PageFeed([[post("a", 1)], [post("b", 2)]])
    items = drain_pages(iter(feed), lookback_hours=6, max_pages=10, label="x")
    assert len(items) == 2
    assert "[saturation]" not in capsys.readouterr().out


def test_drain_empty_page_stops_without_saturation(capsys):
    feed = PageFeed([[post("a", 1)], []])
    items = drain_pages(iter(feed), lookback_hours=6, max_pages=10, label="x")
    assert [p.id for p in items] == ["a"]
    assert feed.pulled == 2
    assert "[saturation]" not in capsys.readouterr().out


def test_drain_saturation_at_page_cap(capsys):
    feed = PageFeed([[post("a", 1)], [post("b", 2)], [post("c", 3)]])
    items = drain_pages(iter(feed), lookback_hours=6, max_pages=2, label="deep-listing")
    assert [p.id for p in items] == ["a", "b"]
    assert feed.pulled == 2
    out = capsys.readouterr().out
    assert "[saturation]" in out and "deep-listing" in out


def test_drain_custom_timestamp_key():
    pages = iter([[{"t": _ago(1)}], [{"t": _ago(7)}], [{"t": _ago(9)}]])
    items = drain_pages(pages, lookback_hours=6, max_pages=10, label="x",
                        ts=lambda item: item["t"])
    assert len(items) == 2


# --- reddit -----------------------------------------------------------------

def test_reddit_new_paginates_until_horizon(monkeypatch):
    monkeypatch.setattr(settings, "reddit_subreddits", ["stocks"])
    monkeypatch.setattr(settings, "ingest_lookback_hours", 6)
    monkeypatch.setattr(RedditAdapter, "_token", lambda self: "tok")

    def child(cid, age_hours):
        return {"data": {"id": cid, "title": f"post {cid}", "selftext": "",
                         "author": "u", "created_utc": _ago(age_hours).timestamp(),
                         "score": 1, "num_comments": 0,
                         "permalink": f"/r/stocks/{cid}"}}

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        params = params or {}
        calls.append((url, dict(params)))
        if url.endswith("/new"):
            if "after" not in params:
                return FakeResp({"data": {"children": [child("n1", 1)], "after": "t3_n1"}})
            assert params["after"] == "t3_n1"
            # oldest item beyond the 6h horizon -> pagination must stop here
            return FakeResp({"data": {"children": [child("n2", 7)], "after": "t3_n2"}})
        return FakeResp({"data": {"children": [child("h1", 3)], "after": None}})

    monkeypatch.setattr(reddit_mod.requests, "get", fake_get)
    ids = [p.id for p in RedditAdapter().fetch()]
    assert ids == ["reddit:n1", "reddit:n2", "reddit:h1"]
    new_calls = [c for c in calls if c[0].endswith("/new")]
    assert len(new_calls) == 2  # t3_n2 page never requested


# --- bluesky ----------------------------------------------------------------

def test_bluesky_paginates_dedupes_and_ids_are_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "ingest_lookback_hours", 6)
    monkeypatch.setattr(BlueskyAdapter, "_session", lambda self: {"accessJwt": "j"})
    monkeypatch.setattr(bluesky_mod, "QUERIES", ["stock market"])

    def item(rkey, age_hours):
        created = _ago(age_hours).isoformat()
        return {"uri": f"at://did:plc:abc/app.bsky.feed.post/{rkey}",
                "record": {"text": "hi", "createdAt": created, "langs": ["en"]},
                "author": {"handle": "u.bsky.social"},
                "likeCount": 0, "repostCount": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        params = params or {}
        if "cursor" not in params:
            return FakeResp({"posts": [item("aaa", 1)], "cursor": "c1"})
        assert params["cursor"] == "c1"
        # crosses the horizon; also repeats aaa, which must dedupe
        return FakeResp({"posts": [item("bbb", 7), item("aaa", 1)]})

    monkeypatch.setattr(bluesky_mod.requests, "get", fake_get)
    first = [p.id for p in BlueskyAdapter().fetch()]
    second = [p.id for p in BlueskyAdapter().fetch()]
    assert first == ["bluesky:aaa:" + first[0].rsplit(":", 1)[-1],
                     "bluesky:bbb:" + first[1].rsplit(":", 1)[-1]]
    # sha1-derived: stable across runs (builtin hash() is salted per process,
    # which made every run mint fresh ids and pile up duplicate DB rows)
    assert first == second
    assert len(set(first)) == 2


# --- mastodon ---------------------------------------------------------------

def test_mastodon_pages_past_filtered_content(monkeypatch):
    monkeypatch.setattr(settings, "ingest_lookback_hours", 6)
    monkeypatch.setattr(mastodon_mod, "TAGS", ["stocks"])
    monkeypatch.setattr(mastodon_mod, "PAGE_LIMIT", 2)

    def status(sid, age_hours, lang):
        return {"id": sid, "content": "<p>market talk long enough to keep</p>",
                "created_at": _ago(age_hours).isoformat(),
                "language": lang, "account": {"acct": "someone"}, "url": "u",
                "favourites_count": 0, "reblogs_count": 0}

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        params = params or {}
        calls.append(dict(params))
        if "max_id" not in params:
            # full page, all fresh, all non-English: everything is filtered
            # from output, but the page still proves its hours were walked,
            # so pagination must continue rather than stop
            return FakeResp([status("200", 1, "de"), status("199", 1, "fr")])
        assert params["max_id"] == "199"
        return FakeResp([status("150", 7, "en")])  # short page + past horizon

    monkeypatch.setattr(mastodon_mod.requests, "get", fake_get)
    posts = list(MastodonAdapter().fetch())
    assert [p.id for p in posts] == ["mastodon:150"]
    assert len(calls) == 2
