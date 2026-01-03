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
            # Relative path - use direct HA connection
            base_url = "http://homeassistant.local.hass.io:8123"
            full_url = f"{base_url}{dashboard_url}"
        else:
            full_url = dashboard_url
            base_url = None

        # Use the long-lived access token we created
        token = self.access_token

        loop = asyncio.get_event_loop()

        def navigate():
            import time

            if token and base_url:
                logger.info(f"Setting up authentication for {base_url}")

                # First navigate to base URL to initialize the page
                self.driver.get(base_url)
                time.sleep(2)

                # Inject the long-lived access token into localStorage
                # Format based on HA frontend's auth storage
                self.driver.execute_script(f"""
                    // Store token in the format HA frontend expects
                    const tokenData = {{
                        hassUrl: "{base_url}",
                        clientId: "{base_url}/",
                        expires: Date.now() + 315360000000,  // 10 years (long-lived token)
                        refresh_token: "",
                        access_token: "{token}",
                        expires_in: 315360000,
                        token_type: "Bearer"
                    }};
                    localStorage.setItem("hassTokens", JSON.stringify(tokenData));
                    console.log("Token injected:", tokenData.hassUrl);
                """)

                logger.info("Token injected, refreshing page")
                time.sleep(1)

            logger.info(f"Navigating to: {full_url}")
            self.driver.get(full_url)

            # Wait for page to load
            time.sleep(5)

            # Log debug info
            logger.info(f"Current URL: {self.driver.current_url}")
            logger.info(f"Page title: {self.driver.title}")

            # Check if we hit the login page
            if "auth" in self.driver.current_url:
                logger.warning("Authentication may have failed - URL contains 'auth'")
                try:
                    body_text = self.driver.find_element("tag name", "body").text[:500]
                    logger.warning(f"Page content: {body_text}")
                except:
                    pass

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
            return

        # Use Supervisor API to talk to Home Assistant
        base_url = "http://supervisor/core/api"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Query HACS installed repositories via frontend/extra_modules or check for kiosk-mode resources
                # Method 1: Check Lovelace resources for kiosk-mode
                async with session.get(
                    f"{base_url}/lovelace/resources",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        resources = await resp.json()
                        # Look for kiosk-mode in the resources
                        for resource in resources:
                            url = resource.get("url", "")
                            if "kiosk-mode" in url.lower():
                                logger.info(
                                    f"Kiosk-mode found in Lovelace resources: {url}"
                                )
                                self.kiosk_mode_detected = True
                                return
                    else:
                        logger.debug(f"Lovelace resources API returned {resp.status}")

                # Method 2: Check frontend extra_module_url in HA config
                async with session.get(
                    f"{base_url}/config",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        config = await resp.json()
                        # Check frontend config for kiosk-mode
                        frontend = config.get("frontend", {})
                        extra_modules = frontend.get("extra_module_url", [])
                        for url in extra_modules:
                            if "kiosk-mode" in url.lower():
                                logger.info(
                                    f"Kiosk-mode found in frontend config: {url}"
                                )
                                self.kiosk_mode_detected = True
                                return

            # If we got here, kiosk-mode wasn't found
            logger.warning(
                "Kiosk-mode not found in Lovelace resources or frontend config"
            )
            self.kiosk_mode_detected = False

        except Exception as e:
            logger.warning(f"Error checking for kiosk-mode via API: {e}")
            self.kiosk_mode_detected = None

    async def capture_frame(self) -> bytes:
        """Capture a PNG screenshot of the current dashboard."""
        async with self.lock:
            loop = asyncio.get_event_loop()

            def take_screenshot() -> bytes:
                return self.driver.get_screenshot_as_png()

            return await loop.run_in_executor(None, take_screenshot)

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
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-r",
            str(fps),
            "-i",
            "-",
            # Video encoding - low latency settings
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",  # Changed from stillimage to zerolatency
            "-crf",
            str(quality),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-g",
            str(fps),  # Keyframe every second (faster segment start)
            "-sc_threshold",
            "0",
            # Low latency HLS settings
            "-f",
            "hls",
            "-hls_time",
            str(segment_time),  # 2 second segments
            "-hls_list_size",
            "3",  # Minimal playlist (3 x 2s = 6s)
            "-hls_flags",
            "delete_segments+discont_start+omit_endlist+split_by_time",
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
        <p>Full URL: <code>http://&lt;your-ha-ip&gt;:8099/hls/stream.m3u8</code></p>
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
    
    <div class="preview">
        <h2>Live Preview</h2>
        <video id="video" controls autoplay muted></video>
    </div>
    
    <script>
        const video = document.getElementById('video');
        const streamUrl = '{stream_url}';
        const baseUrl = '{base_url}';
        const segmentDuration = {self.config.get("segment_duration", 2)};
        
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
        png_data = await self.capture.capture_frame()

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


async def capture_loop(capture: DashboardCapture, encoder: HLSEncoder, config: dict):
    """Main loop that captures frames and feeds them to the encoder."""
    fps = config.get("fps", 10)
    frame_interval = 1.0 / fps
    frame_count = 0

    logger.info(f"Starting capture loop at {fps} fps ({frame_interval:.3f}s interval)")

    while encoder.running:
        try:
            start_time = asyncio.get_event_loop().time()

            # Capture frame
            png_data = await capture.capture_frame()
            frame_count += 1

            # Feed to encoder
            encoder.write_frame(png_data)

            # Log periodically (every second at 10fps)
            if frame_count % fps == 0:
                hls_files = list(HLS_DIR.glob("*"))
                logger.info(
                    f"Captured {frame_count} frames, HLS files: {[f.name for f in hls_files]}"
                )

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
    defaults = {
        "dashboard_url": "/lovelace/0",
        "kiosk_mode": True,
        "dark_mode": True,
        "width": 1920,
        "height": 1080,
        "quality": 23,
        "fps": 5,
        "segment_duration": 2,  # Short segments for low latency
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
