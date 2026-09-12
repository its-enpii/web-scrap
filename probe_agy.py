"""Probe provider Antigravity (agy): halaman + modal Add + link/popup OAuth."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/agy"
popups = []


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(URL, wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)
        txt = await page.evaluate("document.body.innerText")
        open("/root/projects/web-scrap/results/_agy_page.txt", "w").write(txt)
        m = re.search(r"(\d+)\s+connections", txt)
        print("connections:", m.group(1) if m else "?", flush=True)
        print("HEAD:", txt[:600].replace("\n", " | "), flush=True)

        # buka modal Add
        add_btn = page.locator("button:has-text('Add')").first
        await add_btn.click(force=True, timeout=15000)
        await page.wait_for_timeout(3000)
        modal = page.locator("div.fixed.inset-0.z-50")
        if await modal.count():
            mtxt = await modal.inner_text()
            open("/root/projects/web-scrap/results/_agy_modal.txt", "w").write(mtxt)
            print("=== MODAL (head) ===", flush=True)
            print(mtxt[:1200], flush=True)
            # tombol/link di dalam modal
            btns = await modal.locator("button, a").all_inner_texts()
            print("TOMBOL/LINK:", [b.strip() for b in btns if b.strip()][:20], flush=True)
            hrefs = await modal.locator("a").evaluate_all("els => els.map(e=>e.href)")
            print("HREF modal:", hrefs[:10], flush=True)
            # input fields?
            inputs = await modal.locator("input").evaluate_all(
                "els => els.map(e=>({t:e.type, ph:e.placeholder, name:e.name}))")
            print("INPUTS:", inputs, flush=True)
        else:
            print("tidak ada modal .fixed.inset-0.z-50", flush=True)
            btns = await page.locator("button").all_inner_texts()
            print("semua tombol:", [b.strip() for b in btns if b.strip()][:30], flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_agy_probe.png", full_page=True)

asyncio.run(main())
