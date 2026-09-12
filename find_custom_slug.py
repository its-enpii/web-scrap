"""Cari slug custom provider 'bai' via DOM links di halaman providers."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers", wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)
        links = await page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a=>a.getAttribute('href')).filter(h=>h && h.includes('provider'))""")
        for l in sorted(set(links)):
            print("HREF", l, flush=True)
        # juga element clickable (mungkin div onclick) yang berisi teks BAI
        bai = page.locator("text=BAI").first
        parent = await bai.evaluate_handle("e => e.closest('a,div[class*=cursor],button')")
        info = await parent.evaluate("e => ({tag:e.tagName, href:e.getAttribute('href'), oc: !!e.onclick, cls: e.className.slice(0,80)})")
        print("BAI parent:", info, flush=True)
asyncio.run(main())
