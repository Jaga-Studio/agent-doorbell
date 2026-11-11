#!/bin/bash
# agent-doorbell setup. Run it on the always-on machine, in your own terminal (not through an AI agent).
#
#   ./setup.sh             set up and start. No Docker: runs as a background service
#                          (launchd on macOS, systemd --user on Linux)
#   ./setup.sh --docker    the same with Docker Compose
#   ./setup.sh --restart   after you add members or edit config.toml
#   ./setup.sh --status    is it running?
#   ./setup.sh --stop      stop and remove the background service
#
# Needs uv (https://docs.astral.sh/uv/) or Python 3.11+. Without either, it offers to install uv.
set -eu
cd "$(dirname "$0")"

if command -v uv >/dev/null; then
  py=(uv run --quiet --no-project --python 3.12 python)
elif command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  py=(python3)
else
  echo "agent-doorbell needs uv, a small command-line tool that brings its own Python (no GUI, no admin rights)."
  echo "Install it now with the official installer?  curl -LsSf https://astral.sh/uv/install.sh | sh"
  read -rp "[y/N] " answer
  [[ "$answer" == [yY]* ]] || { echo "Install uv or Python 3.11+, then run ./setup.sh again."; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  py=(uv run --quiet --no-project --python 3.12 python)
fi
exec "${py[@]}" tools/setup.py "$@"
