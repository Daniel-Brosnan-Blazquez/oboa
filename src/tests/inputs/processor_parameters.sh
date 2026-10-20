#!/usr/bin/env bash
set -euo pipefail
test "$1" = "-r"
test "$2" = "-f"
test -f "$3"
test "$OBOA_PROCESSING_PATH" = "$3"
