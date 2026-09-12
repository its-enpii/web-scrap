"""Ambil URL otorisasi (Step 1) dari modal agy via input value / clipboard / href."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/agy"


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(URL, wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)
        await page.locator("button:has-text('Add')").first.click(force=True)
        await page.wait_for_timeout(2500)
        modal = page.locator("div.fixed.inset-0.z-50")
        await modal.locator("button:has-text('I understand, continue')").first.click(force=True)
        await page.wait_for_timeout(3500)
        # input values
        vals = await modal.locator("input").evaluate_all("els => els.map(e=>({t:e.type,v:e.value}))")
        print("INPUT VALUES:", flush=True)
        for v in vals:
            print("  ", v, flush=True)
        # coba klik Copy lalu baca clipboard
        try:
            await modal.locator("button:has-text('Copy')").first.click(force=True)
            await page.wait_for_timeout(1000)
            clip = await page.evaluate("navigator.clipboard.readText()")
            print("CLIPBOARD:", clip[:200], flush=True)
        except Exception as e:
            print("clipboard gagal:", str(e)[:100], flush=True)
        await page.keyboard.press("Escape")
asyncio.run(main())
