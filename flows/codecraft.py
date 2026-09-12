import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .human_helper import human_click, human_type, human_delay


class CodeCraftFlow(BaseFlow):
    """
    Alur registrasi & pengambilan API Key CodeCraft (codecraftapi.com).
    1. Register pakai Google OAuth (Gsuite).
    2. Ke halaman plan terus pilih yang basic.
    3. Pilih billing cycle yearly.
    4. Masukin kode promo "DEVWEEK" terus klik activate.
    5. Ke halaman API keys terus create API keys.
    6. Simpan keys dan close browser.
    """

    name = "CodeCraft (codecraftapi.com)"
    flow_name = "codecraft"
    description = "Register via Google OAuth, aktivasi plan Basic yearly (kode DEVWEEK), generate & simpan API Key."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "results/keys_codecraft.txt"

    async def _obtain_codecraft_api_key(
        self, context: BrowserContext, account: Dict[str, Any]
    ) -> Optional[str]:
        email = account.get("email", "")
        print(f"\n[*] [CodeCraft] Memproses akun: {email}")

        page: Page = context.pages[0] if context.pages else await context.new_page()

        # -----------------------------------------------------------
        # 1. Register / Login via Google OAuth
        # -----------------------------------------------------------
        self.mark_stage("navigate")
        print("[*] [CodeCraft] 1. Membuka https://codecraftapi.com/register ...")
        await page.goto("https://codecraftapi.com/register", wait_until="domcontentloaded", timeout=60000)
        await human_delay(1.5, 2.5)

        # Cek apakah sesi sudah login ke dashboard
        if "/dashboard" not in page.url:
            self.mark_stage("google_oauth")
            print("[*] [CodeCraft] Mengarahkan ke Google OAuth...")
            try:
                await page.goto("https://codecraftapi.com/auth/google/redirect", wait_until="domcontentloaded", timeout=60000)
            except Exception as ge:
                # Jika redirect cepat ke accounts.google.com memicu navigation error, abaikan jika sudah di Google
                if "accounts.google.com" not in page.url:
                    raise ge

            # Cari tab Google Sign-In (popup atau tab yang sama)
            google_page: Optional[Page] = None
            for _ in range(40):
                await page.wait_for_timeout(500)
                if "accounts.google.com" in page.url:
                    google_page = page
                    break
                for pg in context.pages:
                    if pg is not page and "accounts.google.com" in pg.url:
                        google_page = pg
                        break
                if google_page:
                    break

            if not google_page:
                raise RuntimeError("Halaman Google Sign In tidak terbuka setelah klik OAuth")

            print("[*] [CodeCraft] Mengisi form login Google...")
            await fill_google_login(google_page, account)

            # Jika Google di popup terpisah, tunggu tertutup
            if google_page is not page:
                try:
                    await google_page.wait_for_event("close", timeout=30000)
                except Exception:
                    if not google_page.is_closed():
                        await google_page.close()

            # Tunggu redirect kembali ke dashboard codecraftapi.com
            print("[*] [CodeCraft] Menunggu redirect kembali ke CodeCraft Dashboard...")
            for _ in range(60):
                await page.wait_for_timeout(1000)
                if "codecraftapi.com" in page.url and "auth/google" not in page.url:
                    break

            await human_delay(2.0, 3.5)

        if "/dashboard" not in page.url:
            raise RuntimeError(f"Gagal landing di dashboard CodeCraft, URL saat ini: {page.url}")

        print(f"[+] [CodeCraft] Berhasil login. URL: {page.url}")

        # -----------------------------------------------------------
        # 2. Ke halaman plan terus pilih yang basic
        # -----------------------------------------------------------
        self.mark_stage("plan_selection")
        print("[*] [CodeCraft] 2. Menuju halaman Plan (https://codecraftapi.com/dashboard/billing/plan)...")
        await page.goto("https://codecraftapi.com/dashboard/billing/plan", wait_until="domcontentloaded", timeout=45000)
        await human_delay(2.0, 3.0)

        plan_html = await page.content()
        is_already_basic_yearly = (
            "Current Plan" in plan_html
            and "Basic" in plan_html
            and "Yearly billing" in plan_html
        )

        if is_already_basic_yearly:
            print("[i] [CodeCraft] Akun sudah memiliki Plan Basic (Yearly billing). Melewati aktivasi kupon.")
        else:
            print("[*] [CodeCraft] Membuka halaman checkout Basic...")
            basic_upgrade_link = page.locator(".card:has-text('Basic') a[href*='checkout'], .card:has-text('Basic') button").first
            if await basic_upgrade_link.count() > 0 and await basic_upgrade_link.is_visible():
                await human_click(basic_upgrade_link)
            else:
                await page.goto("https://codecraftapi.com/dashboard/billing/checkout/1", wait_until="domcontentloaded", timeout=45000)

            await human_delay(2.0, 3.0)

            # -------------------------------------------------------
            # 3. Pilih billing cycle yearly
            # -------------------------------------------------------
            self.mark_stage("select_yearly")
            print("[*] [CodeCraft] 3. Memilih billing cycle Yearly...")
            yearly_selector = page.locator("label:has(input[value='yearly']), label:has-text('Yearly')").first
            if await yearly_selector.count() > 0:
                await human_click(yearly_selector, pre_delay=0.3, post_delay=0.5)
            else:
                await page.evaluate("""() => {
                    const r = document.querySelector("input[value='yearly']");
                    if (r) {
                        r.checked = true;
                        r.dispatchEvent(new Event('change', { bubbles: true }));
                        r.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }""")
            await human_delay(1.5, 2.5)

            # -------------------------------------------------------
            # 4. Masukin kode promo "DEVWEEK" terus klik aktivate
            # -------------------------------------------------------
            self.mark_stage("apply_promo")
            print("[*] [CodeCraft] 4. Memasukkan kode promo DEVWEEK...")
            coupon_input = page.locator("input[x-model='coupon'], input[placeholder*='COUPON']").first
            await coupon_input.wait_for(state="visible", timeout=15000)
            await human_type(coupon_input, "DEVWEEK")
            await human_delay(0.8, 1.2)

            print("[*] [CodeCraft] Mengklik tombol Apply...")
            apply_btn = page.locator("button:has-text('Apply')").first
            await human_click(apply_btn, pre_delay=0.3, post_delay=0.8)

            # Tunggu validasi kupon
            for _ in range(15):
                await page.wait_for_timeout(500)
                applied = await page.locator("span:has-text('Applied'), p:has-text('valid')").count()
                if applied > 0:
                    break

            await human_delay(1.5, 2.0)

            print("[*] [CodeCraft] Mengklik tombol aktivasi / submit plan...")
            submit_btn = page.locator("form[action*='checkout/1'] button[type='submit']").first
            await human_click(submit_btn, pre_delay=0.4, post_delay=1.0)

            # Tunggu redirect setelah aktivasi
            for _ in range(25):
                await page.wait_for_timeout(1000)
                if "checkout/1" not in page.url:
                    break

            print(f"[+] [CodeCraft] Aktivasi selesai, URL: {page.url}")
            await human_delay(2.0, 3.5)

        # -----------------------------------------------------------
        # 5. Ke halaman API keys terus create API keys
        # -----------------------------------------------------------
        self.mark_stage("create_api_key")
        print("[*] [CodeCraft] 5. Menuju halaman API Keys (https://codecraftapi.com/dashboard/api-keys)...")
        await page.goto("https://codecraftapi.com/dashboard/api-keys", wait_until="domcontentloaded", timeout=45000)
        await human_delay(2.0, 3.0)

        print("[*] [CodeCraft] Mengklik tombol 'Create API Key'...")
        create_btn = page.locator("button:has-text('Create API Key')").first
        await create_btn.wait_for(state="visible", timeout=20000)
        await human_click(create_btn, pre_delay=0.4, post_delay=0.8)
        await human_delay(1.0, 1.5)

        key_name = f"key-{email.split('@')[0]}"
        print(f"[*] [CodeCraft] Mengisi nama key: {key_name}...")
        name_input = page.locator("input#name, input[name='name']").first
        await name_input.wait_for(state="visible", timeout=10000)
        await human_type(name_input, key_name)
        await human_delay(0.8, 1.2)

        print("[*] [CodeCraft] Mengklik submit 'Create Key'...")
        submit_create_btn = page.locator("button[type='submit']:has-text('Create Key')").first
        await human_click(submit_create_btn, pre_delay=0.3, post_delay=1.0)
        await human_delay(3.0, 4.5)

        # -----------------------------------------------------------
        # 6. Simpan keys dan close browser
        # -----------------------------------------------------------
        self.mark_stage("extract_key")
        print("[*] [CodeCraft] 6. Mengekstrak API Key...")

        api_key = None
        # Cek kode dari banner kunci baru
        try:
            code_elem = page.locator("code.font-mono.select-all").first
            if await code_elem.count() > 0:
                txt = (await code_elem.text_content() or "").strip()
                if txt.startswith("cc_") and len(txt) > 25:
                    api_key = txt
        except Exception:
            pass

        # Fallback cari via regex di page content
        if not api_key:
            content = await page.content()
            matches = re.findall(r'(cc_[A-Za-z0-9_-]{20,})', content)
            if matches:
                api_key = matches[0]

        # Fallback jika key sudah ada di table tapi tidak di banner baru: gunakan reveal endpoint
        if not api_key:
            try:
                reveal_btn = page.locator("button[title*='Reveal full key'], button[title*='Hide key']").first
                if await reveal_btn.count() > 0:
                    await human_click(reveal_btn, pre_delay=0.3, post_delay=1.0)
                    await human_delay(1.5, 2.5)
                    content = await page.content()
                    matches = re.findall(r'(cc_[A-Za-z0-9_-]{20,})', content)
                    if matches:
                        api_key = matches[0]
            except Exception:
                pass

        if not api_key:
            raise RuntimeError("Gagal mengekstrak API Key CodeCraft (format cc_...)")

        print(f"[+] [CodeCraft] API Key berhasil didapatkan: {api_key[:12]}...{api_key[-4:]}")
        return api_key

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int,
    ) -> bool:
        """
        Menjalankan alur lengkap CodeCraft untuk satu akun.
        """
        email = account.get("email", "")
        self.set_current_account(email)

        try:
            api_key = await self._obtain_codecraft_api_key(context, account)
            if not api_key:
                self.mark_failed("extract_key", "Gagal mendapatkan API Key", retryable=True)
                return False

            self.mark_stage("saving_result")
            self.save_key(email, api_key)
            self.mark_success(key_hint=f"{api_key[:10]}...{api_key[-4:]}")
            print(f"[+] [CodeCraft] SUKSES! API Key tersimpan untuk {email}: {api_key[:12]}...{api_key[-4:]}")
            return True

        except Exception as e:
            print(f"[-] [CodeCraft] Error pada {email}: {e}")
            self.mark_failed("error", str(e), retryable=True)
            return False
