#!/bin/bash
# kport snap installer — installs the snap and connects all required plugs.
# Usage: bash install.sh [--dangerous /path/to/kport.snap]
#        bash install.sh           (installs from Snap Store)

set -e

SNAP_NAME="kport"

# ── Install ───────────────────────────────────────────────────────────────────
if [ "$1" = "--dangerous" ] && [ -n "$2" ]; then
    echo "Installing local snap: $2"
    sudo snap install --dangerous "$2"
else
    echo "Installing kport from Snap Store..."
    sudo snap install "$SNAP_NAME"
fi

# ── Connect required plugs ────────────────────────────────────────────────────
echo ""
echo "Connecting required snap plugs..."

PLUGS=(
    "network-observe"
    "system-observe"
    "process-control"
    "hardware-observe"
)

for plug in "${PLUGS[@]}"; do
    echo "  snap connect ${SNAP_NAME}:${plug}"
    sudo snap connect "${SNAP_NAME}:${plug}" 2>/dev/null && echo "    ✓ connected" || echo "    ⚠ already connected or skipped"
done

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo "Verifying plugs..."
snap connections "$SNAP_NAME"

echo ""
echo "✓ kport is ready. Try: kport list"
