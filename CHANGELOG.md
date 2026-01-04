# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2025-01-03

### Fixed
- Fix internal HA hostname: use `homeassistant:8123` instead of `homeassistant.local.hass.io:8123`

## [0.1.1] - 2025-01-03

### Fixed
- Added netcat-openbsd to Dockerfile for ARM compatibility
- Simplified s6 service startup script
- Removed unnecessary notification-fd handling

## [0.1.0] - 2025-01-03

### Added
- Initial release
- HLS streaming endpoint at `/hls/stream.m3u8`
- Snapshot endpoint at `/snapshot.jpg`
- Web interface with configuration info and live preview
- Configurable resolution, quality, FPS, and segment duration
- Kiosk mode support (requires kiosk-mode from HACS)
- Dark mode support with `dark_mode` config option (default: true)
- Auto-refresh when dashboard configuration changes via WebSocket subscription
- Home Assistant Supervisor API integration for kiosk-mode detection
- Low-latency streaming optimizations
- Ingress support for access via Home Assistant UI
