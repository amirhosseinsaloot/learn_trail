# Fake model service

Placeholder served by `python -m http.server` from `compose.dev.yaml` so the
`fake-model` service name and port exist for the development stack. NU-022
replaces it with the OpenAI-compatible and Tavily-shaped fake server that
development and end-to-end tests use instead of a paid endpoint (I-07).
