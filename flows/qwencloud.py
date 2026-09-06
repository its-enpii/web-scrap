import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, navigate_to_provider
from .human_helper import human_type, human_click, human_delay

class QwenCloudFlow(BaseFlow):
    name = "Qwen Cloud (home.qwencloud.com -> AI-Omni)"
    description = "Login ke Qwen Cloud via Google, buat API Key, dan daftarkan ke AI-Omni (Global) atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
        self.omni_password = config.get("omni_password", "its.enpii-118")
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_qwencloud.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_key(self, context: BrowserContext, qwen_page: Page, account: Dict[str, str]) -> Optional[str]:
        api_key = None
        try:
            self.mark_stage("navigate")
            print("[*] [QwenCloud] Membuka https://www.qwencloud.com...")
            await qwen_page.goto("https://www.qwencloud.com", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # 2. Klik Get Started / Sign Up
            signup_btn = qwen_page.locator("a:has-text('Get Started'), button:has-text('Sign Up'), a[href*='login'], a[href*='signup']").first
            if await signup_btn.is_visible():
                print("[*] [QwenCloud] Mengklik 'Get Started / Sign Up'...")
                await human_click(signup_btn, pre_delay=0.4, post_delay=1.0)
                await human_delay(1.0, 2.0)

            self.mark_stage("login")
            # 3. Klik Google login jika tersedia
            google_btn = qwen_page.locator("button:has-text('Google'), a:has-text('Google'), [aria-label*='Google']").first
            if await google_btn.is_visible():
                print("[*] [QwenCloud] Mengklik login via Google...")
                await human_click(google_btn, pre_delay=0.4, post_delay=1.0)
                await fill_google_login(qwen_page, account)

            # Buka halaman api keys
            print("[*] [QwenCloud] Menuju https://home.qwencloud.com/api-keys...")
            await qwen_page.goto("https://home.qwencloud.com/api-keys", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # 4. Klik Create API key
            create_btn = qwen_page.locator("button:has-text('Create API key'), button:has-text('Create key'), button:has-text('New Key')").first
            await create_btn.wait_for(state="visible", timeout=15000)
            await human_click(create_btn, pre_delay=0.4, post_delay=1.0)

            # 5. Isi nama key
            name_input = qwen_page.locator("input[placeholder*='name'], input#key-name, input[name='name']").first
            if await name_input.is_visible():
                key_name = account["email"].split("@")[0]
                await human_type(name_input, key_name)

            # 6. Klik Generate Key
            gen_btn = qwen_page.locator("button:has-text('Generate Key'), button:has-text('Confirm'), button:has-text('Create')").first
            if await gen_btn.is_visible():
                await human_click(gen_btn, pre_delay=0.4, post_delay=1.5)
                await human_delay(2.0, 3.0)

            self.mark_stage("extract_key")
            # 7. Salin API Key
            print("[*] [QwenCloud] Mengambil API Key...")
            key_el = qwen_page.locator("code, span:has-text('sk-ws-'), [data-slot='key-value']").first
            if await key_el.is_visible():
                raw_key = await key_el.inner_text()
                match = re.search(r'(sk-ws-[a-zA-Z0-9_\-]+)', raw_key)
                if match:
                    api_key = match.group(1).strip()
                else:
                    api_key = raw_key.strip()

            if not api_key:
                body_content = await qwen_page.content()
                match = re.search(r'(sk-ws-[a-zA-Z0-9_\-]{20,})', body_content)
                if match:
                    api_key = match.group(1).strip()

            print(f"[+] [QwenCloud] API Key diperoleh: {api_key[:12] if api_key else 'None'}...")
            return api_key

        except Exception as e:
            print(f"[-] [QwenCloud] Gagal mendapatkan key: {e}")
            self.mark_failed("extract_key", f"pengambilan API key gagal: {e}", retryable=True)
            return None

    async def _add_qwen_to_omni(self, page: Page, account_email: str, api_key: str) -> bool:
        try:
            # 1. Klik Qwen Cloud
            print("[*] [AI-Omni] Menuju provider Qwen Cloud...")
            await navigate_to_provider(page, "qwen-cloud")

            # 2. Klik Tambahkan / Add
            print("[*] [AI-Omni] Mengklik 'Tambahkan / Add'...")
            add_btn = page.locator("button:has-text('Tambahkan'), button:has-text('Add')").first
            await human_click(add_btn, pre_delay=0.4, post_delay=0.8)

            # 3. Klik Global (button[data-region='global-sg'])
            print("[*] [AI-Omni] Memilih region 'Global'...")
            global_btn = page.locator("button[data-region='global-sg'], button:has-text('Global')").first
            await global_btn.wait_for(state="visible", timeout=10000)
            await human_click(global_btn, pre_delay=0.4, post_delay=1.0)

            # 4. Isikan email pada input
            print(f"[*] [AI-Omni] Mengisi email ({account_email})...")
            label_input = page.locator("input[placeholder*='Production Key'], input[type='text']").first
            await human_type(label_input, account_email)

            # 5. Isikan / Paste API Key
            print("[*] [AI-Omni] Mengisi API Key...")
            key_input = page.locator("input[type='password']").first
            await human_type(key_input, api_key, min_delay=0.01, max_delay=0.03)

            # 6. Klik Simpan / Save
            print("[*] [AI-Omni] Mengklik 'Simpan / Save'...")
            save_btn = page.locator("button:has-text('Simpan'), button:has-text('Save')").first
            await human_click(save_btn, pre_delay=0.5, post_delay=1.5)

            # 7. Tunggu sekitar 5 detik
            await human_delay(4.0, 5.0)
            print(f"[+] [AI-Omni] Berhasil menyimpan API Key Qwen Cloud untuk {account_email}!")
            return True

        except Exception as e:
            print(f"[-] [AI-Omni] Gagal menyimpan API key Qwen Cloud: {e}")
            return False

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
            saved = await self._add_qwen_to_omni(main_page, account["email"], api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if saved:
                self.mark_success(f"{api_key[:10]}...{api_key[-4:]}")
            else:
                self.mark_failed("save_key", "AI-Omni menolak atau gagal menyimpan API key", retryable=True)
            return saved
