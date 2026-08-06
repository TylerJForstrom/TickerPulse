"""The ratchet has to be trustworthy to be worth having.

Two ways it could rot silently:
  * a rule gets ratcheted but never actually excluded from the `ruff check`
    gate (or vice versa), so one of the two mechanisms is dead weight;
  * the baseline file drifts out of the shape the script expects and the CI
    step starts erroring instead of ratcheting.
"""

import json
import pathlib
import tomllib

from tools.lint_ratchet import BASELINE_PATH, RATCHETED_RULES

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def ruff_ignored_rules() -> list[str]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["ruff"]["lint"]["ignore"]


def test_ratcheted_rules_match_the_gate_exclusions():
    """Every ratcheted rule must be excluded from the gate, and every gate
    exclusion must be ratcheted. Otherwise a rule is either double-counted or,
    worse, quietly ignored by both."""
    assert sorted(RATCHETED_RULES) == sorted(ruff_ignored_rules()), (
        "pyproject.toml lint.ignore and tools/lint_ratchet.RATCHETED_RULES "
        "disagree — a rule is either gated twice or not watched at all"
    )


def test_baseline_covers_every_ratcheted_rule():
    counts = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["counts"]
    assert sorted(counts) == sorted(RATCHETED_RULES)
    for rule, count in counts.items():
        assert isinstance(count, int) and count >= 0, f"{rule}: {count!r}"


def test_baseline_is_not_a_blank_cheque():
    """A ceiling large enough to never bind is the same as no ceiling. The
    recorded count is the real one at the time of writing; if it is ever
    edited upward without removing this guard, that should be visible."""
    counts = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["counts"]
    assert counts["BLE001"] <= 16, (
        "the BLE001 ceiling was raised above the 2026-08-06 baseline of 16; "
        "the ratchet is supposed to move down only"
    )
