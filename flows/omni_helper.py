import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page, BrowserContext
from .human_helper import human_type, human_click, human_delay

async def ensure_omni_logged_in(page: Page, config: Dict[str, Any]) -> bool:
    base_url = config.get("omni_url", "https://ai-omni.enpiistudio.com/login")
    omni_password = config.get("omni_password", "its.enpii-118")

    print(f"[*] [AI-Omni] Membuka {base_url}...")
    try:
        await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass

    await human_delay(0.8, 1.5)

    if "/dashboard" in page.url:
        print("[+] [AI-Omni] Sesi aktif di Dashboard AI Omni.")
        return True

    pwd_input = page.locator("input[type='password']").first
    if await pwd_input.is_visible():
        print("[*] [AI-Omni] Mengisi kata sandi login...")
        await human_type(pwd_input, omni_password)
        submit_btn = page.locator("button[type='submit']").first
        await human_click(submit_btn)

        try:
            await page.wait_for_url("**/dashboard**", timeout=15000)
            print("[+] [AI-Omni] Login AI-Omni berhasil.")
            await human_delay(1.0, 2.0)
            return True
        except Exception:
            print("[-] [AI-Omni] Navigasi langsung ke /dashboard/providers...")
            await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers", wait_until="domcontentloaded")
            await human_delay(1.0, 2.0)
            return True
    return True

async def navigate_to_provider(page: Page, provider_title_or_href: str) -> bool:
    print(f"[*] [AI-Omni] Menuju menu Penyedia...")
    
    if "/dashboard/providers" not in page.url or page.url.endswith("/providers"):
        provider_menu = page.locator("a[href='/dashboard/providers']").first
        if await provider_menu.is_visible():
            await human_click(provider_menu, pre_delay=0.3, post_delay=0.8)
        else:
            await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers", wait_until="domcontentloaded")
            await human_delay(0.8, 1.5)

    print(f"[*] [AI-Omni] Memilih provider: {provider_title_or_href}...")
    card_loc = page.locator(
        f"a[href*='{provider_title_or_href}'], a:has-text('{provider_title_or_href}')"
    ).first
    await card_loc.wait_for(state="visible", timeout=12000)
    await human_click(card_loc, pre_delay=0.4, post_delay=1.0)
    return True

async def save_api_key_to_omni(page: Page, provider_name: str, account_email: str, api_key: str) -> bool:
    try:
        await navigate_to_provider(page, provider_name)

        print("[*] [AI-Omni] Mengklik 'Tambahkan / Add'...")
        add_btn = page.locator("button:has-text('Tambahkan'), button:has-text('Add')").first
        await human_click(add_btn, pre_delay=0.4, post_delay=0.8)

        print(f"[*] [AI-Omni] Mengisi label/email ({account_email})...")
        label_input = page.locator("input[placeholder*='Production Key'], input[type='text']").first
        await human_type(label_input, account_email)

        print("[*] [AI-Omni] Mengisi API Key...")
        key_input = page.locator("input[type='password'], input[placeholder*='Optional']").first
        await human_type(key_input, api_key, min_delay=0.01, max_delay=0.03)

        print("[*] [AI-Omni] Mengklik tombol Simpan...")
        save_btn = page.locator("button:has-text('Simpan'), button:has-text('Save')").first
        await human_click(save_btn, pre_delay=0.5, post_delay=1.5)

        await human_delay(3.0, 4.0)
        print(f"[+] [AI-Omni] Berhasil menyimpan API key untuk {account_email}!")
        return True
    except Exception as e:
        print(f"[-] [AI-Omni] Gagal menyimpan API key: {e}")
        return False
