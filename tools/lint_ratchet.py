"""Ratchet for lint rules that are not yet hard gates.

The gates (`ruff format --check`, `ruff check`, `mypy`) are all at zero and
blocking. One rule is deliberately not among them: BLE001, `except Exception`.
See the note in pyproject.toml — all 16 occurrences are the same intentional
degrade-gracefully boundary, and narrowing them would be a behavior change,
not a lint fix.

"Not a gate" must not mean "unwatched", which is how a permanently-red
advisory step becomes noise nobody reads. This script re-selects the excluded
rules and enforces a ceiling:

  * count > baseline  -> fail. New debt cannot be added.
  * count < baseline  -> fail, with the new number to write down. The ceiling
                         only ever moves down, and it moves deliberately.
  * count == baseline -> pass.

Usage:
    python -m tools.lint_ratchet          # check against the baseline
    python -m tools.lint_ratchet --update # rewrite the baseline (review it)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tools" / "lint_baseline.json"

# Rules excluded from the `ruff check` gate in pyproject.toml. Every entry here
# MUST also be in that file's `lint.ignore`, or the gate already covers it and
# the ratchet is dead weight — test_lint_ratchet.py asserts the two agree.
RATCHETED_RULES = ["BLE001"]


def count_findings(rule: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            rule,
            "--output-format",
            "json",
            ".",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,  # ruff exits 1 on findings; that is the normal path
    )
    # ruff exits 1 when it finds something; only a hard failure has no JSON.
    try:
        return len(json.loads(proc.stdout))
    except json.JSONDecodeError:
        raise SystemExit(
            f"ruff did not return JSON for {rule} (exit {proc.returncode}):\n"
            f"{proc.stderr}"
        ) from None


def load_baseline() -> dict[str, int]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["counts"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()

    counts = {rule: count_findings(rule) for rule in RATCHETED_RULES}

    if args.update:
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Ceiling for lint rules excluded from the ruff check gate; "
                        "see tools/lint_ratchet.py. Only ever edit this DOWN, and "
                        "only via --update after actually removing findings."
                    ),
                    "counts": counts,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {counts}")
        return 0

    baseline = load_baseline()
    failed = False
    for rule, count in counts.items():
        ceiling = baseline.get(rule)
        if ceiling is None:
            print(f"FAIL {rule}: ratcheted but absent from the baseline file")
            failed = True
        elif count > ceiling:
            print(
                f"FAIL {rule}: {count} findings, ceiling is {ceiling}. "
                f"{count - ceiling} new one(s) — fix them, or make the case for "
                f"raising the ceiling explicitly."
            )
            failed = True
        elif count < ceiling:
            print(
                f"FAIL {rule}: {count} findings, ceiling is still {ceiling}. "
                f"Debt went DOWN — lower the ceiling so it cannot come back: "
                f"python -m tools.lint_ratchet --update"
            )
            failed = True
        else:
            print(f"ok   {rule}: {count} findings, at the {ceiling} ceiling")

    for rule in baseline:
        if rule not in counts:
            print(f"FAIL {rule}: in the baseline but no longer ratcheted — remove it")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
