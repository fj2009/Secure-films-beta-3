#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 no encontrado. Instala Python 3.9+ antes de continuar." >&2
  exit 1
fi

if [ ! -x "$PYTHON_EXE" ]; then
  echo "Creando entorno virtual..."
  python3 -m venv "$VENV_DIR"
fi

echo
echo "Instalacion completada."
echo
echo "El proyecto funciona sin dependencias externas."
echo "Para iniciar el programa ejecuta:"
echo "  ./start_linux.sh --help"
echo
