"""Every requirements file must be parseable by pip, not just the one CI installs.

CI installs requirements.txt only; requirements-ml.txt is installed exclusively by
the pipeline workflow in live mode (needs the DATABASE_URL secret). That gap let a
Dependabot PR propose `torch>=2.13.0+cpu` — invalid under PEP 440, because a local
version label may only be paired with `==` or `!=`. pip rejects the ENTIRE file on
a single bad specifier, so every package in it fails to install, not just torch,
and nothing in CI noticed.

This is a parse check, deliberately: it is offline, instant, and never downloads a
multi-hundred-megabyte torch wheel. It catches malformed specifiers, not
unsatisfiable ones — a floor pinned to a version that does not exist would still
slip through here and only surface at install time.
"""

import pathlib

import pytest
from packaging.requirements import InvalidRequirement, Requirement

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Files pip is pointed at somewhere in the repo (CI, the pipeline workflow, README).
# Keep this assertion honest: if a new requirements file is added, discovery picks it
# up automatically and test_expected_files_discovered fails only if one goes missing.
EXPECTED = {"requirements.txt", "requirements-ml.txt", "requirements-dev.txt"}


def requirements_files():
    return sorted(REPO_ROOT.glob("requirements*.txt"))


def logical_lines(text):
    """Yield (line_number, content) after pip's comment/continuation handling."""
    buffered = ""
    start = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(" #", 1)[0].rstrip() if " #" in raw else raw.rstrip()
        if not buffered:
            start = lineno
        if line.endswith("\\"):
            buffered += line[:-1]
            continue
        joined = (buffered + line).strip()
        buffered = ""
        if not joined or joined.startswith("#"):
            continue
        yield start, joined


def test_expected_files_discovered():
    """Guard against the check silently passing because it found nothing."""
    found = {path.name for path in requirements_files()}
    assert EXPECTED <= found, f"expected requirements files missing: {EXPECTED - found}"


@pytest.mark.parametrize("path", requirements_files(), ids=lambda p: p.name)
def test_every_requirement_is_valid_pep440(path):
    failures = []
    checked = 0
    for lineno, line in logical_lines(path.read_text(encoding="utf-8")):
        if line.startswith("-"):
            continue  # pip option line, e.g. --extra-index-url / -r / -c
        checked += 1
        try:
            Requirement(line)
        except InvalidRequirement as exc:
            failures.append(f"  {path.name}:{lineno}: {line!r}\n    {exc}")

    assert checked, f"{path.name} declares no requirements — did discovery break?"
    assert not failures, (
        f"pip cannot parse {path.name}; it will refuse to install ANY package "
        f"listed in it, not only the offending one:\n" + "\n".join(failures)
    )
