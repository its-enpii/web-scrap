"""Cline connect flow — OAuth via AuthKit (login Google) -> callback ke modal AI-Omni.

Alur (mirror agy_connect, beda halaman otorisasi):
 1. Login AI-Omni -> /dashboard/providers/cline -> modal Add -> dismiss warning.
 2. Step 1 modal berisi URL https://api.cline.bot/api/v1/auth/authorize?...
    (redirect_uri = https://ai-omni.enpiistudio.com/callback — HTTPS, BUKAN 127.0.0.1).
 3. Buka URL di POPUP. Redirect: authkit.cline.bot -> klik "Continue with Google"
    -> login Google (google_auth_helper) -> consent -> api.cline.bot/api/v1/auth/callback
    -> AI-OMNI CALLBACK (halaman error "cannot connect" — normal, URL-nya yang penting).
 4. Capture dari: URL popup / tab mana pun yang cocok callback_url dengan code=
    ATAU halaman cline "code copied" -> baca clipboard.
 5. Paste ke input Step 2 modal (placeholder 'code#state or /callback?code=...'), Connect.
 6. Verifikasi: jumlah "N connections" di halaman cline bertambah.

Usage:
    AGY_PROXY=socks5://127.0.0.1:1080 AGY_WORKERS=2 .venv/bin/python cline_connect.py results/cline_accounts.txt
"""
import asyncio, json, os, re, sys
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from flows.google_auth_helper import fill_google_login
import bulk_add_to_omni as B

OMNI_BASE = "https://ai-omni.enpiistudio.com"
CLINE_URL = f"{OMNI_BASE}/dashboard/providers/cline"
# callback_url tujuan (HTTPS ai-omni) — halaman error tapi URL terbaca address bar
CB_RE = re.compile(r"https?://ai-omni\.enpiistudio\.com/callback\?[^\s\"'\\]*code=[^\s\"'\\]+", re.I)
# singgahan api.cline.bot/api/v1/auth/callback juga membawa code
CB_API_RE = re.compile(r"https?://api\.cline\.bot/api/v1/auth/callback\?[^\s\"'\\]*code=[^\s\"'\\]+", re.I)


def conn_count(txt: str):
    m = re.search(r"(\d+)\s+connections?", txt, re.I)
    return int(m.group(1)) if m else None


async def open_add_modal(page: Page):
    await page.goto(CLINE_URL, wait_until="load", timeout=45000)
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
    for _ in range(5):
        vals = await modal.locator("input").evaluate_all("els => els.map(e=>e.value||'')")
        for v in vals:
            if v.startswith("https://api.cline.bot/"):
                return v
        await asyncio.sleep(2)
    return None


async def _clipboard_route(page: Page) -> Optional[str]:
    """Kalau cline mendarat di halaman 'authorized' (bukan redirect callback),
    kode biasanya bisa disalin lewat tombol copy — baca clipboard."""
    try:
        txt = (await page.evaluate("document.body.innerText") or "").lower()
    except Exception:
        return None
    if not any(k in txt for k in ("copy", "code", "authorized")):
        return None
    for sel in ("button:has-text('copy')", "[role='button']:has-text('copy')",
                "a:has-text('copy')", "button:has-text('Salin')"):
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=5000)
                await page.wait_for_timeout(1500)
                val = await page.evaluate("navigator.clipboard.readText()")
                if val and len(val.strip()) > 10:
                    print(f"[*] [Cline] clipboard: {val.strip()[:40]}...", flush=True)
                    return val.strip()
        except Exception:
            continue
    # alternatif: input readonly panjang berisi kode
    try:
        vals = await page.locator("input[readonly], textarea[readonly]").evaluate_all(
            "els => els.map(e=>e.value||'').filter(v=>v.length>20)")
        if vals:
            return vals[0]
    except Exception:
        pass
    return None


async def run_authkit_and_capture(context, auth_url: str, account: Dict[str, str],
                                  timeout_s: int = 150) -> Optional[str]:
    """Popup: authkit -> Continue with Google -> login -> callback. Return payload
    untuk Step 2 (URL callback penuh atau code#state)."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    captured = None

    def scan(u: str) -> bool:
        nonlocal captured
        for rx in (CB_RE, CB_API_RE):
            m = rx.search(u or "")
            if m and not captured:
                captured = m.group(0)
                return True
        return False

    try:
        async with context.expect_page(timeout=10000) as pinfo:
            await context.pages[0].evaluate("url => window.open(url, '_blank')", auth_url)
        auth_page = await pinfo.value
    except Exception:
        print("[?] [Cline] popup gagal — pakai tab baru", flush=True)
        auth_page = await context.new_page()

    auth_page.on("request", lambda r: scan(r.url))
    auth_page.on("response", lambda r: scan(r.url))

    try:
        await auth_page.goto(auth_url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass

    # 1. Tunggu authkit siap -> klik "Continue with Google" (tag <a>)
    for _ in range(20):
        try:
            g = auth_page.locator("a:has-text('Continue with Google'), button:has-text('Continue with Google')").first
            if await g.count() and await g.is_visible():
                await g.click(timeout=8000)
                print("[*] [Cline] Klik Continue with Google", flush=True)
                break
        except Exception:
            pass
        if scan(auth_page.url if not auth_page.is_closed() else ""):
            break
        await asyncio.sleep(1)

    # 2. Login Google bila muncul accounts.google
    async def watcher():
        while loop.time() < deadline and not captured:
            for pg in context.pages:
                try:
                    if scan(pg.url):
                        return
                except Exception:
                    pass
            try:
                if auth_page.is_closed():
                    return
                u = auth_page.url
                if scan(u):
                    return
                # halaman "selesai" tanpa redirect callback -> clipboard route
                if "accounts.google." not in u and "cline" in u:
                    code = await _clipboard_route(auth_page)
                    if code:
                        nonlocal_captured_set(code)
                        return
            except Exception:
                pass
            await asyncio.sleep(1.5)

    def nonlocal_captured_set(val):
        nonlocal captured
        captured = val

    t = asyncio.ensure_future(watcher())
    try:
        try:
            await asyncio.wait_for(
                auth_page.wait_for_url(re.compile(r"accounts\.google\."), timeout=30000),
                timeout=32)
        except Exception:
            pass
        if not captured:
            await fill_google_login(auth_page, account, timeout_ms=30000)
            while loop.time() < deadline and not captured:
                try:
                    if scan(auth_page.url):
                        break
                except Exception:
                    pass
                await asyncio.sleep(1.5)
    finally:
        t.cancel()
        if not captured:
            try:
                print("[?] [Cline] DIAG tabs:", [p.url[:120] for p in context.pages], flush=True)
                await auth_page.screenshot(path="results/_cline_last.png")
            except Exception:
                pass
        try:
            await auth_page.close()
        except Exception:
            pass
    return captured


def step2_payload(callback: str) -> list:
    """Varian payload untuk input Step 2, prioritas penuh -> code#state -> code."""
    out = [callback]
    m = re.search(r"[?&]code=([^&\s]+)", callback)
    if m:
        code = m.group(1)
        s = re.search(r"[?&]state=([^&\s]+)", callback)
        out.append(f"{code}#{s.group(1)}" if s else code)
    return out


