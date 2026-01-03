#!/usr/bin/env bash
# Build the add-on locally for testing
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building Dashboard Streams add-on..."

docker build \
  --build-arg BUILD_FROM="ghcr.io/home-assistant/amd64-base-python:3.11-alpine3.18" \
  -t local/dashboard-streams \
  "$ADDON_DIR"

echo "Build complete! Image: local/dashboard-streams"
