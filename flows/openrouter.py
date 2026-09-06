import asyncio
import re
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .base import BaseFlow
from .google_auth_helper import fill_google_login
from .human_helper import human_click, human_type, human_delay


class OpenRouterFlow(BaseFlow):
    """
    Alur registrasi & pengambilan API Key OpenRouter (openrouter.ai).
    Menggunakan sign-in dengan Google OAuth via Clerk.
    """

    name = "OpenRouter (openrouter.ai -> AI-Omni)"
    flow_name = "openrouter"

    async def _obtain_openrouter_api_key(
        self, context: BrowserContext, account: Dict[str, Any]
    ) -> Optional[str]:
        email = account.get("email", "")
        print(f"\n[2/1] Memproses Akun OpenRouter: {email}")

        or_page: Page = context.pages[0] if context.pages else await context.new_page()
        api_key = None

        try:
            # 1. Buka OpenRouter sign-in dengan redirect langsung ke keys page
            self.mark_stage("navigate")
            print("[*] [OpenRouter] Membuka https://openrouter.ai/sign-in ...")
            await or_page.goto(
                "https://openrouter.ai/sign-in?redirect_url=https%3A%2F%2Fopenrouter.ai%2Fworkspaces%2Fdefault%2Fkeys",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await human_delay(2.0, 3.5)

            # 2. Klik tombol Google OAuth di form Clerk
            self.mark_stage("click_google_oauth")
            google_btn = or_page.locator(
                "button.cl-socialButtonsIconButton__google, button.cl-button__google, button[data-provider='google']"
            ).first
            await google_btn.wait_for(state="visible", timeout=45000)
            await human_delay(1.5, 2.5)

            print("[*] [OpenRouter] Mengklik tombol Google OAuth Clerk...")
            try:
                await google_btn.click(timeout=5000, force=True)
            except Exception:
                await or_page.evaluate("""() => {
                    const btn = document.querySelector('button.cl-socialButtonsIconButton__google, button.cl-button__google');
                    if (btn) btn.click();
                }""")

            # 3. Handle navigasi ke Google Sign-In (popup atau tab yang sama)
            self.mark_stage("google_oauth")
            google_page: Optional[Page] = None
            for _ in range(40):
                await or_page.wait_for_timeout(500)
                if "accounts.google.com" in or_page.url:
                    google_page = or_page
                    break
                for pg in context.pages:
                    if pg is not or_page and "accounts.google.com" in pg.url:
                        google_page = pg
                        break
                if google_page:
                    break

            if not google_page:
                raise RuntimeError("Halaman Google Sign In tidak terbuka setelah klik OAuth")

            print("[*] [OpenRouter] Google OAuth terbuka, mengisi kredensial...")
            await fill_google_login(google_page, account)

            # Tutup tab popup jika Google terbuka di popup terpisah
            if google_page is not or_page:
                try:
                    await google_page.wait_for_event("close", timeout=30000)
                except Exception:
                    if not google_page.is_closed():
                        await google_page.close()

            # 4. Tunggu callback & redirect protect-check Clerk
            self.mark_stage("wait_protect_check")
            print("[*] [OpenRouter] Menunggu callback & protect-check Clerk...")
            for _ in range(120):
                await or_page.wait_for_timeout(1000)
                u = or_page.url
                if (
                    "protect-check" not in u
                    and "sso-callback" not in u
                    and "accounts.google" not in u
                ):
                    break

            await human_delay(3.0, 4.5)
            print(f"[*] [OpenRouter] Landing: {or_page.url[:120]}")

            # 5. Handle Form Legal / Missing fields jika ada (sign-up/continue)
            if "/sign-up/continue" in or_page.url:
                print("[*] [OpenRouter] Halaman sign-up/continue terdeteksi...")
                try:
                    em_in = or_page.locator("input[name='emailAddress'], input[id='emailAddress-field']").first
                    if await em_in.is_visible():
                        await human_type(em_in, email)
                        await human_delay(0.5, 0.8)
                except Exception:
                    pass
                try:
                    pw_in = or_page.locator("input[name='password'], input[id='password-field']").first
                    if await pw_in.is_visible():
                        await human_type(pw_in, account.get("password", ""))
                        await human_delay(0.5, 0.8)
                except Exception:
                    pass
                try:
                    cb = or_page.locator("input[type='checkbox'], [role='checkbox']").first
                    if await cb.is_visible():
                        await human_click(cb, pre_delay=0.2, post_delay=0.4)
                except Exception:
                    pass
                cont = or_page.locator("button:has-text('Continue')").first
                if await cont.is_visible():
                    await human_click(cont)
                    print("[*] [OpenRouter] Form continue disubmit...")
                    for _ in range(40):
                        await or_page.wait_for_timeout(1000)
                        if "/sign-up/continue" not in or_page.url:
                            break
                    await human_delay(2.0, 3.5)

            # 6. Wizard "Welcome to OpenRouter": pilih Individual -> Next
            h1 = ""
            try:
                h1 = await or_page.locator("h1").first.text_content() or ""
            except Exception:
                pass

            if "Welcome to OpenRouter" in h1:
                print("[*] [OpenRouter] Wizard onboarding terdeteksi — memilih Personal/Individual...")
                await human_delay(1.5, 2.5)
                try:
                    opt = or_page.locator("[role=radio], input[type=radio], label").first
                    if await opt.is_visible():
                        await human_click(opt, pre_delay=0.3, post_delay=0.5)
                except Exception:
                    pass
                nxt = or_page.locator("button:has-text('Next'), button:has-text('Continue'), button:has-text('Get Started')").first
                if await nxt.is_visible():
                    await human_click(nxt)
                    print("[*] [OpenRouter] Wizard step 1 selesai...")
                    await human_delay(3.5, 5.0)

            # 7. Ekstraksi API Key dari konten halaman / modal workspace-ready
            self.mark_stage("extract_key")
            print("[*] [OpenRouter] Mencari API Key (sk-or-v1-...)...")

            # Coba cari dari page content
            content = await or_page.content()
            m = re.search(r'(sk-or-v1-[A-Za-z0-9_-]{20,})', content)
            if m:
                api_key = m.group(1)
                print(f"[+] [OpenRouter] Key ditemukan dari page content: {api_key[:14]}...{api_key[-4:]}")

            # Coba cari dari body.innerText
            if not api_key:
                body_txt = await or_page.evaluate("() => document.body.innerText")
                m = re.search(r'(sk-or-v1-[A-Za-z0-9_-]{20,})', body_txt)
                if m:
                    api_key = m.group(1)
                    print(f"[+] [OpenRouter] Key ditemukan dari body text: {api_key[:14]}...{api_key[-4:]}")

            # 8. Jika belum dapat, dismiss wizard & buka keys page langsung
            if not api_key:
                # Dismiss modal wizard jika ada
                for _ in range(6):
                    modal_exists = await or_page.evaluate("() => !!document.querySelector('.fixed.inset-0')")
                    if not modal_exists:
                        break
                    clicked = False
                    for label in ["I'll do this later", "Next", "Continue", "Done", "Finish", "Skip", "Close"]:
                        try:
                            b = or_page.locator(f".fixed.inset-0 button:has-text(\"{label}\"), .fixed.inset-0 a:has-text(\"{label}\")").first
                            if await b.is_visible():
                                await human_click(b)
                                clicked = True
                                await human_delay(2.0, 3.0)
                                break
                        except Exception:
                            continue
                    if not clicked:
                        break

                # Buka halaman keys
                print("[*] [OpenRouter] Menuju halaman API Keys (workspaces/default/keys)...")
                await or_page.goto("https://openrouter.ai/workspaces/default/keys", wait_until="domcontentloaded")
                await human_delay(2.5, 3.5)

                # Klik New Key
                new_key_btn = or_page.locator("button:has-text('New Key'), a:has-text('New Key'), button:has-text('Create Key')").first
                if await new_key_btn.is_visible():
                    print("[*] [OpenRouter] Mengklik 'New Key'...")
                    await human_click(new_key_btn, pre_delay=0.4, post_delay=1.0)
                    await human_delay(1.5, 2.5)

                    name_in = or_page.locator("[role='dialog'] input, .fixed.inset-0 input").first
                    if await name_in.is_visible():
                        await human_type(name_in, email.split("@")[0])
                        await human_delay(0.5, 1.0)
                        sub_btn = or_page.locator("[role='dialog'] button:has-text('Create'), .fixed.inset-0 button:has-text('Create')").last
                        if await sub_btn.is_visible():
                            await human_click(sub_btn)
                            await human_delay(3.0, 4.5)

                # Ekstrak dari dialog create key
                content = await or_page.content()
                m = re.search(r'(sk-or-v1-[A-Za-z0-9_-]{20,})', content)
                if m:
                    api_key = m.group(1)
                    print(f"[+] [OpenRouter] Key dibuat & ditemukan: {api_key[:14]}...{api_key[-4:]}")

            if not api_key:
                raise RuntimeError("Gagal mengekstrak API Key OpenRouter")

            self.mark_stage("completed")
            return api_key

        except Exception as e:
            print(f"[-] [OpenRouter] Error: {e}")
            raise

    async def run_flow(
        self,
        context: BrowserContext,
        main_page: Optional[Page],
        account: Dict[str, str],
        index: int,
        total: int,
    ) -> bool:
        """
        Menjalankan flow lengkap registrasi & simpan key OpenRouter.
        """
        email = account.get("email", "")
        self.set_current_account(email)

        try:
            api_key = await self._obtain_openrouter_api_key(context, account)
            if not api_key:
                self.mark_failed("extract_key", "Gagal mendapatkan API Key", retryable=True)
                return False

            self.mark_stage("saving_result")
            self.save_key(email, api_key)
            self.mark_success(key_hint=f"{api_key[:10]}...{api_key[-4:]}")
            print(f"[+] [OpenRouter] SUKSES! API Key tersimpan untuk {email}: {api_key[:14]}...{api_key[-4:]}")
            return True

        except Exception as e:
            self.mark_failed("error", str(e), retryable=True)
            return False
