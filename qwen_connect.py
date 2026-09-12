"""Qwen Cloud runner modular & robust untuk multi-account via WARP container proxy.
Menjalankan 1 akun = 1 browser terisolasi, auto onboarding Indonesia + ToS, auto create & capture unmasked API key.
"""
import asyncio, json, os, re, sys
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from flows.google_auth_helper import fill_google_login

RES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
KEYS_FILE = os.path.join(RES_DIR, "keys_qwencloud.txt")
BASE_URL = "https://home.qwencloud.com/api-keys"


async def ensure_logged_in(page: Page, account: Dict[str, str]) -> bool:
    """Login ke QwenCloud via Google SSO & selesaikan onboarding Alibaba jika akun baru."""
    await page.goto(BASE_URL, wait_until="load", timeout=45000)
    await asyncio.sleep(2.5)

    btn = page.locator("button:has-text('Log in now')").first
    if await btn.count() and await btn.is_visible():
        print(f"[{account['email']}] Klik 'Log in now'...", flush=True)
        await btn.evaluate("el => el.click()")

        # Tunggu sampai halaman login Alibaba termuat
        g_btn = page.locator("button:has-text('Log in with Google'), a:has-text('Google'), button:has-text('Google')").first
        try:
            await g_btn.wait_for(state="visible", timeout=25000)
            print(f"[{account['email']}] Klik 'Log in with Google'...", flush=True)
            await g_btn.evaluate("el => el.click()")
            await asyncio.sleep(2.5)
        except Exception as e:
            print(f"[{account['email']}] [!] Tombol Google tidak muncul: {e}", flush=True)

        # Handle Google auth form
        print(f"[{account['email']}] Menjalankan Google auth...", flush=True)
        await fill_google_login(page, account, timeout_ms=30000)
        await asyncio.sleep(4)

    # Tangani onboarding Alibaba jika akun baru (first_login)
    if "first_login" in page.url or "alibabacloud.com" in page.url:
        print(f"[{account['email']}] Menangani onboarding Alibaba Cloud (Indonesia)...", flush=True)
        try:
            inp = page.locator("input[type='text']").first
            if await inp.is_visible():
                await inp.click()
                await inp.fill("Indonesia")
                await asyncio.sleep(1)
                opt = page.locator("text='Indonesia'").last
                if await opt.count():
                    await opt.click()
            # Checkbox ToS via klik label
            label = page.locator("label.maas-terms-text__checkable").first
            if await label.count():
                await label.click(position={"x": 10, "y": 10})
            else:
                cb = page.locator("input.maas-terms-text__checkbox, input[type='checkbox']").first
                if await cb.count():
                    await cb.click(force=True)
            await asyncio.sleep(1)
            # Submit Continue via real Playwright click
            cont = page.locator("button:has-text('Continue')").first
            if await cont.is_visible():
                await cont.click()
                await asyncio.sleep(6)
        except Exception as e:
            print(f"[{account['email']}] [!] Onboarding warning: {e}", flush=True)

    # Tunggu kembali ke home.qwencloud.com
    for _ in range(25):
        if "home.qwencloud.com" in page.url:
            break
        await asyncio.sleep(1)

    if "/api-keys" not in page.url:
        await page.goto(BASE_URL, wait_until="load", timeout=45000)
        await asyncio.sleep(3)

    txt = await page.evaluate("document.body.innerText")
    is_ok = "Log in now" not in txt
    return is_ok


