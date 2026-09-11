"""Preflight: cek eksistensi akun Google sebelum full OAuth flow.
Output:
  results/agy_accounts_valid.txt   — akun yang lolos (email|password)
  results/agy_problem_report.txt   — akun bermasalah + alasan
"""
import asyncio, random, re, sys
from camoufox.async_api import AsyncCamoufox

IN_FILE = sys.argv[1] if len(sys.argv) > 1 else "results/agy_accounts_240.txt"
VALID_OUT = "results/agy_accounts_valid.txt"
REPORT_OUT = "results/agy_problem_report.txt"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
PROXY = "socks5://127.0.0.1:1080"

accounts = []
for line in open(IN_FILE, encoding="utf-8-sig"):
    line = line.strip()
    if not line or "|" not in line:
        continue
    email, pwd = line.split("|", 1)
    accounts.append({"email": email.strip(), "password": pwd.strip()})
print(f"[i] {len(accounts)} akun dicek", flush=True)


def classify(txt: str) -> str:
    t = txt.lower()
    if "enter your password" in t or "masukkan sandi" in t or "to continue" in t and "sign in" in t and "sandi" in t:
        return "ok"
    if "couldn’t find" in t or "couldn't find" in t or "tidak dapat menemukan" in t:
        return "not-found"
    if "unusual traffic" in t or "unusual activity" in t or "confirm you’re human" in t or "captcha" in t:
        return "throttle"
    if "this account already" in t:
        return "ok"
    if "sign in" in t and "password" in t:
        return "ok"
    return "unknown"


async def probe(p, acc, results):
    email = acc["email"]
    try:
        await p.goto("https://accounts.google.com/ServiceLogin", wait_until="load", timeout=30000)
        await p.wait_for_timeout(1500)
        inp = p.locator("input[type='email'], input#identifierId").first
        await inp.click(timeout=10000)
        # ketik per karakter (trigger JS Google), lalu Enter
        await inp.press_sequentially(email, delay=random.randint(30, 70), timeout=20000)
        await p.wait_for_timeout(400)
        await inp.press("Enter", timeout=10000)
        await p.wait_for_timeout(random.uniform(3500, 4500))
        txt = await p.evaluate("document.body.innerText")
        status = classify(txt)
        # retry sekali kalau masih di identifier (klik Next via JS)
        if status == "unknown" and "Email or phone" in txt:
            btn = p.locator("#identifierNext button").first
            try:
                await btn.evaluate("el => el.click()")
                await p.wait_for_timeout(4000)
                txt = await p.evaluate("document.body.innerText")
                status = classify(txt)
            except Exception:
                pass
        if status == "unknown":
            # dump utk analisa pola
            with open("results/_preflight_unknown.txt", "a") as f:
                f.write(f"===== {email} =====\nURL: {p.url[:150]}\nTEXT: {txt[:300]}\n\n")
    except Exception as e:
        status = f"error:{str(e)[:50]}"
    results.append((email, status))
    print(f"[{len(results)}/{len(accounts)}] {email} => {status}", flush=True)


async def main():
    sem = asyncio.Semaphore(WORKERS)
    results = []

    async def worker(acc):
        async with sem:
            async with AsyncCamoufox(headless=True, geoip=False, humanize=False,
                                     proxy={"server": PROXY, "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as b:
                p = await b.new_page()
                await probe(p, acc, results)
                # delay kecil antar probe di worker yang sama
                await asyncio.sleep(random.uniform(0.5, 1.5))

    await asyncio.gather(*[worker(a) for a in accounts])

    valid = [a for a in accounts if any(r[0] == a["email"] and r[1] == "ok" for r in results)]
    with open(VALID_OUT, "w") as f:
        for a in valid:
            f.write(f"{a['email']}|{a['password']}\n")

    lines = [
        "# LAPORAN AKUN BERMASALAH — Antigravity Connect",
        f"# Sumber: {IN_FILE}",
        f"# Total dicek: {len(accounts)}",
        f"# Valid (Google minta password): {len(valid)}",
        f"# Bermasalah: {len(accounts) - len(valid)}",
        "",
    ]
    for email, status in sorted(results, key=lambda r: r[1]):
        if status != "ok":
            reason = {
                "not-found": "Google: Couldn't find this account (akun tidak terdaftar)",
                "throttle": "Google challenge/CAPTCHA (perlu cek manual)",
            }.get(status, f"Error: {status}")
            lines.append(f"{email} — {reason}")
    with open(REPORT_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n=== REKAP ===", flush=True)
    print(f"valid: {len(valid)} | bermasalah: {len(accounts) - len(valid)}", flush=True)
    print(f"file valid: {VALID_OUT}", flush=True)
    print(f"file laporan: {REPORT_OUT}", flush=True)

asyncio.run(main())
