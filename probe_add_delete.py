"""Step 1: probe modal Add di custom provider 'thebai' + mekanisme delete 1 baris di 'bai'."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)

        # --- A. modal Add di thebai ---
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers/thebai", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        add_btn = page.locator("button:has-text('Add')").first
        await add_btn.click(force=True, timeout=15000)
        await page.wait_for_timeout(2500)
        modal = page.locator("div.fixed.inset-0.z-50")
        mtxt = await modal.inner_text()
        print("=== MODAL THEBAI ===", flush=True)
        print(mtxt[:1500], flush=True)
        tabs = await modal.locator("button:has-text('Bulk'), [role='tab']").all_inner_texts()
        print("TABS:", tabs, flush=True)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1500)

        # --- B. delete test: 1 baris user_ di bai ---
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers/bai", wait_until="load", timeout=30000)
        await page.wait_for_function("() => /user_[A-Za-z0-9]{12}/.test(document.body.innerText)", timeout=30000)
        await page.wait_for_timeout(2000)
        target = "user_AMG4GfEGp0Iu"
        row = page.locator(f"text={target}").first
        cont = await row.evaluate_handle("e => e.closest('div[class*=border]')")
        del_btn = cont.locator("button:has-text('delete')")
        n = await del_btn.count()
        print(f"delete buttons dalam baris {target}:", n, flush=True)
        await del_btn.first.click(force=True)
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("document.body.innerText")
        print("确认后 header:", re.findall(r"\d+\s+connections|Delete|confirm|Are you sure", txt)[:6], flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_del_probe.png", full_page=True)
        # kalau muncul modal konfirmasi, tekan konfirm
        conf = page.locator("div.fixed.inset-0.z-50 button").filter(has_text=re.compile("^(Delete|Confirm|Yes|Hapus)$", re.I))
        if await conf.count():
            print("ADA modal konfirmasi — klik", flush=True)
            await conf.first.click(force=True)
            await page.wait_for_timeout(3000)
            txt = await page.evaluate("document.body.innerText")
            m = re.search(r"(\d+)\s+connections", txt)
            print("connections setelah hapus 1:", m.group(1) if m else "n/a", flush=True)
        else:
            m = re.search(r"(\d+)\s+connections", txt)
            print("tanpa modal; connections:", m.group(1) if m else "n/a", flush=True)
asyncio.run(main())
