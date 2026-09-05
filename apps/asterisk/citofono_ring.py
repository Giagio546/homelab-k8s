#!/usr/bin/env python3
from __future__ import annotations
import json, logging, os, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = logging.getLogger("citofono-ring")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AMI_HOST = os.environ.get("AMI_HOST", "127.0.0.1")
AMI_PORT = int(os.environ.get("AMI_PORT", "5038"))
AMI_USER = os.environ.get("AMI_USER", "ha")
AMI_SECRET = os.environ["AMI_SECRET"]
RING_HOST = os.environ.get("RING_HTTP_HOST", "0.0.0.0")
RING_PORT = int(os.environ.get("RING_HTTP_PORT", "8099"))
PHONE = os.environ.get("SIP_PHONE", "PJSIP/100")
CAMERA = os.environ.get("SIP_CAMERA", "PJSIP/300")
BRIDGE = os.environ.get("CONFBRIDGE", "1")


def ami_command(actions):
    chunks = []
    for a in actions:
        for k, v in a.items():
            chunks.append(f"{k}: {v}")
        chunks.append("")
    payload = "\r\n".join(chunks) + "\r\n"
    with socket.create_connection((AMI_HOST, AMI_PORT), timeout=5) as s:
        s.sendall(payload.encode("ascii"))
        s.settimeout(3)
        data = b""
        try:
            while True:
                part = s.recv(4096)
                if not part:
                    break
                data += part
                if b"Response: Goodbye" in data or data.count(b"Response:") >= 3:
                    break
        except socket.timeout:
            pass
    return data.decode("ascii", "replace")


def originate_confbridge():
    login = {"Action": "Login", "Username": AMI_USER, "Secret": AMI_SECRET}
    phone = {
        "Action": "Originate",
        "Channel": PHONE,
        "Application": "ConfBridge",
        "Data": f"{BRIDGE},citofono_bridge,citofono_user",
        "CallerID": "Citofono <200>",
        "Async": "true",
        "Timeout": "45000",
    }
    cam = {
        "Action": "Originate",
        "Channel": CAMERA,
        "Application": "ConfBridge",
        "Data": f"{BRIDGE},citofono_bridge,citofono_cam",
        "CallerID": "CamPortone <300>",
        "Async": "true",
        "Timeout": "15000",
    }
    logoff = {"Action": "Logoff"}
    raw = ami_command([login, phone, cam, logoff])
    if "Authentication accepted" not in raw or "Originate successfully queued" not in raw:
        raise RuntimeError(raw[:800])
    return {"ok": True, "ami": "queued"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        LOG.info("http " + fmt, *args)

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True})
        if self.path.startswith("/ring"):
            try:
                return self._send(200, originate_confbridge())
            except Exception as e:
                LOG.exception("ring failed")
                return self._send(500, {"ok": False, "error": str(e)[:500]})
        self._send(404, {"ok": False})

    def do_POST(self):
        return self.do_GET()


def main():
    srv = ThreadingHTTPServer((RING_HOST, RING_PORT), Handler)
    LOG.info("ring HTTP on %s:%s (ConfBridge %s + %s)", RING_HOST, RING_PORT, PHONE, CAMERA)
    srv.serve_forever()


if __name__ == "__main__":
    main()
