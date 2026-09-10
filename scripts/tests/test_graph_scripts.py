"""graph_impact.py and graph_conflicts.py against a fixture graph and temporary git repositories."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import graph_conflicts as gc  # noqa: E402
import graph_impact as gi  # noqa: E402


def node(node_id: str, source: str | None, community: int) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": node_id,
        "label": f"{node_id}()",
        "community": community,
        "community_name": f"c{community}",
    }
    if source is not None:
        entry["source_file"] = source
    return entry


def fixture_graph(*, directed: bool = False) -> dict[str, object]:
    # b calls a, c calls b, d (no source file) calls c, e calls b.
    return {
        "directed": directed,
        "built_at_commit": "0" * 40,
        "nodes": [
            node("a", "backend/src/nuroli/identity/domain/user.py", 1),
            node("b", "backend/src/nuroli/identity/application/register.py", 1),
            node("c", "backend/src/nuroli/identity/api/router.py", 2),
            node("d", None, 2),
            node("e", "frontend/src/features/auth/api.ts", 3),
            node("f", "frontend/src/features/conversations/api.ts", 3),
        ],
        "links": [
            {"source": "b", "target": "a", "relation": "calls"},
            {"source": "c", "target": "b", "relation": "calls"},
            {"source": "d", "target": "c", "relation": "calls"},
            {"source": "e", "target": "b", "relation": "calls"},
        ],
    }


def write_graph(root: Path, graph: dict[str, object], commit: str | None = None) -> Path:
    if commit is not None:
        graph = {**graph, "built_at_commit": commit}
    path = root / "graphify-out" / "graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph), encoding="utf-8")
    return path


def loaded(graph: dict[str, object], tmp_path: Path) -> gi.Graph:
    return gi.load_graph(write_graph(tmp_path, graph))


def test_changed_files_map_to_nodes_and_nodes_without_source_are_counted(tmp_path: Path) -> None:
    graph = loaded(fixture_graph(), tmp_path)
    assert gi.changed_node_ids(graph, {"backend/src/nuroli/identity/domain/user.py"}) == ["a"]
    assert graph.nodes_without_source == 1


def test_reverse_traversal_respects_depth_and_skips_changed_and_sourceless_nodes(
    tmp_path: Path,
) -> None:
    graph = loaded(fixture_graph(), tmp_path)
    changed_files = {"backend/src/nuroli/identity/domain/user.py"}
    assert gi.affected_node_ids(graph, ["a"], changed_files, depth=1) == {"b": 1}
    assert gi.affected_node_ids(graph, ["a"], changed_files, depth=2) == {"b": 1, "c": 2, "e": 2}
    deep = gi.affected_node_ids(graph, ["a"], changed_files, depth=3)
    assert "d" not in deep, "nodes without a source file are ignored"


def test_directed_graph_traverses_dependents_only(tmp_path: Path) -> None:
    graph = loaded(fixture_graph(directed=True), tmp_path)
    assert gi.affected_node_ids(graph, ["a"], set(), depth=2) == {"b": 1, "c": 2, "e": 2}
    assert gi.affected_node_ids(graph, ["e"], set(), depth=2) == {}


def test_impact_lists_communities_and_god_nodes_touched(tmp_path: Path) -> None:
    graph = loaded(fixture_graph(), tmp_path)
    impact = gi.compute_impact(
        graph, ["backend/src/nuroli/identity/domain/user.py"], depth=2, top=2
    )
    assert impact.changed == ["a"]
    assert impact.communities == [("1", "c1", 1, 1), ("2", "c2", 0, 1), ("3", "c3", 0, 1)]
    assert impact.god_nodes_touched == [("b", 3), ("c", 2)]


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        ({"nodes": [], "built_at_commit": "x"}, "no nodes"),
        ({"nodes": [{"id": "a"}]}, "built_at_commit"),
        ({"nodes": [{"label": "no id"}], "built_at_commit": "x"}, "without a string id"),
    ],
)
def test_unhealthy_graphs_raise(tmp_path: Path, graph: dict[str, object], message: str) -> None:
    with pytest.raises(gi.GraphError, match=message):
        gi.load_graph(write_graph(tmp_path, graph))


def test_missing_graph_exits_one(tmp_path: Path) -> None:
    assert gi.main(["--repo", str(tmp_path), "--graph", "nope/graph.json"]) == gi.EXIT_UNHEALTHY


def test_planning_mode_reports_shared_communities(tmp_path: Path) -> None:
    graph = loaded(fixture_graph(), tmp_path)
    overlaps = gc.community_overlap(
        graph, ["backend/src/nuroli/identity"], ["frontend/src/features/auth"]
    )
    assert overlaps == []
    overlaps = gc.community_overlap(
        graph, ["frontend/src/features/auth"], ["frontend/src/features/conversations"]
    )
    assert [(item.community, item.nodes_a, item.nodes_b, item.total) for item in overlaps] == [
        ("3", 1, 1, 2)
    ]
    assert not overlaps[0].significant
    report = gc.render_overlap(["x"], ["y"], overlaps)
    assert "verdict: parallel" in report


# --- git-backed tests ---------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603
        [gi.GIT, *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "rebuild/v1", ".")
    # Commits and rebases need an identity; CI runners have no global git config.
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.com")
    (root / ".gitignore").write_text("graphify-out/\n.worktree.env\n", encoding="utf-8")
    git(root, "add", ".gitignore")
    commit_file(root, "backend/src/nuroli/identity/domain/user.py", "def user(): ...\n", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/rebuild/v1", base)
    git(root, "checkout", "-q", "-b", "ticket/NU-100-ours")
    commit_file(
        root, "backend/src/nuroli/identity/domain/user.py", "def user(): return 1\n", "ours"
    )
    return root


def test_strict_baseline_passes_on_a_rebased_branch(repo: Path) -> None:
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    code = gi.main(["--repo", str(repo), "--strict-baseline", "--require-current-graph"])
    assert code == gi.EXIT_OK
    report = (repo / "graphify-out" / "impact.md").read_text(encoding="utf-8")
    assert "- rebased on base: yes" in report
    assert "- changed nodes: 1" in report and "`a()`" in report
    for section in [
        "## Baseline",
        "## Changed nodes",
        "## Affected nodes",
        "## Communities",
        "## God nodes",
        "## Conflicts",
    ]:
        assert section in report


def test_strict_baseline_fails_when_base_moved_ahead(repo: Path) -> None:
    git(repo, "checkout", "-q", "rebuild/v1")
    moved = commit_file(repo, "backend/src/nuroli/other.py", "x = 1\n", "base moves on")
    git(repo, "update-ref", "refs/remotes/origin/rebuild/v1", moved)
    git(repo, "checkout", "-q", "ticket/NU-100-ours")
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    assert gi.main(["--repo", str(repo), "--strict-baseline"]) == gi.EXIT_BASELINE
    assert gi.main(["--repo", str(repo)]) == gi.EXIT_OK, (
        "without --strict-baseline the report still exits 0"
    )


def test_baseline_moved_is_detected_from_worktree_env(repo: Path) -> None:
    older = git(repo, "rev-parse", "rebuild/v1")
    (repo / ".worktree.env").write_text(
        f"BASE_COMMIT={older}\nBASE_SCHEMA_HEAD=none\n", encoding="utf-8"
    )
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    assert gi.main(["--repo", str(repo), "--strict-baseline"]) == gi.EXIT_OK
    git(repo, "checkout", "-q", "rebuild/v1")
    moved = commit_file(repo, "docs/note.md", "note\n", "base moves on")
    git(repo, "update-ref", "refs/remotes/origin/rebuild/v1", moved)
    git(repo, "checkout", "-q", "ticket/NU-100-ours")
    git(repo, "rebase", "-q", "origin/rebuild/v1")
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    code = gi.main(["--repo", str(repo), "--strict-baseline"])
    assert code == gi.EXIT_BASELINE
    assert "baseline moved: yes" in (repo / "graphify-out" / "impact.md").read_text(
        encoding="utf-8"
    )


def test_two_alembic_heads_at_base_are_named(repo: Path) -> None:
    git(repo, "checkout", "-q", "rebuild/v1")
    commit_file(
        repo,
        "backend/migrations/versions/0001_a.py",
        "revision = '0001a'\ndown_revision = None\n",
        "m1",
    )
    head = commit_file(
        repo,
        "backend/migrations/versions/0002_b.py",
        "revision = '0002b'\ndown_revision = None\n",
        "m2",
    )
    git(repo, "update-ref", "refs/remotes/origin/rebuild/v1", head)
    assert gi.schema_heads_at(repo, head) == ["0001a", "0002b"]
    git(repo, "checkout", "-q", "ticket/NU-100-ours")
    git(repo, "rebase", "-q", "origin/rebuild/v1")
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    assert gi.main(["--repo", str(repo), "--strict-baseline"]) == gi.EXIT_BASELINE
    assert "two Alembic heads" in (repo / "graphify-out" / "impact.md").read_text(encoding="utf-8")


def test_schema_head_follows_the_chain(repo: Path) -> None:
    head = commit_file(
        repo,
        "backend/migrations/versions/0001_a.py",
        'revision: str = "0001a"\ndown_revision: str | None = None\n',
        "m1",
    )
    head = commit_file(
        repo,
        "backend/migrations/versions/0002_b.py",
        'revision: str = "0002b"\ndown_revision: str | None = "0001a"\n',
        "m2",
    )
    assert gi.schema_heads_at(repo, head) == ["0002b"]
    assert gi.schema_heads_at(repo, git(repo, "rev-parse", "rebuild/v1")) == ["none"]


def test_branch_conflicts_intersect_changed_and_affected_nodes(repo: Path) -> None:
    base = git(repo, "rev-parse", "rebuild/v1")
    git(repo, "checkout", "-q", "-b", "ticket/NU-101-theirs", base)
    theirs = commit_file(
        repo,
        "backend/src/nuroli/identity/application/register.py",
        "def register(): ...\n",
        "theirs",
    )
    git(repo, "update-ref", "refs/remotes/origin/ticket/NU-101-theirs", theirs)
    git(repo, "checkout", "-q", "-b", "ticket/NU-102-far", base)
    far = commit_file(repo, "frontend/src/features/conversations/api.ts", "export {};\n", "far")
    git(repo, "update-ref", "refs/remotes/origin/ticket/NU-102-far", far)
    git(repo, "checkout", "-q", "ticket/NU-100-ours")
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    assert gc.main(["--repo", str(repo)]) == gi.EXIT_OK
    report = (repo / "graphify-out" / "conflicts.md").read_text(encoding="utf-8")
    assert "- origin/ticket/NU-101-theirs: overlap" in report
    assert "shared node: `b()`" in report
    assert "- origin/ticket/NU-102-far: no overlap" in report


def test_no_other_branches_gives_an_empty_conflicts_section(repo: Path) -> None:
    write_graph(repo, fixture_graph(), git(repo, "rev-parse", "HEAD"))
    assert gc.main(["--repo", str(repo)]) == gi.EXIT_OK
    report = (repo / "graphify-out" / "conflicts.md").read_text(encoding="utf-8")
    assert "No other ticket branches" in report
