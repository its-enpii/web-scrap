"""
Bulk add semua API key hasil panen ke AI-Omni per provider.
Pakai tab 'Bulk Add' di modal Add — 1 textarea, format 'name|apiKey' per baris,
lalu klik 'Add All Keys'.

Usage:
    .venv/bin/python bulk_add_to_omni.py                 # semua provider yang ada filenya
    .venv/bin/python bulk_add_to_omni.py opencode_zen    # provider tertentu saja
"""
import asyncio
import os
import sys

from camoufox.async_api import AsyncCamoufox

OMNI_URL = os.getenv("OMNI_URL", "https://ai-omni.enpiistudio.com/login")
OMNI_PASSWORD = os.getenv("OMNI_PASSWORD", "its.enpii-118")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# slug dashboard -> nama file key
PROVIDERS = {
    "opencode-zen": "keys_opencode_zen.txt",
    "tokenrouter": "keys_tokenrouter.txt",
    "openrouter": "keys_openrouter.txt",
    "qwen-cloud": "keys_qwencloud.txt",
    "unorouter": "keys_unorouter.txt",
    "bai": "keys_bai.txt",
    "kiro": "keys_kiro_omni.txt",  # placeholder; di-skip otomatis kalau isinya bukan key
}


def read_keys(path: str):
    """Parse file keys_*.txt -> list of (name, key). Skip placeholder."""
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        email, key = line.split("|", 1)
        key = key.strip()
        if not key or "..." in key or key == "connected_via_device_oauth":
            continue  # placeholder / masked
        if not key.startswith("sk-"):
            continue
        out.append((email, key))
    return out


async def omni_login(page):
    for attempt in range(4):
        try:
            await page.goto(OMNI_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            if "/dashboard" in page.url:
                return
            pwd = page.locator("input[type='password']").first
            await pwd.wait_for(state="visible", timeout=15000)
            await pwd.fill(OMNI_PASSWORD)
            await pwd.press("Enter")
            await page.wait_for_url("**/dashboard**", timeout=30000)
            await page.wait_for_timeout(2000)
            return
        except Exception as e:
            print(f"[!] login percobaan {attempt+1} gagal: {str(e)[:80]}", flush=True)
            await page.wait_for_timeout(5000)
    raise RuntimeError("login AI-Omni gagal 4x")


async def bulk_add_provider(page, slug: str, entries):
    """Tambah semua (name, key) ke provider slug via tab Bulk Add. Return (added, error)."""
    await page.goto(f"https://ai-omni.enpiistudio.com/dashboard/providers/{slug}",
                    wait_until="load", timeout=30000)
    await page.wait_for_timeout(3500)

    # Buka modal Add
    add_btn = page.locator("button:has-text('Add')").first
    await add_btn.click()
    await page.wait_for_timeout(2000)

    # Qwen Cloud: modal minta pilih region dulu (Beijing / Global)
    try:
        global_btn = page.locator("button:has-text('Global')").first
        if await global_btn.is_visible(timeout=2000):
            await global_btn.click()
            await page.wait_for_timeout(2500)
            print("[*] Region Global dipilih.")
    except Exception:
        pass

    # Pindah ke tab Bulk Add
    bulk_tab = page.locator("button:has-text('Bulk Add'), [role='tab']:has-text('Bulk Add')").first
    await bulk_tab.click()
    await page.wait_for_timeout(1500)

    # Isi textarea: 'name|key' per baris
    ta = page.locator("textarea[placeholder*='name1|']").first
    if not await ta.is_visible():
        ta = page.locator("textarea").last
    payload = "\n".join(f"{name}|{key}" for name, key in entries)
    await ta.fill(payload)
    await page.wait_for_timeout(800)

    # Klik 'Add All Keys'
    add_all = page.locator("button:has-text('Add All Keys')").first
    await add_all.click()
    await page.wait_for_timeout(6000)  # tunggu proses import

    # Verifikasi: baca jumlah koneksi di header provider
    txt = await page.evaluate("document.body.innerText")
    import re
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def main(only=None):
    targets = {k: v for k, v in PROVIDERS.items() if not only or k in only or v.replace('keys_', '').replace('.txt', '') in only}
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await omni_login(page)
        print(f"[+] Login AI-Omni sukses.")
        for slug, fname in targets.items():
            entries = read_keys(os.path.join(RESULTS_DIR, fname))
            if not entries:
                print(f"[i] {slug}: tidak ada key valid di {fname} — skip.")
                continue
            print(f"[*] {slug}: bulk add {len(entries)} keys...")
            try:
                conn = await bulk_add_provider(page, slug, entries)
                print(f"[+] {slug}: SELESAI — total koneksi sekarang: {conn}")
            except Exception as e:
                print(f"[-] {slug}: gagal — {str(e)[:120]}")
            await page.wait_for_timeout(2000)


if __name__ == "__main__":
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    asyncio.run(main(only or None))
