"""Conflict and overlap reports from the code graph (R-41).

Branch mode (default): this branch's changed and affected node set is
intersected with every other `origin/ticket/*` branch and written to
graphify-out/conflicts.md. Planning mode (--paths-a and --paths-b): community
overlap between two ownership boundaries, written to graphify-out/overlap.md.
Reads only graphify-out/graph.json and git.

Exit codes: 0 report written, 1 graph missing or unhealthy.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import graph_impact as gi

DEFAULT_CONFLICTS_OUT = Path("graphify-out/conflicts.md")
DEFAULT_OVERLAP_OUT = Path("graphify-out/overlap.md")
TICKET_REFS = "refs/remotes/origin/ticket/"
HANDFUL = 5


@dataclass
class BranchOverlap:
    branch: str
    files: list[str]
    nodes: list[str]


def other_ticket_branches(repo: Path, current_branch: str, refs_prefix: str) -> list[str]:
    listing = gi.git(repo, "for-each-ref", "--format=%(refname:short)", refs_prefix)
    own = f"origin/{current_branch}"
    return [name for name in listing.splitlines() if name and name != own]


def branch_overlaps(
    repo: Path,
    graph: gi.Graph,
    ours: gi.Impact,
    baseline: gi.Baseline,
    refs_prefix: str,
    depth: int,
) -> list[BranchOverlap]:
    our_files = set(ours.changed_files)
    our_nodes = ours.touched()
    overlaps: list[BranchOverlap] = []
    for branch in other_ticket_branches(repo, baseline.branch, refs_prefix):
        merge_base = gi.git(repo, "merge-base", baseline.base_head, branch)
        their_files = gi.changed_files_since(repo, merge_base, branch)
        their_changed = gi.changed_node_ids(graph, set(their_files))
        their_affected = gi.affected_node_ids(graph, their_changed, set(their_files), depth)
        their_nodes = set(their_changed) | set(their_affected)
        overlaps.append(
            BranchOverlap(
                branch=branch,
                files=sorted(our_files & set(their_files)),
                nodes=sorted(our_nodes & their_nodes),
            )
        )
    return overlaps


def render_conflicts(graph: gi.Graph, overlaps: list[BranchOverlap]) -> list[str]:
    if not overlaps:
        return ["No other ticket branches under origin/ticket/; nothing to compare."]
    lines: list[str] = []
    for overlap in overlaps:
        status = "overlap" if overlap.files or overlap.nodes else "no overlap"
        lines.append(f"- {overlap.branch}: {status}")
        lines += [f"  - shared file: {name}" for name in overlap.files]
        lines += [f"  - shared node: {gi._label(graph, node_id)}" for node_id in overlap.nodes]  # noqa: SLF001
    return lines


# --- planning mode --------------------------------------------------------------


def split_paths(value: str) -> list[str]:
    return [part.strip().rstrip("/") for part in value.replace(",", " ").split() if part.strip()]


def nodes_under(graph: gi.Graph, paths: list[str]) -> list[str]:
    def matches(source: str) -> bool:
        return any(source == path or source.startswith(path + "/") for path in paths)

    return sorted(
        node_id
        for node_id, node in graph.nodes.items()
        if (source := gi.source_file_of(node)) is not None and matches(source)
    )


@dataclass
class CommunityOverlap:
    community: str
    name: str
    nodes_a: int
    nodes_b: int
    total: int

    @property
    def significant(self) -> bool:
        return self.nodes_a + self.nodes_b > HANDFUL


def community_overlap(
    graph: gi.Graph, paths_a: list[str], paths_b: list[str]
) -> list[CommunityOverlap]:
    def communities(node_ids: list[str]) -> Counter[tuple[str, str]]:
        return Counter(gi._community_of(graph.nodes[node_id]) for node_id in node_ids)  # noqa: SLF001

    counts_a = communities(nodes_under(graph, paths_a))
    counts_b = communities(nodes_under(graph, paths_b))
    totals = communities(list(graph.nodes))
    shared = sorted(set(counts_a) & set(counts_b))
    return [
        CommunityOverlap(key[0], key[1], counts_a[key], counts_b[key], totals[key])
        for key in shared
    ]


def render_overlap(paths_a: list[str], paths_b: list[str], overlaps: list[CommunityOverlap]) -> str:
    significant = [item for item in overlaps if item.significant]
    lines = ["## Overlap", ""]
    lines.append(f"- A: {', '.join(paths_a)}")
    lines.append(f"- B: {', '.join(paths_b)}")
    lines.append(
        f"- shared communities: {len(overlaps)} (more than a handful of nodes: {len(significant)})"
    )
    for item in overlaps:
        flag = " (significant)" if item.significant else ""
        lines.append(
            f"  - {item.community} {item.name}: {item.nodes_a} nodes from A, "
            f"{item.nodes_b} from B, {item.total} in total{flag}"
        )
    verdict = "sequential" if significant else "parallel"
    lines += ["", f"- verdict: {verdict} (section 3.5 rule 1)", ""]
    return "\n".join(lines)


# --- entry point ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default=gi.DEFAULT_BASE)
    parser.add_argument("--graph", type=Path, default=gi.DEFAULT_GRAPH)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--worktree-env", type=Path, default=gi.DEFAULT_WORKTREE_ENV)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--refs-prefix", default=TICKET_REFS)
    parser.add_argument(
        "--paths-a", default=None, help="planning mode: ownership paths of ticket A"
    )
    parser.add_argument(
        "--paths-b", default=None, help="planning mode: ownership paths of ticket B"
    )
    return parser


def run_planning(graph: gi.Graph, args: argparse.Namespace) -> str:
    paths_a, paths_b = split_paths(args.paths_a), split_paths(args.paths_b)
    return render_overlap(paths_a, paths_b, community_overlap(graph, paths_a, paths_b))


def run_branch(repo: Path, graph: gi.Graph, args: argparse.Namespace) -> str:
    baseline = gi.compute_baseline(repo, args.base, graph, repo / args.worktree_env)
    files = gi.changed_files_since(repo, baseline.merge_base)
    ours = gi.compute_impact(graph, files, args.depth, args.top)
    overlaps = branch_overlaps(repo, graph, ours, baseline, args.refs_prefix, args.depth)
    return gi.render_report(graph, baseline, ours, render_conflicts(graph, overlaps))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo: Path = args.repo
    planning = args.paths_a is not None or args.paths_b is not None
    if planning and (args.paths_a is None or args.paths_b is None):
        print("graph_conflicts: planning mode needs both --paths-a and --paths-b", file=sys.stderr)
        return gi.EXIT_UNHEALTHY
    try:
        graph = gi.load_graph(repo / args.graph)
        report = run_planning(graph, args) if planning else run_branch(repo, graph, args)
    except gi.GraphError as error:
        print(f"graph_conflicts: {error}", file=sys.stderr)
        return gi.EXIT_UNHEALTHY
    out: Path = repo / (args.out or (DEFAULT_OVERLAP_OUT if planning else DEFAULT_CONFLICTS_OUT))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    return gi.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
