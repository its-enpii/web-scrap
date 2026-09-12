"""Diagnosa alur Google agy: log semua URL yang dilewati popup sampai 90s."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
from flows.google_auth_helper import fill_google_login
import bulk_add_to_omni as B
from agy_connect import open_add_modal, get_auth_url

ACCOUNT = {"email": "HowardSegura@grmill.com", "password": "qwertyui"}


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        context = page.context
        await B.omni_login(page)
        modal = await open_add_modal(page)
        auth_url = await get_auth_url(modal)
        print("auth url:", auth_url[:80], flush=True)
        async with context.expect_page(timeout=10000) as pinfo:
            await page.evaluate("url => window.open(url, '_blank')", auth_url)
        auth_page = await pinfo.value
        seen = []
        async def on_nav(f):
            u = f.url
            if not seen or seen[-1] != u:
                seen.append(u)
                print("NAV:", u[:160], flush=True)
        auth_page.on("framenavigated", on_nav)
        await fill_google_login(auth_page, ACCOUNT)
        # polling 60s
        for i in range(40):
            await asyncio.sleep(1.5)
            try:
                u = auth_page.url
                if not seen or seen[-1] != u:
                    seen.append(u)
                    print("URL:", u[:180], flush=True)
            except Exception:
                print("page closed", flush=True)
                break
        print("=== SEMUA URL ===", flush=True)
        for u in seen:
            print("  ", u[:200], flush=True)
        # screenshot kondisi terakhir
        try:
            await auth_page.screenshot(path="/root/projects/web-scrap/results/_agy_diag_last.png", full_page=True)
        except Exception:
            pass
asyncio.run(main())
