import asyncio
import re
from typing import Any, Dict, Optional

from playwright.async_api import BrowserContext, Page

from datetime import datetime, timezone

from .account_state import derive_username
from .base import BaseFlow
from .human_helper import human_click, human_delay, human_type
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni


class UnoRouterFlow(BaseFlow):
    name = "UnoRouter"
    description = "Register/Login ke unorouter.com (username+password), buat API key, daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_unorouter.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _wait_turnstile(self, page: Page) -> bool:
        print("[*] [UnoRouter] Menunggu Turnstile ter-solve otomatis...")
        token_input = page.locator('input[name="cf-turnstile-response"]').first

        try:
            await token_input.wait_for(state="attached", timeout=6000)
        except Exception:
            return True

        for _ in range(40):
            try:
                val = await token_input.input_value()
                if val and len(val) > 10:
                    print("[+] [UnoRouter] Turnstile berhasil ter-solve.")
                    return True
            except Exception:
                pass

            # Coba klik iframe Turnstile jika ada
            try:
                cf_frame = page.locator("iframe[src*='challenges.cloudflare.com']").first
                if await cf_frame.is_visible():
                    await cf_frame.click(timeout=1000)
            except Exception:
                pass

            await asyncio.sleep(1.5)

        print("[-] [UnoRouter] Token Turnstile tidak terisi dalam 60 detik.")
        return False

    async def _register(self, page: Page, username: str, password: str) -> bool:
        print("[*] [UnoRouter] Membuka halaman registrasi...")
        await page.goto("https://unorouter.com/en/register", wait_until="domcontentloaded", timeout=45000)
        await human_delay(2.0, 3.5)

        username_input = page.locator('input[name="username"]').first
        password_input = page.locator('input[name="password"]').first
        await human_type(username_input, username)
        await human_type(password_input, password)

        if not await self._wait_turnstile(page):
            raise RuntimeError("turnstile_timeout")

        submit_button = page.locator('button[type="submit"]:has-text("Create Account")').first
        await human_click(submit_button, pre_delay=0.4, post_delay=1.5)
        await human_delay(4.0, 6.0)

        if "/en/login" in page.url:
            print("[+] [UnoRouter] Registrasi berhasil.")
            return True

        # Pesan IP-limit dari unorouter.com (1 akun per IP): "An account has
        # already been registered from this IP address". Ini BUKAN berarti
        # username ini yang sudah terdaftar — akun sama sekali tidak dibuat.
        # Harus gagal-loud (bukan lanjut login) agar failover proxy mengambil
        # alih dengan IP berbeda.
        page_text = await page.locator("body").inner_text()
        if "registered from this ip" in page_text.lower():
            raise RuntimeError("register_blocked_ip_limit")

        if any(word in page_text.lower() for word in ["already", "taken", "exist"]):
            print("[i] [UnoRouter] Username sudah terdaftar, melanjutkan ke login.")
            return True

        if "/en/register" not in page.url:
            return True

        raise RuntimeError(page_text.strip().splitlines()[0] if page_text.strip() else "register_failed")

    async def _login(self, page: Page, username: str, password: str) -> bool:
        print("[*] [UnoRouter] Membuka halaman login...")
        await page.goto("https://unorouter.com/en/login", wait_until="domcontentloaded", timeout=45000)
        await human_delay(1.5, 3.0)

        username_input = page.locator('input[name="username"]').first
        password_input = page.locator('input[name="password"]').first
        await human_type(username_input, username)
        await human_type(password_input, password)

        if not await self._wait_turnstile(page):
            raise RuntimeError("turnstile_timeout")

        submit_button = page.locator('button[type="submit"]:has-text("Sign In")').first
        await human_click(submit_button, pre_delay=0.4, post_delay=1.5)

        for _ in range(25):
            await page.wait_for_timeout(1000)
            u = page.url
            if "/dashboard" in u or "/token" in u:
                print("[+] [UnoRouter] Login berhasil.")
                return True

        page_text = await page.locator("body").inner_text()
        if "dashboard" in page.url or "token" in page.url:
            print("[+] [UnoRouter] Login berhasil.")
            return True

        print(f"[-] [UnoRouter] Login gagal: {page_text.strip().splitlines()[0] if page_text.strip() else 'tidak dialihkan ke dashboard'}")
        raise RuntimeError("login_failed")

    async def _extract_key_from_row(self, row, page: Page) -> Optional[str]:
        copy_button = row.locator('button[aria-label="Copy Key"]').first
        if await copy_button.is_visible():
            print("[*] [UnoRouter] Mengcopy API key dari baris tabel...")
            await human_click(copy_button, pre_delay=0.3, post_delay=1.0)
            try:
                clipboard_key = (await page.evaluate("navigator.clipboard.readText()") or "").strip()
                if re.fullmatch(r"sk-[A-Za-z0-9]{40,}", clipboard_key):
                    return clipboard_key
            except Exception as error:
                print(f"[-] [UnoRouter] Gagal membaca clipboard: {error}")

        reveal_button = row.locator('button[aria-label="Reveal"]').first
        if await reveal_button.is_visible():
            print("[*] [UnoRouter] Mereveal API key dari baris tabel...")
            await human_click(reveal_button, pre_delay=0.3, post_delay=0.8)
            try:
                key_text = (await row.locator("code").first.inner_text()).strip()
                if re.fullmatch(r"sk-[A-Za-z0-9]{40,}", key_text):
                    return key_text
            except Exception:
                pass

        return None

    async def _create_key(self, context: BrowserContext, page: Page, username: str) -> Optional[str]:
        print("[*] [UnoRouter] Membuka halaman API key...")
        await page.goto("https://unorouter.com/en/token", wait_until="domcontentloaded", timeout=45000)
        await human_delay(1.5, 3.0)

        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        # 1. Cek apakah sudah ada row key di tabel
        rows = page.locator("tbody tr")
        if await rows.count() > 0:
            for r_idx in range(await rows.count()):
                r = rows.nth(r_idx)
                k = await self._extract_key_from_row(r, page)
                if k:
                    print(f"[+] [UnoRouter] Mengambil key yang sudah ada di tabel: {k[:8]}...")
                    return k

        # 2. Buat key baru
        create_key_button = page.locator('button:has-text("Create Key")').last
        if await create_key_button.is_visible():
            await human_click(create_key_button, pre_delay=0.4, post_delay=1.0)

            name_input = page.locator('input[name="name"]').first
            if await name_input.is_visible():
                await human_type(name_input, username)

            create_button = page.locator('button:has-text("Create"):not(:has-text("Key"))').last
            if await create_button.is_visible():
                await human_click(create_button, pre_delay=0.4, post_delay=2.0)
                await human_delay(3.0, 5.0)

        # Cek row setelah create
        rows = page.locator("tbody tr")
        if await rows.count() > 0:
            for r_idx in range(await rows.count()):
                r = rows.nth(r_idx)
                k = await self._extract_key_from_row(r, page)
                if k:
                    print(f"[+] [UnoRouter] API key berhasil diperoleh: {k[:8]}...")
                    return k

        # Fallback: cari dari seluruh content
        content = await page.content()
        keys = re.findall(r'(sk-[A-Za-z0-9]{45,})', content)
        if keys:
            print(f"[+] [UnoRouter] API key ditemukan dari content: {keys[0][:8]}...")
            return keys[0]

        print("[-] [UnoRouter] Baris API key tidak ditemukan.")
        return None

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        email = account["email"]
        if self.state is None:
            self.attach_state("unorouter")
        state = self.state
        self.set_current_account(email)
        record = state.get(email)
        username = record.get("username") or derive_username(email)
        state.update(email, username=username)

        if record.get("status") == "success":
            print(f"[i] Akun {email}: sudah sukses (key dibuat {record.get('key_created_at') or '-'}), dilewati.")
            return True

        if record.get("status") == "failed" and not record.get("retryable", True):
            print(
                f"[i] Akun {email}: gagal sebelumnya di {record.get('stage')} "
                f"({record.get('error')}), TIDAK bisa diulang otomatis (perlu perbaikan manual)."
            )
            return False

        stage = record.get("stage", "register")
        if stage not in ("register", "login", "key_create", "done"):
            stage = "register"

        password = account.get("password") or "qwertyui"

        try:
            if stage == "register":
                self.mark_stage("register")
                await self._register(main_page, username, password)
                stage = "login"
                self.mark_stage("login")

            if stage == "login":
                self.mark_stage("login")
                await self._login(main_page, username, password)
                stage = "key_create"
                self.mark_stage("key_create")

            if stage == "key_create":
                self.mark_stage("key_create")
                api_key = await self._create_key(context, main_page, username)
                if not api_key:
                    raise RuntimeError("api_key_extraction_failed")

                if self.output_mode == "txt":
                    self.save_key(email, api_key)
                elif self.output_mode == "omni" and main_page:
                    await save_api_key_to_omni(main_page, "unorouter", email, api_key)

                self.mark_success(key_hint=f"{api_key[:8]}...")
                print(f"[+] [UnoRouter] Sukses memproses akun {email}!")
                return True

            return False

        except Exception as error:
            error_message = str(error)
            print(f"[-] [UnoRouter] Gagal pada stage '{stage}' untuk akun {email}: {error_message}")
            self.mark_failed(stage, error_message, retryable=True)
            return False
