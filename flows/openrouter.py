import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .omni_helper import ensure_omni_logged_in, save_api_key_to_omni
from .human_helper import human_type, human_click, human_delay

async def handle_turnstile_if_present(page: Page, timeout_ms: int = 6000):
    """Mendeteksi dan mencoba menyelesaikan Cloudflare Turnstile jika muncul."""
    try:
        turnstile_frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
        checkbox = turnstile_frame.locator("input[type='checkbox'], span.mark, div.ctp-checkbox-label").first
        if await checkbox.is_visible(timeout=timeout_ms):
            print("[*] [Cloudflare Turnstile] Terdeteksi widget Turnstile, mengklik verifikasi...")
            await human_click(checkbox, pre_delay=0.5, post_delay=1.5)
            await human_delay(2.0, 3.5)
    except Exception:
        pass

class OpenRouterFlow(BaseFlow):
    name = "OpenRouter"
    description = "Login/Register ke openrouter.ai via Google, buat API Key, dan daftarkan ke AI-Omni atau simpan ke file."

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not self.config.get("output_file") or self.config.get("output_file") == "keys.txt":
            self.output_file = "keys_openrouter.txt"

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        if self.output_mode == "omni" and main_page:
            return await ensure_omni_logged_in(main_page, self.config)
        return True

    async def _obtain_key(self, context: BrowserContext, router_page: Page, account: Dict[str, str]) -> Optional[str]:
        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        api_key = None

        try:
            print("[*] [OpenRouter] Membuka https://openrouter.ai...")
            await router_page.goto("https://openrouter.ai", wait_until="domcontentloaded")
            await human_delay(1.5, 2.5)

            # 1. Klik 'Get API Key' atau 'Sign Up'
            get_key_btn = router_page.locator(
                "a[href='/settings/keys']:has-text('Get API Key'), a:has-text('Get API Key'), a[href='/settings/keys']"
            ).first

            signup_btn = router_page.locator(
                "button:has-text('Sign Up'), a:has-text('Sign Up'), button.bg-primary:has-text('Sign Up')"
            ).first

            if await get_key_btn.is_visible():
                print("[*] [OpenRouter] Mengklik 'Get API Key'...")
                await human_click(get_key_btn, pre_delay=0.5, post_delay=1.2)
                await human_delay(1.0, 2.0)
            elif await signup_btn.is_visible():
                print("[*] [OpenRouter] Mengklik 'Sign Up'...")
                await human_click(signup_btn, pre_delay=0.5, post_delay=1.2)
                await human_delay(1.0, 2.0)
            else:
                fallback_btn = router_page.locator("button:has-text('Sign In'), a:has-text('Sign In'), a[href='/auth']").first
                if await fallback_btn.is_visible():
                    print("[*] [OpenRouter] Mengklik 'Sign In'...")
                    await human_click(fallback_btn, pre_delay=0.5, post_delay=1.2)
                    await human_delay(1.0, 2.0)

            # Cek Turnstile / Cloudflare jika muncul
            await handle_turnstile_if_present(router_page)

            # 2. Klik / centang checkbox persetujuan terms jika ada
            terms_checkbox = router_page.locator(
                "input#legalAccepted-field, input.cl-formFieldCheckboxInput, input[name='legalAccepted'], input[type='checkbox']"
            ).first
            if await terms_checkbox.is_visible():
                print("[*] [OpenRouter] Mencentang persetujuan terms...")
                await human_click(terms_checkbox, pre_delay=0.3, post_delay=0.8)

            # 3. Klik tombol Google
            google_btn = router_page.locator(
                "button.cl-socialButtonsIconButton__google, button.cl-button__google, button:has(span.cl-socialButtonsProviderIcon__google), button:has(span[aria-label*='Google']), button:has-text('Google')"
            ).first
            await google_btn.wait_for(state="visible", timeout=15000)
            print("[*] [OpenRouter] Mengklik login Google...")
            await human_click(google_btn, pre_delay=0.5, post_delay=1.2)
            await router_page.wait_for_load_state("domcontentloaded")

            # 4. Handle Google Auth
            await fill_google_login(router_page, account)

            # 5. Menunggu kembali ke openrouter.ai dan handle modal selamat datang jika ada
            await router_page.wait_for_url("**/openrouter.ai/**", timeout=35000)
            await human_delay(2.0, 3.0)

            next_btn = router_page.locator("button:has-text('Next'), button:has-text('Continue'), button:has-text('Skip')").first
            if await next_btn.is_visible():
                print("[*] [OpenRouter] Menutup modal onboarding...")
                await human_click(next_btn)
                await human_delay(1.0, 1.8)

            # 6. Buka halaman keys
            if "/settings/keys" not in router_page.url and "/workspaces" not in router_page.url:
                print("[*] [OpenRouter] Menuju halaman API Keys...")
                await router_page.goto("https://openrouter.ai/settings/keys", wait_until="domcontentloaded")
                await human_delay(1.5, 2.5)

            # 7. Klik New Key / Create Key
            new_key_btn = router_page.locator("button:has-text('New Key'), button:has-text('Create Key'), button:has-text('Create API Key')").first
            await new_key_btn.wait_for(state="visible", timeout=15000)
            await human_click(new_key_btn, pre_delay=0.4, post_delay=1.0)

            # 8. Isikan nama key
            name_input = router_page.locator("input#name, input[name='name'], input[placeholder*='Key Name'], input[placeholder*='Chatbot Key']").first
            if await name_input.is_visible():
                key_label = account["email"].split("@")[0]
                print(f"[*] [OpenRouter] Mengisi nama key: {key_label}...")
                await human_type(name_input, key_label)

            # 9. Klik Create
            create_btn = router_page.locator("button[type='submit'], button:has-text('Create')").first
            await create_btn.wait_for(state="visible", timeout=8000)
            await human_click(create_btn, pre_delay=0.4, post_delay=1.5)
            await human_delay(2.0, 3.0)

            # 10. Copy key
            print("[*] [OpenRouter] Mengambil token API Key...")
            
            # Coba cari tombol copy di modal key
            copy_btn = router_page.locator("button:has-text('Copy'), button[title*='Copy'], [role='dialog'] button:has-text('Copy')").first
            if await copy_btn.is_visible():
                await human_click(copy_btn, pre_delay=0.2, post_delay=0.5)
                try:
                    clip_text = await router_page.evaluate("navigator.clipboard.readText()")
                    if clip_text and "sk-or-v1-" in clip_text:
                        api_key = clip_text.strip()
                except Exception:
                    pass

            if not api_key:
                key_element = router_page.locator("code, [data-dd-privacy='hidden'], div:has-text('sk-or-v1'), input[value*='sk-or-v1']").first
                if await key_element.is_visible():
                    text_content = await key_element.inner_text()
                    val_attr = await key_element.get_attribute("value") or ""
                    combined = f"{text_content} {val_attr}"
                    match = re.search(r'(sk-or-v1-[a-zA-Z0-9_\-]+)', combined)
                    if match:
                        api_key = match.group(1).strip()
                    else:
                        api_key = text_content.strip()

            if not api_key:
                body_text = await router_page.content()
                match = re.search(r'(sk-or-v1-[a-zA-Z0-9_\-]{30,})', body_text)
                if match:
                    api_key = match.group(1).strip()

            print(f"[+] [OpenRouter] Key berhasil diperoleh: {api_key[:12] if api_key else 'None'}...")
            return api_key

        except Exception as e:
            print(f"[-] [OpenRouter] Gagal mendapatkan key: {e}")
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
            saved = await save_api_key_to_omni(main_page, "OpenRouter", account["email"], api_key)
            await main_page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return saved
