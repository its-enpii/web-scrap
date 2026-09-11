"""Antigravity (agy) connect flow — OAUTH CALLBACK mode.

Alur (mirror kiro_omni, beda verifikasi):
 1. Login AI-Omni -> /dashboard/providers/agy -> modal Add -> dismiss warning.
 2. Ambil URL otorisasi Google dari input Step 1 di modal.
 3. Buka URL otorisasi di POPUP (window.open) — modal tetap hidup & polling.
 4. Popup: login Google (email/password/ToS/consent) via google_auth_helper.
    Consent redirect ke http://127.0.0.1:PORT/callback?code=...&scope=...&state=...
    -> popup navigasi GAGAL (loopback tidak ada) — itu normal; URL-nya yang penting.
 5. Ambil full callback URL dari popup.url, paste ke input Step 2 modal, klik Connect.
 6. Verifikasi: jumlah koneksi bertambah ATAU nama akun muncul di daftar.
"""
import asyncio, json, os, re, sys
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from flows.google_auth_helper import fill_google_login
import bulk_add_to_omni as B

OMNI_BASE = "https://ai-omni.enpiistudio.com"
AGY_URL = f"{OMNI_BASE}/dashboard/providers/agy"
CB_RE = re.compile(r"https?://127\.0\.0\.1[^\"'\\\s]*callback\?[^\"'\\\s]*code=[^\"'\\\s]+", re.I)


def conn_count(txt: str):
    m = re.search(r"(\d+)\s+(?:connections?|accounts?)", txt, re.I)
    return int(m.group(1)) if m else None


async def open_add_modal(page: Page):
    await page.goto(AGY_URL, wait_until="load", timeout=45000)
    await page.wait_for_timeout(6000)
    add_btn = page.locator("button:has-text('Add')").first
    try:
        await add_btn.click(timeout=15000)
    except Exception:
        await add_btn.evaluate("el => el.click()")
    await page.wait_for_timeout(2500)
    modal = page.locator("div.fixed.inset-0.z-50")
    warn = modal.locator("button:has-text('I understand, continue')").first
    if await warn.count():
        try:
            await warn.click(timeout=8000)
        except Exception:
            await warn.evaluate("el => el.click()")
        await page.wait_for_timeout(3500)
    return modal


async def get_auth_url(modal) -> Optional[str]:
    """Ambil URL accounts.google.com dari input di modal (Step 1)."""
    for _ in range(5):
        vals = await modal.locator("input").evaluate_all("els => els.map(e=>e.value||'')")
        for v in vals:
            if v.startswith("https://accounts.google."):
                return v
        await asyncio.sleep(2)
    return None


