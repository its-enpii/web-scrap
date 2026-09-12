# Multi-Account Google Automation Tool

Sistem otomasi modular berbasis **Python & Playwright** untuk melakukan registrasi/login akun Google secara massal ke berbagai provider AI, dengan opsi **Auto Add ke AI-Omni** atau **Catat email|key ke folder results/**.

---

## Fitur Utama
- **Account State Tracking**: Status per akun tersimpan di `state/<provider>.json` dengan field `status`, `stage`, `error`, `retryable`, `attempts`, dan `key_hint`.
- **Skip/Resume Otomatis**: Akun sukses dilewati; kegagalan non-retryable dilaporkan `perlu tindakan manual: <error>`; eksekusi berhenti saat mencapai `MAX_ATTEMPTS` (default `3`, dapat diubah via environment variable).

- **Multi-Provider Support**: Mendukung 7 provider AI (`kiro_omni`, `opencode_zen`, `openrouter`, `tokenrouter`, `bai`, `qwencloud`, `unorouter`) dan opsi untuk menjalankan **SEMUA** provider sekaligus (`all`).
- **Opsi Output Fleksibel**:
  1. **Auto Add ke AI-Omni Portal**: Otomatis memasukkan dan menyimpan API Key/Device Auth ke dashboard AI-Omni.
  2. **Catat email|key ke folder `results/`**: Cukup generate API Key di provider lalu catat baris `email|api_key` ke file `.txt` di folder `results/` tanpa perlu membuka AI-Omni.
- **Pemisahan Data Akun & Proxy**: File akun (`accounts.txt`) dan proxy (`proxies.txt`) terpisah untuk kemudahan manajemen.
- **Auto-Detect Proxy & Rotasi**: Otomatis mendeteksi keberadaan file proxy dan melakukan rotasi per akun (round-robin). Jika tidak ada proxy, sistem otomatis menggunakan direct connection.
- **Sesi Browser Terisolasi**: Setiap akun dijalankan pada context browser terpisah untuk mencegah kebocoran sesi antar akun.
- **Handling Recovery Email**: Mendukung pengisian otomatis prompt verifikasi email pemulihan (recovery email) dari Google.

---

## Daftar Provider yang Didukung

| No | Key Provider | Layanan Target | Deskripsi Alur |
|---|---|---|---|
| 0 | `all` | **Semua Provider** | Menjalankan seluruh provider secara berurutan untuk seluruh akun. |
| 1 | `kiro_omni` | **Kiro AI** | Mengambil link Device Code di AI-Omni -> Login Google -> Klik Approve & Done. |
| 2 | `opencode_zen` | **Opencode Zen** (`opencode.ai/zen`) | Login Google di Opencode -> Salin API Key (`sk-p4k...`). |
| 3 | `openrouter` | **OpenRouter** (`openrouter.ai`) | Login Google di OpenRouter -> Buat API Key (`sk-or-v1...`). |
| 4 | `tokenrouter` | **TokenRouter** (`tokenrouter.com`) | Login Google Popup di TokenRouter -> Buat Key di Console (`sk-irga...`). |
| 5 | `bai` | **BAI** (`chat.b.ai`) | Login Google Popup di `chat.b.ai` -> Buat API Key di `/key` (`sk-...`). |
| 6 | `qwencloud` | **QwenCloud** (`qwencloud.com`) | Registrasi/Login di QwenCloud -> Buat API Key (`sk-ws-...`). |
| 7 | `unorouter` | **UnoRouter** (`unorouter.com`) | Register/Login username+password → buat & copy API Key (`sk-...`). |
| 8 | `codecraft` | **CodeCraft** (`codecraftapi.com`) | Register Google OAuth -> pilih plan Basic Yearly -> kupon `DEVWEEK` -> buat & simpan API Key (`cc_...`). |

---

## Struktur File Input

### 1. File Akun (`accounts.txt`)
Buat file `accounts.txt` di root direktori dengan format (1 akun per baris):
```text
email|password|recovery_email_atau_phone (opsional)
```

**Contoh `accounts.txt`:**
```text
user1@gmail.com|Password123!
user2@gmail.com|PasswordRahasia|recovery2@gmail.com
user3@gmail.com|PasswordLainnya|08123456789
```

### 2. File Proxy (`proxies.txt`) - *Opsional (Auto-Detected)*
Buat file `proxies.txt` di root direktori jika ingin menggunakan proxy:
```text
http://username:password@proxy.example.com:8080
socks5://username:password@127.0.0.1:1080
http://123.45.67.89:8080
192.168.1.50:8080:username:password
192.168.1.51:8080
```

---

## Cara Menjalankan

### 1. Mode Interaktif (Pilih Menu di Terminal)
```bash
python main.py
```
Akan memandu Anda melalui 2 tahap pilihan:

**Tahap 1: Pilih Provider**
```text
==========================================
   PILIH TARGET WEBSITE / FLOW OTOMASI    
==========================================
 [0] SEMUA PROVIDER (Jalankan semua alur)
 [1] Kiro AI (via AI-Omni) (kiro_omni)
 [2] Opencode Zen (opencode_zen)
 [3] OpenRouter (openrouter)
 [4] TokenRouter (tokenrouter)
 [5] BAI (chat.b.ai -> AI-Omni) (bai)
 [7] UnoRouter (unorouter.com -> AI-Omni) (unorouter)
==========================================
Pilih nomor alur [0-6] atau 'q' untuk keluar:
```

**Tahap 2: Pilih Metode Output**
```text
==========================================
           PILIH METODE OUTPUT            
==========================================
 [1] Auto Add ke AI-Omni Portal (Default)
     -> Login ke provider, ambil key, dan masukkan otomatis ke Dashboard AI-Omni
 [2] Catat email|key ke folder 'results/'
     -> Login ke provider, generate key, dan simpan hasilnya ke file .txt (tanpa masuk ke AI-Omni)
==========================================
Pilih mode output [1-2] (tekan Enter untuk opsi 1):
```

---

### 2. Mode Perintah Langsung (CLI Direct)

```bash
# 1. Menjalankan dengan Auto Add ke AI-Omni (Default):
python main.py --flow openrouter --output omni

# 2. Menjalankan hanya untuk mencatat email|key ke folder results/:
python main.py --flow openrouter --output txt

# 3. Menjalankan semua provider dan simpan hasilnya ke folder results/:
python main.py --flow all --output txt

# 4. Menentukan nama path file txt khusus:
python main.py --flow bai --output txt --output-file results/custom_bai.txt

# 5. Opsi proxy dan headless:
python main.py --flow opencode_zen --output txt --headless --proxy http://user:pass@127.0.0.1:8080

# 6. Melihat status tanpa browser:
python main.py --status
python main.py --status unorouter
```

---

## Folder Output (`results/`)

Jika memilih mode output `.txt`, semua key akan tersimpan rapi per provider di folder **`results/`**:

```text
results/
state/
+-- keys_opencode_zen.txt
+-- keys_openrouter.txt
+-- keys_tokenrouter.txt
+-- keys_bai.txt
+-- keys_qwencloud.txt
```

Format isi setiap file:
```text
user1@gmail.com|sk-or-v1-xxxxxxxxxxxxxxxxxxxx
user2@gmail.com|sk-or-v1-yyyyyyyyyyyyyyyyyyyy
```