async def connect_account(page: Page, modal, callback: str) -> bool:
    target = None
    inputs = modal.locator("input")
    for i in range(await inputs.count()):
        ph = (await inputs.nth(i).get_attribute("placeholder") or "").lower()
        if "callback" in ph or "code" in ph:
            target = inputs.nth(i)
            break
    if target is None:
        vals = await inputs.evaluate_all("els => els.map(e=>e.value||'')")
        empties = [i for i, v in enumerate(vals) if v == ""]
        if empties:
            target = inputs.nth(empties[-1])
    if target is None:
        print("[!] input Step 2 tidak ditemukan", flush=True)
        return False

    async def try_connect(payload: str) -> bool:
        await target.fill(payload)
        await page.wait_for_timeout(800)
        await modal.locator("button:has-text('Connect')").first.click(force=True)
        await page.wait_for_timeout(6000)
        m2 = page.locator("div.fixed.inset-0.z-50")
        if not await m2.count():
            return True
        mtxt = await m2.inner_text()
        if "failed" not in mtxt.lower() and "error" not in mtxt.lower():
            return True
        print("[!] ditolak:", " ".join(mtxt.split())[:150], flush=True)
        return False

    for payload in step2_payload(callback):
        if await try_connect(payload):
            return True
    return False


async def verify(page: Page, before: Optional[int]) -> bool:
    await page.goto(CLINE_URL, wait_until="load", timeout=45000)
    await page.wait_for_timeout(5000)
    c = conn_count(await page.evaluate("document.body.innerText"))
    ok = c is not None and before is not None and c > before
    print(f"[i] verifikasi connections: {before} -> {c} | ok: {ok}", flush=True)
    return bool(ok)


async def process_account(acc: Dict[str, str], proxy: str, sem: asyncio.Semaphore) -> tuple:
    email = acc["email"]
    async with sem:
        print(f"\n=== {email} ===", flush=True)
        try:
            async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                                     proxy={"server": proxy,
                                            "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as browser:
                page = await browser.new_page()
                context = page.context
                try:
                    await context.grant_permissions(
                        ["clipboard-read", "clipboard-write", "clipboard-events"])
                except Exception:
                    pass
                await B.omni_login(page)
                print(f"[{email}] login AI-Omni ok", flush=True)
                modal = await open_add_modal(page)
                before = conn_count(await page.evaluate("document.body.innerText"))
                auth_url = await get_auth_url(modal)
                if not auth_url:
                    print(f"[{email}] [-] URL otorisasi cline tidak ditemukan", flush=True)
                    return (email, "no-auth-url")
                cb = await run_authkit_and_capture(context, auth_url, acc)
                if not cb:
                    print(f"[{email}] [-] callback tidak tertangkap", flush=True)
                    return (email, "no-callback")
                print(f"[{email}] [+] callback: {cb[:120]}", flush=True)
                ok = await connect_account(page, modal, cb)
                vok = await verify(page, before)
                status = "success" if (ok and vok) else ("connect-ok-unverified" if ok else "connect-fail")
                print(f"[{email}] => {status}", flush=True)
                return (email, status)
        except Exception as e:
            print(f"[{email}] [-] EXCEPTION: {str(e)[:200]}", flush=True)
            return (email, f"error:{str(e)[:60]}")


async def main():
    accounts_file = sys.argv[1] if len(sys.argv) > 1 else "results/cline_accounts.txt"
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
    workers = int(os.environ.get("AGY_WORKERS", "2"))
    print(f"[i] proxy: {proxy} | workers: {workers}", flush=True)
    sem = asyncio.Semaphore(workers)

    results = []
    tasks = [asyncio.ensure_future(process_account(acc, proxy, sem)) for acc in accounts]
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        json.dump(results, open("results/_cline_results.json", "w"))

    print("\n=== REKAP ===", flush=True)
    ok = sum(1 for _, s in results if s == "success")
    print(f"  success: {ok}/{len(results)}", flush=True)
    json.dump(results, open("results/_cline_results.json", "w"))

asyncio.run(main())
