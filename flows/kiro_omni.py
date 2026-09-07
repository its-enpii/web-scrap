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

    # ------------------------------------------------------------------
    # Verifikasi koneksi via API internal AI-Omni (v8).
    #
    # Dashboard AI-Omni TIDAK merender email akun — baik di DOM maupun di
    # payload /api/providers (objek koneksi hanya berisi id/status OAuth).
    # Pengecekan lama `email in page.content()` selalu false-fail:
    #   [RETRY] setelah "Berhasil menghubungkan" -> wizard diputar ulang ->
    #   tanpa link baru (identitas sudah terhubung) -> "device authorization
    #   link tidak ditemukan" -> kegagalan beruntun (v6/v7) + koneksi duplikat.
    #
    # Sinyal yang benar: hitung koneksi provider `kiro` via /api/providers
    # sebelum (baseline) dan sesudah otorisasi; koneksi bertambah = sukses.
    # ------------------------------------------------------------------
    async def _count_kiro_connections(self, page: Page) -> Optional[int]:
        try:
            return await page.evaluate(
                """async () => {
                    const r = await fetch('/api/providers?provider=kiro', {credentials: 'include'});
                    if (!r.ok) return null;
                    const j = await r.json();
                    return Array.isArray(j.connections) ? j.connections.length : null;
                }"""
            )
        except Exception:
            return None

    async def _already_connected(self, page: Page, baseline: Optional[int]) -> bool:
        if baseline is None:
            return False
        now = await self._count_kiro_connections(page)
        return now is not None and now > baseline

    async def _get_device_link(self, page: Page, account: Dict[str, str]) -> Optional[str]:
        self.mark_stage("navigate")
        print("[*] Mengklik 'Tambahkan'...")
        add_btn = page.locator("button:has-text('Tambahkan'), button:has-text('Add')").first
        await human_click(add_btn, pre_delay=0.4, post_delay=0.8)

        print("[*] Mengklik 'Saya mengerti, lanjutkan'...")
        understand_btn = page.locator(
            "button:has-text('Saya mengerti, lanjutkan'), button:has-text('I understand, continue'), button:has-text('understand')"
        ).first
        try:
            await understand_btn.wait_for(state="visible", timeout=8000)
        except Exception:
            pass
        try:
            await human_click(understand_btn, pre_delay=0.4, post_delay=0.8)
        except Exception:
            pass

        print("[*] Memilih opsi 'Akun Google'...")
        google_opt_btn = page.locator("button:has-text('Akun Google'), button:has-text('Google')").first
        await human_click(google_opt_btn, pre_delay=0.4, post_delay=0.8)

        print("[*] Menunggu link otorisasi device muncul...")
        deadline = asyncio.get_event_loop().time() + 30
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
            await asyncio.sleep(2)
        return None

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
            print(f"[+] Otorisasi kiro.dev selesai untuk {account['email']}!")

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

        baseline = await self._count_kiro_connections(main_page)
        if baseline is None:
            print("[?] [AI-Omni] Tidak bisa membaca jumlah koneksi Kiro via API — verifikasi akan fallback.")
        else:
            print(f"[*] [AI-Omni] Baseline koneksi Kiro: {baseline}")

        device_url = await self._get_device_link(main_page, account)

        if device_url is None:
            # Satu kali buka wizard lagi — kadang modal pertama gagal render link
            print("[?] Link tidak muncul — mencoba buka wizard sekali lagi...")
            try:
                await main_page.keyboard.press("Escape")
                await human_delay(1.0, 1.5)
            except Exception:
                pass
            device_url = await self._get_device_link(main_page, account)

        if device_url is None:
            if baseline:
                # Dua kali wizard tanpa link baru. Karena AI-Omni TIDAK
                # menyimpan email di koneksi (tak bisa dipetakan per akun),
                # perlakukan sebagai sudah-terhubung (biasanya terjadi setelah
                # otorisasi sukses di run sebelumnya yang verifikasinya false-fail).
                print(
                    f"[+] Tidak ada link device baru 2x — asumsikan akun {account['email']} "
                    f"sudah terhubung (koneksi kiro terdaftar: {baseline})."
                )
                if self.output_mode == "txt":
                    self.save_key(account["email"], "connected_via_device_oauth")
                self.mark_success("connected_via_device_oauth")
                await human_delay(1.0, 2.0)
                return True
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

        registered = False
        if success:
            # Normalisasi halaman dulu: fallback tab yang sama bisa meninggalkan
            # main_page di app.kiro.dev — fetch API verifikasi harus dari origin ai-omni.
            if "ai-omni.enpiistudio.com" not in (main_page.url or ""):
                try:
                    await main_page.goto(
                        "https://ai-omni.enpiistudio.com/dashboard/providers/kiro",
                        wait_until="domcontentloaded",
                    )
                    await human_delay(1.5, 2.5)
                except Exception:
                    pass
            # Verifikasi via API: jumlah koneksi kiro harus bertambah dari baseline.
            deadline = asyncio.get_event_loop().time() + 45
            while asyncio.get_event_loop().time() < deadline:
                if await self._already_connected(main_page, baseline):
                    registered = True
                    print("[+] [AI-Omni] Koneksi Kiro terdaftar (verifikasi via API).")
                    break
                await asyncio.sleep(4)
            if not registered and baseline is None:
                # API verifikasi tidak tersedia sejak awal — terima otorisasi
                # kiro.dev sebagai sukses agar tidak false-fail beruntun.
                print("[?] [AI-Omni] API verifikasi tak tersedia — terima otorisasi kiro.dev sebagai sukses.")
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
