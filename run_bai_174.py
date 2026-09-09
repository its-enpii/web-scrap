"""One-off runner: bulk add 174 BAI keys dari bai_174_accounts_1.json ke AI-Omni."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

KEYS_FILE = os.path.join(B.RESULTS_DIR, "keys_bai_174.txt")
DASH = "https://ai-omni.enpiistudio.com/dashboard/providers/bai"


async def close_leftover_modals(page):
    """Tutup modal yang masih terbuka sebelum klik Add berikutnya."""
    for _ in range(3):
        if not await page.locator("div.fixed.inset-0.z-50").count():
            return
        try:
            btn = page.locator("div.fixed.inset-0.z-50 button:has-text('Cancel'), "
                               "div.fixed.inset-0.z-50 button:has-text('Close'), "
                               "div.fixed.inset-0.z-50 button[aria-label='Close']").first
            if await btn.count():
                await btn.click(force=True, timeout=5000)
            else:
                await page.keyboard.press("Escape")
        except Exception:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(1200)
    await page.reload(wait_until="load")
    await page.wait_for_timeout(4000)


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return m.group(1) if m else "n/a"


async def bulk_add_bai(page, entries, chunk=50):
    for i in range(0, len(entries), chunk):
        part = entries[i:i + chunk]
        await close_leftover_modals(page)
        add_btn = page.locator("button:has-text('Add')").first
        await add_btn.click(force=True, timeout=15000)
        await page.wait_for_timeout(2500)
        bulk_tab = page.locator("button:has-text('Bulk Add'), [role='tab']:has-text('Bulk Add')").first
        await bulk_tab.click(force=True, timeout=15000)
        await page.wait_for_timeout(1500)
        ta = page.locator("div.fixed.inset-0.z-50 textarea").last
        payload = "\n".join(f"{n}|{k}" for n, k in part)
        await ta.fill(payload)
        await page.wait_for_timeout(800)
        add_all = page.locator("button:has-text('Add All Keys')").first
        await add_all.click(force=True, timeout=15000)
        # tunggu modal tertutup sendiri = import selesai
        for _ in range(30):
            await page.wait_for_timeout(2000)
            if not await page.locator("div.fixed.inset-0.z-50").count():
                break
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("document.body.innerText")
        print(f"[+] chunk {i+1}-{i+len(part)} dari {len(entries)} — connections: {conn_count(txt)}", flush=True)


async def main():
    entries = B.read_keys(KEYS_FILE)
    print(f"[i] key valid dibaca: {len(entries)}")
    assert len(entries) == 174, "jumlah key tidak 174 — berhenti"
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login AI-Omni sukses", flush=True)
        await page.goto(DASH, wait_until="load", timeout=30000)
        await page.wait_for_timeout(4000)
        await close_leftover_modals(page)
        txt = await page.evaluate("document.body.innerText")
        print("[i] BAI connections SEBELUM:", conn_count(txt), flush=True)
        await bulk_add_bai(page, entries)
        await page.reload(wait_until="load")
        await page.wait_for_timeout(5000)
        txt = await page.evaluate("document.body.innerText")
        print("[+] BAI connections SESUDAH:", conn_count(txt), flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_after_174.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
