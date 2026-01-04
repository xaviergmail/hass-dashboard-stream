#!/usr/bin/env python3
"""Dashboard Streams - Stream Home Assistant dashboards to smart TVs via HLS."""

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import signal
from pathlib import Path
from typing import Optional

from aiohttp import web
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from PIL import Image

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG_PATH = Path("/data/options.json")
HLS_DIR = Path("/tmp/hls")


class DashboardCapture:
    """Captures screenshots from Home Assistant dashboards."""

    def __init__(self, config: dict):
        self.config = config
        self.access_token = config.get("access_token", "")
        self.driver: Optional[webdriver.Chrome] = None
        self.lock = asyncio.Lock()
        self.kiosk_mode_detected: Optional[bool] = None
        self._last_frame_hash: Optional[int] = None

    def _create_driver(self) -> webdriver.Chrome:
        """Create a headless Chrome driver optimized for Pi."""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-default-apps")
        options.add_argument("--no-first-run")
        options.add_argument("--single-process")  # Reduce memory on Pi
        options.add_argument(
            f"--window-size={self.config.get('width', 1920)},{self.config.get('height', 1080)}"
        )
        options.add_argument("--hide-scrollbars")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")

        # Additional CPU optimization flags
        options.add_argument("--disable-animations")
        options.add_argument("--disable-canvas-aa")  # Disable canvas anti-aliasing
        options.add_argument("--disable-2d-canvas-clip-aa")
        options.add_argument("--disable-gl-drawing-for-tests")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-breakpad")  # Disable crash reporting
        options.add_argument("--disable-component-update")
        options.add_argument("--disable-domain-reliability")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-prompt-on-repost")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--memory-pressure-off")
        options.add_argument("--js-flags=--max-old-space-size=128")  # Limit JS heap

        options.binary_location = "/usr/bin/chromium-browser"

        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)

    async def start(self):
        """Start the browser and navigate to the dashboard."""
        loop = asyncio.get_event_loop()
        self.driver = await loop.run_in_executor(None, self._create_driver)

        # Force dark mode via CDP if enabled
        if self.config.get("dark_mode", True):
            await loop.run_in_executor(
                None,
                lambda: self.driver.execute_cdp_cmd(
                    "Emulation.setEmulatedMedia",
                    {"features": [{"name": "prefers-color-scheme", "value": "dark"}]},
                ),
            )
            logger.info("Dark mode enabled via CDP")

        await self._navigate_to_dashboard()
        logger.info("Dashboard capture started")

    async def _get_ha_url(self) -> str:
        """Get the Home Assistant URL from Supervisor API."""
        import aiohttp

        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        if not supervisor_token:
            logger.warning("No SUPERVISOR_TOKEN, falling back to default HA URL")
            return "http://homeassistant:8123"

        headers = {
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # First try to get the configured external/internal URL from HA config
                async with session.get(
                    "http://supervisor/core/api/config",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Try internal_url first, then external_url
                        internal_url = data.get("internal_url")
                        external_url = data.get("external_url")

                        if internal_url:
                            logger.info(
                                f"Using internal_url from HA config: {internal_url}"
                            )
                            return internal_url.rstrip("/")
                        elif external_url:
                            logger.info(
                                f"Using external_url from HA config: {external_url}"
                            )
                            return external_url.rstrip("/")

                # Fallback: Get Home Assistant info from Supervisor
                async with session.get(
                    "http://supervisor/core/info",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        info = data.get("data", data)
                        ip = info.get("ip_address", "homeassistant")
                        port = info.get("port", 8123)
                        ssl = info.get("ssl", False)

                        scheme = "https" if ssl else "http"
                        url = f"{scheme}://{ip}:{port}"
                        logger.info(f"Got HA URL from Supervisor info: {url}")
                        return url
                    else:
                        logger.warning(f"Failed to get HA info: {resp.status}")
        except Exception as e:
            logger.warning(f"Error getting HA URL: {e}")

        return "http://homeassistant:8123"

    async def _navigate_to_dashboard(self):
        """Navigate to the Home Assistant dashboard."""
        dashboard_url = self.config["dashboard_url"]
        kiosk_mode = self.config.get("kiosk_mode", True)

        # Append ?kiosk if kiosk_mode is enabled and not already present
        if kiosk_mode and "kiosk" not in dashboard_url:
            if "?" in dashboard_url:
                dashboard_url = f"{dashboard_url}&kiosk"
            else:
                dashboard_url = f"{dashboard_url}?kiosk"
            logger.info(f"Kiosk mode enabled, URL: {dashboard_url}")

        # Determine the base URL and full URL
        if dashboard_url.startswith("http://") or dashboard_url.startswith("https://"):
            # External URL (for testing or external dashboards)
            full_url = dashboard_url
            base_url = "/".join(full_url.split("/")[:3])
        elif dashboard_url.startswith("/"):
            # Relative path - get HA URL from Supervisor
            base_url = await self._get_ha_url()
            full_url = f"{base_url}{dashboard_url}"
        else:
            full_url = dashboard_url
            base_url = None

        # Use the long-lived access token we created
        token = self.access_token

        loop = asyncio.get_event_loop()

        def navigate():
            import time
            from urllib.parse import urlparse

            if token and base_url:
                logger.info(f"Setting up authentication for {base_url}")

                # Parse the base URL to get the canonical form (without default port)
                parsed = urlparse(base_url)
                # Build canonical URL without explicit port if it's the default
                if (parsed.scheme == "https" and parsed.port == 443) or (
                    parsed.scheme == "http" and parsed.port == 80
                ):
                    canonical_url = f"{parsed.scheme}://{parsed.hostname}"
                else:
                    canonical_url = base_url.rstrip("/")

                logger.info(f"Canonical URL for auth: {canonical_url}")

                # Navigate to base URL first to set up the origin
                self.driver.get(base_url)
                time.sleep(3)

                # Inject the long-lived access token into localStorage
                # Use both the original URL and canonical URL formats
                try:
                    self.driver.execute_script(f"""
                        // Store token in the format HA frontend expects
                        // Try multiple URL formats to match what HA might use
                        const urls = ["{base_url}", "{canonical_url}", "{canonical_url}/"];
                        
                        for (const hassUrl of urls) {{
                            const tokenData = {{
                                hassUrl: hassUrl,
                                clientId: hassUrl.endsWith('/') ? hassUrl : hassUrl + '/',
                                expires: Date.now() + 315360000000,
                                refresh_token: "",
                                access_token: "{token}",
                                expires_in: 315360000,
                                token_type: "Bearer"
                            }};
                            localStorage.setItem("hassTokens", JSON.stringify(tokenData));
                        }}
                        
                        console.log("Token injected for multiple URL formats");
                    """)
                    logger.info("Token injected into localStorage")
                except Exception as e:
                    logger.warning(f"Failed to inject token: {e}")

                # Reload to pick up the token
                time.sleep(1)
                self.driver.refresh()
                time.sleep(3)

            logger.info(f"Navigating to: {full_url}")
            self.driver.get(full_url)

            # Wait for page to load
            time.sleep(8)

            # Log debug info
            current_url = self.driver.current_url
            logger.info(f"Current URL: {current_url}")
            logger.info(f"Page title: {self.driver.title}")

            # Check if we hit the login page
            if "auth" in current_url:
                logger.warning("Authentication may have failed - URL contains 'auth'")

                # If we're on the auth page, try to inject token and redirect
                try:
                    # Get what HA thinks the hassUrl should be from the state parameter
                    import base64
                    import json as json_module
                    from urllib.parse import parse_qs, urlparse as url_parse

                    parsed_url = url_parse(current_url)
                    params = parse_qs(parsed_url.query)
                    if "state" in params:
                        state_data = json_module.loads(
                            base64.b64decode(params["state"][0])
                        )
                        ha_url = state_data.get("hassUrl", "")
                        client_id = state_data.get("clientId", "")
                        logger.info(
                            f"HA expects hassUrl: {ha_url}, clientId: {client_id}"
                        )

                        # Re-inject with the exact URL HA expects
                        self.driver.execute_script(f"""
                            const tokenData = {{
                                hassUrl: "{ha_url}",
                                clientId: "{client_id}",
                                expires: Date.now() + 315360000000,
                                refresh_token: "",
                                access_token: "{token}",
                                expires_in: 315360000,
                                token_type: "Bearer"
                            }};
                            localStorage.setItem("hassTokens", JSON.stringify(tokenData));
                            console.log("Re-injected token with correct hassUrl");
                        """)

                        # Navigate back to the dashboard
                        time.sleep(1)
                        self.driver.get(full_url)
                        time.sleep(5)

                        logger.info(f"After re-auth, URL: {self.driver.current_url}")
                except Exception as e:
                    logger.warning(f"Failed to re-inject token: {e}")

        await loop.run_in_executor(None, navigate)
        logger.info(f"Navigated to dashboard: {full_url}")

        # Inject auto-refresh script for dashboard updates
        await self._inject_auto_refresh()

        # Check if kiosk-mode is installed (after page load)
        await self._check_kiosk_mode()

    async def _inject_auto_refresh(self):
        """Inject JavaScript to auto-refresh when dashboard is updated."""
        loop = asyncio.get_event_loop()

        def inject():
            try:
                self.driver.execute_script("""
                    (function() {
                        // Avoid duplicate injection
                        if (window.__dashboardAutoRefreshActive) return;
                        window.__dashboardAutoRefreshActive = true;
                        
                        console.log('[Dashboard Streams] Setting up auto-refresh on dashboard updates...');
                        
                        // Get the hass object from the DOM
                        function getHassConnection() {
                            const haRoot = document.querySelector('home-assistant');
                            return haRoot?.__hass?.connection || haRoot?.hass?.connection;
                        }
                        
                        function subscribeToUpdates() {
                            const connection = getHassConnection();
                            if (!connection) {
                                // Retry in 1 second if not ready yet
                                console.log('[Dashboard Streams] Waiting for hass connection...');
                                setTimeout(subscribeToUpdates, 1000);
                                return;
                            }
                            
                            console.log('[Dashboard Streams] Found hass connection, subscribing to lovelace_updated...');
                            
                            connection.subscribeEvents((event) => {
                                console.log('[Dashboard Streams] Dashboard updated, refreshing...', event);
                                location.reload();
                            }, 'lovelace_updated').then(() => {
                                console.log('[Dashboard Streams] Subscribed to lovelace_updated events');
                            }).catch((err) => {
                                console.error('[Dashboard Streams] Failed to subscribe:', err);
                            });
                        }
                        
                        // Start subscription attempt
                        subscribeToUpdates();
                    })();
                """)
                logger.info("Auto-refresh script injected")
            except Exception as e:
                logger.warning(f"Failed to inject auto-refresh script: {e}")

        await loop.run_in_executor(None, inject)

    async def _check_kiosk_mode(self):
        """Check if kiosk-mode HACS integration is installed via HA API."""
        import aiohttp

        # Use SUPERVISOR_TOKEN for Supervisor API calls
        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        if not supervisor_token:
            logger.warning(
                "No SUPERVISOR_TOKEN - cannot check for kiosk-mode installation"
            )
            self.kiosk_mode_detected = None
            return

        # Supervisor API to proxy to Home Assistant Core API
        base_url = "http://supervisor/core/api"
        headers = {
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Method 1: Check Lovelace resources for kiosk-mode
                async with session.get(
                    f"{base_url}/lovelace/resources",
                    headers=headers,
                ) as resp:
                    logger.info(f"Lovelace resources API status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        resources = (
                            data if isinstance(data, list) else data.get("result", [])
                        )
                        logger.info(f"Lovelace resources: {resources}")
                        for resource in resources:
                            url = resource.get("url", "")
                            if "kiosk-mode" in url.lower():
                                logger.info(
                                    f"Kiosk-mode found in Lovelace resources: {url}"
                                )
                                self.kiosk_mode_detected = True
                                return
                    else:
                        body = await resp.text()
                        logger.warning(
                            f"Lovelace resources API returned {resp.status}: {body}"
                        )

                # Method 2: Check HACS installed packages (if HACS websocket not available, try states)
                async with session.get(
                    f"{base_url}/states",
                    headers=headers,
                ) as resp:
                    logger.info(f"States API status: {resp.status}")
                    if resp.status == 200:
                        states = await resp.json()
                        for state in states:
                            entity_id = state.get("entity_id", "")
                            # HACS creates update entities for installed packages
                            if (
                                "kiosk" in entity_id.lower()
                                and "mode" in entity_id.lower()
                            ):
                                logger.info(f"Kiosk-mode found via entity: {entity_id}")
                                self.kiosk_mode_detected = True
                                return
                            # Also check attributes for HACS sensors
                            attrs = state.get("attributes", {})
                            if "kiosk-mode" in str(attrs).lower():
                                logger.info(
                                    f"Kiosk-mode found in entity attributes: {entity_id}"
                                )
                                self.kiosk_mode_detected = True
                                return

            # If we got here, kiosk-mode wasn't found
            logger.warning("Kiosk-mode not found via API")
            self.kiosk_mode_detected = False

        except Exception as e:
            logger.warning(f"Error checking for kiosk-mode via API: {e}")
            self.kiosk_mode_detected = None

    async def capture_frame(self) -> tuple[bytes, bool]:
        """Capture a PNG screenshot of the current dashboard.

        Returns:
            Tuple of (png_data, is_new_frame) - is_new_frame is False if identical to last frame
        """
        async with self.lock:
            loop = asyncio.get_event_loop()

            def take_screenshot() -> bytes:
                return self.driver.get_screenshot_as_png()

            png_data = await loop.run_in_executor(None, take_screenshot)

            # Quick hash to detect duplicate frames (saves CPU on encoding)
            frame_hash = hash(png_data)
            is_new = frame_hash != self._last_frame_hash
            self._last_frame_hash = frame_hash

            return png_data, is_new

    async def refresh(self):
        """Refresh the current page in the browser."""
        if self.driver:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.refresh)
            logger.info("Dashboard page refreshed")
            return True
        return False

    async def stop(self):
        """Stop the browser."""
        if self.driver:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.quit)
            self.driver = None
            logger.info("Dashboard capture stopped")


class HLSEncoder:
    """Encodes captured frames into HLS stream using FFmpeg."""

    def __init__(self, config: dict):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.running = False

    def start(self):
        """Start the FFmpeg HLS encoder process."""
        # Clean up old segments
        if HLS_DIR.exists():
            shutil.rmtree(HLS_DIR)
        HLS_DIR.mkdir(parents=True, exist_ok=True)

        # FFmpeg command optimized for LOW LATENCY live streaming
        # Target: ~3-5 second delay
        segment_time = self.config.get("segment_duration", 2)  # Short segments
        fps = self.config.get("fps", 5)
        quality = self.config.get("quality", 23)

        cmd = [
            "ffmpeg",
            "-y",
            # Video input from screenshots
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-r",
            str(fps),
            "-i",
            "-",
            # Silent audio track (required for Roku compatibility)
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            # Video encoding - Roku compatible settings
            "-c:v",
            "libx264",
            "-profile:v",
            "main",  # Roku requires baseline or main profile
            "-level",
            "4.0",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-crf",
            str(quality),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-g",
            str(fps * 2),  # Keyframe every 2 seconds
            "-sc_threshold",
            "0",
            # Audio encoding (silent)
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            "-shortest",  # End when video ends
            # HLS output settings
            "-f",
            "hls",
            "-hls_time",
            str(segment_time),
            "-hls_list_size",
            "6",  # More segments for Roku stability
            "-hls_flags",
            "delete_segments+discont_start+omit_endlist",
            "-hls_segment_type",
            "mpegts",
            "-hls_segment_filename",
            str(HLS_DIR / "segment_%03d.ts"),
            str(HLS_DIR / "stream.m3u8"),
        ]

        logger.info(f"Starting FFmpeg: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.running = True

        # Start a thread to log FFmpeg stderr
        import threading

        def log_ffmpeg_stderr():
            for line in self.process.stderr:
                logger.info(f"FFmpeg: {line.decode().strip()}")

        threading.Thread(target=log_ffmpeg_stderr, daemon=True).start()

        logger.info("HLS encoder started")

    def write_frame(self, png_data: bytes):
        """Write a PNG frame to FFmpeg."""
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(png_data)
                self.process.stdin.flush()
            except BrokenPipeError:
                # Log FFmpeg error before restarting
                if self.process and self.process.stderr:
                    stderr = self.process.stderr.read()
                    if stderr:
                        logger.error(f"FFmpeg error: {stderr.decode()}")
                logger.error("FFmpeg pipe broken, restarting encoder")
                self.restart()

    def restart(self):
        """Restart the encoder."""
        self.stop()
        self.start()

    def stop(self):
        """Stop the FFmpeg process."""
        self.running = False
        if self.process:
            self.process.stdin.close()
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info("HLS encoder stopped")


class StreamServer:
    """HTTP server providing HLS streaming endpoints."""

    def __init__(self, capture: DashboardCapture, encoder: HLSEncoder, config: dict):
        self.capture = capture
        self.encoder = encoder
        self.config = config
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/stream.m3u8", self.handle_playlist)
        self.app.router.add_get("/segment_{name}.ts", self.handle_segment)
        self.app.router.add_get("/snapshot.jpg", self.handle_snapshot)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/api/kiosk-status", self.handle_kiosk_status)
        self.app.router.add_post("/api/refresh", self.handle_refresh)
        # Serve HLS files directly
        self.app.router.add_static("/hls/", HLS_DIR, show_index=False)

    async def handle_index(self, request: web.Request) -> web.Response:
        """Serve the index page with stream info."""
        # Build the stream URL based on the request
        # This handles both direct access (:8099) and ingress access (via HA)
        host = request.host
        scheme = request.scheme

        # Check if accessed via ingress (X-Ingress-Path header)
        ingress_path = request.headers.get("X-Ingress-Path", "")
        if ingress_path:
            # Accessed via HA ingress - use relative URL
            stream_url = f"{ingress_path}/hls/stream.m3u8"
            base_url = ingress_path
        else:
            # Direct access - use absolute URL with port 8099
            stream_url = "/hls/stream.m3u8"
            base_url = ""

        kiosk_enabled = self.config.get("kiosk_mode", True)
        kiosk_detected = self.capture.kiosk_mode_detected

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard Streams</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               margin: 0; padding: 40px; background: #1c1c1c; color: #e0e0e0; }}
        h1 {{ color: #03a9f4; margin-bottom: 10px; }}
        .subtitle {{ color: #888; margin-bottom: 30px; }}
        .endpoint {{ background: #2d2d2d; padding: 20px; margin: 15px 0; border-radius: 8px; 
                    border-left: 4px solid #03a9f4; }}
        .endpoint h3 {{ margin-top: 0; color: #fff; }}
        code {{ background: #3d3d3d; padding: 4px 10px; border-radius: 4px; 
               font-family: 'SF Mono', Monaco, monospace; color: #4fc3f7; }}
        a {{ color: #03a9f4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .preview {{ margin-top: 30px; }}
        video {{ max-width: 100%; border-radius: 8px; background: #000; }}
        .config {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                  gap: 15px; margin-top: 20px; }}
        .config-item {{ background: #2d2d2d; padding: 15px; border-radius: 8px; }}
        .config-item label {{ color: #888; font-size: 12px; text-transform: uppercase; }}
        .config-item value {{ font-size: 18px; color: #fff; display: block; margin-top: 5px; }}
        .btn {{ background: #03a9f4; color: #fff; border: none; padding: 12px 24px; 
               border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500;
               transition: background 0.2s; }}
        .btn:hover {{ background: #0288d1; }}
        .btn:active {{ background: #0277bd; }}
        .btn:disabled {{ background: #555; cursor: not-allowed; }}
        .actions {{ margin-top: 20px; display: flex; gap: 10px; align-items: center; }}
        .action-status {{ color: #888; font-size: 14px; }}
        
        .kiosk-notice {{
            background: #2d2d2d;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #ff9800;
        }}
        .kiosk-notice a {{
            color: #4fc3f7;
        }}
    </style>
</head>
<body>
    <h1>Dashboard Streams</h1>
    <p class="subtitle">Stream your Home Assistant dashboard to any device</p>
    
    <!-- Kiosk Mode Notice (only shown if enabled but not detected) -->
    {f'<div class="kiosk-notice">Kiosk mode not detected. Install <a href="https://github.com/NemesisRE/kiosk-mode" target="_blank">kiosk-mode</a> to hide sidebar and header.</div>' if kiosk_enabled and kiosk_detected is False else ""}
    
    <h2>HLS Stream Endpoints</h2>
    
    <div class="endpoint">
        <h3>HLS Playlist (Primary)</h3>
        <p><code>GET /hls/stream.m3u8</code></p>
        <p>Use this URL in Roku, Apple TV, Chromecast, VLC, or any HLS-compatible player.</p>
        <p>Full URL: <code>http://{host}/hls/stream.m3u8</code></p>
    </div>
    
    <div class="endpoint">
        <h3>Single Snapshot</h3>
        <p><code>GET /snapshot.jpg</code></p>
        <p>Returns a single JPEG image. Useful for thumbnails or automations.</p>
        <p><a href="{base_url}/snapshot.jpg">Get Snapshot</a></p>
    </div>
    
    <h2>Configuration</h2>
    <div class="config">
        <div class="config-item">
            <label>Dashboard</label>
            <value>{self.config["dashboard_url"]}</value>
        </div>
        <div class="config-item">
            <label>Kiosk Mode</label>
            <value>{"Enabled" if kiosk_enabled else "Disabled"}</value>
        </div>
        <div class="config-item">
            <label>Resolution</label>
            <value>{self.config.get("width", 1920)}x{self.config.get("height", 1080)}</value>
        </div>
        <div class="config-item">
            <label>Quality (CRF)</label>
            <value>{self.config.get("quality", 23)}</value>
        </div>
        <div class="config-item">
            <label>FPS</label>
            <value>{self.config.get("fps", 5)}</value>
        </div>
        <div class="config-item">
            <label>Segment Duration</label>
            <value>{self.config.get("segment_duration", 2)}s</value>
        </div>
    </div>
    
    <div class="actions">
        <button class="btn" id="refreshBtn" onclick="refreshDashboard()">Refresh Dashboard</button>
        <span class="action-status" id="refreshStatus"></span>
    </div>
    
    <div class="preview">
        <h2>Live Preview</h2>
        <video id="video" controls autoplay muted></video>
    </div>
    
    <script>
        const video = document.getElementById('video');
        const streamUrl = '{stream_url}';
        const baseUrl = '{base_url}';
        const segmentDuration = {self.config.get("segment_duration", 2)};
        
        async function refreshDashboard() {{
            const btn = document.getElementById('refreshBtn');
            const status = document.getElementById('refreshStatus');
            
            btn.disabled = true;
            status.textContent = 'Refreshing...';
            status.style.color = '#888';
            
            try {{
                const response = await fetch(baseUrl + '/api/refresh', {{ method: 'POST' }});
                const data = await response.json();
                
                if (data.success) {{
                    status.textContent = 'Dashboard refreshed!';
                    status.style.color = '#4caf50';
                }} else {{
                    status.textContent = data.message || 'Refresh failed';
                    status.style.color = '#f44336';
                }}
            }} catch (err) {{
                status.textContent = 'Error: ' + err.message;
                status.style.color = '#f44336';
            }}
            
            btn.disabled = false;
            setTimeout(() => {{ status.textContent = ''; }}, 3000);
        }}
        
        if (Hls.isSupported()) {{
            const hls = new Hls({{
                lowLatencyMode: true,
                liveSyncDuration: segmentDuration,
                liveMaxLatencyDuration: segmentDuration * 3,
                liveDurationInfinity: true,
                highBufferWatchdogPeriod: 1,
            }});
            hls.loadSource(streamUrl);
            hls.attachMedia(video);
            // Jump to live edge on play
            video.addEventListener('play', () => {{
                if (hls.liveSyncPosition) {{
                    video.currentTime = hls.liveSyncPosition;
                }}
            }});
        }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
            // Native HLS support (Safari)
            video.src = streamUrl;
        }}
    </script>
</body>
</html>
"""
        return web.Response(text=html, content_type="text/html")

    async def handle_playlist(self, request: web.Request) -> web.Response:
        """Serve the HLS playlist file."""
        playlist_path = HLS_DIR / "stream.m3u8"
        if not playlist_path.exists():
            return web.Response(status=503, text="Stream not ready yet")

        return web.FileResponse(
            playlist_path,
            headers={
                "Content-Type": "application/vnd.apple.mpegurl",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def handle_segment(self, request: web.Request) -> web.Response:
        """Serve HLS segment files."""
        name = request.match_info["name"]
        segment_path = HLS_DIR / f"segment_{name}.ts"

        if not segment_path.exists():
            return web.Response(status=404, text="Segment not found")

        return web.FileResponse(
            segment_path,
            headers={
                "Content-Type": "video/mp2t",
                "Cache-Control": "max-age=3600",
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def handle_snapshot(self, request: web.Request) -> web.Response:
        """Handle single snapshot requests."""
        png_data, _ = await self.capture.capture_frame()

        # Convert PNG to JPEG (must convert RGBA to RGB first)
        img = Image.open(io.BytesIO(png_data))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)

        return web.Response(
            body=output.getvalue(),
            content_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        playlist_exists = (HLS_DIR / "stream.m3u8").exists()
        return web.json_response(
            {
                "status": "healthy" if playlist_exists else "starting",
                "encoder_running": self.encoder.running,
                "stream_ready": playlist_exists,
            }
        )

    async def handle_kiosk_status(self, request: web.Request) -> web.Response:
        """Return kiosk-mode detection status."""
        kiosk_enabled = self.config.get("kiosk_mode", True)
        return web.json_response(
            {
                "kiosk_mode_enabled": kiosk_enabled,
                "kiosk_mode_detected": self.capture.kiosk_mode_detected,
                "needs_install": kiosk_enabled
                and self.capture.kiosk_mode_detected is False,
            }
        )

    async def handle_refresh(self, request: web.Request) -> web.Response:
        """Trigger a page refresh in the browser."""
        success = await self.capture.refresh()
        return web.json_response(
            {
                "success": success,
                "message": "Dashboard refreshed"
                if success
                else "Browser not available",
            },
            status=200 if success else 503,
        )


async def capture_loop(capture: DashboardCapture, encoder: HLSEncoder, config: dict):
    """Main loop that captures frames and feeds them to the encoder."""
    fps = config.get("fps", 2)
    frame_interval = 1.0 / fps
    frame_count = 0
    skipped_frames = 0
    last_log_time = 0

    logger.info(f"Starting capture loop at {fps} fps ({frame_interval:.3f}s interval)")

    while encoder.running:
        try:
            start_time = asyncio.get_event_loop().time()

            # Capture frame
            png_data, is_new = await capture.capture_frame()
            frame_count += 1

            # Only encode if frame changed (saves significant CPU)
            if is_new:
                encoder.write_frame(png_data)
            else:
                skipped_frames += 1

            # Log every 30 seconds to reduce log spam
            if start_time - last_log_time >= 30:
                logger.info(
                    f"Frames: {frame_count} captured, {skipped_frames} skipped (unchanged)"
                )
                last_log_time = start_time

            # Wait for next frame, accounting for capture time
            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in capture loop: {e}", exc_info=True)
            await asyncio.sleep(0.1)


async def main():
    """Main entry point."""
    # Load configuration
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    else:
        config = {}

    # Apply defaults for optional settings
    # Optimized for low CPU usage on Raspberry Pi
    defaults = {
        "dashboard_url": "/lovelace/0",
        "kiosk_mode": True,
        "dark_mode": True,
        "width": 1920,
        "height": 1080,
        "quality": 28,  # Higher = lower quality but much less CPU (was 23)
        "fps": 2,  # 2 FPS is enough for dashboards (was 5)
        "segment_duration": 4,  # Longer segments = less overhead (was 2)
    }
    for key, value in defaults.items():
        if key not in config:
            config[key] = value

    # Don't log the access token
    config_log = {k: v for k, v in config.items() if k != "access_token"}
    config_log["access_token"] = "***" if config.get("access_token") else "(not set)"
    logger.info(
        f"Starting Dashboard Streams with config: {json.dumps(config_log, indent=2)}"
    )

    # Check for access token
    if not config.get("access_token"):
        logger.warning(
            "No access_token configured! "
            "Create a Long-Lived Access Token in your HA profile and add it to the add-on configuration."
        )

    # Create components
    capture = DashboardCapture(config)
    encoder = HLSEncoder(config)
    server = StreamServer(capture, encoder, config)

    # Start capture
    await capture.start()

    # Start encoder
    encoder.start()

    # Start capture loop
    capture_task = asyncio.create_task(capture_loop(capture, encoder, config))

    # Start HTTP server
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8099)
    await site.start()
    logger.info("Stream server running on http://0.0.0.0:8099")

    # Wait for first HLS segment and notify s6 we're ready
    async def notify_ready():
        playlist_path = Path("/tmp/hls/stream.m3u8")
        while not playlist_path.exists():
            await asyncio.sleep(0.5)
        # Notify s6 via fd 3
        try:
            with os.fdopen(3, "w") as f:
                f.write("\n")
            logger.info("Notified s6 that service is ready")
        except OSError:
            # fd 3 not available (not running under s6)
            logger.debug("fd 3 not available, skipping s6 notification")

    asyncio.create_task(notify_ready())

    # Handle shutdown
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_handler)

    # Wait for shutdown
    await stop_event.wait()

    # Cleanup
    capture_task.cancel()
    try:
        await capture_task
    except asyncio.CancelledError:
        pass

    encoder.stop()
    await capture.stop()
    await runner.cleanup()

    logger.info("Dashboard Streams stopped")


if __name__ == "__main__":
    asyncio.run(main())
