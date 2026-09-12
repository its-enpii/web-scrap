"""Probe modal Add provider agy: langkah-langkah, tombol, popup OAuth."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/agy"
popups = []


async def dump_modal(modal, tag):
    try:
        mtxt = await modal.inner_text()
    except Exception:
        mtxt = "(modal hilang)"
    open(f"/root/projects/web-scrap/results/_agy_modal_{tag}.txt", "w").write(mtxt)
    print(f"=== MODAL {tag} ===", flush=True)
    print(mtxt[:900], flush=True)
    btns = [b.strip() for b in await modal.locator("button, a").all_inner_texts() if b.strip()]
    print("TOMBOL:", btns[:25], flush=True)
    inputs = await modal.locator("input").evaluate_all(
        "els => els.map(e=>({t:e.type, ph:e.placeholder}))")
    print("INPUTS:", inputs, flush=True)


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        ctx = page.context
        ctx.on("page", lambda p: popups.append(p.url))
        await B.omni_login(page)
        await page.goto(URL, wait_until="load", timeout=30000)
        await page.wait_for_timeout(6000)
        add_btn = page.locator("button:has-text('Add')").first
        try:
            await add_btn.click(timeout=20000)
        except Exception:
            await add_btn.click(force=True)
        await page.wait_for_timeout(3500)
        modal = page.locator("div.fixed.inset-0.z-50")
        await dump_modal(modal, "step1")
        await page.screenshot(path="/root/projects/web-scrap/results/_agy_modal1.png", full_page=True)

        # coba cari tombol 'Sign in' / 'Google' / 'Connect' di modal
        for label in ["Sign in with Google", "Google", "Connect", "Sign in", "Add Account", "Next"]:
            loc = modal.locator(f"button:has-text('{label}'), a:has-text('{label}')")
            if await loc.count():
                print(f"[i] tombol '{label}' ADA", flush=True)
        print("popups terdeteksi:", popups, flush=True)
        await page.keyboard.press("Escape")
asyncio.run(main())
