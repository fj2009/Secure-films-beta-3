#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ -x "$VENV_PYTHON" ]; then
  PYTHON_EXE="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="python3"
else
  echo "No se encontró Python en el sistema." >&2
  echo "Instala Python 3.9+ o ejecuta ./install_linux.sh." >&2
  exit 1
fi

if [ $# -eq 0 ]; then
  "$PYTHON_EXE" "$SCRIPT_DIR/secure_file_manager.py" --help
else
  "$PYTHON_EXE" "$SCRIPT_DIR/secure_file_manager.py" "$@"
fi
