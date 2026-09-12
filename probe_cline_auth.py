"""Probe halaman otorisasi Cline (api.cline.bot) — apa form login-nya?
Read-only: tidak submit kredensial."""
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox

AUTH_URL = ("https://api.cline.bot/api/v1/auth/authorize?client_type=extension"
            "&callback_url=https%3A%2F%2Fai-omni.enpiistudio.com%2Fcallback"
            "&redirect_uri=https%3A%2F%2Fai-omni.enpiistudio.com%2Fcallback")
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                             proxy={"server": "socks5://127.0.0.1:1080",
                                    "bypass": "localhost 127.0.0.1 .enpiistudio.com api.cline.bot"}) as browser:
        page = await browser.new_page()
        await page.goto(AUTH_URL, wait_until="load", timeout=60000)
        await page.wait_for_timeout(6000)
        print("FINAL URL:", page.url, flush=True)
        txt = await page.evaluate("document.body.innerText")
        open(f"{RES}/_cline_auth_page.txt", "w").write("URL: " + page.url + "\n\n" + txt)
        print("==== TEXT (2500) ====", flush=True)
        print(txt[:2500], flush=True)
        btns = await page.evaluate("""() => Array.from(document.querySelectorAll('button,a,input'))
            .map(b=>({t:(b.innerText||b.value||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().slice(0,60), tag:b.tagName, id:b.id, type:b.type||''}))
            .filter(x=>x.t||x.id)""")
        print("==== ELEMENTS ====", flush=True)
        for b in btns[:40]:
            print(b, flush=True)
        await page.screenshot(path=f"{RES}/_cline_auth_page.png", full_page=True)

asyncio.run(main())
