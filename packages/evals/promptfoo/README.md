# Promptfoo comparisons

`promptfooconfig.yaml` compares configurations against each other. It is not part
of the merge gate and does not run in CI — see the long comment at the top of that
file for why a comparison has no threshold to enforce.

```bash
set -a && . ./.env && set +a
npx promptfoo@latest eval -c packages/evals/promptfoo/promptfooconfig.yaml
npx promptfoo@latest view
```

Sourcing `.env` is what supplies `LITELLM_MASTER_KEY`; the gateway must be up
(`make up`). The providers point at `localhost:4000`, the host-published port,
because promptfoo runs outside the compose network.

## Adding a comparison

The cases here mirror ids in `../datasets/`, deliberately: when a comparison shows
a regression, the same case already exists as a gated test, so the finding has
somewhere permanent to live. A comparison case with no dataset counterpart is a
question you asked once; a dataset case is one the suite keeps asking.

## What to compare

docs/SPEC.md §9 lists prompt A/B, small versus large model, cloud versus local
(Phase 11), guardrails on versus off, and context-window strategies. The two
providers configured today cover the model-size axis. A prompt A/B needs two
prompt versions to exist — v2 of `learning_summary` will be the first.

## Red-team generation

`redteam.yaml` generates attacks rather than replaying them.

```bash
set -a && . ./.env && set +a
npx promptfoo@latest redteam run -c packages/evals/promptfoo/redteam.yaml
npx promptfoo@latest redteam report
```

It is **not** the gate, and the distinction is the important part. `make redteam`
measures a fixed, curated set, because a gate needs a stable denominator — two
runs are only comparable if they asked the same questions. A generator asks new
ones each time, which is exactly what makes it useful for discovery and useless
for regression.

The loop: generate here, triage by hand, and promote anything that lands into
`../red_team/cases/`. At that point it joins the measured posture and can never
quietly return.
