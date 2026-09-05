import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_click, human_delay

class OpencodeZenFlow(BaseFlow):
    name = "Opencode Zen"
    description = "Login ke Opencode Zen via Google, copy API Key, dan daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_opencode_zen.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_key(self, context: BrowserContext, zen_page: Page, account: Dict[str, str]) -> Optional[str]:
        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        api_key = None

        try:
            print("[*] [Opencode Zen] Membuka https://opencode.ai/zen...")
            await zen_page.goto("https://opencode.ai/zen", wait_until="domcontentloaded")
            await human_delay(1.0, 1.8)

            # 2. Klik Get started with Zen / Login (ambil .first)
            start_btn = zen_page.locator("a:has-text('Get started with Zen'), a[href='/auth']").first
            if await start_btn.is_visible():
                print("[*] [Opencode Zen] Mengklik 'Get started with Zen'...")
                await human_click(start_btn, pre_delay=0.4, post_delay=1.0)
                await zen_page.wait_for_load_state("domcontentloaded")
                await human_delay(0.8, 1.5)

            # 3. Klik Continue with Google
            google_btn = zen_page.locator("a[href*='/google/authorize'], button:has-text('Continue with Google')").first
            if await google_btn.is_visible():
                print("[*] [Opencode Zen] Mengklik 'Continue with Google'...")
                await human_click(google_btn, pre_delay=0.4, post_delay=1.0)
                await zen_page.wait_for_load_state("domcontentloaded")

            # 4-7. Google login
            await fill_google_login(zen_page, account)

            # 8. Copy key di workspace
            print("[*] [Opencode Zen] Menunggu halaman workspace / tombol Copy Key muncul...")
            copy_btn = zen_page.locator(
                "button[title*='Copy API key'], button:has-text('Copy Key'), button[aria-label*='copy'], [data-slot='key-display'] button"
            ).first
            await copy_btn.wait_for(state="visible", timeout=35000)
            await human_delay(1.0, 1.5)

            # Klik tombol Copy Key
            print("[*] [Opencode Zen] Mengklik tombol Copy Key...")
            await human_click(copy_btn, pre_delay=0.4, post_delay=0.8)

            # Ambil full key dari clipboard
            try:
                clipboard_val = await zen_page.evaluate("navigator.clipboard.readText()")
                if clipboard_val and clipboard_val.strip().startswith("sk-") and "*" not in clipboard_val:
                    api_key = clipboard_val.strip()
                    print(f"[+] [Opencode Zen] Full API Key berhasil disalin dari clipboard (panjang: {len(api_key)})")
            except Exception as ce:
                print(f"[?] [Opencode Zen] Clipboard evaluate: {ce}")

            # Fallback jika clipboard belum terbaca
            if not api_key:
                key_element = zen_page.locator("code[data-slot='key-value'], [data-slot='key-display']").first
                raw_text = await key_element.inner_text()
                attr_val = await key_element.get_attribute("data-key") or await key_element.get_attribute("value")
                if attr_val and "*" not in attr_val:
                    api_key = attr_val.strip()
                else:
                    api_key = raw_text.strip()

            print(f"[+] [Opencode Zen] Key diperoleh: {api_key[:12]}... (Total {len(api_key)} karakter)")
            return api_key

        except Exception as e:
            print(f"[-] [Opencode Zen] Gagal mendapatkan key: {e}")
            return None

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        api_key = await self._obtain_key(context, main_page, account)
        if not api_key:
            return False

        if self.output_mode == "txt":
            self.save_key(account["email"], api_key)
            return True
        else:
            saved = await save_api_key_to_omni(main_page, "opencode-zen", account["email"], api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return saved
