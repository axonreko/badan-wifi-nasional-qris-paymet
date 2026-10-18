# Badan Wifi Nasional — Modul Pembayaran QRIS (Mayar)

Modul pembayaran paket internet via QRIS untuk captive portal,
pakai **Mayar API** (https://docs.mayar.id).

## Status

- **Mode `demo`**: jalan tanpa API key. QR dibuat lokal, pembayaran
  disimulasikan via tombol. Untuk uji alur UX.
- **Mode `mayar`**: pakai API asli Mayar, default ke **sandbox**
  (`https://api.mayar.club/hl/v2`). Tinggal isi `api_key` di config
  → langsung bisa transaksi sandbox seperti aslinya.

## Yang perlu disiapkan (untuk mode mayar)

1. Daftar di [mayar.id](https://mayar.id), verifikasi akun.
2. Di dashboard Mayar (sandbox dulu), buat:
   - 1 produk **Membership** bernama mis. "Voucher Wifi"
   - 1 tier per paket (harga = harga paket), catat `tier_id`-nya
   - Catat `product_id`
3. Buat **API key** (read/write) di menu Integrasi → API Keys.
4. Buat **webhook token** bebas (string acak), daftarkan webhook URL:
   `https://<domain-anda>/webhook/mayar?token=<token-anda>`

## Konfigurasi

```bash
cp config.example.json config.json
# edit config.json:
#   "mode": "mayar",
#   "mayar": {
#     "api_key": "PASTE_API_KEY",
#     "base": "https://api.mayar.club/hl/v2",   # sandbox
#     # "base": "https://api.mayar.id/hl/v2",   # production (nanti)
#     "product_id": "...",
#     "tiers": {"p1": "...", "p2": "...", "p3": "...", "p4": "..."},
#     "webhook_token": "..."
#   }
```

Paket default (bisa diubah di config): 1 jam Rp2.000 · 3 jam Rp5.000 ·
12 jam Rp10.000 · 1 hari Rp15.000.

## Cara kerja (mode mayar)

1. `create_payment(paket, ip)` → `POST /memberships/members/create`
   lalu `POST /memberships/members/{id}/invoice/create`
   → user diarahkan ke `bill_url` Mayar, bayar via QRIS/e-wallet/VA.
2. Mayar mengirim webhook `payment.received` (atau portal polling
   `GET /invoices/{id}`) → status `SUCCESS`.
3. Callback `on_paid(ip, duration, ref)` dipanggil → portal mengaktifkan
   internet untuk IP tersebut selama durasi paket.

Lihat `INTEGRATION.md` untuk contoh penyambungan ke `portal.py`.

## Struktur

```
qris/
  __init__.py
  mayar.py     # klien API Mayar (sandbox + production)
  service.py   # orkestrasi: demo | mayar
config.example.json
INTEGRATION.md
```

## Keamanan

- Jangan commit `config.json` yang berisi API key asli.
- Webhook memakai token rahasia di query URL (Mayar tidak sign body).
