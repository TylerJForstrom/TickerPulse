"""Ticker extraction: cashtags, dictionary, aliases, junk disambiguation."""

from worker.models import Post
from worker.nlp.tickers import extract_tickers, tag_posts
from datetime import datetime, timezone


def test_cashtag_basic():
    assert extract_tickers("$AAPL to the moon") == ["AAPL"]


def test_cashtag_case_insensitive():
    assert extract_tickers("loading up on $nvda calls") == ["NVDA"]


def test_dollar_amounts_not_tickers():
    assert extract_tickers("$5 says it drops, $100 price target") == []


def test_blocklisted_cashtags_ignored():
    assert extract_tickers("$YOLO $FOMO $DD this is the way") == []


def test_unknown_plausible_cashtag_counts():
    assert extract_tickers("tiny small cap $ZAPP about to run") == ["ZAPP"]


def test_bare_uppercase_dictionary_symbol():
    assert extract_tickers("NVDA earnings after the close") == ["NVDA"]


def test_bare_lowercase_symbol_ignored():
    assert extract_tickers("nvda is fine") == []  # bare form must be uppercase


def test_ambiguous_word_tickers_need_cashtag():
    # NOW (ServiceNow), ARM, NET are English words — bare form is ignored…
    assert extract_tickers("NOW is the time to ACT, ALL in") == []
    # …but the cashtag form always counts.
    assert extract_tickers("$NOW and $ARM both reported") == ["NOW", "ARM"]


def test_single_letter_only_via_cashtag():
    assert extract_tickers("F it, we ball") == []
    assert extract_tickers("$F is a value trap") == ["F"]


def test_company_name_aliases():
    assert extract_tickers("Nvidia is eating the datacenter world") == ["NVDA"]
    assert extract_tickers("palo alto networks beat estimates") == ["PANW"]


def test_alias_does_not_fire_on_substring():
    # "arm" inside other words must not trigger ARM.
    assert "ARM" not in extract_tickers("the farmland harmed nobody")


def test_multiple_tickers_dedup_and_order():
    out = extract_tickers("Comparing NVDA vs $AMD and Intel, NVDA still wins")
    assert out[0] in ("NVDA", "AMD")  # cashtags scanned first within rules
    assert set(out) == {"NVDA", "AMD", "INTC"}


def test_brk_dot_b_cashtag():
    assert extract_tickers("$BRK.B is the sleep-well stock") == ["BRK.B"]


def test_tag_posts_merges_pretagged():
    p = Post(id="x:1", platform="stocktwits", text="earnings beat across the board",
             author="a", timestamp=datetime.now(timezone.utc), tickers=["TSLA"])
    tag_posts([p])
    assert p.tickers == ["TSLA"]  # pre-tagged survives, nothing bogus added
