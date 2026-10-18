#!/usr/bin/env python3
"""Reverse proxy kecil untuk Tailscale Funnel.

    /bayar/* -> 127.0.0.1:8090 (halaman pembayaran publik)
    /*       -> 127.0.0.1:8000 (lainnya, mis. icecast2)

Jalan di 127.0.0.1:8001, Funnel diarahkan ke sini.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client

ROUTES = [
    ("/bayar", "127.0.0.1", 8090),
    ("/webhook", "192.168.50.1", 8080),
]
DEFAULT = ("127.0.0.1", 8000)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _proxy(self):
        path = self.path
        host, port = DEFAULT
        for prefix, h, p in ROUTES:
            if path == prefix or path.startswith(prefix + "/"):
                host, port = h, p
                break
        conn = http.client.HTTPConnection(host, port, timeout=15)
        # teruskan header penting
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "connection")}
        body = None
        if self.command in ("POST", "PUT", "PATCH"):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n) if n else None
        try:
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("connection", "transfer-encoding",
                                     "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            msg = ("Proxy error: %s" % e).encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
        finally:
            conn.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_HEAD = _proxy


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8001), H)
    srv.daemon_threads = True
    print("funnel-proxy jalan di 127.0.0.1:8001", flush=True)
    srv.serve_forever()
