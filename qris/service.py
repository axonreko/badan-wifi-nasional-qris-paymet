"""Orkestrasi pembayaran paket internet via QRIS.

Dua mode (lihat config.json):
  - demo  : tanpa API key. QR dibuat lokal, pembayaran disimulasikan
            via tombol. Cocok untuk uji alur UX.
  - mayar : pakai MayarClient ke https://api.mayar.club/hl/v2 (sandbox)
            atau https://api.mayar.id/hl/v2 (production).
            Butuh: api_key + product_id + tier per paket (dibuat di
            dashboard Mayar).

Penyimpanan: file JSON sederhana (payments.json). Untuk produksi
serius, ganti dengan database.
"""
import json
import os
import secrets
import datetime

from .mayar import MayarClient, MayarError, SANDBOX_BASE

DEFAULT_CONFIG = {
    "mode": "demo",
    "currency": "Rp",
    "packages": [
        {"id": "p1", "label": "1 Jam", "duration": 3600, "price": 2000},
        {"id": "p2", "label": "3 Jam", "duration": 10800, "price": 5000},
        {"id": "p3", "label": "12 Jam", "duration": 43200, "price": 10000},
        {"id": "p4", "label": "1 Hari", "duration": 86400, "price": 15000},
    ],
    "mayar": {
        "api_key": "",
        "base": SANDBOX_BASE,
        # product_id dari dashboard Mayar (produk Membership "Voucher Wifi")
        "product_id": "",
        # tier_id per paket, dibuat di dashboard Mayar (harga = price paket)
        "tiers": {"p1": "", "p2": "", "p3": "", "p4": ""},
        "webhook_token": "",
    },
}


def load_config(path):
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
        # merge default agar key baru tidak hilang
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        merged["mayar"] = dict(DEFAULT_CONFIG["mayar"])
        merged["mayar"].update(cfg.get("mayar", {}))
        return merged
    with open(path, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=1)
    return dict(DEFAULT_CONFIG)


def rupiah(n):
    return "Rp" + f"{int(n):,}".replace(",", ".")


class PaymentService:
    """Inti logika pembayaran. on_paid(ip, duration, ref) adalah callback
    yang diisi aplikasi (mis. portal.py) untuk mengaktifkan internet."""

    def __init__(self, config_path, store_path, on_paid=None):
        self.config = load_config(config_path)
        self.store_path = store_path
        self.on_paid = on_paid

    # ---- storage ----
    def _load(self):
        try:
            if os.path.exists(self.store_path):
                with open(self.store_path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save(self, pays):
        with open(self.store_path, "w") as f:
            json.dump(pays, f, indent=1)

    def get(self, pay_id):
        return self._load().get(pay_id)

    # ---- API ----
    @property
    def mode(self):
        m = self.config.get("mode", "demo")
        if m == "mayar" and not self.config["mayar"].get("api_key"):
            return "demo"  # fallback aman
        return m

    def packages(self):
        return self.config["packages"]

    def _mayar_client(self):
        m = self.config["mayar"]
        return MayarClient(api_key=m["api_key"],
                           base=m.get("base") or SANDBOX_BASE)

    def create_payment(self, package_id, customer_ip,
                       name="wifi-user", email="wifi@local", mobile=None):
        """Buat pembayaran. Return (pay_dict, error)."""
        pkg = next((p for p in self.packages() if p["id"] == package_id), None)
        if not pkg:
            return None, "Paket tidak ditemukan"
        pays = self._load()
        pay_id = secrets.token_hex(6)
        pay = {
            "id": pay_id,
            "package_id": package_id,
            "label": pkg["label"],
            "amount": pkg["price"],
            "duration": pkg["duration"],
            "ip": customer_ip,
            "status": "pending",
            "mode": self.mode,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "transaction_id": None,
            "bill_url": None,
        }
        if self.mode == "mayar":
            try:
                client = self._mayar_client()
                tier = self.config["mayar"]["tiers"].get(package_id, "")
                if not tier:
                    return None, ("tier_id untuk paket %s belum diisi "
                                  "di config.json" % package_id)
                member_id = client.register_member(
                    product_id=self.config["mayar"]["product_id"],
                    tier_id=tier, name=name, email=email, mobile=mobile)
                tx, url = client.create_member_invoice(
                    member_id, self.config["mayar"]["product_id"])
                pay["member_id"] = member_id
                pay["transaction_id"] = tx
                pay["bill_url"] = url
            except MayarError as e:
                return None, "Mayar: %s" % e
        else:
            pay["qr_data"] = "DEMO-QRIS-BWN-" + pay_id.upper()
        pays[pay_id] = pay
        self._save(pays)
        return pay, None

    def check_status(self, pay_id):
        """Cek status ke Mayar (mode mayar) atau kembalikan status lokal."""
        pays = self._load()
        pay = pays.get(pay_id)
        if not pay:
            return None
        if pay["status"] == "paid":
            return pay
        if self.mode == "mayar" and pay.get("transaction_id"):
            try:
                inv = self._mayar_client().get_invoice(pay["transaction_id"])
                if MayarClient.is_paid(inv):
                    self._mark_paid(pays, pay)
            except MayarError:
                pass
        return pays.get(pay_id)

    def confirm_demo(self, pay_id, request_ip):
        """Simulasikan pembayaran berhasil (hanya mode demo)."""
        if self.mode != "demo":
            return False, "Bukan mode demo"
        pays = self._load()
        pay = pays.get(pay_id)
        if not pay or pay["ip"] != request_ip:
            return False, "Pembayaran tidak valid"
        self._mark_paid(pays, pay)
        return True, None

    def handle_webhook(self, payload):
        """Proses webhook Mayar. Return True jika ada pembayaran diaktifkan."""
        from .mayar import parse_webhook
        info = parse_webhook(payload)
        if not info or not info["paid"] or not info["transaction_id"]:
            return False
        pays = self._load()
        for pid, pay in pays.items():
            if (pay.get("transaction_id") == info["transaction_id"]
                    and pay["status"] == "pending"):
                self._mark_paid(pays, pay)
                return True
        return False

    def _mark_paid(self, pays, pay):
        pay["status"] = "paid"
        pay["paid_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        self._save(pays)
        if self.on_paid:
            try:
                self.on_paid(pay["ip"], int(pay["duration"]),
                             "QRIS-" + pay["id"][:6].upper())
            except Exception:
                pass