async def create_or_get_api_key(page: Page, email: str) -> Optional[str]:
    """Cek tabel atau buat key baru dan ekstrak unmasked key."""
    captured_key = None

    async def on_response(response):
        nonlocal captured_key
        try:
            if any(x in response.url for x in ("apikey", "api-key", "token", "create")):
                text = await response.text()
                m = re.findall(r'(sk-ws-[A-Za-z0-9_.-]{30,}|sk-[A-Za-z0-9_.-]{30,})', text)
                if m:
                    captured_key = m[0]
                    print(f"[{email}] [NET] Key tertangkap dari API: {captured_key[:15]}...", flush=True)
        except Exception:
            pass

    page.on("response", on_response)

    # Klik tombol Create API key
    create_btn = page.locator("button:has-text('Create API key')").last
    if not await create_btn.count():
        create_btn = page.locator("button:has-text('Create key')").first

    if not await create_btn.count():
        print(f"[{email}] [-] Tombol Create API key tidak ditemukan di halaman", flush=True)
        return None

    await create_btn.evaluate("el => el.click()")
    await asyncio.sleep(2)

    # Isi input dialog
    dialog_inp = page.locator("[role='dialog'] input").first
    if await dialog_inp.count():
        key_name = email.split("@")[0]
        await dialog_inp.click()
        await page.keyboard.type(key_name, delay=25)
        await asyncio.sleep(1)

    # Klik Generate Key
    gen_btn = page.locator("[role='dialog'] button:has-text('Generate Key')").first
    if await gen_btn.count():
        await gen_btn.click()
        print(f"[{email}] [+] Generate Key diklik, menunggu respons...", flush=True)
        await asyncio.sleep(4)

    # Coba tombol Copy di dialog
    if not captured_key:
        copy_btn = page.locator('[role="dialog"] button:has-text("Copy"), [role="dialog"] button[aria-label*="Copy"]').first
        if await copy_btn.count():
            await copy_btn.click()
            await asyncio.sleep(1)
            try:
                cb = await page.evaluate("navigator.clipboard.readText()")
                if cb and cb.strip().startswith("sk-"):
                    captured_key = cb.strip()
                    print(f"[{email}] [CLIPBOARD] Key disalin: {captured_key[:15]}...", flush=True)
            except Exception:
                pass

    if not captured_key:
        # Coba input value
        val_in = page.locator('[role="dialog"] input[value^="sk-"]').first
        if await val_in.count():
            captured_key = await val_in.get_attribute("value")

    return captured_key


async def process_account(acc: Dict[str, str], proxy: str, sem: asyncio.Semaphore) -> tuple:
    email = acc["email"]
    async with sem:
        print(f"\n=== [Qwen] {email} ===", flush=True)
        try:
            async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                                     proxy={"server": proxy,
                                            "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as browser:
                page = await browser.new_page()
                try:
                    await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
                except Exception:
                    pass

                logged = await ensure_logged_in(page, acc)
                if not logged:
                    print(f"[{email}] [-] Gagal login QwenCloud", flush=True)
                    return (email, "login-failed")

                print(f"[{email}] [+] Berhasil login QwenCloud", flush=True)
                key = await create_or_get_api_key(page, email)
                if key:
                    print(f"[{email}] => SUCCESS: {key[:15]}...", flush=True)
                    with open(KEYS_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{email}|{key}\n")
                    return (email, "success")
                else:
                    print(f"[{email}] => key-extract-failed", flush=True)
                    return (email, "key-extract-failed")
        except Exception as e:
            print(f"[{email}] [-] EXCEPTION: {str(e)[:150]}", flush=True)
            return (email, f"error:{str(e)[:50]}")


async def main():
    accounts_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RES_DIR, "agy_accounts_valid.txt")

    # Muat akun yang sudah pernah dapat key agar tidak duplikat
    done_emails = set()
    if os.path.exists(KEYS_FILE):
        for line in open(KEYS_FILE, encoding="utf-8-sig"):
            if "|" in line:
                done_emails.add(line.strip().split("|")[0].lower())

    accounts = []
    for line in open(accounts_file, encoding="utf-8-sig"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        email, pwd = line.split("|", 1)
        if email.strip().lower() in done_emails:
            continue
        accounts.append({"email": email.strip(), "password": pwd.strip()})

    print(f"[i] Total akun siap diproses: {len(accounts)} (sudah ada key: {len(done_emails)})", flush=True)
    if not accounts:
        print("[i] Semua akun sudah memiliki key!")
        return

    proxy = os.environ.get("AGY_PROXY", "socks5://127.0.0.1:1080")
    workers = int(os.environ.get("AGY_WORKERS", "3"))
    print(f"[i] Proxy: {proxy} | Workers: {workers}", flush=True)
    sem = asyncio.Semaphore(workers)

    results = []
    tasks = [asyncio.ensure_future(process_account(acc, proxy, sem)) for acc in accounts]
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        with open(os.path.join(RES_DIR, "_qwen_results.json"), "w") as jf:
            json.dump(results, jf, indent=2)

    print("\n=== REKAP AKHIR QWEN ===", flush=True)
    ok_count = sum(1 for _, s in results if s == "success")
    print(f"  Berhasil : {ok_count}/{len(results)}", flush=True)
    fail_count = len(results) - ok_count
    print(f"  Gagal    : {fail_count}/{len(results)}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
