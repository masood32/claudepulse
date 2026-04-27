"""
Local HTTP server (port 54321) that receives data pushed by the browser extension:
  POST /data  { key, usage, endpoint }
  POST /session-key  { key }   (legacy, still supported)
"""

import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 54321
_on_data_received = None   # callback(key, usage_dict)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._reply(400, "Bad JSON")
            return

        if self.path == "/data":
            key = (body.get("key") or "").strip()
            usage = body.get("usage")
            endpoint = body.get("endpoint")
            if endpoint:
                print(f"[key_server] usage data via {endpoint}")
            if _on_data_received:
                _on_data_received(key, usage)
            self._reply(200, "OK")

        elif self.path == "/session-key":
            key = (body.get("key") or "").strip()
            if _on_data_received:
                _on_data_received(key, None)
            self._reply(200, "OK")

        else:
            self._reply(404, "Not found")

    def _reply(self, code, text):
        data = text.encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def start(on_data_received):
    """Start the receiver server in a daemon thread."""
    global _on_data_received
    _on_data_received = on_data_received

    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"[key_server] listening on port {PORT}")
    except OSError:
        print(f"[key_server] port {PORT} in use — another instance may be running")
