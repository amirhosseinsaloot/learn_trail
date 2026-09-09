"""Impact report from the code graph (R-41, IMPLEMENTATION.md section 3.5).

Changed files against a base ref map to graph nodes; a traversal of depth N
finds the nodes outside the changed files that depend on them; the report
lists communities and god nodes touched. Reads only graphify-out/graph.json
and git, never application code.

Exit codes: 0 report written, 1 graph missing or unhealthy, 2 branch not
rebased or baseline moved (only with --strict-baseline, used by preflight).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_UNHEALTHY = 1
EXIT_BASELINE = 2

DEFAULT_BASE = "origin/rebuild/v1"
DEFAULT_GRAPH = Path("graphify-out/graph.json")
DEFAULT_OUT = Path("graphify-out/impact.md")
DEFAULT_WORKTREE_ENV = Path(".worktree.env")
MIGRATIONS_DIR = "backend/migrations/versions"
GIT = shutil.which("git") or "git"

REVISION_LINE = re.compile(r"^revision(?:: str)? = ['\"]([^'\"]+)['\"]", re.MULTILINE)
DOWN_REVISION_LINE = re.compile(r"^down_revision(?:: [^=]+)? = ['\"]([^'\"]+)['\"]", re.MULTILINE)


class GraphError(Exception):
    """The graph is missing or unhealthy; the caller exits 1."""


@dataclass
class Graph:
    nodes: dict[str, dict[str, object]]
    dependents: dict[str, set[str]]
    built_at_commit: str
    directed: bool
    nodes_without_source: int = 0

    edge_degree: Counter[str] = field(default_factory=Counter)

    def degree(self) -> Counter[str]:
        """Edges per node, each edge counted once for both endpoints."""
        return Counter(self.edge_degree)


def load_graph(path: Path) -> Graph:
    """Read graph.json; raise GraphError when it is absent or malformed."""
    if not path.exists():
        raise GraphError(f"graph missing at {path}; run make graph-build")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GraphError(f"graph unreadable at {path}: {error}") from error
    if not isinstance(raw, dict):
        raise GraphError("graph.json is not a JSON object")
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise GraphError("graph has no nodes; the code tree is empty or extraction failed")
    built_at = raw.get("built_at_commit")
    if not isinstance(built_at, str) or not built_at:
        raise GraphError("graph has no built_at_commit; rebuild it with make graph-build")
    return _build_graph(raw, raw_nodes, built_at)


def _build_graph(raw: dict[str, object], raw_nodes: list[object], built_at: str) -> Graph:
    directed = bool(raw.get("directed", False))
    nodes: dict[str, dict[str, object]] = {}
    without_source = 0
    for entry in raw_nodes:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise GraphError("graph node without a string id; the graph is unhealthy")
        node: dict[str, object] = dict(entry)
        if not node.get("source_file"):
            without_source += 1
        nodes[str(node["id"])] = node
    dependents: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    edge_degree: Counter[str] = Counter()
    raw_links = raw.get("links") or raw.get("edges") or []
    if isinstance(raw_links, list):
        for link in raw_links:
            _add_link(link, nodes, dependents, directed, edge_degree)
    return Graph(nodes, dependents, built_at, directed, without_source, edge_degree)


def _add_link(
    link: object,
    nodes: dict[str, dict[str, object]],
    dependents: dict[str, set[str]],
    directed: bool,
    edge_degree: Counter[str],
) -> None:
    if not isinstance(link, dict):
        return
    source, target = link.get("source"), link.get("target")
    if not isinstance(source, str) or not isinstance(target, str):
        return
    if source not in nodes or target not in nodes or source == target:
        return
    # An edge source -> target means the source depends on the target, so the
    # target's dependents include the source. Undirected graphs count both ways.
    dependents[target].add(source)
    if not directed:
        dependents[source].add(target)
    edge_degree[source] += 1
    edge_degree[target] += 1


def source_file_of(node: dict[str, object]) -> str | None:
    value = node.get("source_file")
    return value if isinstance(value, str) and value else None


def changed_node_ids(graph: Graph, changed_files: set[str]) -> list[str]:
    return sorted(
        node_id for node_id, node in graph.nodes.items() if source_file_of(node) in changed_files
    )


def affected_node_ids(
    graph: Graph, changed_ids: list[str], changed_files: set[str], depth: int
) -> dict[str, int]:
    """Nodes outside the changed files reachable by reverse traversal within depth."""
    distance: dict[str, int] = dict.fromkeys(changed_ids, 0)
    queue: deque[str] = deque(changed_ids)
    affected: dict[str, int] = {}
    while queue:
        current = queue.popleft()
        if distance[current] >= depth:
            continue
        for dependent in sorted(graph.dependents.get(current, ())):
            if dependent in distance:
                continue
            distance[dependent] = distance[current] + 1
            queue.append(dependent)
            node = graph.nodes[dependent]
            source = source_file_of(node)
            if source is not None and source not in changed_files:
                affected[dependent] = distance[dependent]
    return affected


def god_node_ids(graph: Graph, top: int) -> list[tuple[str, int]]:
    ranked = sorted(graph.degree().items(), key=lambda item: (-item[1], item[0]))
    return ranked[:top]


@dataclass
class Impact:
    changed_files: list[str]
    changed: list[str]
    affected: dict[str, int]
    communities: list[tuple[str, str, int, int]] = field(default_factory=list)
    god_nodes_touched: list[tuple[str, int]] = field(default_factory=list)

    def touched(self) -> set[str]:
        return set(self.changed) | set(self.affected)


def compute_impact(graph: Graph, changed_files: list[str], depth: int, top: int) -> Impact:
    files = set(changed_files)
    changed = changed_node_ids(graph, files)
    affected = affected_node_ids(graph, changed, files, depth)
    counts: dict[tuple[str, str], list[int]] = {}
    for node_id in changed:
        counts.setdefault(_community_of(graph.nodes[node_id]), [0, 0])[0] += 1
    for node_id in affected:
        counts.setdefault(_community_of(graph.nodes[node_id]), [0, 0])[1] += 1
    communities = sorted((key[0], key[1], value[0], value[1]) for key, value in counts.items())
    touched = set(changed) | set(affected)
    gods = [(node_id, degree) for node_id, degree in god_node_ids(graph, top) if node_id in touched]
    return Impact(sorted(files), changed, affected, communities, gods)


def _community_of(node: dict[str, object]) -> tuple[str, str]:
    return (str(node.get("community", "?")), str(node.get("community_name", "")))


# --- git ---------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    # Fixed argument list; nothing user-controlled reaches a shell.
    result = subprocess.run(  # noqa: S603
        [GIT, *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    result = subprocess.run(  # noqa: S603
        [GIT, *args], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def changed_files_since(repo: Path, merge_base: str, ref: str | None = None) -> list[str]:
    """Files changed between merge_base and ref (working tree when ref is None)."""
    if ref is None:
        tracked = git(repo, "diff", "--name-only", merge_base)
        untracked = git(repo, "ls-files", "--others", "--exclude-standard")
        names = set(tracked.splitlines()) | set(untracked.splitlines())
    else:
        names = set(git(repo, "diff", "--name-only", f"{merge_base}..{ref}").splitlines())
    return sorted(name for name in names if name)


def schema_heads_at(repo: Path, ref: str) -> list[str]:
    """Alembic heads recorded by the migration files of a commit ("none" when absent)."""
    if not git_ok(repo, "cat-file", "-e", f"{ref}:{MIGRATIONS_DIR}"):
        return ["none"]
    listing = git(repo, "ls-tree", "-r", "--name-only", ref, "--", MIGRATIONS_DIR)
    revisions: list[str] = []
    downs: set[str] = set()
    for name in listing.splitlines():
        if not name.endswith(".py"):
            continue
        text = git(repo, "show", f"{ref}:{name}")
        revisions.extend(REVISION_LINE.findall(text))
        downs.update(DOWN_REVISION_LINE.findall(text))
    heads = [revision for revision in revisions if revision not in downs]
    return sorted(heads) or ["none"]


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


@dataclass
class Baseline:
    base_ref: str
    base_head: str
    head: str
    branch: str
    merge_base: str
    rebased: bool
    base_commit: str | None
    base_schema_head: str | None
    schema_heads_at_base: list[str]
    baseline_moved: bool
    graph_built_at: str
    graph_current: bool

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.rebased:
            problems.append(
                f"branch is not rebased on {self.base_ref} ({self.base_head[:7]}); "
                f"run: git rebase {self.base_ref}"
            )
        if self.baseline_moved:
            problems.append(
                f"baseline moved: worktree started from {(self.base_commit or '')[:7]} with schema "
                f"head {self.base_schema_head}, {self.base_ref} is now {self.base_head[:7]} with "
                f"schema head {', '.join(self.schema_heads_at_base)}; rebase, then rerun make check"
            )
        if len(self.schema_heads_at_base) > 1:
            problems.append(
                "two Alembic heads at the base: " + ", ".join(self.schema_heads_at_base)
            )
        return problems


def compute_baseline(repo: Path, base_ref: str, graph: Graph, env_path: Path) -> Baseline:
    if not git_ok(repo, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"):
        raise GraphError(f"base ref {base_ref} does not exist; fetch it or pass --base")
    base_head = git(repo, "rev-parse", f"{base_ref}^{{commit}}")
    head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    merge_base = git(repo, "merge-base", base_head, head)
    env = read_env_file(env_path)
    base_commit = env.get("BASE_COMMIT")
    moved = False
    if base_commit:
        # Moved when the base has commits the worktree's starting point lacks.
        moved = not git_ok(repo, "merge-base", "--is-ancestor", base_head, base_commit)
    return Baseline(
        base_ref=base_ref,
        base_head=base_head,
        head=head,
        branch=branch,
        merge_base=merge_base,
        rebased=merge_base == base_head,
        base_commit=base_commit,
        base_schema_head=env.get("BASE_SCHEMA_HEAD"),
        schema_heads_at_base=schema_heads_at(repo, base_head),
        baseline_moved=moved,
        graph_built_at=graph.built_at_commit,
        graph_current=graph.built_at_commit == head,
    )


# --- report ------------------------------------------------------------------


def _label(graph: Graph, node_id: str) -> str:
    node = graph.nodes[node_id]
    return f"`{node.get('label', node_id)}` ({source_file_of(node) or 'no source file'})"


def render_report(
    graph: Graph, baseline: Baseline, impact: Impact, conflicts_section: list[str]
) -> str:
    lines = ["## Baseline", ""]
    lines.append(f"- base: {baseline.base_ref} @ {baseline.base_head[:7]}")
    lines.append(
        f"- head: {baseline.branch} @ {baseline.head[:7]} (merge base {baseline.merge_base[:7]})"
    )
    lines.append(f"- rebased on base: {'yes' if baseline.rebased else 'no'}")
    if baseline.base_commit:
        lines.append(
            f"- worktree baseline: BASE_COMMIT {baseline.base_commit[:7]}, "
            f"BASE_SCHEMA_HEAD {baseline.base_schema_head or 'none'}"
        )
        lines.append(f"- baseline moved: {'yes' if baseline.baseline_moved else 'no'}")
    else:
        lines.append("- worktree baseline: none recorded (no .worktree.env)")
    lines.append(f"- schema head at base: {', '.join(baseline.schema_heads_at_base)}")
    lines.append(
        f"- graph built_at_commit: {baseline.graph_built_at[:7]} "
        f"({'current' if baseline.graph_current else 'stale, rebuild with make graph-build'})"
    )
    lines.append(
        f"- graph: {len(graph.nodes)} nodes, "
        f"{graph.nodes_without_source} without source file (ignored)"
    )
    for problem in baseline.problems():
        lines.append(f"- problem: {problem}")
    lines += ["", "## Changed nodes", ""]
    lines.append(f"- changed files: {len(impact.changed_files)}")
    lines += [f"  - {name}" for name in impact.changed_files]
    lines.append(f"- changed nodes: {len(impact.changed)}")
    lines += [f"  - {_label(graph, node_id)}" for node_id in impact.changed]
    lines += ["", "## Affected nodes", ""]
    lines.append(f"- affected nodes outside the changed files: {len(impact.affected)}")
    for node_id, distance in sorted(impact.affected.items(), key=lambda item: (item[1], item[0])):
        lines.append(f"  - {_label(graph, node_id)} at distance {distance}")
    lines += ["", "## Communities", ""]
    lines.append(f"- communities touched: {len(impact.communities)}")
    for community, name, changed, affected in impact.communities:
        lines.append(f"  - {community} {name}: {changed} changed, {affected} affected")
    lines += ["", "## God nodes", ""]
    lines.append(f"- god nodes touched: {len(impact.god_nodes_touched)}")
    lines += [
        f"  - {_label(graph, node_id)} with {degree} edges"
        for node_id, degree in impact.god_nodes_touched
    ]
    lines += ["", "## Conflicts", "", *conflicts_section, ""]
    return "\n".join(lines)


# --- entry point --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default=DEFAULT_BASE, help="base ref (default origin/rebuild/v1)")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--depth", type=int, default=2, help="reverse traversal depth")
    parser.add_argument("--top", type=int, default=10, help="god nodes considered")
    parser.add_argument("--worktree-env", type=Path, default=DEFAULT_WORKTREE_ENV)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--strict-baseline",
        action="store_true",
        help="exit 2 when not rebased or the baseline moved",
    )
    parser.add_argument(
        "--require-current-graph",
        action="store_true",
        help="exit 1 when built_at_commit is not HEAD",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo: Path = args.repo
    try:
        graph = load_graph(repo / args.graph)
        baseline = compute_baseline(repo, args.base, graph, repo / args.worktree_env)
    except GraphError as error:
        print(f"graph_impact: {error}", file=sys.stderr)
        return EXIT_UNHEALTHY
    files = changed_files_since(repo, baseline.merge_base)
    impact = compute_impact(graph, files, args.depth, args.top)
    report = render_report(
        graph, baseline, impact, ["Not computed by this report; run `make graph-conflicts`."]
    )
    out: Path = repo / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    if args.require_current_graph and not baseline.graph_current:
        print("graph_impact: graph built_at_commit is not HEAD", file=sys.stderr)
        return EXIT_UNHEALTHY
    if args.strict_baseline and baseline.problems():
        for problem in baseline.problems():
            print(f"graph_impact: {problem}", file=sys.stderr)
        return EXIT_BASELINE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
