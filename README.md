# Dashboard Streams

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/addons/)

Stream your Home Assistant Lovelace dashboards to Roku, Apple TV, Chromecast, Fire TV, and any device that supports HLS video streams.

## Features

- **HLS Streaming**: Industry-standard HTTP Live Streaming compatible with all major devices
- **Low Latency**: Optimized for ~3-5 second delay with automatic dashboard refresh
- **Dark Mode**: Forces dark theme for better TV viewing (configurable)
- **Kiosk Mode**: Hides sidebar and header for a clean display
- **Auto-Refresh**: Automatically updates when dashboard configuration changes
- **Universal Compatibility**: Works with Roku, Apple TV, Chromecast, Fire TV, VLC, and more

## Prerequisites

### Kiosk Mode (Required for clean display)

To hide the Home Assistant sidebar and header, install **kiosk-mode** from HACS:

1. Open HACS in Home Assistant
2. Go to **Frontend** > **Explore & Download Repositories**
3. Search for "kiosk-mode" and install it
4. Restart Home Assistant

GitHub: https://github.com/NemesisRE/kiosk-mode

## Installation

1. In Home Assistant, go to **Settings** > **Add-ons** > **Add-on Store**
2. Click the **⋮** menu (top right) > **Repositories**
3. Add this repository URL:
   ```
   https://github.com/xaviergmail/hass-dashboard-stream
   ```
4. Click **Add** > **Close**
5. Find "Dashboard Streams" in the add-on store and click **Install**
6. Create a Long-Lived Access Token (see below)
7. Configure your settings and click **Save**
8. Start the add-on

## Configuration

### Required Options

| Option | Description |
|--------|-------------|
| `dashboard_url` | Path to the Lovelace dashboard (e.g., `/lovelace/0`) |
| `access_token` | Long-lived access token for authentication |
| `kiosk_mode` | Hide sidebar and header (requires kiosk-mode from HACS) |
| `dark_mode` | Force dark theme for the stream |

### Optional Options

| Option | Default | Description |
|--------|---------|-------------|
| `width` | `1920` | Stream width in pixels |
| `height` | `1080` | Stream height in pixels |
| `quality` | `23` | H.264 CRF quality (18=best, 28=smallest) |
| `fps` | `5` | Frames per second |
| `segment_duration` | `2` | HLS segment duration in seconds |

### Creating an Access Token

1. Go to your Home Assistant profile (click your username in the sidebar)
2. Scroll down to **Long-Lived Access Tokens**
3. Click **Create Token**
4. Name it "Dashboard Streams"
5. Copy the token and paste it into the add-on configuration
6. Restart the add-on

### Quality Settings

Lower CRF = higher quality, larger bandwidth:
- `18-20`: Near-lossless, best for 4K displays
- `21-23`: High quality, recommended for most TVs
- `24-28`: Good quality, lower bandwidth

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/hls/stream.m3u8` | HLS stream for media players |
| `/snapshot.jpg` | Single JPEG image |
| `/` | Web interface with live preview |
| `/health` | JSON health check status |

Default port: `8099`

## Device Setup

### Roku
Install "Roku Media Player" or any HLS-compatible channel and add the stream URL.

### Apple TV
Use any media player app that supports HLS streams.

### Chromecast / Google TV
Cast using a Home Assistant automation:
```yaml
service: media_player.play_media
target:
  entity_id: media_player.living_room_tv
data:
  media_content_id: "http://<your-ha-ip>:8099/hls/stream.m3u8"
  media_content_type: "video/mp4"
```

### Fire TV
Install VLC or any HLS-compatible app and open the network stream.

### VLC (Any Platform)
Media > Open Network Stream > Enter the stream URL.

## Home Assistant Automations

### Cast Dashboard on Motion
```yaml
automation:
  - alias: "Show dashboard on TV when motion detected"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_motion
        to: "on"
    action:
      - service: media_player.play_media
        target:
          entity_id: media_player.living_room_tv
        data:
          media_content_id: "http://<your-ha-ip>:8099/hls/stream.m3u8"
          media_content_type: "video/mp4"
```

### Cast Dashboard on Schedule
```yaml
automation:
  - alias: "Show morning dashboard"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: media_player.play_media
        target:
          entity_id: media_player.kitchen_tv
        data:
          media_content_id: "http://<your-ha-ip>:8099/hls/stream.m3u8"
          media_content_type: "video/mp4"
```

## Troubleshooting

### Stream not loading
- Check the health endpoint: `http://<your-ha-ip>:8099/health`
- Wait 10-15 seconds after starting for the first segments to generate
- Ensure port 8099 is accessible from your device

### High CPU usage
- Reduce `fps` to 3 or lower
- Increase `quality` value (e.g., 28)
- Reduce resolution to 1280x720

### Poor image quality
- Lower the `quality` value (e.g., 18-20)
- Ensure `width` and `height` match your TV resolution

### Sidebar and header still showing
- Ensure **kiosk-mode** is installed from HACS
- Set `kiosk_mode` to `true` in the add-on configuration
- Restart the add-on

### Dashboard shows light theme
- Set `dark_mode` to `true` in the add-on configuration
- Restart the add-on

### Authentication failed
- Verify your Long-Lived Access Token is correct
- Check add-on logs for error messages
- Create a new token if the old one was revoked

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Home Assistant](https://www.home-assistant.io/) for the amazing platform
- [kiosk-mode](https://github.com/NemesisRE/kiosk-mode) for the clean display functionality
