import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, navigate_to_provider
from .human_helper import human_click, human_delay

class KiroAlreadyConnected(Exception):
    """Modal AI-Omni menampilkan koneksi yang sudah terdaftar (bukan link device baru)."""


class KiroOmniFlow(BaseFlow):
    name = "Kiro AI (via AI-Omni)"
    description = "Registrasi dan hubungkan akun Google ke Provider Kiro AI di AI-Omni Portal."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._connect_cycles = 0
        self.base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
        self.omni_password = config.get("omni_password", "its.enpii-118")
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_kiro.txt"

    def set_current_account(self, email: str | None):
        super().set_current_account(email)
        self._connect_cycles = 0

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _get_device_link(self, page: Page, account: Dict[str, str]) -> Optional[str]:
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
        email_l = account["email"].lower()
        user_l = email_l.split("@")[0]
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            try:
                link = await page.evaluate(
                    "() => { const a = document.querySelector(\"a[href*='app.kiro.dev/account/device']\"); return a ? a.href : null; }"
                )
            except Exception:
                link = None
            if link:
                print(f"[+] Device Auth Link: {link}")
                return link
            # Koneksi mungkin sudah terdaftar dari percobaan sebelumnya — modal
            # menampilkan baris koneksi (email akun) alih-alih link device baru.
            try:
                low = (await page.content()).lower()
            except Exception:
                low = ""
            if "belum ada koneksi" not in low and "no connections yet" not in low:
                if email_l in low or user_l in low:
                    raise KiroAlreadyConnected()
            await asyncio.sleep(2)
        raise RuntimeError("device authorization link tidak ditemukan")

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

    async def _wait_connection_registered(self, page: Page, account_email: str, timeout_s: int = 40) -> bool:
        """Tunggu koneksi terlihat di halaman AI-Omni.

        Sinyal: email/username akun tampil pada daftar koneksi DAN empty state
        ('Belum ada koneksi'/'No connections yet') tidak ada. Absennya empty state
        saja tidak cukup — halaman non-dashboard juga tidak memuat teks itu.
        """
        email_l = account_email.lower()
        user_l = email_l.split("@")[0]
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                low = (await page.content()).lower()
                if "belum ada koneksi" not in low and "no connections yet" not in low:
                    if email_l in low or user_l in low:
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
        try:
            device_url = await self._get_device_link(main_page, account)
        except KiroAlreadyConnected:
            print(f"[+] Koneksi Kiro untuk {account['email']} sudah terdaftar di AI-Omni.")
            if self.output_mode == "txt":
                self.save_key(account["email"], "connected_via_device_oauth")
            self.mark_success("connected_via_device_oauth")
            await human_delay(1.0, 2.0)
            return True
        if not device_url:
            print(f"[-] Gagal mendapatkan device link untuk {account['email']}")
            self.mark_failed("navigate", "device authorization link tidak ditemukan", retryable=True)
            return False

        # Otorisasi device di TAB BARU — tab AI-Omni (modal device link) harus tetap hidup
        # supaya polling koneksi jalan. Navigasi main_page ke kiro.dev mematikan koneksi.
        # Camoufox menolak context.new_page() -> buka tab via window.open() dari halaman.
        device_page = None
        try:
            async with context.expect_page(timeout=10000) as popup_info:
                await main_page.evaluate("url => window.open(url, '_blank')", device_url)
            device_page = await popup_info.value
        except Exception as popup_err:
            print(f"[?] Popup device auth gagal dibuka ({popup_err}); fallback tab yang sama...")

        if device_page is not None:
            success = await self._handle_google_login(device_page, device_url, account)
            try:
                if not device_page.is_closed():
                    await device_page.close()
            except Exception:
                pass
        else:
            # Fallback: gunakan tab yang sama, lalu kembali ke dashboard AI-Omni
            success = await self._handle_google_login(main_page, device_url, account)
            try:
                await main_page.goto(
                    "https://ai-omni.enpiistudio.com/dashboard/providers/kiro",
                    wait_until="domcontentloaded",
                )
            except Exception:
                pass

        registered = False
        if success:
            self._connect_cycles += 1
            # Normalisasi halaman dulu: window.open() pada Camoufox me-redirect
            # main_page ke app.kiro.dev, sehingga polling tanpa navigasi membaca
            # halaman yang salah dan _wait_connection_registered selalu false-fail.
            if "ai-omni.enpiistudio.com" not in (main_page.url or ""):
                try:
                    await main_page.goto(
                        "https://ai-omni.enpiistudio.com/dashboard/providers/kiro",
                        wait_until="domcontentloaded",
                    )
                    await human_delay(1.5, 2.5)
                except Exception:
                    pass
            registered = await self._wait_connection_registered(main_page, account["email"], timeout_s=40)
            if not registered:
                # Fallback: reload halaman Kiro lalu cek sekali lagi
                try:
                    await main_page.reload(wait_until="domcontentloaded")
                    await human_delay(1.0, 2.0)
                    registered = await self._wait_connection_registered(main_page, account["email"], timeout_s=15)
                except Exception:
                    pass
            if not registered and self._connect_cycles >= 2:
                # 2x otorisasi device (Approve+Done) sukses namun UI AI-Omni tak
                # bisa dikonfirmasi — percayai hasil kiro.dev agar tidak crash-loop
                # di attempt berikutnya (link tak muncul lagi karena sudah terhubung).
                print("[?] [AI-Omni] Verifikasi UI gagal 2x — terima otorisasi kiro.dev sebagai sukses.")
                registered = True

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
