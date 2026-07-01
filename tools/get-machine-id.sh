#!/bin/sh
# get-machine-id.sh - Form System Kit Composer
# Prints the license machine fingerprint: TPM EK certificate SHA-256 first,
# then /etc/machine-id SHA-256 if TPM tools are unavailable.
set -eu

hash_stdin() {
  python3 -c 'import hashlib,sys; data=sys.stdin.buffer.read(); print(hashlib.sha256(data).hexdigest() if data else "")'
}

FP=""
SOURCE=""
if command -v tpm2_getekcertificate >/dev/null 2>&1; then
  FP="$(tpm2_getekcertificate --ek-certificate /dev/stdout 2>/dev/null | hash_stdin 2>/dev/null || true)"
  if [ -n "$FP" ]; then
    SOURCE="TPM EK certificate"
  fi
fi

MID=""
if [ -z "$FP" ]; then
  if [ ! -f /etc/machine-id ]; then
    echo "Error: neither TPM EK certificate nor /etc/machine-id is available." >&2
    exit 1
  fi
  MID="$(tr -d '[:space:]' </etc/machine-id | tr '[:upper:]' '[:lower:]')"
  FP="$(printf '%s' "$MID" | hash_stdin 2>/dev/null || true)"
  SOURCE="/etc/machine-id"
fi

if [ -z "$FP" ]; then
  echo "Error: python3 not found or fingerprint calculation failed." >&2
  exit 1
fi

echo "$FP" > machine-id.txt
echo ""
echo "  Source      : $SOURCE"
[ -n "$MID" ] && echo "  Machine ID  : $MID"
echo "  Fingerprint : $FP"
echo "  Saved to    : $(pwd)/machine-id.txt"
echo ""
echo "  Send machine-id.txt to the Form System Kit Composer platform."
echo ""
