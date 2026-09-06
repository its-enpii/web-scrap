import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_type, human_click, human_delay

class OpenRouterFlow(BaseFlow):
    name = "OpenRouter (openrouter.ai -> AI-Omni)"
    description = "Login ke OpenRouter via Google OAuth Clerk, buat API Key di /settings/keys, dan daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
        self.omni_password = config.get("omni_password", "its.enpii-118")
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_openrouter.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_openrouter_api_key(self, context: BrowserContext, or_page: Page, account: Dict[str, str]) -> Optional[str]:
        api_key = None
        email = account["email"]

        try:
            # 1. Buka OpenRouter
            self.mark_stage("navigate")
            print("[*] [OpenRouter] Membuka https://openrouter.ai...")
            await or_page.goto("https://openrouter.ai", wait_until="domcontentloaded")
            await human_delay(2.0, 3.0)

            # 2. Buka Modal Sign Up / Sign In
            signup_btn = or_page.locator("header button:has-text('Sign Up'), button:has-text('Sign Up'), a:has-text('Sign Up')").first
            if await signup_btn.is_visible():
                self.mark_stage("open_modal")
                print("[*] [OpenRouter] Mengklik tombol 'Sign Up'...")
                await human_click(signup_btn)
                await human_delay(1.5, 2.5)

                # 3. Klik Tombol Google OAuth di Modal Clerk
                self.mark_stage("click_google")
                google_btn = or_page.locator("button.cl-socialButtonsIconButton__google, button.cl-button__google").first
                await google_btn.wait_for(state="visible", timeout=12000)
                print("[*] [OpenRouter] Mengklik tombol Google OAuth Clerk...")
                await human_click(google_btn)
                await or_page.wait_for_load_state("domcontentloaded")

                # 4. Handle Google Login
                await fill_google_login(or_page, account)
                await human_delay(2.0, 3.0)

                # 5. Tunggu protect-check & callback redirect
                print("[*] [OpenRouter] Menunggu verifikasi Clerk protect-check...")
                for _ in range(35):
                    await or_page.wait_for_timeout(1000)
                    url = or_page.url
                    if "protect-check" not in url and "sso-callback" not in url and "accounts.google" not in url:
                        break

            # 6. Buka halaman keys
            self.mark_stage("open_keys_page")
            print("[*] [OpenRouter] Menuju halaman API Keys (https://openrouter.ai/settings/keys)...")
            await or_page.goto("https://openrouter.ai/settings/keys", wait_until="domcontentloaded")
            await human_delay(2.5, 3.5)

            # 7. Klik Create Key
            self.mark_stage("create_key")
            create_btn = or_page.locator("button:has-text('Create Key'), button:has-text('Create API Key'), button:has-text('Create')").first
            await create_btn.wait_for(state="visible", timeout=15000)
            print("[*] [OpenRouter] Mengklik 'Create Key'...")
            await human_click(create_btn, pre_delay=0.4, post_delay=1.0)
            await human_delay(1.5, 2.5)

            # Isi nama key jika ada modal
            name_in = or_page.locator("input[placeholder*='Name' i], [role='dialog'] input[type='text']").first
            if await name_in.is_visible():
                key_name = email.split("@")[0]
                await human_type(name_in, key_name)
                await human_delay(0.5, 1.0)
                sub_btn = or_page.locator("[role='dialog'] button:has-text('Create'), [role='dialog'] button[type='submit']").last
                await human_click(sub_btn)
                await human_delay(2.5, 3.5)

            # 8. Ekstrak API Key dari modal atau clipboard
            self.mark_stage("extract_key")
            copy_btn = or_page.locator("button:has-text('Copy'), [role='dialog'] button[aria-label*='copy' i]").first
            if await copy_btn.is_visible():
                await human_click(copy_btn, pre_delay=0.2, post_delay=0.5)
                try:
                    cb = await or_page.evaluate("navigator.clipboard.readText()")
                    if cb and cb.strip().startswith("sk-or-"):
                        api_key = cb.strip()
                except Exception:
                    pass

            if not api_key:
                val_in = or_page.locator("[role='dialog'] input[value^='sk-or-']").first
                if await val_in.is_visible():
                    api_key = await val_in.get_attribute("value")

            if not api_key:
                content = await or_page.content()
                keys = re.findall(r'(sk-or-[A-Za-z0-9_-]{20,})', content)
                if keys:
                    api_key = keys[0]

            if api_key:
                print(f"[+] [OpenRouter] Berhasil mendapatkan API Key: {api_key[:12]}...{api_key[-4:]}")
            else:
                raise Exception("Gagal mengekstrak API Key OpenRouter")

            return api_key

        except Exception as e:
            self.mark_failed("create_key", str(e), retryable=True)
            return None

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int
    ) -> bool:
        email = account["email"]
        print(f"\n[{index+1}/{total}] Memproses Akun OpenRouter: {email}")
        self.set_current_account(email)

        or_page = main_page or await context.new_page()

        try:
            api_key = await self._obtain_openrouter_api_key(context, or_page, account)
            if not api_key:
                return False

            if self.output_mode == "txt":
                self.save_key(email, api_key)
            elif self.output_mode == "omni" and main_page:
                self.mark_stage("omni_save")
                await save_api_key_to_omni(main_page, "openrouter", email, api_key)

            self.mark_success()
            return True

        except Exception as e:
            self.mark_failed("general", str(e), retryable=True)
            return False
