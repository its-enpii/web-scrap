"""Inspect isi halaman radar-challenge/send dari cline/authkit."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
from flows.google_auth_helper import fill_google_login
import bulk_add_to_omni as B

AUTH_URL = ("https://api.cline.bot/api/v1/auth/authorize?client_type=extension"
            "&callback_url=https%3A%2F%2Fai-omni.enpiistudio.com%2Fcallback"
            "&redirect_uri=https%3A%2F%2Fai-omni.enpiistudio.com%2Fcallback")
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                             proxy={"server": "socks5://127.0.0.1:1080",
                                    "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as browser:
        page = await browser.new_page()
        await page.goto(AUTH_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        g = page.locator("a:has-text('Continue with Google')").first
        await g.click()
        await page.wait_for_timeout(3000)
        acc = {"email": "vlof@grmill.com", "password": "qwertyui"}
        await fill_google_login(page, acc, timeout_ms=30000)
        await page.wait_for_timeout(10000)
        print("URL SEKARANG:", page.url, flush=True)
        txt = await page.evaluate("document.body.innerText")
        open(f"{RES}/_radar_page.txt", "w").write(f"URL: {page.url}\n\n{txt}")
        print("==== RADAR PAGE TEXT ====", flush=True)
        print(txt, flush=True)
        html = await page.content()
        open(f"{RES}/_radar_page.html", "w").write(html)
        btns = await page.evaluate("""() => Array.from(document.querySelectorAll('button,a,input'))
            .map(b=>({t:(b.innerText||b.value||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().slice(0,60), tag:b.tagName, id:b.id, type:b.type||''}))
            .filter(x=>x.t||x.id)""")
        print("==== RADAR ELEMENTS ====", flush=True)
        for b in btns:
            print(b, flush=True)
        await page.screenshot(path=f"{RES}/_radar_page.png", full_page=True)

asyncio.run(main())
