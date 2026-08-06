"""Regressions for the defects the 2026-08-06 lint/type pass turned up.

Each test below exists because a checker found something real and the fix
changed code that nothing else covered. Grouped here rather than scattered so
the reason they exist stays legible.
"""

import datetime as dt

from worker.ingest.fileloader import _parse_ts
from worker.ingest.market import COINS, yahoo_symbol
from worker.ingest.mastodon import _status_ts
from worker.metrics.backtest import _parse_ts as _backtest_parse_ts
from worker.models import Post
from worker.nlp.tickers import load_dictionary

UTC = dt.UTC


class TestZSuffixTimestamps:
    """`datetime.fromisoformat(s.replace("Z", "+00:00"))` was removed in five
    parsers — redundant since 3.11, which parses the military "Z" natively.
    Every one of those parsers reads a live third-party feed that emits "Z",
    and none of them had a test. A silent regression here would not raise: it
    would produce naive datetimes and quietly corrupt every window boundary
    downstream, so assert tzinfo explicitly, not just that parsing succeeds.
    """

    def test_mastodon_status(self):
        got = _status_ts({"created_at": "2026-08-06T12:30:00.000Z"})
        assert got == dt.datetime(2026, 8, 6, 12, 30, tzinfo=UTC)
        assert got.tzinfo is not None

    def test_backtest_event_timestamp(self):
        got = _backtest_parse_ts("2026-08-06T12:30:00Z")
        assert got == dt.datetime(2026, 8, 6, 12, 30, tzinfo=UTC)

    def test_fileloader_iso_and_epoch(self):
        assert _parse_ts("2026-08-06T12:30:00Z") == dt.datetime(
            2026, 8, 6, 12, 30, tzinfo=UTC
        )
        # The epoch branch must keep working alongside it.
        assert _parse_ts(1785500000).tzinfo is not None

    def test_post_from_dict(self):
        post = Post.from_dict(
            {
                "id": "x:1",
                "platform": "sample",
                "source": "s",
                "author": "a",
                "text": "t",
                "timestamp": "2026-08-06T12:30:00Z",
            }
        )
        assert post.timestamp == dt.datetime(2026, 8, 6, 12, 30, tzinfo=UTC)

    def test_offset_form_still_parses(self):
        """Feeds that send +00:00 instead of Z must be unaffected."""
        assert _status_ts({"created_at": "2026-08-06T12:30:00+00:00"}) == dt.datetime(
            2026, 8, 6, 12, 30, tzinfo=UTC
        )


class TestYahooSymbol:
    """`yahoo_symbol` loaded the ticker dictionary and threw the result away
    (`tickers, _, _ = load_dictionary()`, never read). Removing the dead line
    is safe only because COINS — not the dictionary — is what actually decides
    the suffix, and nothing asserted that. It matters: the dictionary's
    "Crypto" sector covers crypto-adjacent EQUITIES too, and suffixing one of
    those yields a symbol Yahoo does not know, which `fetch_prices` swallows
    by falling back to a synthetic random walk. A real ticker would silently
    start charting invented prices.
    """

    def test_pure_coins_get_the_usd_pair(self):
        assert yahoo_symbol("BTC") == "BTC-USD"
        assert yahoo_symbol("ETH") == "ETH-USD"

    def test_crypto_sector_equities_are_left_alone(self):
        for equity in ("COIN", "MSTR", "MARA", "RIOT", "IBIT"):
            assert yahoo_symbol(equity) == equity, (
                f"{equity} is sector=Crypto in the dictionary but is an equity; "
                "suffixing it would silently fall back to synthetic prices"
            )

    def test_every_crypto_sector_symbol_is_classified_on_purpose(self):
        """The two lists must stay in sync: any NEW sector=Crypto symbol is
        either a coin (belongs in COINS) or an equity (must not be suffixed).
        Adding one to the dictionary alone is the failure mode this catches."""
        tickers, _, _ = load_dictionary()
        crypto = {s for s, i in tickers.items() if i.get("sector") == "Crypto"}
        assert COINS <= crypto, f"COINS not in the dictionary: {COINS - crypto}"
        equities = crypto - COINS
        assert equities == {"COIN", "MSTR", "MARA", "RIOT", "IBIT"}, (
            "sector=Crypto membership changed; classify the new symbol as a "
            f"coin (add to COINS) or an equity (extend this list): {equities}"
        )

    def test_dotted_symbols_still_map(self):
        assert yahoo_symbol("BRK.B") == "BRK-B"

    def test_already_suffixed_is_not_double_suffixed(self):
        assert yahoo_symbol("BTC-USD") == "BTC-USD"
