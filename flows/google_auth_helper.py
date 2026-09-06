import asyncio
from typing import Dict
from playwright.async_api import Page
from .human_helper import human_type, human_click, human_delay

async def fill_google_login(auth_page: Page, account: Dict[str, str], timeout_ms: int = 25000) -> bool:
    """
    Helper reusable untuk menangani form login Google (Email, Password, Recovery)
    dengan pengetikan dan klik alami (human-like behavior).
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
            
            # Coba klik tombol Next atau tekan Enter
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

            await human_delay(2.5, 4.0)
        except Exception as pe:
            print(f"[?] [Google Auth] Input password tidak muncul / dilewati: {pe}")

        # 3. Handle Workspace Terms of Service (Speedbump / Welcome to your new account)
        try:
            tos_btn = auth_page.locator(
                "button:has-text('I understand'), button:has-text('Saya mengerti'), button:has-text('Saya paham'), button:has-text('Accept'), button:has-text('Agree')"
            ).first
            if await tos_btn.is_visible(timeout=5000):
                print("[*] [Google Auth] Mendeteksi Workspace Terms of Service (I understand), mengklik...")
                await human_click(tos_btn)
                await human_delay(2.0, 3.5)
        except Exception:
            pass

        # 4. Input Recovery Email jika diminta Google
        rec_locator = auth_page.locator(
            "text=Confirm your recovery email, text=Konfirmasikan email pemulihan Anda, div[data-challengetype='12']"
        ).first
        if await rec_locator.is_visible(timeout=4000) and account.get("recovery"):
            print("[*] [Google Auth] Google meminta konfirmasi recovery email...")
            rec_input = auth_page.locator("input[type='email'], input#knowledge-preregistered-email-response").first
            if await rec_input.is_visible():
                await human_type(rec_input, account["recovery"])
                await human_delay(0.2, 0.4)
                await auth_page.keyboard.press("Enter")
                await human_delay(2.5, 3.5)

        return True
    except Exception as e:
        print(f"[-] [Google Auth] Error: {e}")
        return False
