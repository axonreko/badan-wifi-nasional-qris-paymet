# Badan Wifi Nasional — Portal + Pembayaran QRIS (Mayar)

Repo ini berisi **varian portal dengan pembayaran QRIS**.
Untuk portal biasa (voucher saja), lihat repo `badan-wifi-nasional`.

## Isi

| File | Fungsi |
|---|---|
| `portal.py` | Portal lengkap: voucher + beli paket QRIS + klaim + panel admin |
| `qris/mayar.py` | Klien API Mayar asli (sandbox `api.mayar.club` / production `api.mayar.id`) |
| `qris/service.py` | Logika pembayaran (mode demo / mayar) |
| `public_pay.py` | Halaman pembayaran publik via Tailscale Funnel (bisa dibuka pakai kuota HP) |
| `funnel_proxy.py` | Reverse proxy untuk Funnel (`/bayar` → halaman publik) |
| `config.example.json` | Contoh konfigurasi pembayaran |

## Fitur QRIS

- **Beli paket** (`/buy`): 1 jam Rp2rb / 3 jam Rp5rb / 12 jam Rp10rb / 1 hari Rp15rb
- **Bayar** (`/pay`): QR + link pembayaran publik + kode order
- **Klaim** (`/claim`): bayar pakai kuota (matikan WiFi) → connect lagi → masukkan kode
- **Link publik**: `https://<funnel>/bayar/<KODE>` — kode + tombol bayar + status live
- **Panel admin**: pengaturan Mayar (mode, API key, product ID) + riwayat pembayaran
- **Keamanan**: rate limiting, anti-XSS, kode acak, 1 kode = 1 HP aktif

## Instalasi di STB

```bash
git clone https://github.com/axonreko/badan-wifi-nasional-qris-paymet.git
cd badan-wifi-nasional-qris-paymet
# copy portal.py + qris/ ke /opt/portal/, lalu restart portal-web
# (atau pakai install.sh dari repo badan-wifi-nasional lalu timpa portal.py)
```

## Aktifkan Mayar asli

1. Daftar di [mayar.id](https://mayar.id), verifikasi akun
2. Buat produk Membership + tier per paket di dashboard (sandbox dulu)
3. Buat API key → paste di panel admin → ganti mode ke Mayar
4. Daftarkan webhook: `https://<funnel>/webhook/mayar?token=<token>`

Lihat `INTEGRATION.md` untuk detail teknis.
