# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-01-04

### Fixed
- Fix HTTP 304 responses on HLS playlist by removing ETag/Last-Modified headers
- Playlist now always returns fresh content for live streaming

## [0.2.1] - 2026-01-04

### Fixed
- Roku compatibility: added silent audio track (Roku requires audio)
- Roku compatibility: set H.264 Main profile and level 4.0
- Increased HLS playlist size from 3 to 6 segments for player stability

## [0.2.0] - 2026-01-04

### Added
- Supervisor API integration for reliable Home Assistant connectivity
- s6 readiness notification when HLS stream becomes available
- SSL certificate error handling for self-signed certificates
- Refresh dashboard button in web UI to manually reload the captured page
- Frame deduplication - skip encoding when dashboard content unchanged

### Fixed
- Authentication now uses HA's configured internal/external URL instead of internal IP
- Improved token injection with multiple URL format support
- Fixed auth URL mismatch between `https://host:443` and `https://host`
- Parse HA's expected `hassUrl` from OAuth state for correct token storage
- Removed duplicate kiosk-mode detection code causing NameError

### Changed
- Fetch HA URL from Supervisor API (`/core/api/config`) for proper external URL support
- Added `hassio_api: true` permission for Supervisor API access

### Optimized
- Reduced default FPS from 5 to 2 (dashboards don't need high frame rates)
- Increased default CRF from 23 to 28 (lower CPU encoding overhead)
- Increased default segment duration from 2s to 4s (less HLS overhead)
- Added 15+ Chromium flags to reduce CPU/memory usage
- Reduced logging frequency from every second to every 30 seconds

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
