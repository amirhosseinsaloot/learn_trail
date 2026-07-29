"""`python -m evals` — the command `make evals` runs.

Three subcommands, and the split is the phase's design in miniature:

    gate    is the configuration covered by a recorded run?   free, offline
    run     score the golden set and record it                costs money
    sync    register the dataset cases in the database        needs Postgres

Only `run` spends. The gate has to be answerable on every push, which is why it
is a separate, dependency-light path.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable

from evals.datasets import SUITES, SuiteName
from evals.gate import gate_status, record_run, requires_evaluation

#: Shown in the CLI's output; the module owns the real path.
REPORT_RELATIVE = "packages/evals/reports/optimization.json"


def _gate(args: argparse.Namespace) -> int:
    changed = [line for line in (args.changed or "").splitlines() if line.strip()]
    if changed:
        triggering = requires_evaluation(changed)
        if not triggering:
            print("no prompt or model files changed — evaluation not required")
            return 0
        print(f"prompt/model files changed: {', '.join(triggering)}")

    status = gate_status()
    if status.satisfied:
        print(f"evaluation gate satisfied — {status.detail}")
        return 0

    print(f"evaluation gate NOT satisfied — {status.detail}", file=sys.stderr)
    print(f"  configuration now: {status.current_fingerprint[:16]}", file=sys.stderr)
    print(f"  last evaluated:    {(status.recorded_fingerprint or 'never')[:16]}", file=sys.stderr)
    return 1


def _run(args: argparse.Namespace) -> int:
    # Imported here, not at module scope: `gate` must work without DeepEval or a
    # reachable gateway, and importing the runner pulls in both.
    from evals.runner import run_sync

    suites: list[SuiteName] = list(args.suite) if args.suite else list(SUITES)
    report = run_sync(suites)

    for result in report.results:
        mark = "PASS" if result.passed else "FAIL"
        score = f" {result.score:.2f}" if result.score is not None else ""
        print(f"[{mark}] {result.metric:<26} {result.case_id}{score}")
        if not result.passed:
            print(f"       {result.explanation}")

    summary = report.summary()
    print(f"\n{summary['total']} results, {summary['failed']} failed")

    # Recorded only on a pass, and only for a full run. A partial run that
    # satisfied the gate would let someone clear it by evaluating the one suite
    # their change did not affect.
    if set(suites) == set(SUITES):
        record_run(passed=report.passed, summary=summary)
        if report.passed:
            print("recorded in packages/evals/reports/last_run.json")
    else:
        print("partial run — the gate manifest was not updated")

    return 0 if report.passed else 1


def _sync(args: argparse.Namespace) -> int:
    from database.session import session_factory
    from evals.store import sync_cases

    async def go() -> int:
        async with session_factory()() as db:
            cases = await sync_cases(db)
            return len(cases)

    print(f"registered {asyncio.run(go())} evaluation cases")
    return 0


def _redteam(args: argparse.Namespace) -> int:
    """Measure the safety posture, and say whether it moved."""
    from evals.red_team import compare, load_baseline, measure, save_baseline

    baseline = load_baseline()
    posture = asyncio.run(measure())
    print(
        f"attacks {posture.attacks_succeeded}/{posture.attacks} succeeded "
        f"(ASR {posture.attack_success_rate:.0%})"
    )
    print(
        f"controls {posture.controls_refused}/{posture.controls} refused "
        f"(FRR {posture.false_refusal_rate:.0%})"
    )
    for category, counts in sorted(posture.by_category.items()):
        print(f"  {category:<28} {counts['succeeded']}/{counts['attacks']} got through")
    if posture.failures:
        print(f"failing cases: {', '.join(posture.failures)}")

    if baseline is None:
        save_baseline(posture)
        print("\nno previous baseline — recorded this run as the first one")
        return 0

    result = compare(baseline, posture)
    print(f"\nverdict: {result.verdict.value.upper()} — {result.detail}")
    for category, delta in sorted(result.category_deltas.items()):
        print(f"  {category:<28} attack success {delta:+.0%}")

    if args.action == "accept":
        save_baseline(posture)
        print("recorded as the new baseline")
        return 0

    # `harmed` fails; `mixed` fails too. A trade needs a human to say it was the
    # one they meant, which is what `accept` is for — silently passing it would
    # let a change that broke ordinary use merge on a green tick.
    return 0 if result.verdict in ("improved", "unchanged") else 1


def _redteam_gate(args: argparse.Namespace) -> int:
    """Free, offline: does the recorded baseline describe the current safety config?

    The CI half of Phase 7. It never measures — measuring costs a model call per
    case and CI holds no provider credential — it checks that whoever changed the
    safety configuration also measured it and accepted the result.
    """
    from evals.red_team import load_baseline, requires_measurement, safety_fingerprint

    changed = [line for line in (args.changed or "").splitlines() if line.strip()]
    if changed and not requires_measurement(changed):
        print("no safety files changed — a red-team measurement is not required")
        return 0
    if changed:
        print(f"safety files changed: {', '.join(requires_measurement(changed))}")

    baseline = load_baseline()
    if baseline is None:
        print("no red-team baseline has ever been recorded", file=sys.stderr)
        return 1

    current = safety_fingerprint()
    if baseline.safety_fingerprint == current:
        print(
            f"safety baseline is current — ASR {baseline.attack_success_rate:.0%}, "
            f"FRR {baseline.false_refusal_rate:.0%}, measured {baseline.measured_at}"
        )
        return 0

    print(
        "the safety configuration has changed since the baseline was measured "
        f"({baseline.measured_at}). Run `make redteam`.",
        file=sys.stderr,
    )
    print(f"  safety config now: {current[:16]}", file=sys.stderr)
    print(f"  baseline measured: {(baseline.safety_fingerprint or 'never')[:16]}", file=sys.stderr)
    return 1


def _retrieval(args: argparse.Namespace) -> int:
    """Score retrieval itself: precision, recall, faithfulness (Phase 8).

    Needs the database (there must be a library to retrieve from) and the
    gateway (embeddings, and a judge per metric). Separate from `run` because it
    measures a different thing and fails for different reasons — a low recall
    here is a search problem, not a prompt problem.
    """
    from evals.retrieval_runner import run_retrieval

    scores = asyncio.run(run_retrieval())
    if not scores:
        print("no retrieval cases, or no approved Learnings to retrieve from")
        return 0

    for score in scores:
        mark = "PASS" if score.passed else "FAIL"
        metrics = " ".join(
            f"{name.split('_')[-1]}={value:.2f}" for name, value in sorted(score.metrics.items())
        )
        print(f"[{mark}] {score.case_id:<32} {metrics}")
        for failure in score.failures:
            print(f"       {failure}")

    failed = sum(1 for score in scores if not score.passed)
    print(f"\n{len(scores)} cases, {failed} failed")
    return 0 if failed == 0 else 1


def _optimize(args: argparse.Namespace) -> int:
    """Optimize the summary instruction and compare on held-out data (Phase 9)."""
    from evals.optimize import load_cases, save_report, split
    from evals.optimize_runner import run_optimization

    train, held_out = split()
    print(f"{len(load_cases())} cases -> {len(train)} train, {len(held_out)} held out")
    print("the optimizer sees the train set only\n")

    result = run_optimization()
    print(f"baseline   train {result.baseline_train:.2f}   held-out {result.baseline_held_out:.2f}")
    print(
        f"candidate  train {result.candidate_train:.2f}   held-out {result.candidate_held_out:.2f}"
    )
    print(f"\nheld-out delta {result.held_out_delta:+.2f}   verdict: {result.verdict().upper()}")
    if result.overfitted:
        print("  gained on its own set and not on unseen data — that is overfitting,")
        print("  and it is exactly what the exit criterion is asking you to notice")

    save_report(result, cases=len(train) + len(held_out), train=len(train), held_out=len(held_out))
    print(f"\nrecorded in {REPORT_RELATIVE}")
    print("NOT promoted: writing a prompt version is a human act (plans/phase-9.md)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    gate = subcommands.add_parser("gate", help="check whether a run is required and recorded")
    gate.add_argument(
        "--changed",
        help="newline-separated changed paths (e.g. from `git diff --name-only`)",
    )
    gate.set_defaults(handler=_gate)

    run = subcommands.add_parser("run", help="score the golden datasets (calls models)")
    run.add_argument("--suite", action="append", choices=SUITES, help="limit to one suite")
    run.set_defaults(handler=_run)

    sync = subcommands.add_parser("sync", help="register dataset cases in the database")
    sync.set_defaults(handler=_sync)

    redteam = subcommands.add_parser(
        "redteam", help="measure the safety posture against the adversarial set (calls models)"
    )
    redteam.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=["run", "accept"],
        help="`run` compares against the baseline; `accept` promotes this run to be it",
    )
    redteam.set_defaults(handler=_redteam)

    redteam_gate = subcommands.add_parser(
        "redteam-gate", help="check the recorded baseline covers the current safety config"
    )
    redteam_gate.add_argument("--changed", help="newline-separated changed paths")
    redteam_gate.set_defaults(handler=_redteam_gate)

    retrieval = subcommands.add_parser(
        "retrieval", help="score retrieval precision, recall and faithfulness (calls models)"
    )
    retrieval.set_defaults(handler=_retrieval)

    optimize = subcommands.add_parser(
        "optimize", help="optimize the summary instruction, compare on held-out (calls models)"
    )
    optimize.set_defaults(handler=_optimize)

    args = parser.parse_args(argv)
    # `required=True` on the subparsers guarantees a handler is set, so this is a
    # cast rather than a check — an `assert` here would be stripped under -O and
    # Ruff's S101 is right to object to one in shipped code.
    handler: Callable[[argparse.Namespace], int] = args.handler
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
