import asyncio
import re
from typing import Dict, Any, Optional
from urllib.parse import unquote
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .human_helper import human_click, human_type, human_delay


class APInexFlow(BaseFlow):
    """
    Alur registrasi & pengambilan API Key APInex (apinex.bond).
    1. Buka https://apinex.bond/register
    2. Centang checkbox terms & klik 'Continue with Google'
    3. Google OAuth biasa
    4. Buka https://apinex.bond/keys
    5. Buat API key baru ('Create key')
    6. Ekstrak dan simpan API key ke results/keys_apinex.txt
    """

    name = "APInex (apinex.bond)"
    flow_name = "apinex"
    description = "Register via Google OAuth, buat API Key di /keys, dan simpan key."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "results/keys_apinex.txt"

    async def _obtain_apinex_api_key(
        self, context: BrowserContext, account: Dict[str, Any]
    ) -> Optional[str]:
        email = account.get("email", "")
        print(f"\n[*] [APInex] Memproses akun: {email}")

        page: Page = context.pages[0] if context.pages else await context.new_page()

        # -----------------------------------------------------------
        # 1. Register / Login via Google OAuth
        # -----------------------------------------------------------
        self.mark_stage("navigate")
        print("[*] [APInex] 1. Membuka https://apinex.bond/register ...")
        await page.goto("https://apinex.bond/register", wait_until="domcontentloaded", timeout=45000)
        await human_delay(1.5, 2.5)

        # Cek apakah sesi sudah aktif / di keys
        if "/keys" not in page.url and "/overview" not in page.url:
            self.mark_stage("terms_checkbox")
            print("[*] [APInex] Menunggu checkbox terms dan tombol Google...")
            
            # Tunggu elemen checkbox terms termuat
            cb = page.locator("input[type='checkbox']").first
            await cb.wait_for(state="visible", timeout=30000)
            await human_delay(0.5, 1.0)

            # Centang checkbox
            print("[*] [APInex] Mencentang checkbox terms...")
            await page.evaluate("""() => {
                const cb = document.querySelector("input[type='checkbox']");
                if (cb && !cb.checked) {
                    cb.click();
                }
            }""")
            await human_delay(0.8, 1.2)

            # Klik Continue with Google
            self.mark_stage("google_oauth")
            print("[*] [APInex] 2. Mengklik tombol 'Continue with Google'...")
            google_btn = page.locator("a.user-google-btn, a:has-text('Continue with Google')").first
            await google_btn.wait_for(state="visible", timeout=15000)
            await google_btn.click()

            # Cari tab / halaman Google Sign-In
            google_page: Optional[Page] = None
            for _ in range(40):
                await page.wait_for_timeout(500)
                if "accounts.google.com" in page.url:
                    google_page = page
                    break
                for pg in context.pages:
                    if pg is not page and "accounts.google.com" in pg.url:
                        google_page = pg
                        break
                if google_page:
                    break

            if not google_page:
                raise RuntimeError("Halaman Google Sign In tidak terbuka setelah klik OAuth")

            print("[*] [APInex] Mengisi form login Google...")
            await fill_google_login(google_page, account)

            # Jika Google di popup terpisah, tunggu tertutup
            if google_page is not page:
                try:
                    await google_page.wait_for_event("close", timeout=30000)
                except Exception:
                    if not google_page.is_closed():
                        await google_page.close()

            # Tunggu redirect kembali ke apinex.bond
            print("[*] [APInex] Menunggu redirect kembali ke APInex...")
            for _ in range(60):
                await page.wait_for_timeout(1000)
                if "apinex.bond" in page.url and "api/user/auth/google" not in page.url:
                    break
                for pg in context.pages:
                    if "apinex.bond" in pg.url and "api/user/auth/google" not in pg.url:
                        page = pg
                        break

            await human_delay(2.0, 3.5)

        # Cek apakah redirect mengembalikan error autentikasi
        if "auth_error=" in page.url:
            match = re.search(r'auth_error=([^&]+)', page.url)
            err_msg = unquote(match.group(1)) if match else "Authentication error"
            raise RuntimeError(f"APInex menolak akun ({err_msg})")

        # Periksa error alert di DOM bila ada
        error_elem = page.locator(".admin-login-error").first
        if await error_elem.count() > 0 and await error_elem.is_visible():
            err_text = (await error_elem.text_content() or "").strip()
            if err_text:
                raise RuntimeError(f"APInex login error: {err_text}")

        print(f"[+] [APInex] Sesi Google OAuth berhasil mendarat di: {page.url}")

        # -----------------------------------------------------------
        # 2. Buka https://apinex.bond/keys
        # -----------------------------------------------------------
        self.mark_stage("navigate_keys")
        print("[*] [APInex] 3. Menuju halaman API Keys (https://apinex.bond/keys)...")
        await page.goto("https://apinex.bond/keys", wait_until="domcontentloaded", timeout=45000)
        await human_delay(2.0, 3.0)

        # Cek apakah terlempar ke login kembali (sesi tidak sah)
        if "/login" in page.url or "/register" in page.url:
            error_elem = page.locator(".admin-login-error").first
            err_text = ""
            if await error_elem.count() > 0:
                err_text = (await error_elem.text_content() or "").strip()
            raise RuntimeError(f"Gagal mengakses /keys, diarahkan ke {page.url}. {err_text}".strip())

        # -----------------------------------------------------------
        # 3. Klik tombol 'Create key'
        # -----------------------------------------------------------
        self.mark_stage("create_key_modal")
        print("[*] [APInex] Mencari tombol 'Create key'...")
        create_btn = page.locator("button:has-text('Create key')").first
        await create_btn.wait_for(state="visible", timeout=25000)
        await human_click(create_btn, pre_delay=0.3, post_delay=0.8)
        await human_delay(1.0, 1.5)

        # -----------------------------------------------------------
        # 4. Mengisi form & submit pembuatan key
        # -----------------------------------------------------------
        self.mark_stage("submit_key")
        key_name = f"key-{email.split('@')[0]}"
        print(f"[*] [APInex] Mengisi nama key: {key_name} ...")
        name_input = page.locator("input#key-name").first
        await name_input.wait_for(state="visible", timeout=10000)
        await human_type(name_input, key_name)
        await human_delay(0.5, 1.0)

        print("[*] [APInex] Mengklik tombol submit 'Create key'...")
        modal_submit_btn = page.locator("button.btn-primary:has-text('Create key')").last
        await human_click(modal_submit_btn, pre_delay=0.3, post_delay=1.0)
        await human_delay(3.0, 4.5)

        # -----------------------------------------------------------
        # 5. Ekstraksi API key dari modal 'Save your key'
        # -----------------------------------------------------------
        self.mark_stage("extract_key")
        print("[*] [APInex] 4. Mengekstrak API Key...")
        api_key = None

        # Modal 'Save your key' menampilkan key di dalam .reveal-box code
        reveal_box = page.locator(".reveal-box code, .reveal-box").first
        if await reveal_box.count() > 0:
            txt = (await reveal_box.text_content() or "").strip()
            if txt.startswith("sk-") and len(txt) > 20:
                api_key = txt

        # Fallback via regex di konten halaman
        if not api_key:
            content = await page.content()
            m = re.search(r'(sk-[A-Za-z0-9_-]{25,})', content)
            if m:
                api_key = m.group(1)

        # Fallback via tombol Copy key
        if not api_key:
            try:
                copy_btn = page.locator("button:has-text('Copy key')").first
                if await copy_btn.count() > 0 and await copy_btn.is_visible():
                    await human_click(copy_btn, pre_delay=0.2, post_delay=0.5)
                    clip_text = await page.evaluate("() => navigator.clipboard ? navigator.clipboard.readText() : ''")
                    if clip_text and clip_text.startswith("sk-"):
                        api_key = clip_text.strip()
            except Exception:
                pass

        if not api_key:
            raise RuntimeError("Gagal mengekstrak API Key APInex (format sk-...)")

        print(f"[+] [APInex] API Key berhasil didapatkan: {api_key[:12]}...{api_key[-4:]}")

        # Tutup modal Save your key jika ada tombol Done
        done_btn = page.locator("button:has-text('Done')").first
        if await done_btn.count() > 0 and await done_btn.is_visible():
            await human_click(done_btn, pre_delay=0.2, post_delay=0.5)

        return api_key

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int,
    ) -> bool:
        """
        Menjalankan alur lengkap APInex untuk satu akun.
        """
        email = account.get("email", "")
        self.set_current_account(email)

        try:
            api_key = await self._obtain_apinex_api_key(context, account)
            if not api_key:
                self.mark_failed("extract_key", "Gagal mendapatkan API Key", retryable=True)
                return False

            self.mark_stage("saving_result")
            self.save_key(email, api_key)
            self.mark_success(key_hint=f"{api_key[:10]}...{api_key[-4:]}")
            print(f"[+] [APInex] SUKSES! API Key tersimpan untuk {email}: {api_key[:12]}...{api_key[-4:]}")
            return True

        except Exception as e:
            err_str = str(e)
            print(f"[-] [APInex] Error pada {email}: {err_str}")
            # Jika ditolak karena domain bukan @gmail.com, tandai non-retryable agar tidak membuang waktu retry
            is_non_retryable = "gmail.com" in err_str.lower()
            self.mark_failed("error", err_str, retryable=not is_non_retryable)
            return False
