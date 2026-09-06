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
    description = "Login ke chat.b.ai via Google, generate API Key, dan daftarkan ke AI-Omni atau simpan ke file."

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

        try:
            self.mark_stage("navigate")
            print(f"[*] [BAI] Membuka https://chat.b.ai/chat...")
            await bai_page.goto("https://chat.b.ai/chat", wait_until="domcontentloaded")
            await human_delay(1.0, 1.8)

            # 2. Klik tombol "Log in"
            login_btn = bai_page.locator("button:has-text('Log in')").first
            if await login_btn.is_visible():
                print("[*] [BAI] Mengklik tombol 'Log in'...")
                await human_click(login_btn, pre_delay=0.4, post_delay=0.8)
                await human_delay(0.8, 1.5)

            # 3. Klik "Continue with Google"
            google_btn = bai_page.locator("button:has-text('Continue with Google')").first
            await google_btn.wait_for(state="visible", timeout=10000)

            print("[*] [BAI] Mengklik 'Continue with Google'...")
            try:
                async with context.expect_page(timeout=5000) as new_page_info:
                    await human_click(google_btn)
                popup_page = await new_page_info.value
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

            # 6. Buka halaman https://chat.b.ai/key
            print("[*] [BAI] Menuju halaman API Key (https://chat.b.ai/key)...")
            await bai_page.goto("https://chat.b.ai/key", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # 6b. Klik tombol "Create API key"
            create_key_btn = bai_page.locator("button:has-text('Create API key'), button:has-text('Create API Key')").first
            await create_key_btn.wait_for(state="visible", timeout=15000)
            await human_click(create_key_btn, pre_delay=0.4, post_delay=1.0)

            # 7. Isikan nama key pada input
            key_name_input = bai_page.locator("input#model-provider-api-key-name, input[name='api-key-create-name']").first
            await key_name_input.wait_for(state="visible", timeout=10000)
            
            key_name = account["email"].split("@")[0]
            print(f"[*] [BAI] Mengisi nama API Key: {key_name}...")
            await human_type(key_name_input, key_name)

            # 8. Klik Confirm
            confirm_btn = bai_page.locator("button:has-text('Confirm')").first
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await human_click(confirm_btn, pre_delay=0.4, post_delay=1.5)
            await human_delay(2.0, 3.0)

            # 9. Copy API key yang ditampilkan (sk-...)
            key_span = bai_page.locator("span:has-text('sk-')").first
            if await key_span.is_visible():
                api_key = (await key_span.inner_text()).strip()
            else:
                modal_body = bai_page.locator(".ant-modal-body").first
                if await modal_body.is_visible():
                    body_text = await modal_body.inner_text()
                    match = re.search(r'(sk-[a-zA-Z0-9_-]+)', body_text)
                    if match:
                        api_key = match.group(1).strip()

            self.mark_stage("extract_key")
            if api_key:
                print(f"[+] [BAI] Berhasil mendapatkan API Key: {api_key[:10]}...")
            else:
                print("[-] [BAI] Gagal mengekstrak API Key dari modal.")

            cancel_or_copy = bai_page.locator(".ant-modal-body button").first
            if await cancel_or_copy.is_visible():
                try:
                    await human_click(cancel_or_copy, pre_delay=0.2, post_delay=0.4)
                except Exception:
                    pass

            return api_key

        except Exception as e:
            print(f"[-] [BAI] Terjadi error saat generate API Key di chat.b.ai: {e}")
            self.mark_failed("extract_key", f"generate API key gagal: {e}", retryable=True)
            return None

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        api_key = await self._obtain_bai_api_key(context, main_page, account)
        if not api_key:
            print(f"[-] Gagal mendapatkan API key untuk {account['email']}")
            if self.state is None:
                self.mark_failed("extract_key", "API key tidak ditemukan setelah generate", retryable=True)
            return False

        self.mark_stage("save_key")
        if self.output_mode == "txt":
            self.save_key(account["email"], api_key)
            self.mark_success(f"{api_key[:10]}...{api_key[-4:]}")
            return True
        else:
            saved = await save_api_key_to_omni(main_page, "openai-compatible-chat", account["email"], api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if saved:
                self.mark_success(f"{api_key[:10]}...{api_key[-4:]}")
            else:
                self.mark_failed("save_key", "AI-Omni menolak atau gagal menyimpan API key", retryable=True)
            return saved
