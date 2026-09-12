"""Probe modal agy step-2: setelah dismiss warning, apa isi modal (device link? callback paste?)."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/agy"


async def dump_modal(modal, tag):
    try:
        mtxt = await modal.inner_text()
    except Exception:
        mtxt = "(modal hilang)"
    open(f"/root/projects/web-scrap/results/_agy_modal_{tag}.txt", "w").write(mtxt)
    print(f"=== MODAL {tag} ===", flush=True)
    print(mtxt[:1400], flush=True)
    btns = [b.strip() for b in await modal.locator("button, a").all_inner_texts() if b.strip()]
    print("TOMBOL:", btns[:25], flush=True)
    hrefs = await modal.locator("a").evaluate_all("els => els.map(e=>e.href)")
    print("HREF:", [h for h in hrefs if h][:10], flush=True)
    inputs = await modal.locator("input, textarea").evaluate_all(
        "els => els.map(e=>({tag:e.tagName, t:e.type, ph:e.placeholder}))")
    print("INPUTS:", inputs, flush=True)


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(URL, wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)
        add_btn = page.locator("button:has-text('Add')").first
        try:
            await add_btn.click(timeout=20000)
        except Exception:
            await add_btn.click(force=True)
        await page.wait_for_timeout(2500)
        modal = page.locator("div.fixed.inset-0.z-50")
        # step1: warning
        cont = modal.locator("button:has-text('I understand, continue')").first
        if await cont.count():
            # centang checkbox don't show again? tidak perlu; langsung continue
            await cont.click(force=True)
            await page.wait_for_timeout(3500)
        await dump_modal(modal, "step2")
        await page.screenshot(path="/root/projects/web-scrap/results/_agy_modal2.png", full_page=True)
        await page.keyboard.press("Escape")
asyncio.run(main())
