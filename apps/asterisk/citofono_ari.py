#!/usr/bin/env python3
"""Citofono Stasis app: Linphone 100 + Frigate cam_130_h264 via ExternalMedia."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets

LOG = logging.getLogger("citofono")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ARI_HOST = os.environ.get("ARI_HOST", "127.0.0.1")
ARI_PORT = os.environ.get("ARI_PORT", "8088")
ARI_USER = os.environ.get("ARI_USER", "citofono")
ARI_PASSWORD = os.environ["ARI_PASSWORD"]
APP = os.environ.get("STASIS_APP", "citofono")
RTSP_URL = os.environ.get("RTSP_URL", "rtsp://10.43.38.49:8554/cam_130_h264")
RING_HTTP_HOST = os.environ.get("RING_HTTP_HOST", "0.0.0.0")
RING_HTTP_PORT = int(os.environ.get("RING_HTTP_PORT", "8099"))
ENDPOINT = os.environ.get("SIP_ENDPOINT", "PJSIP/100")
CALLER_ID = os.environ.get("CALLER_ID", "Citofono <200>")
ORIGINATE_TIMEOUT = int(os.environ.get("ORIGINATE_TIMEOUT", "45"))

# phone_channel_id -> session
SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()


def _api_key() -> str:
    return f"{ARI_USER}:{ARI_PASSWORD}"


def ari_url(path: str, query: dict | None = None) -> str:
    q = dict(query or {})
    q["api_key"] = _api_key()
    return f"http://{ARI_HOST}:{ARI_PORT}/ari{path}?{urllib.parse.urlencode(q)}"


def ari_request(method: str, path: str, query: dict | None = None, data: dict | None = None):
    url = ari_url(path, query)
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        LOG.error("ARI %s %s -> %s %s", method, path, e.code, err)
        raise


def start_ffmpeg(rtp_host: str, rtp_port: str) -> subprocess.Popen:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        RTSP_URL,
        "-an",
        "-c:v",
        "copy",
        "-bsf:v",
        "h264_mp4toannexb,dump_extra",
        "-f",
        "rtp",
        "-payload_type",
        "96",
        f"rtp://{rtp_host}:{rtp_port}",
    ]
    LOG.info("starting ffmpeg RTP to %s:%s", rtp_host, rtp_port)
    logf = open('/tmp/ffmpeg-citofono.log', 'ab', buffering=0)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=logf)


def cleanup_session(phone_id: str) -> None:
    with LOCK:
        sess = SESSIONS.pop(phone_id, None)
    if not sess:
        return
    proc = sess.get("ffmpeg")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    em_id = sess.get("em_id")
    bridge_id = sess.get("bridge_id")
    if em_id:
        try:
            ari_request("DELETE", f"/channels/{em_id}")
        except Exception as e:
            LOG.warning("delete em %s: %s", em_id, e)
    if bridge_id:
        try:
            ari_request("DELETE", f"/bridges/{bridge_id}")
        except Exception as e:
            LOG.warning("delete bridge %s: %s", bridge_id, e)
    LOG.info("cleaned session for %s", phone_id)


def attach_video(phone_id: str) -> None:
    with LOCK:
        if phone_id in SESSIONS:
            LOG.info("video already attached to %s", phone_id)
            return
        SESSIONS[phone_id] = {}

    try:
        bridge = ari_request("POST", "/bridges", {"type": "mixing", "name": f"citofono-{phone_id[:8]}", "video_mode": "single_src"})
        bridge_id = bridge["id"]
        LOG.info("bridge created id=%s video_mode=%s", bridge_id, bridge.get("video_mode"))
        # Asterisk UDP ExternalMedia only supports connection_type=client (server needs websocket).
        # Asterisk allocates UNICASTRTP_LOCAL_* for us to send ffmpeg RTP into the bridge.
        em = ari_request(
            "POST",
            "/channels/externalMedia",
            {
                "app": APP,
                "external_host": "127.0.0.1:12000",
                "format": "h264",
                "encapsulation": "rtp",
                "transport": "udp",
                "connection_type": "client",
                "direction": "both",
                "channelVariables": "UNICASTRTP_LOCAL_ADDRESS,UNICASTRTP_LOCAL_PORT",
            },
        )
        em_id = em["id"]
        vars_ = em.get("channelvars") or {}
        rtp_host = vars_.get("UNICASTRTP_LOCAL_ADDRESS")
        rtp_port = vars_.get("UNICASTRTP_LOCAL_PORT")
        if not rtp_port:
            rtp_host = ari_request(
                "GET", f"/channels/{em_id}/variable", {"variable": "UNICASTRTP_LOCAL_ADDRESS"}
            )["value"]
            rtp_port = ari_request(
                "GET", f"/channels/{em_id}/variable", {"variable": "UNICASTRTP_LOCAL_PORT"}
            )["value"]
        if not rtp_host or rtp_host in ("0.0.0.0", "::"):
            rtp_host = "127.0.0.1"

        ari_request("POST", f"/bridges/{bridge_id}/addChannel", {"channel": phone_id})
        ari_request("POST", f"/bridges/{bridge_id}/addChannel", {"channel": em_id})
        try:
            ari_request("POST", f"/bridges/{bridge_id}/videoSource/{em_id}")
            LOG.info("set videoSource=%s on bridge=%s", em_id, bridge_id)
        except Exception as e:
            LOG.warning("set videoSource failed: %s", e)
        try:
            ari_request("POST", f"/channels/{phone_id}/progress")
        except Exception as e:
            LOG.info("progress (optional): %s", e)

        proc = start_ffmpeg(rtp_host, str(rtp_port))
        with LOCK:
            SESSIONS[phone_id] = {"bridge_id": bridge_id, "em_id": em_id, "ffmpeg": proc}
        LOG.info("video bridged phone=%s em=%s bridge=%s rtp=%s:%s", phone_id, em_id, bridge_id, rtp_host, rtp_port)
    except Exception:
        LOG.exception("attach_video failed for %s", phone_id)
        cleanup_session(phone_id)
        raise


def originate_ring() -> dict:
    # Hang up any previous citofono sessions first
    with LOCK:
        existing = list(SESSIONS.keys())
    for cid in existing:
        try:
            ari_request("DELETE", f"/channels/{cid}")
        except Exception:
            cleanup_session(cid)
    ch = ari_request(
        "POST",
        "/channels",
        {
            "endpoint": ENDPOINT,
            "app": APP,
            "callerId": CALLER_ID,
            "timeout": str(ORIGINATE_TIMEOUT),
            "formats": "ulaw,h264",
        },
    )
    LOG.info("originated ring channel %s", ch.get("id"))
    return ch


class RingHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        LOG.info("http " + fmt, *args)

    def _ok(self, payload: dict, code: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._ok({"ok": True})
            return
        if self.path.startswith("/ring"):
            try:
                ch = originate_ring()
                self._ok({"ok": True, "channel": ch.get("id")})
            except Exception as e:
                self._ok({"ok": False, "error": str(e)}, 500)
            return
        self._ok({"error": "not found"}, 404)

    def do_POST(self):
        self.do_GET()


def start_http():
    srv = ThreadingHTTPServer((RING_HTTP_HOST, RING_HTTP_PORT), RingHandler)
    LOG.info("ring HTTP on %s:%s", RING_HTTP_HOST, RING_HTTP_PORT)
    srv.serve_forever()


async def ari_events():
    q = urllib.parse.urlencode(
        {"app": APP, "api_key": _api_key(), "subscribeAll": "false"}
    )
    uri = f"ws://{ARI_HOST}:{ARI_PORT}/ari/events?{q}"
    while True:
        try:
            LOG.info("connecting ARI websocket")
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                LOG.info("ARI websocket connected app=%s", APP)
                async for raw in ws:
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    et = ev.get("type")
                    if et == "StasisStart":
                        ch = ev.get("channel") or {}
                        cid = ch.get("id")
                        name = ch.get("name", "")
                        # Ignore ExternalMedia channels entering Stasis
                        if name.startswith("UnicastRTP/") or name.startswith("AsyncGoto/"):
                            continue
                        args = ev.get("args") or []
                        LOG.info("StasisStart %s name=%s args=%s", cid, name, args)
                        try:
                            await asyncio.get_event_loop().run_in_executor(None, attach_video, cid)
                        except Exception:
                            LOG.exception("attach failed")
                    elif et in ("StasisEnd", "ChannelDestroyed"):
                        ch = ev.get("channel") or {}
                        cid = ch.get("id")
                        if cid:
                            await asyncio.get_event_loop().run_in_executor(None, cleanup_session, cid)
                    elif et == "ChannelStateChange":
                        ch = ev.get("channel") or {}
                        LOG.info("state %s -> %s", ch.get("name"), ch.get("state"))
        except Exception:
            LOG.exception("ARI websocket error; retry in 3s")
            await asyncio.sleep(3)


async def main():
    # Wait for ARI HTTP
    for i in range(60):
        try:
            ari_request("GET", "/asterisk/info")
            LOG.info("ARI HTTP ready")
            break
        except Exception as e:
            LOG.info("waiting ARI (%s): %s", i, e)
            await asyncio.sleep(2)
    else:
        raise SystemExit("ARI not available")

    threading.Thread(target=start_http, daemon=True).start()
    await ari_events()


if __name__ == "__main__":
    asyncio.run(main())
