"""Perbaikan migrasi:
Target benar: openai-compatible-chat-200bd992-3cb8-421c-9506-37bf8d1d349b (custom BAI).
 1. Bulk add 174 key ke target.
 2. Verifikasi 174/174 ada di target.
 3. Hapus connections user_* dari 'thebai' (salah target sebelumnya).
 4. Hapus connections user_* dari 'bai' (sisa default).
 5. Verifikasi akhir semua halaman.
"""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

BASE = "https://ai-omni.enpiistudio.com/dashboard/providers"
TARGET = "openai-compatible-chat-200bd992-3cb8-421c-9506-37bf8d1d349b"
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


async def wait_modal_closed(page, max_wait=90):
    for _ in range(max_wait // 2):
        await page.wait_for_timeout(2000)
        if not await page.locator("div.fixed.inset-0.z-50").count():
            return
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(1500)


async def bulk_add(page, slug, entries, chunk=50):
    for i in range(0, len(entries), chunk):
        part = entries[i:i + chunk]
        await close_modals(page)
        await page.locator("button:has-text('Add')").first.click(force=True, timeout=15000)
        await page.wait_for_timeout(2500)
        modal = page.locator("div.fixed.inset-0.z-50")
        tab = modal.locator("button:has-text('Bulk Add'), [role='tab']:has-text('Bulk Add')").first
        if await tab.count():
            await tab.click(force=True, timeout=15000)
            await page.wait_for_timeout(1500)
        ta = modal.locator("textarea").last
        await ta.fill("\n".join(f"{n}|{k}" for n, k in part))
        await page.wait_for_timeout(800)
        btn = modal.locator("button:has-text('Add All Keys')").first
        if not await btn.count():
            btn = modal.locator("button:has-text('Save')").first
        await btn.click(force=True, timeout=15000)
        await wait_modal_closed(page)
        await page.wait_for_timeout(2000)
        await page.reload(wait_until="load")
        await page.wait_for_timeout(3500)
        txt = await page.evaluate("document.body.innerText")
        print(f"[+] {slug[:40]}… chunk {i+1}-{i+len(part)}/{len(entries)} — connections: {conn_count(txt)}", flush=True)


async def goto_provider_ready(page, slug):
    await page.goto(f"{BASE}/{slug}", wait_until="load", timeout=30000)
    await page.wait_for_timeout(4000)


async def delete_all_prefixed(page, slug, prefix="user_"):
    """Hapus semua baris dengan name ber-prefix via tombol delete per baris."""
    await goto_provider_ready(page, slug)
    pat = re.compile(prefix + r"[A-Za-z0-9]{8,}")
    removed = 0
    stuck = 0
    while True:
        txt = await page.evaluate("document.body.innerText")
        users = set(pat.findall(txt))
        if not users:
            await page.reload(wait_until="load")
            await page.wait_for_timeout(3500)
            txt = await page.evaluate("document.body.innerText")
            users = set(pat.findall(txt))
            if not users:
                break
        target = sorted(users)[0]
        ok = await page.evaluate("""(u) => {
            const els = Array.from(document.querySelectorAll('*')).filter(e =>
                e.children.length === 0 && (e.textContent||'').trim() === u);
            for (const el of els) {
                let p = el;
                for (let k = 0; k < 8 && p.parentElement; k++) {
                    p = p.parentElement;
                    const dels = Array.from(p.querySelectorAll('button')).filter(b =>
                        (b.innerText||'').trim() === 'delete');
                    if (dels.length >= 1) { dels[0].click(); return true; }
                }
            }
            return false;
        }""", target)
        if not ok:
            stuck += 1
            await page.reload(wait_until="load")
            await page.wait_for_timeout(3500)
            if stuck > 5:
                print(f"[!] {slug}: stuck, {target} tak bisa dihapus", flush=True)
                break
            continue
        await page.wait_for_timeout(1500)
        conf = page.locator("div.fixed.inset-0.z-50 button").filter(
            has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
        if await conf.count():
            await conf.first.click(force=True)
            await page.wait_for_timeout(1500)
        removed += 1
        stuck = 0
        if removed % 25 == 0:
            m = re.search(r"(\d+)\s+connections", await page.evaluate("document.body.innerText"))
            print(f"[+] {slug[:20]}… removed {removed} — connections: {m.group(1) if m else '?'}", flush=True)
            await page.reload(wait_until="load")
            await page.wait_for_timeout(3500)
    print(f"[+] {slug[:30]}… penghapusan selesai — total {removed}", flush=True)
    return removed


async def verify_target(page, entries):
    mine = set(n for n, _ in entries)
    seen = set()
    await goto_provider_ready(page, TARGET)
    txt = await page.evaluate("document.body.innerText")
    m = re.search(r"(\d+)\s+accounts", txt)
    total = int(m.group(1)) if m else conn_count(txt) or 0
    npages = max(1, -(-total // 50))
    for pg in range(npages):
        txt = await page.evaluate("document.body.innerText")
        seen |= set(re.findall(r"user_[A-Za-z0-9]{12}", txt))
        if pg < npages - 1:
            nxt = page.locator("button:has-text('chevron_right')").first
            await nxt.scroll_into_view_if_needed()
            await nxt.click(force=True)
            await page.wait_for_timeout(2500)
    missing = mine - seen
    print(f"[i] TARGET: header={total} matched={len(mine & seen)}/174 missing={len(missing)}", flush=True)
    return not missing


async def main():
    entries = B.read_keys(KEYS_FILE)
    assert len(entries) == 174

    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)

        # 1. bulk add ke target benar
        await goto_provider_ready(page, TARGET)
        await close_modals(page)
        txt = await page.evaluate("document.body.innerText")
        print("[i] TARGET SEBELUM:", conn_count(txt), flush=True)
        await bulk_add(page, TARGET, entries)

        # 2. verifikasi — gerbang untuk semua cleanup
        ok = await verify_target(page, entries)
        if not ok:
            print("[!] verifikasi target GAGAL — cleanup DITAHAN", flush=True)
            return
        print("[+] Verifikasi target LOLOS", flush=True)

        # 3. cleanup thebai (salah sasaran sebelumnya)
        await goto_provider_ready(page, "thebai")
        txt = await page.evaluate("document.body.innerText")
        print("[i] thebai sebelum cleanup:", conn_count(txt), flush=True)
        await delete_all_prefixed(page, "thebai")

        # 4. cleanup sisa bai default
        await goto_provider_ready(page, "bai")
        txt = await page.evaluate("document.body.innerText")
        print("[i] bai sebelum cleanup:", conn_count(txt), flush=True)
        await delete_all_prefixed(page, "bai")

        # 5. verifikasi akhir
        for slug in [TARGET, "thebai", "bai"]:
            await goto_provider_ready(page, slug)
            txt = await page.evaluate("document.body.innerText")
            left = len(set(re.findall(r"user_[A-Za-z0-9]{12}", txt)))
            print(f"[V] {slug[:45]}: connections={conn_count(txt)} user_di_hal1={left}", flush=True)
            await page.screenshot(path=f"/root/projects/web-scrap/results/_final_{slug[:20]}.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
