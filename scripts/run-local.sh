#!/usr/bin/env bash
# Run the add-on locally for testing (without Home Assistant integration)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON_DIR="$(dirname "$SCRIPT_DIR")"

# Create test data directory
mkdir -p /tmp/dashboard-streams-data

# Create test options.json
cat > /tmp/dashboard-streams-data/options.json << 'EOF'
{
  "dashboard_url": "https://demo.home-assistant.io",
  "access_token": "",
  "kiosk_mode": false,
  "dark_mode": true
}
EOF

echo "Starting Dashboard Streams locally..."
echo "Stream will be available at: http://localhost:8099/"
echo "Using demo.home-assistant.io as test dashboard"
echo ""
echo "Press Ctrl+C to stop"

docker run \
  --rm \
  -it \
  --name dashboard-streams \
  -v /tmp/dashboard-streams-data:/data \
  -p 8099:8099 \
  local/dashboard-streams
