#!/usr/bin/env python3
"""Captive portal Badan Wifi Nasional: voucher + panel admin."""
import subprocess, json, os, sys, datetime, re, base64, secrets, threading, time
import html as _html

# rate limiting sederhana untuk endpoint sensitif (/claim)
_CLAIM_HITS = {}
def claim_rate_ok(ip):
    now = time.time()
    hits = [t for t in _CLAIM_HITS.get(ip, []) if now - t < 300]
    if len(hits) >= 10:  # maks 10x klaim per 5 menit per IP
        return False
    hits.append(now)
    _CLAIM_HITS[ip] = hits
    return True
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BIND = "192.168.50.1"
PORT = 8080
VF = "/opt/portal/vouchers.json"
SESF = "/opt/portal/sessions.json"
PASSF = "/opt/portal/admin_pass.txt"
PAYF = "/opt/portal/payment.json"
PAYMENTS = "/opt/portal/payments.json"

DEFAULT_PAYMENT = {
    "mode": "demo",  # demo | mayar
    "currency": "Rp",
    "packages": [
        {"id": "p1", "label": "1 Jam", "duration": 3600, "price": 2000},
        {"id": "p2", "label": "3 Jam", "duration": 10800, "price": 5000},
        {"id": "p3", "label": "12 Jam", "duration": 43200, "price": 10000},
        {"id": "p4", "label": "1 Hari", "duration": 86400, "price": 15000},
    ],
    "mayar": {
        "api_key": "",
        "api_base": "https://api.mayar.club/hl/v2",
        "webhook_token": ""
    },
    # URL publik halaman bayar (via Tailscale Funnel). User salin link ini
    # sebelum matikan WiFi — bisa dibuka pakai kuota HP.
    "public_base": "https://aml-s9xx-box.tailc28155.ts.net/bayar"
}

# preset durasi akses (detik): label -> detik. 0 = tanpa batas waktu
DURATIONS = [
    ("Tanpa batas waktu", 0),
    ("30 menit", 1800),
    ("1 jam", 3600),
    ("2 jam", 7200),
    ("3 jam", 10800),
    ("6 jam", 21600),
    ("12 jam", 43200),
    ("1 hari", 86400),
    ("3 hari", 259200),
    ("7 hari", 604800),
]
DUR_LABEL = {s: l for l, s in DURATIONS}

