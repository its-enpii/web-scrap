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
        try:
            await device_link_loc.wait_for(state="visible", timeout=20000)
        except Exception:
            # Fallback: cari href via querySelectorAll (kadang elemen off-viewport/partial render)
            link = await page.evaluate(
                "() => { const a = document.querySelector(\"a[href*='app.kiro.dev/account/device']\"); return a ? a.href : null; }"
            )
            if not link:
                raise RuntimeError("device authorization link tidak ditemukan")
            return link
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

    async def _wait_connection_registered(self, page: Page, timeout_s: int = 40) -> bool:
        """Tunggu AI-Omni mendaftarkan koneksi (empty state 'No connections yet'/'0 connections' hilang)."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                low = (await page.content()).lower()
                if "no connections yet" not in low and "0 connection" not in low:
                    print("[+] [AI-Omni] Koneksi Kiro terdaftar di dashboard!")
                    return True
            except Exception:
                pass
            # Klik tombol cek/selesai di modal AI-Omni bila ada
            for sel in (
                "button:has-text('Check status')", "button:has-text('Cek status')",
                "button:has-text('Selesai')", "button:has-text('Done')",
            ):
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        await human_click(btn)
                        break
                except Exception:
                    pass
            await asyncio.sleep(3)
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

        # Otorisasi device di TAB BARU — tab AI-Omni (modal device link) harus tetap hidup
        # supaya polling koneksi jalan. Navigasi main_page ke kiro.dev mematikan koneksi.
        device_page = await context.new_page()
        success = await self._handle_google_login(device_page, device_url, account)
        try:
            if not device_page.is_closed():
                await device_page.close()
        except Exception:
            pass

        registered = False
        if success:
            registered = await self._wait_connection_registered(main_page, timeout_s=40)
            if not registered:
                # Fallback: reload halaman Kiro lalu cek sekali lagi
                try:
                    await main_page.reload(wait_until="domcontentloaded")
                    await human_delay(1.0, 2.0)
                    registered = await self._wait_connection_registered(main_page, timeout_s=15)
                except Exception:
                    pass

        if success and registered:
            if self.output_mode == "txt":
                self.save_key(account["email"], "connected_via_device_oauth")
            self.mark_success("connected_via_device_oauth")
        else:
            self.mark_failed(
                "register",
                "otorisasi kiro selesai tapi koneksi belum terdaftar di ai-omni",
                retryable=True,
            )
            success = False

        await human_delay(1.5, 2.5)
        return success
