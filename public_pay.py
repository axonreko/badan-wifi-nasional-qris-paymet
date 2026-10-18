#!/usr/bin/env python3
"""Halaman pembayaran publik via Tailscale Funnel.

Diserve di 127.0.0.1:8090, dipublish via:
    tailscale serve --https=443 --set-path=/bayar http://127.0.0.1:8090

URL publik: https://aml-s9xx-box.tailc28155.ts.net/bayar/<KODE-ORDER>
Halaman ini bisa dibuka pakai kuota HP (tidak perlu WiFi portal).
Menampilkan: kode order, paket, nominal, tombol bayar (Mayar),
dan status pembayaran live.
"""
import json
import os
import sys
import html
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

PAYF = "/opt/portal/payment.json"
PAYMENTS = "/opt/portal/payments.json"

# rate limiting sederhana: maks 30 request/menit per IP
RATE = {}
RATE_MAX = 30
RATE_WINDOW = 60

def rate_ok(ip):
    now = time.time()
    hits = RATE.get(ip, [])
    hits = [t for t in hits if now - t < RATE_WINDOW]
    if len(hits) >= RATE_MAX:
        return False
    hits.append(now)
    RATE[ip] = hits
    # bersihkan IP lama sesekali
    if len(RATE) > 500:
        for k in list(RATE):
            if not [t for t in RATE[k] if now - t < RATE_WINDOW]:
                del RATE[k]
    return True

def esc(s):
    return html.escape(str(s or ""), quote=True)

sys.path.insert(0, "/opt/portal")
try:
    from qris.mayar import MayarClient, SANDBOX_BASE
    HAS_MAYAR = True
except Exception:
    HAS_MAYAR = False


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def rp(n):
    return "Rp" + f"{int(n):,}".replace(",", ".")


CSS = """
body{font-family:-apple-system,system-ui,sans-serif;background:#f1f5f9;margin:0;
padding:20px 14px;color:#0f172a}
.card{max-width:420px;margin:0 auto;background:#fff;border-radius:14px;
padding:26px 22px;box-shadow:0 2px 12px rgba(0,0,0,.07);text-align:center}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#64748b;font-size:13px;margin:0 0 14px}
.code{font-family:ui-monospace,monospace;font-size:30px;font-weight:800;
letter-spacing:4px;color:#1e40af;background:#eff6ff;border:1px dashed #1e40af;
border-radius:10px;padding:12px;margin:12px 0}
.row{display:flex;justify-content:space-between;padding:8px 0;
border-bottom:1px solid #f1f5f9;font-size:14px}
.row span:last-child{font-weight:700}
button{background:#1e40af;color:#fff;border:0;border-radius:10px;
padding:14px;width:100%;font-size:16px;font-weight:700;margin-top:16px;cursor:pointer}
.badge{display:inline-block;padding:6px 14px;border-radius:20px;font-size:13px;
font-weight:700;margin:10px 0}
.b-green{background:#dcfce7;color:#166534}
.b-amber{background:#fef3c7;color:#92400e}
.steps{text-align:left;background:#f8fafc;border-radius:10px;padding:12px 14px;
margin-top:14px;font-size:13px;line-height:1.8;color:#334155}
.foot{margin-top:14px;font-size:12px;color:#94a3b8}
"""


def find_payment(code):
    # validasi format ketat: hanya huruf/angka/dash, maks 12 char
    code = (code or "").upper().replace("-", "").replace(" ", "")
    if not code or len(code) > 12 or not code.isalnum():
        return None
    pays = load_json(PAYMENTS)
    for p in pays.values():
        oc = (p.get("order_code") or "").replace("-", "")
        if oc == code:
            return p
    return None


def check_paid(pay):
    """Cek status ke Mayar jika mode mayar + ada transaction_id."""
    if pay.get("status") == "paid":
        return True
    cfg = load_json(PAYF)
    if cfg.get("mode") == "mayar" and pay.get("transaction_id") and HAS_MAYAR:
        try:
            m = cfg["mayar"]
            if m.get("api_key"):
                c = MayarClient(api_key=m["api_key"],
                                base=m.get("base") or SANDBOX_BASE)
                inv = c.get_invoice(pay["transaction_id"])
                return MayarClient.is_paid(inv)
        except Exception:
            pass
    return False


def page_bayar(pay, paid):
    ocode = esc(pay.get("order_code", ""))
    bill = esc(pay.get("bill_url") or "#")
    label = esc(pay.get("label", "-"))
    if paid:
        status = '<div class="badge b-green">LUNAS ✅</div>'
        action = (
            '<div class="steps"><b>Pembayaran berhasil!</b><br>'
            '1. Nyalakan WiFi HP<br>'
            '2. Connect ke <b>BADAN WIFI NASIONAL</b><br>'
            '3. Buka halaman portal → klik <b>Klaim akses</b><br>'
            '4. Masukkan kode: <b>' + ocode + '</b></div>')
    else:
        status = '<div class="badge b-amber">Menunggu pembayaran</div>'
        action = (
            '<a href="' + bill + '"><button>BAYAR ' + rp(pay["amount"]) +
            '</button></a>'
            '<div class="steps">Klik tombol di atas untuk bayar via QRIS / '
            'GoPay / OVO / DANA / transfer bank.<br>'
            'Setelah bayar, halaman ini otomatis berubah jadi LUNAS.</div>'
            '<script>setTimeout(function(){location.reload()},15000)</script>')
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Bayar Wifi - " + ocode + "</title>"
            "<style>" + CSS + "</style></head><body><div class='card'>"
            "<h1>BADAN WIFI NASIONAL</h1>"
            "<p class='sub'>Pembayaran paket internet</p>"
            "<div class='code'>" + ocode + "</div>" + status +
            "<div class='row'><span>Paket</span><span>" + label +
            "</span></div>"
            "<div class='row' style='border:0'><span>Nominal</span><span>" +
            rp(pay.get("amount", 0)) + "</span></div>" +
            action +
            "<div class='foot'>Simpan link halaman ini — bisa dibuka kapan saja.</div>"
            "</div></body></html>")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        client_ip = self.client_address[0]
        if not rate_ok(client_ip):
            b = b"Terlalu banyak request. Coba lagi sebentar."
            self.send_response(429)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Retry-After", "60")
            self.end_headers()
            self.wfile.write(b)
            return
        u = urlparse(self.path)
        parts = unquote(u.path).strip("/").split("/")
        # path: /bayar/<KODE>  (Funnel strip /bayar, jadi terima dua bentuk)
        code = parts[-1] if parts else ""
        if len(parts) >= 2 and parts[-2].lower() == "bayar":
            code = parts[-1]
        pay = find_payment(code)
        if not pay:
            body = ("<!DOCTYPE html><html><body style='font-family:sans-serif;"
                    "text-align:center;padding:40px'>"
                    "<h2>Kode tidak ditemukan</h2>"
                    "<p>Periksa kembali link pembayaran kamu.</p></body></html>")
            b = body.encode()
            self.send_response(404)
        else:
            paid = check_paid(pay)
            b = page_bayar(pay, paid).encode()
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8090), H)
    srv.daemon_threads = True
    print("public_pay jalan di 127.0.0.1:8090", flush=True)
    srv.serve_forever()
