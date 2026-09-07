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
        email = account["email"]
        self.set_current_account(email)
        tr_page = main_page or await context.new_page()

        try:
            # 1. Buka TokenRouter
            self.mark_stage("navigate")
            print(f"\n[{index+1}/{total}] [*] [TokenRouter] Membuka https://www.tokenrouter.com/ ({email})...")
            await tr_page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded", timeout=45000)
            await human_delay(1.5, 2.5)

            # 2. Buka Modal Sign In jika belum login
            # FIX: sebelumnya, bila modal gagal terbuka setelah klik Sign In,
            # flow diam-diam skip OAuth lalu membuka /console/token dalam
            # keadaan BELUM login -> gagal ekstraksi key 100% pada attempt
            # tersebut (8x beruntun di log batch). Sekarang: tunggu modal
            # muncul, klik ulang Sign In bila perlu, dan gagalkan attempt
            # (retryable -> failover proxy) bila modal tetap tidak terbuka.
            self.mark_stage("open_signin_modal")
            google_btn = tr_page.locator("button.tr-auth-social-button:has(img[class*='goo'])").first
            modal_open = False
            for modal_attempt in range(1, 4):
                try:
                    await google_btn.wait_for(state="visible", timeout=8000)
                    modal_open = True
                    break
                except Exception:
                    # Modal belum terbuka — coba klik ulang tombol Sign In.
                    # Prioritaskan selector header (spesifik) di atas selector
                    # generik, karena :has-text bisa match CTA lain di landing.
                    signin_btn = tr_page.locator("button.tr-landing-header-action:has-text('Sign In')").first
                    if not await signin_btn.count() or not await signin_btn.is_visible():
                        signin_btn = tr_page.locator("button:has-text('Sign In')").first
                    if await signin_btn.count() > 0 and await signin_btn.is_visible():
                        print(f"[*] [TokenRouter] Modal belum terbuka — klik ulang Sign In (percobaan {modal_attempt})...")
                        await human_click(signin_btn)
                        print("[*] [TokenRouter] Tombol Sign In diklik.")
                        await human_delay(1.0, 2.0)
                    else:
                        # Tidak ada tombol Sign In: kemungkinan sudah login (session persist)
                        print("[*] [TokenRouter] Tombol Sign In tidak ditemukan — kemungkinan sudah login.")
                        modal_open = True
                        break
            if not modal_open:
                raise Exception("signin_modal_timeout: modal Sign In tidak terbuka setelah klik Sign In")

            # 3. Centang agreement checkbox & klik tombol Google
            self.mark_stage("click_google_oauth")

            # Centang agreement box jika ada
            agree_checkbox = tr_page.locator("button[style*='border: 1px solid rgb(0, 134, 255)'], button.w-\\[14px\\], button.h-\\[14px\\]").first
            if await agree_checkbox.count() > 0 and await agree_checkbox.is_visible():
                await human_click(agree_checkbox)
                print("[*] [TokenRouter] Agreement checkbox dicentang.")
                await human_delay(0.5, 1.0)

            # Klik Google OAuth (popup window)
            # FIX: bila popup Google gagal dibuka/dideteksi, jangan lanjut
            # diam-diam (sebelumnya flow lanjut ke /console/token belum login).
            auth_page = None
            try:
                async with context.expect_page(timeout=15000) as popup_info:
                    await human_click(google_btn)
                auth_page = await popup_info.value
            except Exception:
                # Cari di context.pages
                for p in context.pages:
                    if p != tr_page and "accounts.google.com" in p.url:
                        auth_page = p
                        break

            if not auth_page:
                raise Exception("google_popup_timeout: popup Google OAuth tidak terbuka")

            await auth_page.wait_for_load_state("domcontentloaded")
            await human_delay(1.0, 2.0)
            self.mark_stage("google_auth")
            await fill_google_login(auth_page, account)
            try:
                await auth_page.wait_for_event("close", timeout=20000)
            except Exception:
                if not auth_page.is_closed():
                    await auth_page.close()
            await tr_page.wait_for_timeout(3000)

            # 4. Navigasi ke Halaman API Keys
            self.mark_stage("open_tokens_page")
            print("[*] [TokenRouter] Membuka halaman https://www.tokenrouter.com/console/token...")
            await tr_page.goto("https://www.tokenrouter.com/console/token", wait_until="domcontentloaded", timeout=45000)
            await tr_page.wait_for_timeout(4000)

            # 5. Buat key jika belum ada row
            self.mark_stage("ensure_token_exists")
            copy_btn = tr_page.locator("button[aria-label='copy token key']").first
            if await copy_btn.count() == 0 or not await copy_btn.is_visible():
                print("[*] [TokenRouter] Belum ada key, membuat API key baru...")
                create_btn = tr_page.locator("button:has-text('Create Key')").first
                if await create_btn.is_visible():
                    await human_click(create_btn)
                    await tr_page.wait_for_timeout(2000)

                    # Isi Nama Key
                    name_input = tr_page.locator("input[placeholder='Please enter a name']").first
                    if await name_input.is_visible():
                        await human_type(name_input, "auto-key-tokenrouter")
                        await human_delay(0.5, 1.0)

                    # Klik Submit di Side Sheet
                    submit_btn = tr_page.locator(".side-sheet-footer-confirm, div:has-text('Submit'):not(:has(*))").last
                    if await submit_btn.is_visible():
                        await human_click(submit_btn)
                        print("[*] [TokenRouter] Submit create key diklik.")
                        await tr_page.wait_for_timeout(4000)

            # 6. Salin Key dari Clipboard / Reveal
            self.mark_stage("copy_api_key")
            api_key = None
            copy_btn = tr_page.locator("button[aria-label='copy token key']").first
            if await copy_btn.is_visible():
                await human_click(copy_btn)
                await human_delay(1.0, 1.5)
                try:
                    cb = await tr_page.evaluate("navigator.clipboard.readText()")
                    if cb and re.match(r"^sk-[A-Za-z0-9_-]{20,}$", cb.strip()):
                        api_key = cb.strip()
                except Exception:
                    pass

            if not api_key:
                reveal_btn = tr_page.locator("button[aria-label='toggle token visibility']").first
                if await reveal_btn.is_visible():
                    await human_click(reveal_btn)
                    await human_delay(1.0, 1.5)
                    row_text = await tr_page.locator("tbody tr").first.inner_text()
                    m = re.search(r"(sk-[A-Za-z0-9_-]{20,})", row_text)
                    if m:
                        api_key = m.group(1).strip()

            if not api_key:
                # Coba cari dari page content
                content = await tr_page.content()
                keys = re.findall(r'(sk-[A-Za-z0-9_-]{20,})', content)
                if keys:
                    api_key = keys[0].strip()

            if not api_key or not re.match(r"^sk-[A-Za-z0-9_-]{20,}$", api_key.strip()):
                raise Exception("Gagal mengekstrak valid API Key dari TokenRouter")

            print(f"[+] [TokenRouter] Berhasil mendapatkan API Key (Panjang: {len(api_key)})")
            self.save_key(email, api_key.strip())
            self.mark_success(key_hint=api_key.strip()[:10] + "...")
            return True

        except Exception as e:
            err_msg = str(e)
            print(f"[-] [TokenRouter] Error: {err_msg}")
            self.mark_failed("error", err_msg, retryable=True)
            return False
