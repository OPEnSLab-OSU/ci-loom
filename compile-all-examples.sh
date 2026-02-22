#!/usr/bin/env bash
set -u

# Config
ARDUINO_CLI_PATH="${ARDUINO_CLI_PATH:-$(command -v arduino-cli || true)}"
FQBN="${FQBN:-loom4:samd:adafruit_feather_m0}"
EXAMPLES_DIR="${EXAMPLES_DIR:-examples}"
SHARED_CACHE="${SHARED_CACHE:-$(pwd)/.build_}"

if [ -z "$ARDUINO_CLI_PATH" ]; then
  echo "ERROR: arduino-cli not found. Install it or set ARDUINO_CLI_PATH."
  exit 1
fi

mkdir -p "$SHARED_CACHE"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

FAILED=0
PASSED=0

echo "Compiling all examples from: $EXAMPLES_DIR"
# Use NUL-delimited find to handle spaces/newlines in names
while IFS= read -r -d '' sketch; do
    parent="$(dirname "$sketch")"
    echo "Compiling $sketch (dir: $parent)..."
    output=$("$ARDUINO_CLI_PATH" compile --fqbn "$FQBN" --build-path "$SHARED_CACHE" "$parent" 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        echo -e "${RED}✗ FAILED: $sketch${NC}"
        echo "$output"
        FAILED=$((FAILED+1))
    else
        echo -e "${GREEN}✓ PASSED: $sketch${NC}"
        PASSED=$((PASSED+1))
    fi
done < <(find "$EXAMPLES_DIR" -type f -name "*.ino" -print0)

echo ""
echo "======================================"
echo "Compilation Results:"
echo "PASSED: $PASSED"
echo "FAILED: $FAILED"
echo "======================================"

if [ $FAILED -ne 0 ]; then
  exit 1
fi