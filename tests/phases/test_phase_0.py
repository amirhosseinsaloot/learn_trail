"""Phase 0 — Development environment

See docs/SPEC.md, "Phase 0 — Development environment" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

# Every service compose is expected to define *right now* — not a minimum, and
# not only Phase 0's three. Phoenix (+ OTel collector) joins in Phase 5 and the
# optional local model runtime in Phase 11, per CLAUDE.md invariant #6, so an
# unlisted service is a phase violation and this is set equality, not a subset.
#
# `litellm` was added by Phase 1. That is the intended workflow: the phase that
# adds a compose service widens this constant in the same commit. Phase 0's own
# criterion — every service healthy — is unchanged by the addition; it simply
# now covers four services, which is why the name below is no longer accurate
# and the comment says so rather than pretending otherwise.
PHASE_0_SERVICES = frozenset({"postgres", "backend", "frontend", "litellm", "phoenix"})

# Distinguishing the two failure modes is the whole point of the messages below
# (plans/phase-0.md, "Phase test"): "the stack is not running" is an environment
# problem the reader fixes with one command, while "compose declares no
# healthcheck" means the phase is not built. A bare assertion error cannot tell
# them apart, and `make status` prints only PASS/FAIL, so the distinction has to
# survive in the failure text itself.
_NOT_INSTALLED = (
    "docker CLI not found on PATH — Phase 0's exit criterion is about the "
    "docker-compose stack, so it cannot be evaluated without Docker. Install "
    "Docker with the Compose v2 plugin, then run `make up`."
)
_NOT_RUNNING = (
    "docker is installed but the stack is not up — the daemon is unreachable or "
    "the project was never started. Run `make up` (= `docker compose up -d "
    "--wait`) and re-run. This says nothing about whether Phase 0 is built; the "
    "static compose check in this file is what answers that."
)


def _docker() -> str:
    """Absolute path to the docker CLI, or fail with the explicit message."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail(_NOT_INSTALLED)
    return docker


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `docker compose` against this repo's compose file.

    `--file` is passed explicitly so the result cannot depend on whichever
    directory pytest was invoked from; the compose project name still comes from
    the file's own top-level `name:` key.
    """
    return subprocess.run(  # noqa: S603 - fixed argv, binary resolved by shutil.which
        [_docker(), "compose", "--file", str(COMPOSE_FILE), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _parse_ps(stdout: str) -> list[dict[str, Any]]:
    """Parse `docker compose ps --format json`, which has two shapes in the wild.

    On the Compose this was written against (v5.3.1) the output is **JSON
    Lines** — one object per line, no enclosing array — while other versions
    emit a single JSON array. Both are accepted so a Compose upgrade cannot turn
    the phase red with a JSONDecodeError that reads like a broken stack.
    """
    stripped = stdout.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return [json.loads(line) for line in stripped.splitlines() if line.strip()]
    if isinstance(parsed, dict):
        return [parsed]
    return list(parsed)


@pytest.mark.phase
def test_phase_0_compose_declares_a_healthcheck_for_every_service() -> None:
    """Static half of the criterion: the compose file itself is well-formed.

    This runs without the Docker daemon — `docker compose config` only parses
    and interpolates — so it still says something useful on a machine where the
    stack is down. That is what makes a failure attributable: if this passes and
    the live check below fails, the phase is built and the environment is off.
    """
    result = _compose("config", "--format", "json")
    if result.returncode != 0:
        pytest.fail(
            f"`docker compose config` rejected {COMPOSE_FILE.name} — the compose file "
            f"is missing or invalid, so Phase 0 is not built:\n{result.stderr.strip()}"
        )

    config: dict[str, Any] = json.loads(result.stdout)
    services: dict[str, Any] = config.get("services", {})

    assert set(services) == set(PHASE_0_SERVICES), (
        f"Phase 0 defines exactly {sorted(PHASE_0_SERVICES)}; compose defines "
        f"{sorted(services)}. A service joins docker-compose.yml in the phase that "
        f"introduces its concept (CLAUDE.md invariant #6)."
    )

    for name in sorted(services):
        healthcheck: dict[str, Any] = services[name].get("healthcheck") or {}
        assert healthcheck, (
            f"service `{name}` declares no healthcheck. Phase 0's exit criterion is "
            f"that every service reports healthy, which a service without a probe can "
            f"never do."
        )
        assert not healthcheck.get("disable"), (
            f"service `{name}` sets `healthcheck.disable`, which switches off even the "
            f"healthcheck inherited from its image."
        )
        assert healthcheck.get("test"), (
            f"service `{name}` has a healthcheck with no `test` command, so Docker "
            f"reports its health as `none` and never as `healthy`."
        )


@pytest.mark.phase
def test_phase_0_exit_criterion() -> None:
    """Phase 0 — Development environment.

    PROXY criterion — docs/SPEC.md defines no verbatim exit criterion for this
    phase. This is a derived stand-in, not a quote from the spec:

        "Every service docker-compose.yml defines in Phase 0 (Postgres, backend,
        frontend) reports a healthy status."

    Phoenix and LiteLLM Proxy are deliberately excluded: a service joins
    docker-compose.yml in the phase that introduces its concept (LiteLLM in
    Phase 1, Phoenix in Phase 5), and each phase test checks only the services
    that exist by its phase.

    Live half: `docker compose ps` must report every service `running` and
    `healthy`. Health is read back from Docker rather than probed from here on
    purpose — the criterion is about the healthchecks compose declares, and
    re-implementing those probes in the test would assert something else.
    """
    result = _compose("ps", "--all", "--format", "json")
    if result.returncode != 0:
        pytest.fail(f"{_NOT_RUNNING}\n\n{result.stderr.strip()}")

    # --all, so a created-but-exited container is reported as unhealthy below
    # rather than vanishing from the listing and being mistaken for a stack that
    # was never started.
    containers = _parse_ps(result.stdout)
    if not containers:
        pytest.fail(_NOT_RUNNING)

    by_service = {c["Service"]: c for c in containers}

    missing = sorted(PHASE_0_SERVICES - set(by_service))
    if missing:
        pytest.fail(
            f"{_NOT_RUNNING}\n\nNo container exists for: {missing}. Compose knows "
            f"the service(s); they were simply never started."
        )

    def state_of(service: str) -> str:
        container = by_service[service]
        # `Health` is the empty string for a container whose image and compose
        # entry declare no probe; render that as `none`, matching `docker ps`.
        return f"{container.get('State')}/{container.get('Health') or 'none'}"

    unhealthy = {
        name: state_of(name)
        for name in sorted(PHASE_0_SERVICES)
        if state_of(name) != "running/healthy"
    }
    assert not unhealthy, (
        f"not every Phase 0 service reports healthy (state/health): {unhealthy}. "
        f"Inspect with `make ps` and `make logs`."
    )
