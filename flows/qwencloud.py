import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_type, human_click, human_delay

class QwenCloudFlow(BaseFlow):
    name = "Qwen Cloud (home.qwencloud.com -> AI-Omni)"
    description = "Login ke Qwen Cloud via Google SSO Alibaba, buat API Key, dan daftarkan ke AI-Omni atau simpan ke file."

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

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int
    ) -> bool:
        email = account["email"]
        print(f"\n[{index+1}/{total}] Memproses Akun Qwen Cloud: {email}")
        self.set_current_account(email)

        qwen_page = main_page or await context.new_page()
        api_key = None

        try:
            self.mark_stage("navigate")
            print("[*] [QwenCloud] Membuka https://home.qwencloud.com/api-keys...")
            await qwen_page.goto("https://home.qwencloud.com/api-keys", wait_until="domcontentloaded", timeout=45000)
            await human_delay(1.5, 2.5)

            # Jika belum login, klik 'Log in now'
            login_btn = qwen_page.locator("button:has-text('Log in now')").first
            if await login_btn.is_visible():
                self.mark_stage("login")
                print("[*] [QwenCloud] Mengklik 'Log in now'...")
                await human_click(login_btn)
                await qwen_page.wait_for_load_state("domcontentloaded")

                google_btn = qwen_page.locator("button:has-text('Log in with Google'), button:has-text('Google')").first
                try:
                    await google_btn.wait_for(state="visible", timeout=15000)
                    print("[*] [QwenCloud] Mengklik 'Log in with Google'...")
                    await human_click(google_btn)
                    await qwen_page.wait_for_load_state("domcontentloaded")
                except Exception:
                    pass

                # Handle Google Auth
                await fill_google_login(qwen_page, account)
                await human_delay(2.0, 3.0)

                # Handle First Login Alibaba Cloud jika ada (onboarding region Indonesia)
                if "first_login.htm" in qwen_page.url or "alibabacloud.com" in qwen_page.url:
                    print("[*] [QwenCloud] Menangani form Onboarding Alibaba Cloud (Indonesia)...")
                    region_in = qwen_page.locator("input[placeholder*='Select your country/region'], input[type='text']").first
                    if await region_in.is_visible():
                        await human_click(region_in)
                        await human_delay(0.5, 1.0)
                        indo_opt = qwen_page.locator("li:has-text('Indonesia'), div:has-text('Indonesia')").last
                        if await indo_opt.is_visible():
                            await human_click(indo_opt)
                            await human_delay(0.5, 1.0)

                    # Centang Terms of Use
                    terms_cb = qwen_page.locator("input[type='checkbox'], span.next-checkbox").first
                    if await terms_cb.is_visible():
                        await human_click(terms_cb)
                        await human_delay(0.5, 1.0)

                    # Klik Confirm
                    confirm_btn = qwen_page.locator("button:has-text('Confirm'), button:has-text('Submit'), button:has-text('Next')").first
                    if await confirm_btn.is_visible():
                        await human_click(confirm_btn)
                        print("[*] [QwenCloud] Form Onboarding Alibaba disubmit...")
                        await qwen_page.wait_for_timeout(4000)

            # Tunggu kembali ke home.qwencloud.com
            for _ in range(30):
                if "home.qwencloud.com" in qwen_page.url:
                    break
                await qwen_page.wait_for_timeout(1000)

            # Pastikan berada di halaman api-keys
            if "/api-keys" not in qwen_page.url:
                await qwen_page.goto("https://home.qwencloud.com/api-keys", wait_until="domcontentloaded", timeout=45000)
                await human_delay(2.0, 3.5)

            self.mark_stage("generate_key")

            # 1. Cek apakah sudah ada row key di tabel
            content = await qwen_page.content()
            keys = re.findall(r'(sk-ws-[A-Za-z0-9_.-]{30,})', content)
            if keys:
                api_key = keys[0]
                print(f"[+] [QwenCloud] API Key ditemukan di tabel: {api_key[:12]}...{api_key[-4:]}")

            # 2. Jika belum ada, klik Create API key
            if not api_key:
                create_btn = qwen_page.locator("button:has-text('Create API key'), button:has-text('Create key')").first
                await create_btn.wait_for(state="visible", timeout=25000)
                print("[*] [QwenCloud] Mengklik 'Create API key'...")
                await human_click(create_btn, pre_delay=0.4, post_delay=1.0)

                # Isi Description agar tombol Generate Key enabled
                desc_in = qwen_page.locator('input[placeholder*="Production API key" i], [role="dialog"] input[type="text"]').first
                await desc_in.wait_for(state="visible", timeout=20000)
                key_name = account["email"].split("@")[0]
                await human_type(desc_in, key_name)
                await human_delay(0.5, 1.0)

                # Klik Generate Key
                gen_btn = qwen_page.locator("button:has-text('Generate Key')").first
                await gen_btn.wait_for(state="visible", timeout=20000)
                print("[*] [QwenCloud] Mengklik 'Generate Key'...")
                await human_click(gen_btn, pre_delay=0.4, post_delay=1.5)
                await human_delay(3.0, 5.0)

                # Ekstrak API Key dari dialog hasil
                copy_btn = qwen_page.locator('button[aria-label*="Copy" i], button:has-text("Copy")').last
                if await copy_btn.is_visible():
                    await human_click(copy_btn, pre_delay=0.2, post_delay=0.5)
                    try:
                        cb_key = await qwen_page.evaluate("navigator.clipboard.readText()")
                        if cb_key and cb_key.strip().startswith("sk-"):
                            api_key = cb_key.strip()
                    except Exception:
                        pass

                if not api_key:
                    val_in = qwen_page.locator('[role="dialog"] input[value^="sk-"]').first
                    if await val_in.is_visible():
                        api_key = await val_in.get_attribute("value")

                if not api_key:
                    content = await qwen_page.content()
                    keys = re.findall(r'(sk-ws-[A-Za-z0-9_.-]{30,}|sk-[A-Za-z0-9_.-]{20,})', content)
                    if keys:
                        api_key = keys[0]

            if api_key:
                print(f"[+] [QwenCloud] Berhasil mendapatkan API Key: {api_key[:12]}...{api_key[-4:]}")
            else:
                raise Exception("Gagal mengekstrak API Key dari dialog Qwen Cloud")

            if self.output_mode == "txt":
                self.save_key(email, api_key)
            elif self.output_mode == "omni" and main_page:
                self.mark_stage("omni_save")
                await save_api_key_to_omni(main_page, "qwen", email, api_key)

            self.mark_success()
            return True

        except Exception as e:
            self.mark_failed("generate_key", str(e), retryable=True)
            return False
