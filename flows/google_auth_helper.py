import asyncio
from typing import Dict
from playwright.async_api import Page
from .human_helper import human_type, human_click, human_delay


async def _try_click_first(page: Page, selectors) -> bool:
    """Coba klik selector pertama yang visible. Return True jika ada yang diklik."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await human_click(loc)
                print(f"[*] [Google Auth] Klik: {sel}", flush=True)
                await human_delay(2.0, 3.0)
                return True
        except Exception:
            continue
    return False


async def fill_google_login(auth_page: Page, account: Dict[str, str], timeout_ms: int = 25000) -> bool:
    """
    Helper reusable untuk menangani form login Google (Email, Password, ToS Workspace,
    OAuth Consent, Recovery) dengan pengetikan dan klik alami (human-like behavior).
    Setelah submit password, masuk loop polling 30s untuk menangani semua interstitial
    Google secara berurutan sampai popup keluar dari accounts.google.com.
    """
    try:
        print("[*] [Google Auth] Menunggu halaman Sign In Google termuat...")

        # 1. Tunggu input email Google muncul
        email_input = auth_page.locator("input[type='email'], input#identifierId, input[name='identifier']").first
        try:
            await email_input.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            print("[?] [Google Auth] Form email Google tidak muncul, memeriksa apakah sudah ada sesi...")

        if await email_input.is_visible():
            print(f"[*] [Google Auth] Mengetik email ({account['email']})...")
            await human_type(email_input, account["email"])

            next_email_btn = auth_page.locator("#identifierNext button, button:has-text('Next'), button:has-text('Berikutnya')").first
            if await next_email_btn.is_visible():
                await human_click(next_email_btn)
            else:
                await human_delay(0.2, 0.4)
                await auth_page.keyboard.press("Enter")

            await human_delay(2.0, 3.0)

        # 2. Tunggu input password Google muncul
        print("[*] [Google Auth] Menunggu input kata sandi...")
        pwd_input = auth_page.locator("input[type='password'], input[name='Passwd']").first
        try:
            await pwd_input.wait_for(state="visible", timeout=timeout_ms)
            print("[*] [Google Auth] Mengetik kata sandi...")
            await human_type(pwd_input, account["password"])

            next_pwd_btn = auth_page.locator("#passwordNext button, button:has-text('Next'), button:has-text('Berikutnya')").first
            if await next_pwd_btn.is_visible():
                await human_click(next_pwd_btn)
            else:
                await human_delay(0.2, 0.4)
                await auth_page.keyboard.press("Enter")

            await human_delay(2.0, 3.0)
        except Exception as pe:
            print(f"[?] [Google Auth] Input password tidak muncul / dilewati: {pe}")

        # 3. Loop post-login: Workspace ToS -> OAuth Consent (bisa >1 halaman) -> Recovery
        #    Polling tiap ~1s sampai 30s atau popup keluar dari accounts.google.com
        print("[*] [Google Auth] Menangani post-login (ToS/Consent/Recovery)...")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 30
        while loop.time() < deadline:
            try:
                url = auth_page.url
            except Exception:
                print("[*] [Google Auth] Popup ditutup oleh opener.")
                break
            if "accounts.google." not in url and "accounts.youtube.com" not in url and "gsi/transform" not in url:
                print(f"[*] [Google Auth] Keluar dari Google: {url[:80]}")
                break

            clicked = False
            # 3a. Workspace ToS ("Welcome to your new account")
            clicked = await _try_click_first(auth_page, [
                "button:has-text('I understand')",
                "button:has-text('Saya mengerti')",
                "button:has-text('Saya paham')",
                "button:has-text('Accept')",
                "button:has-text('Agree')",
            ])
            # 3b. OAuth Consent screen (bisa muncul berulang utk halaman izin kedua)
            if not clicked:
                clicked = await _try_click_first(auth_page, [
                    "button#submit_approve_access",
                    "#submit_approve_access",
                    "[data-id='EBS5ae']",
                    "div[role='button']:has-text('Continue')",
                    "div[role='button']:has-text('Lanjutkan')",
                    "div[role='button']:has-text('Allow')",
                    "div[role='button']:has-text('Izinkan')",
                    "button:has-text('Continue')",
                    "button:has-text('Lanjutkan')",
                    "button:has-text('Allow')",
                    "button:has-text('Izinkan')",
                    "button:has-text('Select all')",
                    "button:has-text('Pilih semua')",
                ])
            # 3c. Recovery email challenge
            if not clicked and account.get("recovery"):
                rec = auth_page.locator(
                    "text=Confirm your recovery email, text=Konfirmasikan email pemulihan Anda"
                ).first
                try:
                    if await rec.count() > 0 and await rec.is_visible():
                        print("[*] [Google Auth] Google meminta konfirmasi recovery email...")
                        rec_input = auth_page.locator("input[type='email'], input#knowledge-preregistered-email-response").first
                        await human_type(rec_input, account["recovery"])
                        await human_delay(0.2, 0.4)
                        await auth_page.keyboard.press("Enter")
                        await human_delay(2.0, 3.0)
                        clicked = True
                except Exception:
                    pass

            if not clicked:
                await asyncio.sleep(1)

        return True
    except Exception as e:
        print(f"[-] [Google Auth] Error: {e}")
        return False
