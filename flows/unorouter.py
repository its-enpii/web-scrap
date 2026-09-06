import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from playwright.async_api import BrowserContext, Page

from .account_state import AccountState, derive_username
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
            await token_input.wait_for(state="attached", timeout=5000)
        except Exception:
            return True

        for _ in range(15):
            try:
                if await token_input.input_value():
                    print("[+] [UnoRouter] Turnstile berhasil ter-solve.")
                    return True
            except Exception:
                return False
            await asyncio.sleep(2)

        print("[-] [UnoRouter] Token Turnstile tidak terisi dalam 30 detik.")
        return False

    async def _register(self, page: Page, username: str, password: str) -> bool:
        print("[*] [UnoRouter] Membuka halaman registrasi...")
        await page.goto("https://unorouter.com/en/register", wait_until="domcontentloaded")
        await human_delay(2.0, 4.0)

        username_input = page.locator('input[name="username"]').first
        password_input = page.locator('input[name="password"]').first
        await human_type(username_input, username)
        await human_type(password_input, password)

        if not await self._wait_turnstile(page):
            raise RuntimeError("turnstile_timeout")

        submit_button = page.locator('button[type="submit"]:has-text("Create Account")').first
        await human_click(submit_button, pre_delay=0.4, post_delay=1.5)
        await human_delay(5.0, 8.0)

        if "/en/login" in page.url:
            print("[+] [UnoRouter] Registrasi berhasil.")
            return True

        page_text = await page.locator("body").inner_text()
        if any(word in page_text.lower() for word in ["already", "taken", "exist"]):
            print("[i] [UnoRouter] Username sudah terdaftar, melanjutkan ke login.")
            return True

        raise RuntimeError(page_text.strip().splitlines()[0] if page_text.strip() else "register_failed")

    async def _login(self, page: Page, username: str, password: str) -> bool:
        print("[*] [UnoRouter] Membuka halaman login...")
        await page.goto("https://unorouter.com/en/login", wait_until="domcontentloaded")
        await human_delay(1.5, 3.0)

        username_input = page.locator('input[name="username"]').first
        password_input = page.locator('input[name="password"]').first
        await human_type(username_input, username)
        await human_type(password_input, password)

        if not await self._wait_turnstile(page):
            raise RuntimeError("turnstile_timeout")

        submit_button = page.locator('button[type="submit"]:has-text("Sign In")').first
        await human_click(submit_button, pre_delay=0.4, post_delay=1.5)
        try:
            await page.wait_for_url("**/dashboard", timeout=20000)
        except Exception:
            page_text = await page.locator("body").inner_text()
            print(f"[-] [UnoRouter] Login gagal: {page_text.strip().splitlines()[0] if page_text.strip() else 'tidak dialihkan ke dashboard'}")
            raise RuntimeError("login_failed")

        print("[+] [UnoRouter] Login berhasil.")
        return True

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
            key_text = (await row.locator("code").first.inner_text()).strip()
            if re.fullmatch(r"sk-[A-Za-z0-9]{40,}", key_text):
                return key_text

        return None

    async def _create_key(self, context: BrowserContext, page: Page, username: str) -> Optional[str]:
        print("[*] [UnoRouter] Membuka halaman API key...")
        await page.goto("https://unorouter.com/en/token", wait_until="domcontentloaded")
        await human_delay(1.5, 3.0)

        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        create_key_button = page.locator('button:has-text("Create Key")').last
        await human_click(create_key_button, pre_delay=0.4, post_delay=1.0)

        name_input = page.locator('input[name="name"]').first
        await human_type(name_input, username)

        create_button = page.locator('button:has-text("Create"):not(:has-text("Key"))').last
        await human_click(create_button, pre_delay=0.4, post_delay=2.0)
        await human_delay(4.0, 6.0)

        target_row = page.locator("tr", has_text=username).last
        if not await target_row.is_visible():
            print("[-] [UnoRouter] Baris API key baru tidak ditemukan.")
            return None

        api_key = await self._extract_key_from_row(target_row, page)
        if not api_key:
            print("[-] [UnoRouter] API key tidak valid atau gagal diambil.")
            return None

        print(f"[+] [UnoRouter] API key berhasil diperoleh: {api_key[:8]}...")
        return api_key

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        email = account["email"]
        state = AccountState("unorouter")
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
        if record.get("status") == "failed":
            print(f"[i] Akun {email}: gagal sebelumnya di {stage} ({record.get('error')}), melanjutkan dari stage tsb.")

        state.update(email, attempts=record.get("attempts", 0) + 1, status="new", error=None)

        current_stage = stage
        try:
            if stage == "register":
                await self._register(main_page, username, account["password"])
                state.update(email, stage="login", registered_at=datetime.now(timezone.utc).isoformat())
                current_stage = "login"

            await self._login(main_page, username, account["password"])
            state.update(email, stage="key_create")
            current_stage = "key_create"

            api_key = await self._create_key(context, main_page, username)
            if not api_key:
                raise RuntimeError("key_invalid")

            state.update(
                email,
                stage="done",
                status="success",
                retryable=True,
                key_hint=f"{api_key[:8]}...{api_key[-4:]}",
                key_created_at=datetime.now(timezone.utc).isoformat(),
                error=None,
            )
        except Exception as error:
            error_text = str(error)
            retryable = error_text != "login_failed"
            state.update(email, status="failed", stage=current_stage, error=error_text, retryable=retryable)
            print(f"[-] [UnoRouter] Alur gagal pada {current_stage}: {error_text}")
            return False

        if self.output_mode == "txt":
            self.save_key(email, api_key)
        else:
            saved = await save_api_key_to_omni(main_page, "UnoRouter", email, api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return saved

        return True
