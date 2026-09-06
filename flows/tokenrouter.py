import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import Page, BrowserContext
from .base import BaseFlow
from .human_helper import human_type, human_click, human_delay
from .google_auth_helper import fill_google_login


class TokenRouterFlow(BaseFlow):
    name = "tokenrouter"

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int
    ) -> bool:
        """
        Flow otomatis untuk TokenRouter:
        1. Landing page -> Buka Modal Sign In
        2. Centang agreement checkbox (border biru 14x14)
        3. Klik Google OAuth -> Login Google GSuite (ToS + Consent auto-handled)
        4. Masuk ke /console/token
        5. Buat API Key baru jika belum ada (Side Sheet form)
        6. Klik copy token key -> Ambil API Key dari clipboard
        """
        tr_page = main_page or await context.new_page()

        try:
            # 1. Buka TokenRouter
            self.mark_stage("navigate")
            print("[*] [TokenRouter] Membuka https://www.tokenrouter.com/...")
            await tr_page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # 2. Buka Modal Sign In
            self.mark_stage("open_signin_modal")
            signin_btn = tr_page.locator("button.tr-landing-header-action:has-text('Sign In'), button:has-text('Sign In')").first
            if await signin_btn.is_visible():
                await human_click(signin_btn)
                print("[*] [TokenRouter] Tombol Sign In diklik.")
            await human_delay(1.0, 2.0)

            # 3. Centang agreement checkbox & klik tombol Google
            self.mark_stage("click_google_oauth")
            social_btn = tr_page.locator("button.tr-auth-social-button").first
            await social_btn.wait_for(state="visible", timeout=15000)

            # Centang agreement box
            agree_checkbox = tr_page.locator("button[style*='border: 1px solid rgb(0, 134, 255)'], button.w-\\[14px\\], button.h-\\[14px\\]").first
            if await agree_checkbox.count() > 0 and await agree_checkbox.is_visible():
                await human_click(agree_checkbox)
                print("[*] [TokenRouter] Agreement checkbox dicentang.")
                await human_delay(0.5, 1.0)

            # Klik Google OAuth (popup window)
            google_btn = tr_page.locator("button.tr-auth-social-button:has(img[class*='goo'])").first
            async with context.expect_page(timeout=20000) as popup_info:
                await human_click(google_btn)
                print("[*] [TokenRouter] Tombol Google OAuth diklik.")

            auth_page = await popup_info.value
            await auth_page.wait_for_load_state("domcontentloaded")
            await human_delay(1.0, 2.0)

            # 4. Handle Login Google
            self.mark_stage("google_auth")
            login_success = await fill_google_login(auth_page, account)
            if not login_success:
                raise Exception("Gagal login Google OAuth untuk TokenRouter")

            # Tunggu redirect ke dashboard / console
            self.mark_stage("wait_for_console")
            for _ in range(30):
                if "/console" in tr_page.url:
                    break
                await tr_page.wait_for_timeout(1000)

            if not auth_page.is_closed():
                try:
                    await auth_page.wait_for_event("close", timeout=15000)
                except Exception:
                    await auth_page.close()
                await tr_page.wait_for_timeout(3000)

            # 5. Navigasi ke Halaman API Keys
            self.mark_stage("open_tokens_page")
            print("[*] [TokenRouter] Membuka halaman https://www.tokenrouter.com/console/token...")
            await tr_page.goto("https://www.tokenrouter.com/console/token", wait_until="domcontentloaded")
            await tr_page.wait_for_timeout(5000)

            # 6. Buat key jika belum ada row
            self.mark_stage("ensure_token_exists")
            copy_btn = tr_page.locator("button[aria-label='copy token key']").first
            if await copy_btn.count() == 0 or not await copy_btn.is_visible():
                print("[*] [TokenRouter] Belum ada key, membuat API key baru...")
                create_btn = tr_page.locator("button:has-text('Create Key')").first
                await create_btn.wait_for(state="visible", timeout=15000)
                await human_click(create_btn)
                await tr_page.wait_for_timeout(2000)

                # Isi Nama Key
                name_input = tr_page.locator("input[placeholder='Please enter a name']").first
                if await name_input.is_visible():
                    await human_type(name_input, "auto-key-tokenrouter")
                    await human_delay(0.5, 1.0)

                # Klik Submit di Side Sheet
                submit_btn = tr_page.locator(".side-sheet-footer-confirm, div:has-text('Submit'):not(:has(*))").last
                await human_click(submit_btn)
                print("[*] [TokenRouter] Submit create key diklik.")
                await tr_page.wait_for_timeout(4000)

            # 7. Salin Key dari Clipboard
            self.mark_stage("copy_api_key")
            copy_btn = tr_page.locator("button[aria-label='copy token key']").first
            await copy_btn.wait_for(state="visible", timeout=15000)
            await human_click(copy_btn)
            await human_delay(1.0, 1.5)

            api_key = await tr_page.evaluate("navigator.clipboard.readText()")
            if not api_key or not re.match(r"^sk-[A-Za-z0-9_-]{20,}$", api_key.strip()):
                # Fallback: reveal dan baca dari cell tabel
                reveal_btn = tr_page.locator("button[aria-label='toggle token visibility']").first
                if await reveal_btn.is_visible():
                    await human_click(reveal_btn)
                    await human_delay(1.0, 1.5)
                    row_text = await tr_page.locator("tbody tr").first.inner_text()
                    m = re.search(r"(sk-[A-Za-z0-9_-]{20,})", row_text)
                    if m:
                        api_key = m.group(1).strip()

            if not api_key or not re.match(r"^sk-[A-Za-z0-9_-]{20,}$", api_key.strip()):
                raise Exception("Gagal mengekstrak valid API Key dari TokenRouter")

            print(f"[+] [TokenRouter] Berhasil mendapatkan API Key (Panjang: {len(api_key)})")
            self.save_key(account["email"], api_key.strip(), "results/keys_tokenrouter.txt")
            self.mark_success(key_hint=api_key.strip()[:10] + "...")
            return True

        except Exception as e:
            err_msg = str(e)
            print(f"[-] [TokenRouter] Error: {err_msg}")
            self.mark_failed(stage=self.state.get_account_state(account['email']).get('stage', 'unknown') if self.state else 'unknown', error=err_msg, retryable=True)
            return False
