"""Migrasi: pindahkan 174 BAI key dari provider default 'bai' ke custom provider 'thebai'.

Langkah:
 1. Bulk add 174 key ke /dashboard/providers/thebai (tab Bulk Add, chunk 50).
 2. Verifikasi via enumerasi halaman: 174/174 user_ ada di thebai.
 3. Hapus semua koneksi user_* dari provider default 'bai' (sisakan 3 key grmill lama).
 4. Verifikasi akhir: bai = 3 connections (tanpa user_), thebai = 174.
"""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

BASE = "https://ai-omni.enpiistudio.com/dashboard/providers"
KEYS_FILE = os.path.join(B.RESULTS_DIR, "keys_bai_174.txt")


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def close_modals(page):
    for _ in range(3):
        if not await page.locator("div.fixed.inset-0.z-50").count():
            return
        try:
            btn = page.locator("div.fixed.inset-0.z-50 button:has-text('Cancel')").first
            if await btn.count():
                await btn.click(force=True, timeout=5000)
            else:
                await page.keyboard.press("Escape")
        except Exception:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(1200)


async def bulk_add(page, slug, entries, chunk=50):
    for i in range(0, len(entries), chunk):
        part = entries[i:i + chunk]
        await close_modals(page)
        await page.locator("button:has-text('Add')").first.click(force=True, timeout=15000)
        await page.wait_for_timeout(2500)
        modal = page.locator("div.fixed.inset-0.z-50")
        await modal.locator("button:has-text('Bulk Add')").first.click(force=True, timeout=15000)
        await page.wait_for_timeout(1500)
        ta = modal.locator("textarea").last
        await ta.fill("\n".join(f"{n}|{k}" for n, k in part))
        await page.wait_for_timeout(800)
        await modal.locator("button:has-text('Add All Keys')").first.click(force=True, timeout=15000)
        for _ in range(40):  # tunggu modal tertutup = import kelar
            await page.wait_for_timeout(2000)
            if not await page.locator("div.fixed.inset-0.z-50").count():
                break
        await page.wait_for_timeout(2000)
        txt = await page.evaluate("document.body.innerText")
        print(f"[+] {slug} chunk {i+1}-{i+len(part)}/{len(entries)} — connections: {conn_count(txt)}", flush=True)


async def enumerate_users(page, slug, first_wait=True):
    seen = set()
    await page.goto(f"{BASE}/{slug}", wait_until="load", timeout=30000)
    if first_wait:
        try:
            await page.wait_for_function("() => /user_[A-Za-z0-9]{12}/.test(document.body.innerText)", timeout=20000)
        except Exception:
            pass
    await page.wait_for_timeout(3000)
    txt = await page.evaluate("document.body.innerText")
    total = int(re.search(r"(\d+)\s+accounts", txt).group(1)) if re.search(r"(\d+)\s+accounts", txt) else 0
    npages = max(1, -(-total // 50))
    for pg in range(npages):
        txt = await page.evaluate("document.body.innerText")
        seen |= set(re.findall(r"user_[A-Za-z0-9]{12}", txt))
        if pg < npages - 1:
            nxt = page.locator("button:has-text('chevron_right')").first
            await nxt.scroll_into_view_if_needed()
            await nxt.click(force=True)
            await page.wait_for_timeout(2500)
    return seen, total


async def delete_one_user(page, user):
    """Klik tombol delete pada baris `user` lalu konfirmasi. Return True jika hilang."""
    ok = await page.evaluate("""(u) => {
        const els = Array.from(document.querySelectorAll('*')).filter(e =>
            e.children.length === 0 && (e.textContent||'').trim() === u);
        for (const el of els) {
            let p = el;
            for (let k = 0; k < 8 && p.parentElement; k++) {
                p = p.parentElement;
                const dels = Array.from(p.querySelectorAll('button')).filter(b =>
                    (b.innerText||'').trim() === 'delete');
                if (dels.length === 1) { dels[0].click(); return true; }
                if (dels.length > 1) break;
            }
        }
        return false;
    }""", user)
    if not ok:
        return False
    await page.wait_for_timeout(1500)
    conf = page.locator("div.fixed.inset-0.z-50 button").filter(
        has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
    if await conf.count():
        await conf.first.click(force=True)
        await page.wait_for_timeout(1500)
    return True


async def main():
    entries = B.read_keys(KEYS_FILE)
    assert len(entries) == 174
    mine = set(n for n, _ in entries)

    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)

        # 1. bulk add ke thebai
        await page.goto(f"{BASE}/thebai", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        await close_modals(page)
        print("[i] thebai SEBELUM:", conn_count(await page.evaluate("document.body.innerText")), flush=True)
        await bulk_add(page, "thebai", entries)

        # 2. verifikasi thebai
        got, total = await enumerate_users(page, "thebai")
        missing = mine - got
        print(f"[i] thebai: total header={total} user_ ditemukan={len(got & mine)}/174 missing={len(missing)}", flush=True)
        if missing:
            print("[!] penghapusan DITAHAN — bulk add belum lengkap:", flush=True)
            for m in sorted(missing):
                print("   ", m, flush=True)
            return
        print("[+] Verifikasi thebai LOLOS — lanjut hapus dari default bai", flush=True)

        # 3. hapus semua user_ dari bai
        await page.goto(f"{BASE}/bai", wait_until="load", timeout=30000)
        await page.wait_for_timeout(4000)
        removed = 0
        for loop in range(200):
            txt = await page.evaluate("document.body.innerText")
            users = re.findall(r"user_[A-Za-z0-9]{12}", txt)
            if not users:
                # refresh untuk lihat halaman berikutnya
                await page.reload(wait_until="load")
                await page.wait_for_timeout(3500)
                txt = await page.evaluate("document.body.innerText")
                users = re.findall(r"user_[A-Za-z0-9]{12}", txt)
                if not users:
                    break
            # hapus dari yang paling bawah dulu (stabil terhadap pergeseran halaman)
            target = users[-1]
            done = await delete_one_user(page, target)
            if not done:
                await page.reload(wait_until="load")
                await page.wait_for_timeout(3500)
                continue
            removed += 1
            if removed % 25 == 0:
                m = re.search(r"(\d+)\s+connections", await page.evaluate("document.body.innerText"))
                print(f"[+] removed {removed} — connections sekarang: {m.group(1) if m else '?'}", flush=True)
                await page.reload(wait_until="load")
                await page.wait_for_timeout(3500)
        print(f"[+] penghapusan selesai — total dihapus: {removed}", flush=True)

        # 4. verifikasi akhir
        await page.reload(wait_until="load")
        await page.wait_for_timeout(4000)
        txt = await page.evaluate("document.body.innerText")
        left_users = set(re.findall(r"user_[A-Za-z0-9]{12}", txt))
        print("bai SESUDAH: connections =", conn_count(txt), "| user_ tersisa di halaman 1 =", len(left_users), flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_after_migrate.png", full_page=True)
        await page.goto(f"{BASE}/thebai", wait_until="load", timeout=30000)
        await page.wait_for_timeout(4000)
        print("thebai SESUDAH: connections =", conn_count(await page.evaluate("document.body.innerText")), flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_thebai_after_migrate.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
