#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 ]]; then
  printf '%s\n' 'Usage: rollback.sh MODIFIED_ISO PATCH_ZIP RESTORED_ISO' >&2
  exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python -X utf8 "$ROOT/tools/apply_patch.py" --reverse --input "$1" --patch "$2" --output "$3"
