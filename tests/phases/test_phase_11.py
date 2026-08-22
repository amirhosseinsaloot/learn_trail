"""Phase 11 — Local models

See docs/SPEC.md, "Phase 11 — Local models" section, for the full Build/AI-stack/Learn
breakdown. This file only encodes the exit criterion as an executable check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_11_exit_criterion() -> None:
    """Phase 11 — Local models.

    docs/SPEC.md states no verbatim exit criterion; the plan's proxy is used
    (plans/phase-11.md):

        "A chat request can be served entirely by a locally-registered LiteLLM
        model (Ollama/vLLM) with no outbound call to a cloud provider, and a
        cloud-versus-local benchmark result is recorded."

    Two halves, asserted separately.

    **Served locally, with no cloud call.** The `learning-local` alias exists, is
    a real `ModelAlias`, and is registered in LiteLLM against a *local* endpoint —
    Ollama, not a cloud host, and carrying no cloud credential. Privacy mode
    routes every request to it and, critically, a local failure has no fallback
    to a cloud alias: "no outbound call" is a guarantee that must survive an
    error, not only the happy path.

    **A benchmark is recorded.** `packages/evals/reports/benchmark.json` exists,
    compares the cloud and local aliases, and carries latency, quality and cost
    for each side — the trade-off a local model asks you to accept, as numbers.

    **No model, no network.** This asserts the *wiring and the recorded artifact*,
    not a live generation. Running the benchmark is `make benchmark`; serving a
    request locally is verified there and in the graph tests. `make status` must
    stay runnable with nothing but a checkout.
    """
    import json

    import yaml

    from ai_core.models.aliases import ModelAlias
    from ai_core.models.routing import fallback_for, route

    repo = Path(__file__).resolve().parents[2]

    # --- the local alias exists and is distinct --------------------------------
    assert ModelAlias.LEARNING_LOCAL.value == "learning-local"

    # --- it is registered against a LOCAL endpoint, with no cloud key ----------
    config = yaml.safe_load((repo / "infra/litellm/config.yaml").read_text())
    by_name = {m["model_name"]: m["litellm_params"] for m in config["model_list"]}
    assert "learning-local" in by_name, "the local alias is not registered in LiteLLM"

    local = by_name["learning-local"]
    # It points at an api_base (a specific endpoint), unlike the cloud aliases,
    # which use the provider's default. That api_base is Ollama's, resolved from
    # the environment so a host or a compose service can serve it.
    assert "api_base" in local, "the local alias names no endpoint — it cannot be local"
    assert "OLLAMA_BASE_URL" in str(local["api_base"])
    # It carries no cloud credential. The cloud aliases read OPENAI_API_KEY; the
    # local one must not, or "no outbound call to a cloud provider" is a fiction.
    assert "OPENAI_API_KEY" not in str(local.get("api_key", "")), (
        "the local alias carries a cloud credential, which contradicts being local"
    )

    # --- privacy mode routes local, and cannot leak on failure -----------------
    for question in ("define an index", "why is this a deep trade-off, in detail?"):
        _, alias = route(question, local_only=True)
        assert alias is ModelAlias.LEARNING_LOCAL, "privacy mode did not force the local model"

    assert fallback_for(ModelAlias.LEARNING_LOCAL) is None, (
        "the local model has a fallback — a local failure could leak the request "
        "to a cloud alias, which defeats privacy mode"
    )

    # --- Ollama is a real, registered runtime ----------------------------------
    # The compose service exists (profile-gated — it is the optional local runtime
    # docs/SPEC.md §6 names, not one of the mandatory five). Asserted with the
    # `local` profile active, because a profiled service is absent otherwise.
    import shutil
    import subprocess

    docker = shutil.which("docker")
    if docker is not None:
        result = subprocess.run(  # noqa: S603 - fixed argv, binary from shutil.which
            [docker, "compose", "--profile", "local", "config", "--format", "json"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        services = json.loads(result.stdout).get("services", {}) if result.returncode == 0 else {}
        assert "ollama" in services, "the ollama compose service is not defined"
        assert "profiles" in services["ollama"], (
            "the ollama service is not profile-gated; the optional local runtime "
            "must not burden the default `make up`"
        )
    # If docker is absent this environment cannot check compose, which is fine —
    # the alias and routing assertions above do not depend on it.

    # --- the benchmark result is recorded --------------------------------------
    report_path = repo / "packages/evals/reports/benchmark.json"
    assert report_path.exists(), (
        "no cloud-vs-local benchmark has been recorded — run `make benchmark`"
    )
    report: dict[str, Any] = json.loads(report_path.read_text())
    for side in ("cloud", "local"):
        assert side in report, f"the benchmark report is missing the {side} side"
        for field in ("alias", "served", "avg_latency_ms", "avg_coverage", "total_cost_usd"):
            assert field in report[side], f"the {side} side is missing {field!r}"

    # The cloud side must have actually run — a benchmark with no cloud figures
    # has nothing to compare local against.
    assert report["cloud"]["served"] is True, (
        "the recorded benchmark never reached the cloud model, so it is not a "
        "cloud-vs-local comparison"
    )
    # And the two sides are the two aliases, not the same one twice.
    assert report["cloud"]["alias"] == ModelAlias.LEARNING_FAST.value
    assert report["local"]["alias"] == ModelAlias.LEARNING_LOCAL.value
