import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_type, human_click, human_delay

class TokenRouterFlow(BaseFlow):
    name = "TokenRouter"
    description = "Login ke tokenrouter.com via Google, generate API Key, dan daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_tokenrouter.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_key(self, context: BrowserContext, tr_page: Page, account: Dict[str, str]) -> Optional[str]:
        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        api_key = None

        try:
            self.mark_stage("navigate")
            print("[*] [TokenRouter] Membuka https://www.tokenrouter.com/...")
            await tr_page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded")
            await human_delay(1.0, 1.8)

            # 2. Klik Sign in
            signin_btn = tr_page.locator("button.tr-landing-header-action, button:has-text('Sign In')").first
            if await signin_btn.is_visible():
                print("[*] [TokenRouter] Mengklik 'Sign In'...")
                try:
                    await signin_btn.evaluate("el => el.click()")
                except Exception:
                    await human_click(signin_btn, pre_delay=0.4, post_delay=1.0)
                await human_delay(1.0, 1.8)

            # 3. Klik/Centang checkbox
            checkbox_btn = tr_page.locator("button[type='button'].bg-white, input[type='checkbox']").first
            if await checkbox_btn.is_visible():
                print("[*] [TokenRouter] Mencentang persetujuan Conditions of Use...")
                await human_click(checkbox_btn)

            self.mark_stage("login")
            # 4. Klik Google
            google_btn = tr_page.locator("button.tr-auth-social-button, button:has-text('Google')").first
            await google_btn.wait_for(state="visible", timeout=10000)

            print("[*] [TokenRouter] Mengklik Google...")
            # Cek apakah memicu popup atau navigasi langsung
            try:
                async with context.expect_page(timeout=8000) as new_page_info:
                    await google_btn.evaluate("el => el.click()")
                target_page = await new_page_info.value
                await target_page.wait_for_load_state("domcontentloaded")
                await human_delay(1.5, 2.5)
                await fill_google_login(target_page, account)
                try:
                    await target_page.wait_for_event("close", timeout=30000)
                except Exception:
                    if not target_page.is_closed():
                        await target_page.close()
            except Exception:
                # Navigasi pada tab yang sama
                await fill_google_login(tr_page, account)

            # 6-7. Buka halaman console/token
            print("[*] [TokenRouter] Membuka halaman console token...")
            await tr_page.goto("https://www.tokenrouter.com/console/token", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # Klik Create new
            create_btn = tr_page.locator("button.tr-token-action-primary, button:has-text('Create Key'), button:has-text('Create new')").first
            await create_btn.wait_for(state="visible", timeout=15000)
            await human_click(create_btn, pre_delay=0.4, post_delay=1.0)

            # 8. Isikan nama api key
            name_input = tr_page.locator("input#name, input[placeholder*='name']").first
            await name_input.wait_for(state="visible", timeout=10000)
            key_name = account["email"].split("@")[0]
            print(f"[*] [TokenRouter] Mengisi nama key: {key_name}...")
            await human_type(name_input, key_name)

            # 9. Klik submit
            submit_btn = tr_page.locator(".side-sheet-footer-confirm, button:has-text('Submit')").first
            await submit_btn.wait_for(state="visible", timeout=10000)
            await human_click(submit_btn, pre_delay=0.4, post_delay=1.5)
            await human_delay(2.0, 3.0)

            self.mark_stage("extract_key")
            # 10. Copy API key dari tombol copy baris table pertama
            print("[*] [TokenRouter] Mengambil token API Key...")
            copy_btn = tr_page.locator("button[aria-label='copy token key'], button[title*='copy']").first
            if await copy_btn.is_visible():
                await human_click(copy_btn, pre_delay=0.3, post_delay=0.6)
                try:
                    clipboard_val = await tr_page.evaluate("navigator.clipboard.readText()")
                    if clipboard_val and clipboard_val.strip().startswith("sk-") and "*" not in clipboard_val:
                        api_key = clipboard_val.strip()
                except Exception:
                    pass

            if not api_key or "*" in api_key:
                key_input = tr_page.locator(".key-input input, input.semi-input-small").first
                if await key_input.is_visible():
                    raw_val = await key_input.get_attribute("value")
                    if raw_val and "sk-" in raw_val and "*" not in raw_val:
                        api_key = raw_val

            print(f"[+] [TokenRouter] Key diperoleh: {api_key[:12] if api_key else 'None'}... (Total {len(api_key) if api_key else 0} karakter)")
            return api_key

        except Exception as e:
            print(f"[-] [TokenRouter] Gagal mendapatkan key: {e}")
            self.mark_failed("extract_key", f"pengambilan API key gagal: {e}", retryable=True)
            return None

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        api_key = await self._obtain_key(context, main_page, account)
        if not api_key:
            if self.state is None:
                self.mark_failed("extract_key", "API key tidak ditemukan setelah login", retryable=True)
            return False

        self.mark_stage("save_key")
        if self.output_mode == "txt":
            self.save_key(account["email"], api_key)
            self.mark_success(f"{api_key[:10]}...{api_key[-4:]}")
            return True
        else:
            saved = await save_api_key_to_omni(main_page, "tokenrouter", account["email"], api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if saved:
                self.mark_success(f"{api_key[:10]}...{api_key[-4:]}")
            else:
                self.mark_failed("save_key", "AI-Omni menolak atau gagal menyimpan API key", retryable=True)
            return saved