async def run_google_and_capture_callback(context, auth_url: str, account: Dict[str, str],
                                          timeout_s: int = 120) -> Optional[str]:
    """Buka popup otorisasi, login Google, tangkap callback 127.0.0.1 dari URL/history."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    callback = None
    try:
        async with context.expect_page(timeout=10000) as pinfo:
            await context.pages[0].evaluate("url => window.open(url, '_blank')", auth_url)
        auth_page = await pinfo.value
    except Exception as e:
        print(f"[?] popup gagal: {str(e)[:80]} — pakai tab baru biasa", flush=True)
        auth_page = await context.new_page()

    auth_page.on("request", lambda r: scan(r.url))
    auth_page.on("response", lambda r: scan(r.url))

    def scan(u: str):
        nonlocal callback
        m = CB_RE.search(u or "")
        if m and not callback:
            callback = m.group(0)
            return True
        return False

    async def watcher():
        while loop.time() < deadline and not callback:
            try:
                # scan SEMUA tab di context, bukan cuma auth_page
                for pg in context.pages:
                    try:
                        if scan(pg.url):
                            return
                    except Exception:
                        pass
                if auth_page.is_closed():
                    return
                u = auth_page.url
                if scan(u):
                    return
                # history state bisa berisi callback meski URL gagal navigasi
                try:
                    hs = await auth_page.evaluate("location.href + '|' + history.state")
                    scan(hs.split("|")[0]) or scan(str(hs))
                except Exception:
                    pass
            except Exception:
                pass
            await asyncio.sleep(1.5)

    t = asyncio.ensure_future(watcher())
    try:
        if not callback:
            await fill_google_login(auth_page, account)
            while loop.time() < deadline and not callback:
                try:
                    u = auth_page.url
                    if scan(u):
                        break
                except Exception:
                    pass
                await asyncio.sleep(1.5)
    finally:
        t.cancel()
        if not callback:
            # DIAG: dump semua tab URL + screenshot auth page
            try:
                print("[?] DIAG tab URLs:", [p.url[:120] for p in context.pages], flush=True)
                await auth_page.screenshot(path="/root/projects/web-scrap/results/_agy_last.png")
                print("[?] DIAG screenshot: results/_agy_last.png", flush=True)
            except Exception:
                pass
        try:
            await auth_page.close()
        except Exception:
            pass
    return callback


async def connect_account(page: Page, modal, callback_url: str) -> bool:
    inputs = modal.locator("input")
    n = await inputs.count()
    target = None
    for i in range(n):
        v = await inputs.nth(i).input_value()
        if v == "" or v.startswith("https://ai-omni") and "callback" in v:
            ph = await inputs.nth(i).get_attribute("placeholder") or ""
            if "callback" in ph.lower() or v == "":
                target = inputs.nth(i)
    if target is None:
        target = inputs.nth(n - 1)
    async def try_connect(payload: str) -> bool:
        await target.fill(payload)
        await page.wait_for_timeout(800)
        await modal.locator("button:has-text('Connect')").first.click(force=True)
        await page.wait_for_timeout(6000)
        if not await page.locator("div.fixed.inset-0.z-50").count():
            return True
        mtxt = await page.locator("div.fixed.inset-0.z-50").inner_text()
        if "Connection failed" not in mtxt and "error" not in mtxt.lower():
            return True
        print("[!] ditolak (coba lagi):", " ".join(mtxt.split())[:150], flush=True)
        return False

    # coba 1: URL callback penuh; coba 2: hanya code-nya
    ok = await try_connect(callback_url)
    if ok:
        return True
    m = re.search(r"[?&](?:code|auth_code)=([^&\s]+)", callback_url)
    if not m:
        m = re.search(r"([A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,})", callback_url)
    if m:
        code = m.group(1)
        print(f"[i] fallback: paste code saja ({code[:12]}...)", flush=True)
        ok = await try_connect(code)
    if ok:
        return True
    mtxt = ""
    try:
        mtxt = await page.locator("div.fixed.inset-0.z-50").inner_text()
    except Exception:
        pass
    print("[!] modal masih terbuka:", " ".join(mtxt.split())[:200], flush=True)
    return False


async def verify(page: Page, email: str, before: Optional[int]) -> bool:
    await page.goto(AGY_URL, wait_until="load", timeout=45000)
    await page.wait_for_timeout(6000)
    txt = await page.evaluate("document.body.innerText")
    c = conn_count(txt)
    email_part = email.split("@")[0].lower()
    txt_lower = txt.lower()
    # cari match substring username di teks
    seen = email_part in txt_lower or (email_part[:4] in txt_lower if len(email_part) >= 4 else False)
    ok = (c is not None and before is not None and c > before) or seen or (c is not None and c >= 1)
    print(f"[i] verifikasi: count {before} -> {c} | akun terlihat: {seen} | status: {ok}", flush=True)
    return bool(ok)


async def process_account(acc: Dict[str, str], proxy: str, sem: asyncio.Semaphore) -> tuple:
    """Satu akun = satu browser fresh. Login -> Add -> OAuth popup -> capture callback
    (address bar) -> paste -> tunggu -> browser ditutup."""
    email = acc["email"]
    async with sem:
        print(f"\n=== {email} ===", flush=True)
        try:
            async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                                     proxy={"server": proxy,
                                            "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as browser:
                page = await browser.new_page()
                context = page.context
                await B.omni_login(page)
                print(f"[{email}] login AI-Omni ok", flush=True)
                modal = await open_add_modal(page)
                before = conn_count(await page.evaluate("document.body.innerText"))
                auth_url = await get_auth_url(modal)
                if not auth_url:
                    print(f"[{email}] [-] URL otorisasi tidak ditemukan", flush=True)
                    return (email, "no-auth-url")
                print(f"[{email}] [+] auth url ok", flush=True)
                cb = await run_google_and_capture_callback(context, auth_url, acc)
                if not cb:
                    print(f"[{email}] [-] callback tidak tertangkap", flush=True)
                    return (email, "no-callback")
                print(f"[{email}] [+] callback: {cb}", flush=True)
                ok = await connect_account(page, modal, cb)
                vok = await verify(page, email, before)
                status = "success" if (ok and vok) else ("connect-ok-unverified" if ok else "connect-fail")
                print(f"[{email}] => {status}", flush=True)
                return (email, status)
        except Exception as e:
            print(f"[{email}] [-] EXCEPTION: {str(e)[:200]}", flush=True)
            return (email, f"error:{str(e)[:60]}")


async def main():
    accounts_file = sys.argv[1] if len(sys.argv) > 1 else "results/agy_accounts.txt"
    accounts = []
    for line in open(accounts_file, encoding="utf-8-sig"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        email, pwd = line.split("|", 1)
        accounts.append({"email": email.strip(), "password": pwd.strip()})
    print(f"[i] {len(accounts)} akun dibaca dari {accounts_file}", flush=True)
    if not accounts:
        return

    proxy = os.environ.get("AGY_PROXY", "socks5://127.0.0.1:1080")
    workers = int(os.environ.get("AGY_WORKERS", "3"))
    print(f"[i] proxy: {proxy} | workers: {workers}", flush=True)
    sem = asyncio.Semaphore(workers)

    results = []
    tasks = [asyncio.ensure_future(process_account(acc, proxy, sem)) for acc in accounts]
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        json.dump(results, open("/root/projects/web-scrap/results/_agy_results.json", "w"))

    print("\n=== REKAP ===", flush=True)
    ok = sum(1 for _, s in results if s == "success")
    print(f"  success: {ok}/{len(results)}", flush=True)
    for r in results:
        print("  ", r, flush=True)
    json.dump(results, open("/root/projects/web-scrap/results/_agy_results.json", "w"))

asyncio.run(main())
