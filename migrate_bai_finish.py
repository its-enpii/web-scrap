"""Finish migrasi BAI ke custom provider.

State saat mulai:
- TARGET (openai-compatible-chat-200bd992-...): ~168-192, chunk terakhir belum terverifikasi.
- thebai: 174 user_ (salah sasaran) -> hapus semua.
- bai default: ~127 (177-50) dengan ~124 user_ -> hapus user_ saja, 3 grmill tetap.

Steps:
 1. Enumerate TARGET; hitung matched dari 174. Re-add yang missing (bulk, dedupe aman).
 2. Gate: 174/174 di TARGET.
 3. Delete semua user_* di thebai.
 4. Delete semua user_* di bai.
 5. Verifikasi akhir 3 halaman.
"""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

BASE = "https://ai-omni.enpiistudio.com/dashboard/providers"
TARGET = "openai-compatible-chat-200bd992-3cb8-421c-9506-37bf8d1d349b"
KEYS_FILE = os.path.join(B.RESULTS_DIR, "keys_bai_174.txt")
UPAT = re.compile(r"user_[A-Za-z0-9]{12}")


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def goto(page, slug):
    await page.goto(f"{BASE}/{slug}", wait_until="load", timeout=45000)
    await page.wait_for_timeout(4500)


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


async def safe_reload(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        await page.wait_for_timeout(3000)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
    await page.wait_for_timeout(4000)


async def bulk_add(page, slug, entries, chunk=50):
    url = f"{BASE}/{slug}"
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
        await modal.locator("textarea").last.fill("\n".join(f"{n}|{k}" for n, k in part))
        await page.wait_for_timeout(800)
        btn = modal.locator("button:has-text('Add All Keys')").first
        if not await btn.count():
            btn = modal.locator("button:has-text('Save')").first
        await btn.click(force=True, timeout=15000)
        for _ in range(45):
            await page.wait_for_timeout(2000)
            if not await page.locator("div.fixed.inset-0.z-50").count():
                break
        await page.wait_for_timeout(2000)
        await safe_reload(page, url)
        print(f"[+] add {slug[:30]}… chunk {i+1}-{i+len(part)} — connections: {conn_count(await page.evaluate('document.body.innerText'))}", flush=True)


async def enumerate_users(page, slug):
    url = f"{BASE}/{slug}"
    await safe_reload(page, url)
    seen = set()
    txt = await page.evaluate("document.body.innerText")
    m = re.search(r"(\d+)\s+accounts", txt)
    total = int(m.group(1)) if m else (conn_count(txt) or 0)
    npages = max(1, -(-total // 50))
    for pg in range(npages):
        txt = await page.evaluate("document.body.innerText")
        seen |= set(UPAT.findall(txt))
        if pg < npages - 1:
            nxt = page.locator("button:has-text('chevron_right')").first
            try:
                await nxt.scroll_into_view_if_needed()
                await nxt.click(force=True)
                await page.wait_for_timeout(2500)
            except Exception:
                break
    return seen, total


async def delete_all_users(page, slug):
    url = f"{BASE}/{slug}"
    await safe_reload(page, url)
    removed = 0
    stuck = 0
    while True:
        txt = await page.evaluate("document.body.innerText")
        users = UPAT.findall(txt)
        if not users:
            await safe_reload(page, url)
            users = UPAT.findall(await page.evaluate("document.body.innerText"))
            if not users:
                break
        target = users[-1]  # bawah dulu -> stabil saat list bergeser
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
            await safe_reload(page, url)
            if stuck > 5:
                print(f"[!] {slug[:20]}… stuck di {target}", flush=True)
                break
            continue
        await page.wait_for_timeout(1200)
        conf = page.locator("div.fixed.inset-0.z-50 button").filter(
            has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
        if await conf.count():
            await conf.first.click(force=True)
            await page.wait_for_timeout(1200)
        removed += 1
        stuck = 0
        if removed % 25 == 0:
            print(f"[+] {slug[:20]}… removed {removed} — connections: "
                  f"{conn_count(await page.evaluate('document.body.innerText'))}", flush=True)
            await safe_reload(page, url)
    print(f"[+] {slug[:30]}… SELESAI hapus {removed} user_", flush=True)
    return removed


async def main():
    entries = B.read_keys(KEYS_FILE)
    assert len(entries) == 174
    mine = set(n for n, _ in entries)
    ekey = dict(entries)

    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)

        # 1. cek & lengkapi TARGET
        seen, total = await enumerate_users(page, TARGET)
        print(f"[i] TARGET: header={total} matched={len(mine & seen)}/174", flush=True)
        missing = mine - seen
        if missing:
            print(f"[*] re-add {len(missing)} missing...", flush=True)
            await goto(page, TARGET)
            await bulk_add(page, TARGET, [(u, ekey[u]) for u in sorted(missing)])
            seen, total = await enumerate_users(page, TARGET)
            missing = mine - seen
        if missing:
            print(f"[!] TARGET MASIH KURANG {len(missing)} — cleanup ditahan", flush=True)
            for m in sorted(missing):
                print("   ", m, flush=True)
            return
        print("[+] Gate 174/174 di TARGET LOLOS", flush=True)

        # 2. cleanup thebai
        got, total = await enumerate_users(page, "thebai")
        print(f"[i] thebai: header={total} user_ ditemukan={len(got)}", flush=True)
        if got:
            await delete_all_users(page, "thebai")

        # 3. cleanup bai default
        got, total = await enumerate_users(page, "bai")
        print(f"[i] bai: header={total} user_ ditemukan={len(got)}", flush=True)
        if got:
            await delete_all_users(page, "bai")

        # 4. verifikasi akhir
        out = {}
        for slug in [TARGET, "thebai", "bai"]:
            await goto(page, slug)
            txt = await page.evaluate("document.body.innerText")
            out[slug] = {"connections": conn_count(txt), "users_page1": len(set(UPAT.findall(txt)))}
            print(f"[V] {slug[:45]}: {out[slug]}", flush=True)
            await page.screenshot(path=f"/root/projects/web-scrap/results/_fin_{slug[:18]}.png", full_page=True)
        json.dump(out, open("/root/projects/web-scrap/results/_migrate_final.json", "w"))
        print("[+] MIGRASI SELESAI", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
