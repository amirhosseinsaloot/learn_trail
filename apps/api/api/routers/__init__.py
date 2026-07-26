"""HTTP routers, one module per resource.

Each module exposes a single `router` that `api.main` includes. Keeping the app
object free of route definitions is what lets `api.main` stay a three-line
entrypoint as the surface grows.
"""
