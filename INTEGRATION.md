"""Contoh integrasi paket qris ke portal.py (captive portal).

Salin repo ini sejajar dengan portal, mis. /opt/portal/qris/,
lalu di portal.py:

    import sys
    sys.path.insert(0, "/opt/portal")   # agar paket qris bisa diimpor
    from qris import PaymentService

    svc = PaymentService(
        config_path="/opt/portal/payment.json",   # copy dari config.example.json
        store_path="/opt/portal/payments.json",
        on_paid=aktifkan_internet,  # callback: (ip, duration_detik, ref)
    )

    def aktifkan_internet(ip, duration, ref):
        # 1. catat sesi berdurasi
        # 2. ipset add portal_allow <ip> timeout <duration>

Route yang dibutuhkan (lihat portal.py repo utama sebagai referensi):
  GET  /buy            -> daftar paket (svc.packages())
  POST /buy            -> svc.create_payment(pkg_id, client_ip) -> redirect /pay?id=
  GET  /pay?id=        -> tampilkan QR (mode demo) atau bill_url (mode mayar)
  GET  /pay/qr?id=     -> PNG QR (mode demo; generate dari pay["qr_data"])
  POST /pay/confirm    -> svc.confirm_demo(pay_id, client_ip)  [demo saja]
  GET  /pay/status?id= -> svc.check_status(pay_id)             [polling, mode mayar]
  POST /webhook/mayar?token= -> svc.handle_webhook(payload)    [mode mayar]

Fungsi on_paid dipanggil otomatis saat:
  - confirm_demo() (mode demo), atau
  - check_status()/handle_webhook() mendeteksi pembayaran lunas (mode mayar).
"""
