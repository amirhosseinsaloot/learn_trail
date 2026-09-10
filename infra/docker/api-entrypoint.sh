#!/bin/sh
# API container entrypoint (ARCHITECTURE.md section 15): apply migrations under
# the advisory lock, then hand over to the server command. A failed migration
# stops the container before it serves anything.
set -eu
python -m nuroli.platform.cli migrate
exec "$@"
