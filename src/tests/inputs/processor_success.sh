#!/usr/bin/env bash
set -euo pipefail
test -f "$1"
test "$OBOA_PROCESSING_PATH" = "$1"