# Logo: file /opt/portal/logo.webp diserve via route /logo.webp
LOGO_IMG = '<img class="logo-img" src="/logo.webp" alt="Badan Wifi Nasional">'
LOGO_FILE = "/opt/portal/logo.webp"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:#f1f5f9;color:#0f172a;min-height:100vh;display:flex;align-items:center;
justify-content:center;padding:24px}
body.admin{align-items:flex-start}
.card{background:#fff;border-radius:12px;padding:40px 36px;width:100%;max-width:380px;
box-shadow:0 1px 3px rgba(15,23,42,.08),0 4px 12px rgba(15,23,42,.05)}
.card.wide{max-width:860px}
.brand{width:46px;height:46px;border-radius:11px;background:#1e40af;color:#fff;
display:flex;align-items:center;justify-content:center;font-weight:700;font-size:19px;
letter-spacing:.5px;margin-bottom:22px}
.logo{width:118px;height:118px;margin:0 auto 22px;display:block}
.logo.sm{width:44px;height:44px;margin:0}
.logo.xs{width:36px;height:36px;margin:0;flex:none}
.logo-img{width:118px;height:118px;margin:0 auto 22px;display:block;border-radius:50%;
box-shadow:0 4px 14px rgba(15,23,42,.18)}
.logo-img.sm{width:64px;height:64px;margin:0 auto 18px}
.logo-img.xs{width:36px;height:36px;margin:0;flex:none;border-radius:50%}
.adm-head{display:flex;align-items:center;gap:12px}
.adm-head h1{margin:0}
h1{font-size:20px;font-weight:650;margin-bottom:6px;letter-spacing:-.2px}
h2{font-size:15px;font-weight:650;margin:28px 0 12px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}
p.sub{color:#64748b;font-size:14px;line-height:1.55;margin-bottom:26px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:8px;color:#334155}
input.code{width:100%;padding:13px 14px;font-size:17px;border:1px solid #cbd5e1;
border-radius:8px;letter-spacing:3px;text-transform:uppercase;text-align:center;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#0f172a}
input.code:focus{outline:none;border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.13)}
input.txt,select.txt{padding:10px 12px;font-size:14px;border:1px solid #cbd5e1;border-radius:8px;width:100%}
button{width:100%;margin-top:16px;padding:13px;font-size:15px;font-weight:600;color:#fff;
background:#1e40af;border:none;border-radius:8px;cursor:pointer}
button:hover{background:#1e3a8a}
.btn-sm{width:auto;margin:0;padding:7px 14px;font-size:13px;border-radius:7px;display:inline-block;text-decoration:none;color:#fff}
.btn-red{background:#dc2626}.btn-red:hover{background:#b91c1c}
.btn-gray{background:#64748b}.btn-gray:hover{background:#475569}
.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;padding:11px 14px;
border-radius:8px;font-size:13px;margin-bottom:18px;line-height:1.5}
.ok{background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;padding:11px 14px;
border-radius:8px;font-size:13px;margin-bottom:18px}
.ok-icon{width:52px;height:52px;border-radius:50%;background:#dcfce7;color:#15803d;
display:flex;align-items:center;justify-content:center;font-size:26px;margin-bottom:20px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;padding:10px 12px;color:#64748b;font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #e2e8f0}
td{padding:11px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.badge{display:inline-block;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:600}
.b-green{background:#dcfce7;color:#15803d}.b-amber{background:#fef3c7;color:#b45309}
.b-gray{background:#f1f5f9;color:#64748b}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.foot{margin-top:26px;font-size:12px;color:#94a3b8;text-align:center;line-height:1.6}
.meta{margin-top:18px;padding-top:18px;border-top:1px solid #f1f5f9;font-size:12.5px;color:#64748b}
.meta b{color:#334155}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:12px;flex-wrap:wrap}
.topbar h1{margin:0}
.pkgs{display:flex;flex-direction:column;gap:10px;margin-bottom:8px}
button.pkg{display:flex;justify-content:space-between;align-items:center;width:100%;
margin:0;padding:15px 18px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
cursor:pointer;color:#0f172a}
button.pkg:hover{border-color:#1e40af;background:#eff6ff}
.pkg-label{font-size:15px;font-weight:650}
.pkg-price{font-size:15px;font-weight:700;color:#1e40af}
img.qr{width:220px;height:220px;margin:6px auto 4px;display:block;border:1px solid #e2e8f0;
border-radius:12px;padding:8px;background:#fff}
.order-box{background:#eff6ff;border:1px dashed #1e40af;border-radius:10px;
padding:14px;margin:12px 0}
.order-code{font-family:ui-monospace,monospace;font-size:26px;font-weight:800;
letter-spacing:3px;text-align:center;color:#1e40af;margin-top:6px}
.link-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
padding:10px 12px;margin:8px 0;font-size:12px;word-break:break-all;
text-align:center;font-family:ui-monospace,monospace}
.steps{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
padding:12px 14px;margin-top:14px;font-size:13px;line-height:1.7;color:#334155}
.info-box{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
padding:12px 14px;margin:12px 0;font-size:13px;line-height:1.7;color:#14532d}
.info-box b{color:#166534}
a{color:#1e40af}
@media(max-width:640px){.grid2{grid-template-columns:1fr}.card{padding:28px 22px}}
"""

def page(title, body, wide=False, admin=False):
    cls = "card wide" if wide else "card"
    ab = ' class="admin"' if admin else ""
    return ("<!DOCTYPE html><html lang=\"id\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>" + title + "</title><style>" + CSS + "</style></head>\n"
            "<body" + ab + "><div class=\"" + cls + "\">" + body +
            "\n<div class=\"foot\">Badan Wifi Nasional &middot; Akses internet nirkabel</div>\n"
            "</div></body></html>")

def load():
    return json.load(open(VF)) if os.path.exists(VF) else {}

def save(d):
    json.dump(d, open(VF, "w"), indent=1)

def load_ses():
    try:
        return json.load(open(SESF)) if os.path.exists(SESF) else {}
    except Exception:
        return {}

def save_ses(s):
    json.dump(s, open(SESF, "w"), indent=1)

# ---------- pembayaran ----------
def pay_config():
    try:
        cfg = json.load(open(PAYF))
        # merge default untuk key yang belum ada
        for k, v in DEFAULT_PAYMENT.items():
            cfg.setdefault(k, v)
        # mode mayar tanpa API key = demo (fallback aman)
        if cfg.get("mode") == "mayar" and not cfg["mayar"].get("api_key"):
            cfg["_real_mode"] = "demo"
        else:
            cfg["_real_mode"] = cfg.get("mode", "demo")
        return cfg
    except Exception:
        json.dump(DEFAULT_PAYMENT, open(PAYF, "w"), indent=1)
        cfg = dict(DEFAULT_PAYMENT)
        cfg["_real_mode"] = "demo"
        return cfg

def pay_mode(cfg):
    return cfg.get("_real_mode", cfg.get("mode", "demo"))

def load_pays():
    try:
        return json.load(open(PAYMENTS)) if os.path.exists(PAYMENTS) else {}
    except Exception:
        return {}

def save_pays(p):
    json.dump(p, open(PAYMENTS, "w"), indent=1)

def rp(n):
    return "Rp" + f"{n:,}".replace(",", ".")

def make_qr_png(data):
    """Generate QR PNG bytes (untuk QRIS demo)."""
    import qrcode, io
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()

def create_payment(pkg_id, ip):
    """Buat pembayaran baru. Return (pay_id, info). Mode demo: QR lokal."""
    cfg = pay_config()
    pkg = next((x for x in cfg["packages"] if x["id"] == pkg_id), None)
    if not pkg:
        return None, "Paket tidak ditemukan."
    pays = load_pays()
    pay_id = secrets.token_hex(6)
    pay = {
        "id": pay_id, "package_id": pkg_id, "ip": ip,
        "amount": pkg["price"], "duration": pkg["duration"],
        "label": pkg["label"], "status": "pending",
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "transaction_id": None, "bill_url": None,
        "order_code": gen_code(),
    }
    if cfg["mode"] == "mayar" and cfg["mayar"]["api_key"]:
        ok, info = mayar_create_invoice(cfg, pay)
        if not ok:
            return None, info
        pay["transaction_id"] = info.get("transaction_id")
        pay["bill_url"] = info.get("bill_url")
    else:
        # demo: QR berisi string demo
        pay["qr_data"] = "DEMO-QRIS-BADANWIFINASIONAL-" + pay_id.upper()
    pays[pay_id] = pay
    save_pays(pays)
    return pay_id, None

def activate_payment_for_ip(pay, ip):
    """Aktifkan akses untuk IP tertentu (bisa beda dari IP saat beli,
    mis. user putus-sambung WiFi untuk bayar pakai kuota).
    Kalau kode diklaim dari IP baru, sesi IP lama dipindah (tidak diduplikat)."""
    pays = load_pays()
    pid = pay["id"]
    pay = pays.get(pid, pay)
    if pay["status"] != "paid":
        pay["status"] = "paid"
        pay["paid_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    old_ip = pay.get("claimed_ip")
    pay["claimed_ip"] = ip
    save_pays(pays)
    s = load_ses()
    # pindahkan sesi: cabut akses IP lama kalau beda
    if old_ip and old_ip != ip:
        s.pop(old_ip, None)
        subprocess.run(["ipset", "del", "portal_allow", old_ip],
                       capture_output=True)
    dur = int(pay["duration"])
    end = datetime.datetime.now().timestamp() + dur
    s[ip] = {"code": "QRIS-" + pid[:6].upper(),
             "start": datetime.datetime.now().isoformat(timespec="seconds"),
             "end": end, "duration": dur, "via": "qris"}
    save_ses(s)
    subprocess.run(["ipset", "add", "portal_allow", ip,
                    "timeout", str(dur)], capture_output=True)
    return True

def activate_payment(pay_id):
    """Aktifkan akses internet untuk pembayaran yang lunas."""
    pays = load_pays()
    pay = pays.get(pay_id)
    if not pay or pay["status"] == "paid":
        return False
    return activate_payment_for_ip(pay, pay["ip"])

# ---------- Mayar (klien asli dari repo badan-wifi-nasional-qris-paymet) ----------
def _mayar_client(cfg):
    """Buat MayarClient asli. Return None jika modul qris belum dipasang."""
    try:
        sys.path.insert(0, "/opt/portal")
        from qris.mayar import MayarClient, SANDBOX_BASE
        m = cfg["mayar"]
        return MayarClient(api_key=m["api_key"],
                           base=m.get("base") or SANDBOX_BASE)
    except Exception:
        return None

def mayar_create_invoice(cfg, pay):
    """Buat invoice Mayar asli. Return (True, {transaction_id, bill_url})
    atau (False, pesan_error)."""
    client = _mayar_client(cfg)
    if not client:
        return False, "Modul qris belum dipasang di /opt/portal/qris."
    m = cfg["mayar"]
    tier = m.get("tiers", {}).get(pay["package_id"], "")
    if not tier:
        return False, ("tier_id untuk paket %s belum diisi "
                       "(atur di payment.json)" % pay["package_id"])
    try:
        member_id = client.register_member(
            product_id=m["product_id"], tier_id=tier,
            name="wifi-user", email="wifi@local")
        tx, url = client.create_member_invoice(member_id, m["product_id"])
        return True, {"transaction_id": tx, "bill_url": url,
                      "member_id": member_id}
    except Exception as e:
        return False, "Mayar: %s" % e

def mayar_check_status(cfg, pay):
    """Cek status invoice ke Mayar. Return 'paid'/'pending'."""
    client = _mayar_client(cfg)
    if not client or not pay.get("transaction_id"):
        return "pending"
    try:
        from qris.mayar import MayarClient as MC
        inv = client.get_invoice(pay["transaction_id"])
        return "paid" if MC.is_paid(inv) else "pending"
    except Exception:
        return "pending"

def kick_ip(ip):
    """Putuskan akses 1 IP: hapus dari ipset + sesi."""
    subprocess.run(["ipset", "del", "portal_allow", ip], capture_output=True)
    s = load_ses()
    if ip in s:
        del s[ip]
        save_ses(s)

def sweep():
    """Hapus sesi yang waktunya habis. Jalan tiap 30 detik di thread terpisah."""
    while True:
        try:
            now = datetime.datetime.now().timestamp()
            s = load_ses()
            changed = False
            for ip, ses in list(s.items()):
                if ses.get("end") and now >= ses["end"]:
                    subprocess.run(["ipset", "del", "portal_allow", ip],
                                   capture_output=True)
                    del s[ip]
                    changed = True
            if changed:
                save_ses(s)
        except Exception:
            pass
        time.sleep(30)

def fmt_sisa(end_ts):
    """Format sisa waktu jadi teks Indonesia, mis. '2 jam 15 mnt'."""
    sisa = int(end_ts - datetime.datetime.now().timestamp())
    if sisa <= 0:
        return "habis"
    hari, sisa = divmod(sisa, 86400)
    jam, sisa = divmod(sisa, 3600)
    mnt, _ = divmod(sisa, 60)
    parts = []
    if hari:
        parts.append(str(hari) + " hari")
    if jam:
        parts.append(str(jam) + " jam")
    if mnt and not hari:
        parts.append(str(mnt) + " mnt")
    return " ".join(parts) if parts else "< 1 mnt"

def cek_voucher(norm):
    d = load()
    hit = {re.sub(r"[^A-Z0-9]", "", k.upper()): k for k in d}
    code = hit.get(norm)
    v = d.get(code) if code else None
    if not v:
        return None, "Kode voucher tidak dikenali. Periksa kembali penulisan kode.", None
    if v["uses"] >= v["max_uses"]:
        return None, "Voucher ini sudah habis digunakan.", None
    if v["expires"] and datetime.datetime.now().isoformat() > v["expires"]:
        return None, "Voucher ini sudah kedaluwarsa.", None
    return d, None, code

def form(err=""):
    e = "<div class=\"err\">" + err + "</div>" if err else ""
    return page("Badan Wifi Nasional - Masukkan Voucher",
        LOGO_IMG + "<h1 style=\"text-align:center\">Selamat datang</h1>\n"
        "<p class=\"sub\" style=\"text-align:center\">Masukkan kode voucher untuk terhubung ke internet.</p>" + e + "\n"
        "<form method=\"POST\" action=\"/connect\">\n"
        "<label for=\"v\">Kode voucher</label>\n"
        "<input class=\"code\" id=\"v\" name=\"voucher\" placeholder=\"XXXX-XXXX\"\n"
        "maxlength=\"12\" autocomplete=\"off\" autofocus required>\n"
        "<button type=\"submit\">Hubungkan</button></form>"
        "<div class=\"info-box\">"
        "<b>2 cara dapat internet:</b><br>"
        "1. <b>Voucher cash</b> — beli voucher fisik ke penjual, masukkan kodenya di atas. "
        "Cocok kalau HP-mu nggak ada kuota.<br>"
        "2. <b>Bayar via QRIS</b> — <a href=\"/buy\">beli paket di sini</a> "
        "(butuh kuota HP saat bayar). Sudah bayar? "
        "<a href=\"/claim\">Klaim akses di sini</a>."
        "</div>")

def success(code, dur_sec=0):
    info = ""
    if dur_sec > 0:
        info = ("<div class=\"meta\">Masa aktif: <b>" + DUR_LABEL.get(dur_sec, "") +
                "</b> sejak sekarang.</div>")
    return page("Badan Wifi Nasional - Terhubung",
        LOGO_IMG.replace('logo-img', 'logo-img sm') +
        "<div class=\"ok-icon\">&#10003;</div><h1>Terhubung</h1>\n"
        "<p class=\"sub\">Perangkat ini sekarang memiliki akses internet.</p>\n"
        "<div class=\"meta\">Voucher <b>" + code + "</b> telah digunakan.</div>" + info)

def page_claim(msg=""):
    m = "<div class=\"err\">" + msg + "</div>" if msg else ""
    return page("Badan Wifi Nasional - Klaim Pembayaran",
        LOGO_IMG.replace('logo-img', 'logo-img sm') +
        "<h1 style=\"text-align:center\">Klaim Akses</h1>\n"
        "<p class=\"sub\" style=\"text-align:center\">Sudah bayar via QRIS pakai "
        "kuota HP? Masukkan kode order kamu:</p>\n" + m +
        "<form method=\"POST\" action=\"/claim\">"
        "<input class=\"code\" name=\"order_code\" placeholder=\"XXXX-XXXX\" "
        "autocomplete=\"off\" style=\"text-transform:uppercase\">"
        "<button type=\"submit\">Aktifkan Internet</button></form>"
        "<div class=\"meta\" style=\"text-align:center\">"
        "<a href=\"/\">Kembali</a></div>")

def page_buy():
    cfg = pay_config()
    cards = ""
    for p in cfg["packages"]:
        cards += (
            "<form method=\"POST\" action=\"/buy\" style=\"margin:0\">"
            "<input type=\"hidden\" name=\"package_id\" value=\"" + p["id"] + "\">"
            "<button type=\"submit\" class=\"pkg\">"
            "<span class=\"pkg-label\">" + p["label"] + "</span>"
            "<span class=\"pkg-price\">" + rp(p["price"]) + "</span>"
            "</button></form>")
    demo_note = ""
    if pay_mode(cfg) == "demo":
        demo_note = ("<div class=\"meta\" style=\"text-align:center\">"
                     "Mode demo &mdash; pembayaran disimulasikan, "
                     "tidak ada uang asli.</div>")
    quota_note = (
        "<div class=\"info-box\">"
        "<b>Ngga punya kuota HP?</b> Bayar QRIS butuh internet dari kuota HP "
        "kamu dulu (matikan WiFi saat bayar).<br>"
        "Kalau kuotamu habis, beli <b>voucher fisik bayar cash</b> aja ke "
        "penjual — langsung dapat kode, masukkan di halaman utama."
        "</div>")
    return page("Badan Wifi Nasional - Beli Paket",
        LOGO_IMG +
        "<h1 style=\"text-align:center\">Pilih Paket Internet</h1>\n"
        "<p class=\"sub\" style=\"text-align:center\">Bayar via QRIS, "
        "akses langsung aktif otomatis.</p>\n" + quota_note +
        "<div class=\"pkgs\">" + cards + "</div>\n"
        "<div class=\"meta\" style=\"text-align:center\">"
        "Punya kode voucher? <a href=\"/\">Masukkan di sini</a></div>" + demo_note)

def page_pay(pay):
    cfg = pay_config()
    if pay_mode(cfg) == "demo":
        action = (
            "<form method=\"POST\" action=\"/pay/confirm\" style=\"margin-top:18px\">"
            "<input type=\"hidden\" name=\"id\" value=\"" + pay["id"] + "\">"
            "<button type=\"submit\">Saya Sudah Bayar (Simulasi)</button></form>"
            "<div class=\"meta\" style=\"text-align:center\">Mode demo: "
            "klik tombol untuk mensimulasikan pembayaran berhasil.</div>")
        qr_block = ("<img class=\"qr\" src=\"/pay/qr?id=" + pay["id"] +
                    "\" alt=\"QRIS\">")
    else:
        # mode mayar: user dapat LINK PUBLIK yang bisa dibuka pakai kuota HP.
        # Link ini menampilkan kode order + tombol bayar + status live,
        # jadi user cukup simpan 1 link sebelum matikan WiFi.
        ocode = pay.get("order_code", "")
        pub_base = cfg.get("public_base", "").rstrip("/")
        pub_link = pub_base + "/" + ocode if pub_base else (pay.get("bill_url") or "#")
        action = (
            "<div class=\"order-box\"><div class=\"meta\" style=\"text-align:center\">"
            "Kode order kamu (screenshot juga boleh):</div>"
            "<div class=\"order-code\">" + ocode + "</div></div>"
            "<div class=\"steps\" style=\"border-color:#f59e0b;background:#fffbeb\">"
            "<b>⚠️ Cara bayar pakai kuota HP:</b><br>"
            "1. <b>Salin link</b> di bawah ini (tahan & salin)<br>"
            "2. <b>Matikan WiFi</b> HP — pakai kuota dulu<br>"
            "3. Buka link yang disalin di Chrome → klik <b>BAYAR</b><br>"
            "4. Setelah bayar, <b>nyalakan WiFi</b> lagi → connect "
            "<b>BADAN WIFI NASIONAL</b><br>"
            "5. Di halaman portal klik <b>Klaim akses</b>, masukkan kode di atas"
            "</div>"
            "<div class=\"meta\" style=\"text-align:center;margin-top:10px\">"
            "Link pembayaran & status (tahan untuk menyalin):</div>"
            "<div class=\"link-box\"><a href=\"" + pub_link + "\">" + pub_link +
            "</a></div>"
            "<a href=\"" + pub_link + "\" target=\"_blank\">"
            "<button type=\"button\" style=\"margin-top:14px\">"
            "Buka Link Pembayaran</button></a>"
            "<script>setTimeout(function(){location.reload()},15000)</script>")
        qr_block = ("<img class=\"qr\" src=\"/pay/qr?id=" + pay["id"] +
                    "\" alt=\"QRIS\">")
    return page("Badan Wifi Nasional - Bayar QRIS",
        LOGO_IMG.replace('logo-img', 'logo-img sm') +
        "<h1 style=\"text-align:center\">Bayar " + rp(pay["amount"]) + "</h1>\n"
        "<p class=\"sub\" style=\"text-align:center\">Paket <b>" + pay["label"] +
        "</b></p>\n" + qr_block + action)

def admin_pass():
    try:
        return open(PASSF).read().strip()
    except Exception:
        return ""

def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return ""

def leases():
    out = []
    for line in sh(["cat", "/var/lib/misc/dnsmasq.leases"]).splitlines():
        p = line.split()
        if len(p) >= 4:
            out.append({"mac": p[1], "ip": p[2], "name": p[3]})
    return out

def allowed_ips():
    return set(re.findall(r"^(\d+\.\d+\.\d+\.\d+)", sh(["ipset", "list", "portal_allow"]), re.M))

def signals():
    sig = {}
    cur = None
    for line in sh(["iw", "dev", "wlan1", "station", "dump"]).splitlines():
        m = re.match(r"Station ([0-9a-f:]+)", line)
        if m:
            cur = m.group(1).lower()
        m = re.search(r"signal:\s*(-?\d+)", line)
        if m and cur:
            sig[cur] = m.group(1) + " dBm"
    return sig

def admin_dashboard(msg=""):
    allowed = allowed_ips()
    sig = signals()
    devs = leases()
    rows = ""
    for dvc in devs:
        on = dvc["ip"] in allowed
        badge = ('<span class="badge b-green">Online</span>' if on
                 else '<span class="badge b-amber">Di portal</span>')
        if on:
            kick = ("<a class=\"btn-sm btn-red\" href=\"/admin/kick?ip=" + dvc["ip"] +
                    "\">Putuskan</a>")
        else:
            kick = "<span style=\"color:#94a3b8\">-</span>"
        rows += ("<tr><td><b>" + dvc["name"] + "</b><br>"
                 "<span class=\"mono\" style=\"color:#64748b\">" + dvc["ip"] + "</span></td>"
                 "<td class=\"mono\">" + dvc["mac"] + "</td>"
                 "<td>" + sig.get(dvc["mac"].lower(), "-") + "</td>"
                 "<td>" + badge + "</td><td>" + kick + "</td></tr>")
    if not rows:
        rows = ("<tr><td colspan=\"5\" style=\"text-align:center;color:#94a3b8\">"
                "Belum ada perangkat terhubung</td></tr>")
    vrows = ""
    for code, v in sorted(load().items()):
        left = v["max_uses"] - v["uses"]
        st = ('<span class="badge b-gray">Habis</span>' if left <= 0
              else '<span class="badge b-green">Sisa ' + str(left) + "x</span>")
        exp = v["expires"][:10] if v["expires"] else "-"
        dur_txt = DUR_LABEL.get(int(v.get("duration", 0) or 0), "-")
        vrows += ("<tr><td class=\"mono\"><b>" + code + "</b></td>"
                  "<td>" + str(v["uses"]) + "/" + str(v["max_uses"]) + "</td>"
                  "<td>" + dur_txt + "</td>"
                  "<td>" + exp + "</td><td>" + st + "</td>"
                  "<td><a class=\"btn-sm btn-gray\" href=\"/admin/delv?code=" + code +
                  "\">Hapus</a></td></tr>")
    if not vrows:
        vrows = ("<tr><td colspan=\"6\" style=\"text-align:center;color:#94a3b8\">"
                 "Belum ada voucher</td></tr>")
    # --- riwayat pembayaran QRIS ---
    pays = load_pays()
    prows = ""
    for pid, p in sorted(pays.items(), key=lambda kv: kv[1].get("created", ""),
                         reverse=True)[:20]:
        st = ('<span class="badge b-green">Lunas</span>'
              if p["status"] == "paid"
              else '<span class="badge b-amber">Menunggu</span>')
        prows += ("<tr><td class=\"mono\">" + pid[:8].upper() + "</td>"
                  "<td>" + p.get("label", "-") + "</td>"
                  "<td>" + rp(p.get("amount", 0)) + "</td>"
                  "<td class=\"mono\">" + p.get("ip", "-") + "</td>"
                  "<td>" + st + "</td></tr>")
    pay_block = ""
    if prows:
        pay_block = ("<h2>Pembayaran QRIS (20 terakhir)</h2>\n"
                     "<table><tr><th>ID</th><th>Paket</th><th>Nominal</th>"
                     "<th>IP</th><th>Status</th></tr>" + prows + "</table>\n")
    # --- tabel sesi aktif (berdurasi) ---
    ses = load_ses()
    srows = ""
    for ip, s in sorted(ses.items(), key=lambda kv: kv[1].get("end", 0)):
        end = s.get("end")
        if not end:
            continue
        sisa = fmt_sisa(end)
        nama = next((dvc["name"] for dvc in devs if dvc["ip"] == ip), "-")
        srows += ("<tr><td><b>" + nama + "</b><br>"
                  "<span class=\"mono\" style=\"color:#64748b\">" + ip + "</span></td>"
                  "<td class=\"mono\">" + s.get("code", "-") + "</td>"
                  "<td><span class=\"badge b-green\">" + sisa + " lagi</span></td>"
                  "<td><a class=\"btn-sm btn-red\" href=\"/admin/kick?ip=" + ip +
                  "\">Putuskan</a></td></tr>")
    ses_block = ""
    if srows:
        ses_block = ("<h2>Sesi aktif berdurasi (" + str(len([1 for s in ses.values() if s.get("end")])) +
                     ")</h2>\n<table><tr><th>Perangkat</th><th>Voucher</th>"
                     "<th>Sisa waktu</th><th>Aksi</th></tr>" + srows + "</table>\n")
    # --- dropdown durasi ---
    dur_opts = "".join(
        "<option value=\"" + str(s) + "\">" + l + "</option>" for l, s in DURATIONS)
    # --- form pengaturan Mayar ---
    pcfg = pay_config()
    pm = pcfg["mayar"]
    mode_demo_sel = " selected" if pcfg.get("mode") != "mayar" else ""
    mode_mayar_sel = " selected" if pcfg.get("mode") == "mayar" else ""
    base_sb_sel = " selected" if "mayar.club" in pm.get("base", "") else ""
    base_pr_sel = " selected" if "mayar.id" in pm.get("base", "") and "club" not in pm.get("base", "") else ""
    key_masked = ("****" + pm.get("api_key", "")[-4:] if pm.get("api_key") else "")
    mayar_form = (
        "<h2>Pengaturan Pembayaran (Mayar QRIS)</h2>\n"
        "<form method=\"POST\" action=\"/admin/mayar\"><div class=\"grid2\">\n"
        "<div><label>Mode pembayaran</label>"
        "<select class=\"txt\" name=\"mode\">"
        "<option value=\"demo\"" + mode_demo_sel + ">Demo (simulasi, tanpa uang asli)</option>"
        "<option value=\"mayar\"" + mode_mayar_sel + ">Mayar (QRIS asli)</option>"
        "</select></div>\n"
        "<div><label>Mayar API base</label>"
        "<select class=\"txt\" name=\"api_base\">"
        "<option value=\"https://api.mayar.club/hl/v2\"" + base_sb_sel + ">Sandbox - mayar.club (uji coba)</option>"
        "<option value=\"https://api.mayar.id/hl/v2\"" + base_pr_sel + ">Production - mayar.id (uang asli)</option>"
        "</select></div>\n"
        "<div><label>API Key " + (("(tersimpan " + key_masked + ")") if key_masked else "(belum diisi)") + "</label>"
        "<input class=\"txt mono\" type=\"password\" name=\"api_key\" placeholder=\"Paste API key Mayar di sini\" autocomplete=\"off\"></div>\n"
        "<div><label>Product ID (dashboard Mayar)</label>"
        "<input class=\"txt mono\" name=\"product_id\" value=\"" + pm.get("product_id", "") + "\"></div>\n"
        "<div><label>Webhook token</label>"
        "<input class=\"txt mono\" name=\"webhook_token\" value=\"" + pm.get("webhook_token", "") + "\"></div>\n"
        "</div>"
        "<div class=\"meta\">API key hanya diganti jika kolom diisi. "
        "Tier ID per paket diatur di file <span class=\"mono\">/opt/portal/payment.json</span>.</div>\n"
        "<button type=\"submit\">Simpan pengaturan</button></form>\n")
    m = "<div class=\"ok\">" + msg + "</div>" if msg else ""
    return page("Admin - Badan Wifi Nasional",
        "<div class=\"topbar\"><div class=\"adm-head\">" + LOGO_IMG.replace('logo-img', 'logo-img xs') +
        "<h1>Panel Admin</h1></div>"
        "<a class=\"btn-sm btn-gray\" href=\"/admin/reset\" "
        "onclick=\"return confirm('Reset semua login? Semua perangkat harus login ulang.')\">"
        "Reset semua login</a></div>\n"
        "<p class=\"sub\">Kelola voucher dan perangkat yang terhubung.</p>" + m +
        "<h2>Perangkat terhubung (" + str(len(devs)) + ")</h2>\n"
        "<table><tr><th>Perangkat</th><th>MAC</th><th>Sinyal</th><th>Status</th><th>Aksi</th></tr>"
        + rows + "</table>\n"
        + ses_block + pay_block +
        mayar_form +
        "<h2>Buat voucher baru</h2>\n"
        "<form method=\"POST\" action=\"/admin/gen\"><div class=\"grid2\">\n"
        "<div><label>Jumlah</label>"
        "<input class=\"txt\" type=\"number\" name=\"n\" value=\"5\" min=\"1\" max=\"100\"></div>\n"
        "<div><label>Maks. dipakai</label>"
        "<input class=\"txt\" type=\"number\" name=\"uses\" value=\"1\" min=\"1\" max=\"50\"></div>\n"
        "<div><label>Durasi akses sekali pakai</label>"
        "<select class=\"txt\" name=\"duration\">" + dur_opts + "</select></div>\n"
        "<div><label>Voucher berlaku (hari, 0 = selamanya)</label>"
        "<input class=\"txt\" type=\"number\" name=\"hari\" value=\"0\" min=\"0\" max=\"365\"></div>\n"
        "</div><button type=\"submit\">Buat voucher</button></form>\n"
        "<h2>Daftar voucher</h2>\n"
        "<table><tr><th>Kode</th><th>Terpakai</th><th>Durasi</th><th>Expired</th><th>Status</th><th>Aksi</th></tr>"
        + vrows + "</table>\n",
        wide=True, admin=True)

ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def gen_code():
    return "-".join("".join(secrets.choice(ALPH) for _ in range(4)) for _ in range(2))

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, html, code=200):
        b = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _need_auth(self):
        auth = self.headers.get("Authorization", "")
        want = "Basic " + base64.b64encode(("admin:" + admin_pass()).encode()).decode()
        if not admin_pass() or auth != want:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Admin Badan Wifi Nasional"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def _redir(self, loc):
        self.send_response(303)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/logo.webp":
            try:
                data = open(LOGO_FILE, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "image/webp")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(404)
                self.end_headers()
            return
        if u.path == "/buy":
            self._send(page_buy())
            return
        if u.path == "/claim":
            self._send(page_claim())
            return
        if u.path == "/pay":
            q = parse_qs(u.query)
            pay = load_pays().get(q.get("id", [""])[0])
            if not pay:
                self._send(form("Pembayaran tidak ditemukan."))
                return
            if pay["status"] == "paid":
                self._send(success("QRIS-" + pay["id"][:6].upper(),
                                   int(pay["duration"])))
                return
            # mode mayar: cek status ke API saat halaman dibuka
            cfg = pay_config()
            if cfg["mode"] == "mayar" and pay["status"] == "pending":
                if mayar_check_status(cfg, pay) == "paid":
                    activate_payment(pay["id"])
                    self._send(success("QRIS-" + pay["id"][:6].upper(),
                                       int(pay["duration"])))
                    return
            self._send(page_pay(pay))
            return
        if u.path == "/pay/qr":
            q = parse_qs(u.query)
            pay = load_pays().get(q.get("id", [""])[0])
            if not pay:
                self.send_response(404)
                self.end_headers()
                return
            try:
                qr_data = pay.get("qr_data") or pay.get("bill_url") or "BADANWIFINASIONAL"
                data = make_qr_png(qr_data)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(500)
                self.end_headers()
            return
        if u.path.startswith("/admin"):
            if self._need_auth():
                return
            q = parse_qs(u.query)
            if u.path == "/admin/kick":
                kick_ip(q.get("ip", [""])[0])
                self._redir("/admin/?msg=Perangkat+diputus")
            elif u.path == "/admin/reset":
                subprocess.run(["ipset", "flush", "portal_allow"], capture_output=True)
                save_ses({})
                self._redir("/admin/?msg=Semua+login+direset")
            elif u.path == "/admin/delv":
                d = load()
                d.pop(q.get("code", [""])[0], None)
                save(d)
                self._redir("/admin/?msg=Voucher+dihapus")
            else:
                msg = q.get("msg", [""])[0].replace("+", " ")
                self._send(admin_dashboard(msg))
            return
        self._send(form())

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/webhook/mayar":
            # webhook Mayar: body JSON mentah (bukan form)
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n).decode() or "{}")
            except Exception:
                payload = {}
            qs = parse_qs(urlparse(self.path).query)
            cfg = pay_config()
            token_ok = (qs.get("token", [""])[0] ==
                        cfg["mayar"].get("webhook_token", ""))
            if token_ok and payload.get("event") == "payment.received":
                data = payload.get("data", {})
                st = str(data.get("status", "")).lower()
                if st in ("success", "paid", "successful"):
                    tid = data.get("transactionId") or data.get("id")
                    pays = load_pays()
                    for pid, p in pays.items():
                        if p.get("transaction_id") == tid and p["status"] == "pending":
                            activate_payment(pid)
                            break
            self.send_response(200)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        q = parse_qs(self.rfile.read(n).decode())
        if u.path == "/buy":
            pay_id, err = create_payment(q.get("package_id", [""])[0],
                                         self.client_address[0])
            if err:
                self._send(page_buy())
                return
            self._redir("/pay?id=" + pay_id)
            return
        if u.path == "/claim":
            if not claim_rate_ok(self.client_address[0]):
                self._send(page_claim("Terlalu banyak percobaan. Tunggu 5 menit."))
                return
            raw = q.get("order_code", [""])[0].strip().upper()
            code = raw.replace(" ", "").replace("-", "")
            pays = load_pays()
            pay = None
            for p in pays.values():
                oc = (p.get("order_code") or "").replace("-", "")
                if oc == code and code:
                    pay = p
                    break
            if not pay:
                self._send(page_claim("Kode order tidak ditemukan."))
                return
            if pay["status"] == "paid":
                # sudah lunas: aktifkan IP saat ini
                activate_payment_for_ip(pay, self.client_address[0])
                self._send(success("QRIS-" + pay["id"][:6].upper(),
                                   int(pay["duration"])))
                return
            # cek ke Mayar apakah sudah bayar
            cfg = pay_config()
            if mayar_check_status(cfg, pay) == "paid":
                activate_payment_for_ip(pay, self.client_address[0])
                self._send(success("QRIS-" + pay["id"][:6].upper(),
                                   int(pay["duration"])))
            else:
                self._send(page_claim("Belum ada pembayaran untuk kode ini."))
            return
        if u.path == "/pay/confirm":
            # mode demo: simulasi pembayaran berhasil
            cfg = pay_config()
            if pay_mode(cfg) != "demo":
                self.send_response(403)
                self.end_headers()
                return
            pay_id = q.get("id", [""])[0]
            pays = load_pays()
            pay = pays.get(pay_id)
            if not pay or pay["ip"] != self.client_address[0]:
                self.send_response(403)
                self.end_headers()
                return
            activate_payment(pay_id)
            self._send(success("QRIS-" + pay_id[:6].upper(),
                               int(pay["duration"])))
            return
        if u.path == "/admin/mayar":
            if self._need_auth():
                return
            cfg = pay_config()
            cfg["mode"] = "mayar" if q.get("mode", ["demo"])[0] == "mayar" else "demo"
            m = cfg["mayar"]
            m["api_base"] = q.get("api_base", [m.get("base", "")])[0] or m.get("base", "")
            m["base"] = m["api_base"]
            new_key = q.get("api_key", [""])[0].strip()
            if new_key:
                m["api_key"] = new_key
            m["product_id"] = q.get("product_id", [""])[0].strip()
            m["webhook_token"] = q.get("webhook_token", [""])[0].strip()
            json.dump(cfg, open(PAYF, "w"), indent=1)
            self._redir("/admin/?msg=Pengaturan+Mayar+disimpan")
            return
        if u.path == "/admin/gen":
            if self._need_auth():
                return
            try:
                cnt = max(1, min(100, int(q.get("n", ["5"])[0] or 5)))
            except ValueError:
                cnt = 5
            try:
                uses = max(1, min(50, int(q.get("uses", ["1"])[0] or 1)))
            except ValueError:
                uses = 1
            try:
                hari = max(0, min(365, int(q.get("hari", ["0"])[0] or 0)))
            except ValueError:
                hari = 0
            try:
                duration = int(q.get("duration", ["0"])[0] or 0)
            except ValueError:
                duration = 0
            if duration not in DUR_LABEL:
                duration = 0
            d = load()
            now = datetime.datetime.now().isoformat(timespec="seconds")
            exp = ((datetime.datetime.now() + datetime.timedelta(days=hari))
                   .isoformat(timespec="seconds") if hari else None)
            for _ in range(cnt):
                c = gen_code()
                while c in d:
                    c = gen_code()
                d[c] = {"created": now, "max_uses": uses, "uses": 0,
                        "expires": exp, "duration": duration}
            save(d)
            self._redir("/admin/?msg=" + str(cnt) + "+voucher+baru+dibuat")
            return
        if u.path.startswith("/connect"):
            raw = q.get("voucher", [""])[0] or ""
            norm = re.sub(r"[^A-Z0-9]", "", raw.strip().upper())
            d, err, code = cek_voucher(norm)
            if err:
                self._send(form(err))
                return
            v = d[code]
            dur = int(v.get("duration", 0) or 0)
            v["uses"] += 1
            v["last_used"] = datetime.datetime.now().isoformat(timespec="seconds")
            v["last_ip"] = self.client_address[0]
            save(d)
            ip = self.client_address[0]
            if dur > 0:
                # sesi berdurasi: catat akhir masa aktif + timeout ipset mengikuti
                end = datetime.datetime.now().timestamp() + dur
                s = load_ses()
                s[ip] = {"code": code, "start": datetime.datetime.now().isoformat(timespec="seconds"),
                         "end": end, "duration": dur}
                save_ses(s)
                subprocess.run(["ipset", "add", "portal_allow", ip,
                                "timeout", str(dur)], capture_output=True)
            else:
                subprocess.run(["ipset", "add", "portal_allow", ip], capture_output=True)
            self._send(success(code, dur))
            return
        self.send_response(404)
        self.end_headers()

# bersihkan sesi kadaluarsa tiap 30 detik (background)
threading.Thread(target=sweep, daemon=True).start()

class PortalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    timeout = 10  # jangan nunggu request setengah-setengah lebih dari 10 detik

PortalServer((BIND, PORT), H).serve_forever()
