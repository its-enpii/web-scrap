"""Cek halaman custom provider thebai: jumlah koneksi & struktur modal Add."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        for slug in ["thebai", "bai"]:
            await page.goto(f"https://ai-omni.enpiistudio.com/dashboard/providers/{slug}", wait_until="load", timeout=30000)
            await page.wait_for_timeout(5000)
            try:
                await page.wait_for_function("() => /connections/.test(document.body.innerText)", timeout=15000)
            except Exception:
                pass
            txt = await page.evaluate("document.body.innerText")
            head = txt[:400].replace("\n", " | ")
            m = re.search(r"(\d+)\s+connections", txt)
            print(f"=== {slug}: connections={m.group(1) if m else 'n/a'}", flush=True)
            print("   HEAD:", head[:300], flush=True)
            open(f"/root/projects/web-scrap/results/_prov_{slug}.txt", "w").write(txt)
            # cek apakah 174 user_ juga muncul di slug ini
            users = set(re.findall(r"user_[A-Za-z0-9]{12}", txt))
            print(f"   user_ di halaman 1: {len(users)}", flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_thebai.png", full_page=True)
asyncio.run(main())
