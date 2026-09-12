"""Diagnosa halaman login AI-Omni: screenshot + DOM form + percobaan submit Enter."""
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox

OMNI_URL = "https://ai-omni.enpiistudio.com/login"
OMNI_PASSWORD = "its.enpii-118"

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await page.goto(OMNI_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        print("url:", page.url, flush=True)
        info = await page.evaluate("""() => ({
            forms: document.querySelectorAll('form').length,
            pwds: Array.from(document.querySelectorAll('input[type=password]')).map(i=>({ph:i.placeholder, dis:i.disabled})),
            btns: Array.from(document.querySelectorAll('button')).map(b=>({t:(b.innerText||'').slice(0,30), dis:b.disabled, ty:b.type})).slice(0,10),
            body: document.body.innerText.slice(0,500)
        })""")
        print("FORMS:", info['forms'], "PWD:", info['pwds'], flush=True)
        print("BTNS:", info['btns'], flush=True)
        print("BODY:", info['body'].replace(chr(10), ' | ')[:400], flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_login_diag.png", full_page=True)
        if info['pwds']:
            pwd = page.locator("input[type='password']").first
            await pwd.fill(OMNI_PASSWORD)
            await pwd.press("Enter")
            for i in range(20):
                await page.wait_for_timeout(1500)
                if "/dashboard" in page.url:
                    print("MASUK dashboard via Enter setelah", (i+1)*1.5, "s", flush=True)
                    break
            else:
                print("GAGAL masuk. url sekarang:", page.url, flush=True)
                print("body:", (await page.evaluate("document.body.innerText"))[:300].replace(chr(10), ' | '), flush=True)
                await page.screenshot(path="/root/projects/web-scrap/results/_login_fail.png", full_page=True)
asyncio.run(main())
