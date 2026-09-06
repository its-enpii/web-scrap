import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, navigate_to_provider
from .human_helper import human_click, human_delay

class KiroOmniFlow(BaseFlow):
    name = "Kiro AI (via AI-Omni)"
    description = "Registrasi dan hubungkan akun Google ke Provider Kiro AI di AI-Omni Portal."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
        self.omni_password = config.get("omni_password", "its.enpii-118")
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_kiro.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _get_device_link(self, page: Page) -> Optional[str]:
        self.mark_stage("navigate")
        print("[*] Mengklik 'Tambahkan'...")
        add_btn = page.locator("button:has-text('Tambahkan'), button:has-text('Add')").first
        await human_click(add_btn, pre_delay=0.4, post_delay=0.8)

        print("[*] Mengklik 'Saya mengerti, lanjutkan'...")
        understand_btn = page.locator("button:has-text('Saya mengerti, lanjutkan'), button:has-text('understand')").first
        await human_click(understand_btn, pre_delay=0.4, post_delay=0.8)

        print("[*] Memilih opsi 'Akun Google'...")
        google_opt_btn = page.locator("button:has-text('Akun Google'), button:has-text('Google')").first
        await human_click(google_opt_btn, pre_delay=0.4, post_delay=0.8)

        print("[*] Menunggu link otorisasi device muncul...")
        device_link_loc = page.locator("a[href*='app.kiro.dev/account/device']").first
        await device_link_loc.wait_for(state="visible", timeout=15000)
        link = await device_link_loc.get_attribute("href")
        print(f"[+] Device Auth Link: {link}")
        return link

    async def _handle_google_login(self, page: Page, device_url: str, account: Dict[str, str]) -> bool:
        try:
            self.mark_stage("login")
            print(f"[*] Menavigasi ke URL otorisasi Kiro Dev ({account['email']})...")
            await page.goto(device_url, wait_until="domcontentloaded")
            await human_delay(1.0, 2.0)

            # Mengisi form login Google
            await fill_google_login(page, account)

            # Klik Approve di Kiro Dev
            print("[*] Menunggu tombol 'Approve' di Kiro Dev...")
            approve_btn = page.locator(
                "button:has-text('Approve'), button:has-text('Allow'), button:has-text('Confirm'), button:has-text('Authorize'), button:has-text('Setuju')"
            ).first
            await approve_btn.wait_for(state="visible", timeout=30000)
            await human_click(approve_btn, pre_delay=0.8, post_delay=1.5)
            print("[+] Tombol Approve diklik.")

            # Klik Done / Finish
            print("[*] Menunggu tombol 'Done'...")
            done_btn = page.locator(
                "button:has-text('Done'), button:has-text('Finish'), button:has-text('Selesai'), button:has-text('Close')"
            ).first
            await done_btn.wait_for(state="visible", timeout=15000)
            await human_click(done_btn, pre_delay=0.8, post_delay=1.2)
            print(f"[+] Berhasil menghubungkan akun {account['email']}!")

            await human_delay(1.5, 2.5)
            return True

        except Exception as err:
            print(f"[-] Gagal pada akun {account['email']}: {err}")
            self.mark_failed("login", f"Google/Kiro authorization gagal: {err}", retryable=True)
            try:
                done_btn = page.locator("button:has-text('Done')").first
                if await done_btn.is_visible(timeout=5000):
                    await human_click(done_btn)
                    return True
            except Exception:
                pass
            return False

    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        if not main_page:
            main_page = await context.new_page()

        await navigate_to_provider(main_page, "kiro")
        device_url = await self._get_device_link(main_page)
        if not device_url:
            print(f"[-] Gagal mendapatkan device link untuk {account['email']}")
            self.mark_failed("navigate", "device authorization link tidak ditemukan", retryable=True)
            return False

        # Langsung gunakan main_page yang sama (1 Single Window)
        success = await self._handle_google_login(main_page, device_url, account)
        if success:
            if self.output_mode == "txt":
                self.save_key(account["email"], "connected_via_device_oauth")
            self.mark_success("connected_via_device_oauth")

        await human_delay(1.5, 2.5)
        return success
