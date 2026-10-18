"""Klien API Mayar (https://docs.mayar.id).

Mendukung sandbox (https://api.mayar.club/hl/v2) dan production
(https://api.mayar.id/hl/v2). Autentikasi: Bearer API key.

Alur yang dipakai (Membership API, sesuai dokumentasi Mayar):
  1. POST /memberships/members/create            -> memberId
  2. POST /memberships/members/{id}/invoice/create -> transactionId + bill URL
  3. User bayar di halaman Mayar (QRIS / e-wallet / VA)
  4. Webhook payment.received (status SUCCESS) -> akses diaktifkan
     (atau polling GET /invoices/{transactionId})
"""
import json
import urllib.request
import urllib.error

SANDBOX_BASE = "https://api.mayar.club/hl/v2"
PROD_BASE = "https://api.mayar.id/hl/v2"


class MayarError(Exception):
    pass


class MayarClient:
    def __init__(self, api_key, base=SANDBOX_BASE, timeout=25):
        if not api_key:
            raise MayarError("Mayar API key kosong. Isi di config.json")
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _req(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode() or "{}")
            except Exception:
                payload = {}
            msg = (payload.get("message") or
                   payload.get("messages") or
                   "Mayar API error HTTP %s" % e.code)
            if isinstance(msg, list):
                msg = ", ".join(msg)
            raise MayarError(str(msg))
        except Exception as e:
            raise MayarError("Gagal menghubungi Mayar: %s" % e)
        # envelope: {statusCode, message, data}
        code = payload.get("statusCode", 200)
        if isinstance(code, int) and code >= 400:
            raise MayarError(str(payload.get("message") or
                                 payload.get("messages") or
                                 "Mayar API error %s" % code))
        data_out = payload.get("data")
        if data_out is None:
            # beberapa endpoint mengembalikan langsung tanpa envelope
            data_out = {k: v for k, v in payload.items()
                        if k not in ("statusCode", "message", "messages")}
        return data_out

    # ---- Membership API ----
    def register_member(self, product_id, tier_id, name, email,
                        mobile=None, period_months=1):
        """Daftarkan pembeli sebagai member. Return memberId."""
        customer = {"name": name, "email": email}
        if mobile:
            customer["mobile"] = mobile
        data = self._req("POST", "/memberships/members/create", {
            "productId": product_id,
            "membershipTierId": tier_id,
            "membershipMonthlyPeriod": period_months,
            "customerInfo": customer,
        })
        mc = data.get("membershipCustomer") or {}
        member_id = (mc.get("memberId") or mc.get("id") or
                     data.get("memberId") or data.get("id"))
        if not member_id:
            raise MayarError("Mayar tidak mengembalikan memberId: %s" % data)
        return member_id

    def create_member_invoice(self, member_id, product_id):
        """Buat invoice untuk member. Return (transaction_id, bill_url)."""
        data = self._req(
            "POST", "/memberships/members/%s/invoice/create" % member_id,
            {"productId": product_id})
        tx = data.get("transactionId") or data.get("id")
        url = data.get("membershipBillUrl") or data.get("link")
        if not tx or not url:
            raise MayarError("Mayar tidak mengembalikan invoice: %s" % data)
        return tx, url

    def get_invoice(self, transaction_id):
        """Ambil status invoice. Return dict mentah."""
        return self._req("GET", "/invoices/%s" % transaction_id)

    @staticmethod
    def is_paid(invoice):
        st = invoice.get("transactionStatus", "")
        st2 = invoice.get("status", "")
        return (str(st).lower() in ("paid", "success", "successful") or
                str(st2).lower() in ("paid", "success", "successful"))


def verify_webhook_token(query_token, expected_token):
    """Mayar tidak sign body (tidak seperti Stripe), jadi token rahasia
    di query URL adalah verifikasinya."""
    return bool(expected_token) and query_token == expected_token


def parse_webhook(payload):
    """Urai webhook Mayar. Return dict {event, transaction_id, paid, amount,
    payment_method} atau None jika bukan event pembayaran."""
    if not isinstance(payload, dict):
        return None
    event = payload.get("event")
    data = payload.get("data") or {}
    tid = data.get("transactionId") or data.get("id")
    st = str(data.get("status", "")).lower()
    st2 = str(data.get("transactionStatus", "")).lower()
    paid = st in ("paid", "success", "successful") or \
        st2 in ("paid", "success", "successful")
    return {
        "event": event,
        "transaction_id": tid,
        "paid": paid and event == "payment.received",
        "amount": data.get("amount"),
        "payment_method": data.get("paymentMethod"),
    }
