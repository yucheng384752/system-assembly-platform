#!/usr/bin/env bash
# get-machine-id.sh — Form System Kit Composer
# Generates a machine fingerprint from /etc/machine-id and writes it to machine-id.txt
set -euo pipefail

if [ ! -f /etc/machine-id ]; then
  echo "Error: /etc/machine-id not found. This script requires Linux." >&2
  exit 1
fi

MID=$(cat /etc/machine-id | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
FP=$(python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" "$MID" 2>/dev/null)

if [ -z "$FP" ]; then
  echo "Error: python3 not found. Please install Python 3." >&2
  exit 1
fi

echo "$FP" > machine-id.txt
echo ""
echo "  Fingerprint : $FP"
echo "  Saved to    : $(pwd)/machine-id.txt"
echo ""
echo "  請將 machine-id.txt 上傳至 Form System Kit Composer 平台。"
echo ""
