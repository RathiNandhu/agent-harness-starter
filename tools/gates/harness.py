#!/usr/bin/env python3
"""Shared vocabulary for every gate in this harness. No third-party dependencies, deliberately.

WHY NO DEPENDENCIES. A gate that cannot run is not a gate. The moment a check needs `pip install`
to work, it acquires a way to fail that has nothing to do with the property it checks — and the
failure looks identical to the property being broken. Everything here is Python standard library so
a gate's verdict never depends on an environment someone forgot to set up.

WHY FOUR EXIT CODES AND NOT TWO. This is the single most load-bearing idea in the harness, so it
lives in one place and every gate imports it.

    0  VERIFIED   the check ran, and the property holds
    1  VIOLATED   the check ran, and the property is broken
    2  CANNOT_RUN something the check needed was missing, so it reached no verdict
    3  INCOMPLETE the check ran, but part of what it should have covered was unreachable

Two and three exist because **"I checked and it is fine" and "I could not check the important part"
look identical from a green badge.** Collapse them into pass/fail and you eventually ship a control
that has never once executed while a dashboard reports it healthy. That is not a hypothetical: it is
the most common way a real quality gate dies.

The rule that follows from it, and the one to enforce in review:

    **2 AND 3 ARE NOT PASSES.** A caller that treats them as success has reintroduced the defect
    this vocabulary exists to remove.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

VERIFIED = 0
VIOLATED = 1
CANNOT_RUN = 2
INCOMPLETE = 3

# A caller wanting "did this pass" must ask explicitly, so the question is visible in the code rather
# than hidden in a truthiness check on the exit code.
PASSING = frozenset({VERIFIED})


def repo_root(start: Path | None = None) -> Path:
    """The repository root, found by walking up for a `.git` entry.

    Deliberately not `parents[2]` relative to the gate file: that hard-codes the gate's own depth, so
    moving a gate one directory silently changes what it scans, and the gate keeps passing while
    looking at the wrong tree.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    # No .git — a tarball, a container build, a vendored copy. Fall back rather than fail, but the
    # caller should treat a surprising root as a reason to check.
    return here.parents[2] if len(here.parents) >= 3 else here.parent


def scan_root(start: Path | None = None) -> Path:
    """The tree a gate should INSPECT, which is not always the tree it lives in.

    WHY THIS IS SEPARATE FROM `repo_root`. A gate answers two different questions with a path:
    "where is my own configuration" and "what code am I checking". Those are the same directory in
    the ordinary case — the kit is copied into the repo it guards — and `scan_root` then returns
    exactly `repo_root`, so a normal install behaves identically and needs no change.

    They are NOT the same when one checkout guards code it does not contain: a workspace that holds
    the harness once and references sibling repositories, rather than copying the gates into every
    one of them. Without this split, such a team either installs the kit everywhere or runs the
    gates against the workspace while the report reads as though it covered the services. The second
    is a could-not-run wearing a verdict's clothes, which is the failure this harness exists to
    remove.

    `HARNESS_SCAN_ROOT` names the tree to inspect — absolute, or relative to `repo_root()`. A value
    that does not resolve to a directory is a hard error and never a silent fallback: a typo that
    quietly reverted to scanning the gate's own repository would produce a clean report about code
    nobody looked at, which is worse than no report at all.
    """
    configured = os.environ.get("HARNESS_SCAN_ROOT", "").strip()
    if not configured:
        return repo_root(start)
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = repo_root(start) / candidate
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise SystemExit(
            "HARNESS_SCAN_ROOT=" + repr(configured) + " does not resolve to a directory "
            "(" + str(candidate) + ").\n"
            "Refusing to fall back to the gate's own repository: a gate that silently scans the\n"
            "wrong tree reports a verdict about code it never looked at."
        )
    return candidate


def report(
    name: str,
    code: int,
    verified: list[str] | None = None,
    violations: list[str] | None = None,
    unproven: list[str] | None = None,
    note: str | None = None,
) -> int:
    """Print a verdict in the one shape every gate in this harness uses, and return the exit code.

    Consistency here is not tidiness. When ten gates report ten ways, readers stop reading them and
    start reading only the colour — at which point the text of a finding, which is the part that
    tells you what to do, is wasted effort.

    Findings go to stderr and successes to stdout, so a CI log filtered to stderr shows exactly the
    lines someone has to act on.
    """
    label = {
        VERIFIED: "VERIFIED",
        VIOLATED: "VIOLATED",
        CANNOT_RUN: "CANNOT RUN",
        INCOMPLETE: "INCOMPLETE",
    }.get(code, f"UNKNOWN({code})")

    stream = sys.stdout if code == VERIFIED else sys.stderr
    print(f"{name}: {label}", file=stream)

    if verified:
        for line in verified:
            print(f"  verified: {line}", file=stream)
    if violations:
        print("", file=stream)
        for line in violations:
            print(f"  - {line}", file=stream)
    if unproven:
        print("\n  UNPROVEN — this is NOT a pass:", file=stream)
        for line in unproven:
            print(f"  - {line}", file=stream)
    if note:
        print(f"\nnote: {note}", file=stream)

    if code == CANNOT_RUN:
        print(
            "\nRefusing to report a pass for a check that did not run. Install what is missing and "
            "re-run — do not record this as green.",
            file=stream,
        )
    return code
