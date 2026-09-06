import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_type, human_click, human_delay

class BAIFlow(BaseFlow):
    name = "BAI (chat.b.ai -> AI-Omni)"
    description = "Login ke chat.b.ai via Google, buat API Key, dan daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
        self.omni_password = config.get("omni_password", "its.enpii-118")
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_bai.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_bai_api_key(self, context: BrowserContext, bai_page: Page, account: Dict[str, str]) -> Optional[str]:
        api_key = None
        email = account["email"]

        try:
            # 1. Buka chat.b.ai
            self.mark_stage("navigate")
            print("[*] [BAI] Membuka https://chat.b.ai...")
            await bai_page.goto("https://chat.b.ai", wait_until="domcontentloaded")
            await human_delay(3.0, 4.0)

            # 2. Cek apakah ada tombol "Log in"
            login_btn = bai_page.locator("button:has-text('Log in')").first
            try:
                await login_btn.wait_for(state="visible", timeout=8000)
                is_logged_out = True
            except Exception:
                is_logged_out = False

            if is_logged_out:
                self.mark_stage("login")
                print("[*] [BAI] Mengklik tombol 'Log in'...")
                await human_click(login_btn, pre_delay=0.4, post_delay=0.8)
                await human_delay(2.0, 3.0)

                # 3. Klik "Continue with Google" (membuka popup OAuth)
                google_btn = bai_page.locator("button:has-text('Continue with Google')").first
                await google_btn.wait_for(state="visible", timeout=10000)
                print("[*] [BAI] Mengklik 'Continue with Google'...")

                try:
                    async with context.expect_page(timeout=8000) as popup_info:
                        await human_click(google_btn)
                    popup_page = await popup_info.value
                    await popup_page.wait_for_load_state("domcontentloaded")
                    await fill_google_login(popup_page, account)
                    try:
                        await popup_page.wait_for_event("close", timeout=25000)
                    except Exception:
                        if not popup_page.is_closed():
                            await popup_page.close()
                except Exception as auth_error:
                    self.mark_failed("login", f"Google login gagal: {auth_error}", retryable=True)
                    return None

                await human_delay(3.0, 4.0)

            # 4. Buka halaman https://chat.b.ai/key
            self.mark_stage("open_key_page")
            print("[*] [BAI] Menuju halaman API Key (https://chat.b.ai/key)...")
            await bai_page.goto("https://chat.b.ai/key", wait_until="domcontentloaded")
            await human_delay(3.0, 4.0)

            # 5. Klik tombol "Create API key"
            self.mark_stage("create_api_key")
            create_key_btn = bai_page.locator("button:has-text('Create API key'), button:has-text('Create API Key')").first
            await create_key_btn.wait_for(state="visible", timeout=15000)
            print("[*] [BAI] Mengklik 'Create API key'...")
            await human_click(create_key_btn, pre_delay=0.4, post_delay=1.0)
            await human_delay(1.5, 2.5)

            # 6. Isi nama key di modal dan klik Confirm
            modal_in = bai_page.locator(".ant-modal input, [role='dialog'] input").first
            if await modal_in.is_visible():
                key_name = email.split("@")[0]
                await human_type(modal_in, key_name)
                await human_delay(0.5, 1.0)

                confirm_btn = bai_page.locator(".ant-modal button:has-text('Confirm'), .ant-modal button.ant-btn-primary, [role='dialog'] button:has-text('Confirm')").last
                await human_click(confirm_btn)
                print("[*] [BAI] Modal create key disubmit.")
                await human_delay(3.0, 4.0)

            # 7. Salin API Key dari dialog hasil atau clipboard
            self.mark_stage("extract_key")
            modal_copy = bai_page.locator(".ant-modal button:has-text('Copy'), [role='dialog'] button:has-text('Copy')").first
            if await modal_copy.is_visible():
                await human_click(modal_copy, pre_delay=0.3, post_delay=0.5)
                try:
                    cb = await bai_page.evaluate("navigator.clipboard.readText()")
                    if cb and cb.strip().startswith("sk-"):
                        api_key = cb.strip()
                except Exception:
                    pass

            if not api_key:
                # Fallback: cari dari teks modal atau body
                content = await bai_page.content()
                keys = re.findall(r'(sk-[A-Za-z0-9_-]{20,})', content)
                if keys:
                    api_key = keys[0]

            if api_key:
                print(f"[+] [BAI] Berhasil mendapatkan API Key: {api_key[:10]}...{api_key[-4:]}")
            else:
                raise Exception("Gagal mengekstrak API Key dari modal BAI")

            return api_key

        except Exception as e:
            self.mark_failed("create_api_key", str(e), retryable=True)
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
        print(f"\n[{index+1}/{total}] Memproses Akun BAI: {email}")
        self.set_current_account(email)

        bai_page = main_page or await context.new_page()

        try:
            api_key = await self._obtain_bai_api_key(context, bai_page, account)
            if not api_key:
                return False

            if self.output_mode == "txt":
                self.save_key(email, api_key)
            elif self.output_mode == "omni" and main_page:
                self.mark_stage("omni_save")
                await save_api_key_to_omni(main_page, "bai", email, api_key)

            self.mark_success()
            return True

        except Exception as e:
            self.mark_failed("general", str(e), retryable=True)
            return False
