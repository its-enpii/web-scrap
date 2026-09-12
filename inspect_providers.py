"""Inspeksi: daftar provider default vs custom di AI-Omni dashboard."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        txt = await page.evaluate("document.body.innerText")
        open("/root/projects/web-scrap/results/_providers_page.txt", "w").write(txt)
        # tampilkan link ke halaman provider
        links = await page.evaluate("""() => Array.from(document.querySelectorAll('a[href*="providers"]')).map(a=>({h:a.getAttribute('href'), t:(a.innerText||'').replace(/\\s+/g,' ').slice(0,60)}))""")
        seen = set()
        for l in links:
            k = l['h']
            if k in seen: continue
            seen.add(k)
            print("LINK", k, "|", l['t'], flush=True)
        print("---- custom section text ----", flush=True)
        idx = txt.lower().find("custom")
        print(txt[max(0,idx-300):idx+1200] if idx >= 0 else "TIDAK ADA teks 'custom'", flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_providers_page.png", full_page=True)
asyncio.run(main())
