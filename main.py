import os
import sys
import argparse
import asyncio
from typing import List, Dict, Optional
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from flows import AVAILABLE_FLOWS
from flows.account_state import AccountState
from flows.proxy_helper import parse_proxy, load_proxies_file

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False

load_dotenv()

HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "accounts.txt")
PROXIES_FILE = os.getenv("PROXIES_FILE", "proxies.txt")
DEFAULT_OUTPUT_DIR = os.getenv("OUTPUT_DIR", "results")
DEFAULT_ENGINE = os.getenv("BROWSER_ENGINE", "camoufox" if CAMOUFOX_AVAILABLE else "chromium")
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))

def parse_accounts(file_path: str) -> List[Dict[str, str]]:
    if not os.path.exists(file_path):
        print(f"[!] File '{file_path}' tidak ditemukan.")
        return []

    accounts = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                print(f"[!] Baris {line_num} dilewati (format: email|password|recovery): {line}")
                continue
            
            email = parts[0]
            password = parts[1]
            recovery = parts[2] if len(parts) > 2 else ""

            accounts.append({
                "email": email,
                "password": password,
                "recovery": recovery,
                "line": line_num
            })
    return accounts

def select_flow_interactive() -> List[str]:
    print("\n==========================================")
    print("   PILIH TARGET WEBSITE / FLOW OTOMASI    ")
    print("==========================================")
    flow_keys = list(AVAILABLE_FLOWS.keys())
    print(" [0] SEMUA PROVIDER (Jalankan semua alur per akun)")
    for idx, key in enumerate(flow_keys, 1):
        flow_cls = AVAILABLE_FLOWS[key]
        print(f" [{idx}] {flow_cls.name} ({key})")
        print(f"     -> {flow_cls.description}")
    print("==========================================")

    while True:
        choice = input(f"Pilih nomor alur [0-{len(flow_keys)}] atau 'q' untuk keluar: ").strip()
        if choice.lower() == "q":
            sys.exit(0)
        if choice == "0" or choice.lower() == "all" or choice.lower() == "semua":
            return flow_keys
        if choice.isdigit():
            val = int(choice)
            if 1 <= val <= len(flow_keys):
                return [flow_keys[val - 1]]
        print("[!] Pilihan tidak valid, silakan coba lagi.")

def select_output_mode_interactive() -> str:
    print("\n==========================================")
    print("           PILIH METODE OUTPUT            ")
    print("==========================================")
    print(" [1] Auto Add ke AI-Omni Portal (Default)")
    print("     -> Login ke provider, ambil key, dan masukkan otomatis ke Dashboard AI-Omni")
    print(f" [2] Catat email|key ke folder '{DEFAULT_OUTPUT_DIR}/'")
    print("     -> Login ke provider, generate key, dan simpan hasilnya ke file .txt (tanpa masuk ke AI-Omni)")
    print("==========================================")

    while True:
        choice = input("Pilih mode output [1-2] (tekan Enter untuk opsi 1): ").strip()
        if choice == "" or choice == "1" or choice.lower() == "omni":
            return "omni"
        if choice == "2" or choice.lower() == "txt" or choice.lower() == "file":
            return "txt"
        print("[!] Pilihan tidak valid, silakan masukkan 1 atau 2.")

def print_provider_status(provider: str):
    if provider != "all" and provider not in AVAILABLE_FLOWS:
        print(f"[!] Flow tidak terdaftar: {provider}")
        print(f"[*] Flow yang tersedia: {', '.join(AVAILABLE_FLOWS.keys())}")
        return

    providers = AccountState.list_providers() if provider == "all" else [provider]
    if not providers:
        print("[i] Belum ada file state/*.json.")
        return

    for provider_name in providers:
        if provider_name not in AVAILABLE_FLOWS:
            print(f"\n[i] Status akun untuk {provider_name}:")
            print("[i] Provider tidak terdaftar di AVAILABLE_FLOWS.")
            continue
        state = AccountState(provider_name)
        print(f"\n[i] Status akun untuk {AVAILABLE_FLOWS[provider_name].name}:")
        lines = state.summary()
        if not lines:
            print("[i] Belum ada status akun tersimpan.")
            continue
        for line in lines:
            print(f"[i] {line}")

def should_skip_account_state(record: Optional[Dict]) -> Optional[str]:
    if not record:
        return None
    status = record.get("status")
    if status == "success":
        return f"sudah sukses, key ada ({record.get('key_created_at') or 'tanpa timestamp'})"
    if status == "failed" and record.get("retryable") is False:
        return f"perlu tindakan manual: {record.get('error') or 'tidak ada detail kegagalan'}"
    if record.get("attempts", 0) >= MAX_ATTEMPTS:
        return (
            f"batas percobaan tercapai ({record.get('attempts', 0)}/{MAX_ATTEMPTS}); "
            "periksa atau reset state sebelum mencoba lagi"
        )
    return None

async def launch_smart_chromium(playwright_instance, is_headless: bool) -> Browser:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars"
    ]
    try:
        return await playwright_instance.chromium.launch(
            headless=is_headless,
            args=args
        )
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            try:
                print("[*] Menggunakan Google Chrome sistem (channel='chrome')...")
                return await playwright_instance.chromium.launch(
                    channel="chrome",
                    headless=is_headless,
                    args=args
                )
            except Exception:
                print("[*] Menggunakan Microsoft Edge sistem (channel='msedge')...")
                return await playwright_instance.chromium.launch(
                    channel="msedge",
                    headless=is_headless,
                    args=args
                )
        raise e

async def close_context_completely(context: Optional[BrowserContext]):
    if not context:
        return
    try:
        for page in list(context.pages):
            try:
                await page.close()
            except Exception:
                pass
        await context.close()
    except Exception:
        pass

async def run_single_flow_task(
    flow_inst,
    acc: Dict[str, str],
    acc_idx: int,
    total_acc: int,
    assigned_proxy: Optional[Dict[str, str]],
    is_headless: bool,
    engine: str,
    needs_omni: bool
) -> bool:
    """Menjalankan 1 task flow dengan tepat 1 single browser page/tab."""
    # Khusus BAI (chat.b.ai), Next.js memerlukan rendering Chromium standar
    flow_name_lower = getattr(flow_inst, "name", "").lower()
    if "bai" in flow_name_lower or getattr(flow_inst, "key", "") == "bai":
        engine = "chromium"

    if engine == "camoufox" and CAMOUFOX_AVAILABLE:
        camoufox_kwargs = {
            "headless": is_headless,
            "humanize": True,
        }
        if assigned_proxy:
            camoufox_kwargs["proxy"] = assigned_proxy
            camoufox_kwargs["geoip"] = True
        else:
            camoufox_kwargs["geoip"] = False

        print(f"[*] Meluncurkan Camoufox (1 Single Window)...")
        async with AsyncCamoufox(**camoufox_kwargs) as browser:
            # Gunakan default page Camoufox (fingerprint konsisten, TANPA override UA/viewport
            # — override merusak konsistensi fingerprint dan membuat Turnstile gagal solve)
            page = await browser.new_page()

            if needs_omni:
                await flow_inst.setup(page.context, page)

            ok = await flow_inst.run_flow(page.context, page, acc, acc_idx, total_acc)
            await close_context_completely(page.context)
            return ok
    else:
        # Fallback Chromium
        async with async_playwright() as p:
            browser = await launch_smart_chromium(p, is_headless)
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "locale": "en-US",
                "permissions": ["clipboard-read", "clipboard-write"]
            }
            if assigned_proxy:
                context_kwargs["proxy"] = assigned_proxy

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            if needs_omni:
                await flow_inst.setup(context, page)

            ok = await flow_inst.run_flow(context, page, acc, acc_idx, total_acc)
            await close_context_completely(context)
            try:
                await browser.close()
            except Exception:
                pass
            return ok

async def run_automation(
    flow_keys: List[str],
    accounts_path: str,
    proxies_path: str,
    output_mode: str = "omni",
    custom_output_file: Optional[str] = None,
    headless_override: Optional[bool] = None,
    single_proxy: Optional[str] = None,
    engine: str = "camoufox"
):
    invalid_keys = [k for k in flow_keys if k not in AVAILABLE_FLOWS]
    if invalid_keys:
        print(f"[!] Flow tidak terdaftar: {', '.join(invalid_keys)}")
        print(f"[*] Flow yang tersedia: {', '.join(AVAILABLE_FLOWS.keys())}")
        return

    accounts = parse_accounts(accounts_path)
    if not accounts:
        print(f"[!] Silakan buat file '{accounts_path}' dengan format: email|password|recovery(opsional)")
        print(f"[*] Template tersedia di 'accounts.txt.example'")
        return

    proxies_list: List[Dict[str, str]] = []
    if single_proxy:
        parsed = parse_proxy(single_proxy)
        if parsed:
            proxies_list = [parsed]
    elif os.path.exists(proxies_path):
        proxies_list = load_proxies_file(proxies_path)

    is_headless = HEADLESS if headless_override is None else headless_override

    if output_mode == "txt":
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

    print(f"\n==========================================")
    print(f"[*] Browser Engine  : {engine.upper()} (Anti-Bot / Turnstile Stealth)")
    print(f"[*] Target Alur     : {len(flow_keys)} alur ({', '.join(flow_keys)})")
    print(f"[*] Mode Output     : {'Auto Add ke AI-Omni' if output_mode == 'omni' else f'Catat email|key ke folder {DEFAULT_OUTPUT_DIR}/'}")
    print(f"[*] Jumlah Akun     : {len(accounts)}")
    if proxies_list:
        print(f"[+] Proxy Terdeteksi: {len(proxies_list)} proxy aktif (mode rotasi otomatis)")
    else:
        print(f"[*] Status Proxy    : Direct Connection (tanpa proxy)")
    print(f"[*] Mode Headless   : {is_headless}")
    print(f"==========================================")

    flow_instances = {}
    for f_key in flow_keys:
        flow_cls = AVAILABLE_FLOWS[f_key]
        default_file = os.path.join(DEFAULT_OUTPUT_DIR, f"keys_{f_key}.txt")
        target_output_file = custom_output_file or default_file

        config = {
            "omni_url": os.getenv("OMNI_URL", "https://ai-omni.enpiistudio.com/login"),
            "omni_password": os.getenv("OMNI_PASSWORD", "its.enpii-118"),
            "output_mode": output_mode,
            "output_file": target_output_file
        }
        flow_instances[f_key] = flow_cls(config)

    stats = {f_key: {"success": 0, "failed": 0, "name": flow_instances[f_key].name, "file": flow_instances[f_key].output_file} for f_key in flow_keys}

    # Loop Luar: Per-Akun
    for acc_idx, acc in enumerate(accounts, 1):
        assigned_proxy = None
        if proxies_list:
            assigned_proxy = proxies_list[(acc_idx - 1) % len(proxies_list)]

        proxy_label = assigned_proxy['server'] if assigned_proxy else 'Direct'

        print(f"\n=======================================================")
        print(f"[{acc_idx}/{len(accounts)}] MEMPROSES AKUN: {acc['email']}")
        print(f"[*] Proxy: {proxy_label}")
        print(f"=======================================================")

        # Loop Dalam: Semua Provider yang Dipilih
        for f_key in flow_keys:
            flow_inst = flow_instances[f_key]
            print(f"\n---> Menjalankan Flow: {flow_inst.name} ({f_key}) untuk {acc['email']}")

            state = flow_inst.attach_state(f_key)
            flow_inst.set_current_account(acc["email"])
            record = state.get(acc["email"])
            skip_reason = should_skip_account_state(record)
            if skip_reason:
                print(f"[SKIP] {acc['email']} di {flow_inst.name}: {skip_reason}")
                continue

            state.update(acc["email"], attempts=record.get("attempts", 0) + 1)

            needs_omni = output_mode == "omni" or f_key == "kiro_omni"

            try:
                ok = await run_single_flow_task(
                    flow_inst=flow_inst,
                    acc=acc,
                    acc_idx=acc_idx,
                    total_acc=len(accounts),
                    assigned_proxy=assigned_proxy,
                    is_headless=is_headless,
                    engine=engine,
                    needs_omni=needs_omni
                )
                if ok:
                    if state.get(acc["email"]).get("status") != "success":
                        flow_inst.mark_success()
                    stats[f_key]["success"] += 1
                    print(f"[SUCCESS] {acc['email']} berhasil di {flow_inst.name}")
                else:
                    if state.get(acc["email"]).get("status") != "failed":
                        flow_inst.mark_failed(
                            f_key,
                            f"flow {f_key} selesai tanpa detail kegagalan",
                            retryable=True,
                        )
                    stats[f_key]["failed"] += 1
                    print(f"[FAILED] {acc['email']} gagal di {flow_inst.name}")
            except Exception as e:
                _rec = flow_inst.state.get(acc["email"]) if flow_inst.state else {}
                _stage = _rec.get("stage") if _rec.get("stage") in ("register", "login", "key_create", "done") else "register"
                flow_inst.mark_failed(_stage, f"unhandled exception: {e}", retryable=True)
                print(f"[ERROR] Exception pada {acc['email']} di {flow_inst.name}: {e}")
                stats[f_key]["failed"] += 1

            await asyncio.sleep(1)

    print(f"\n==========================================")
    print(f"           RINGKASAN KESELURUHAN          ")
    print(f"==========================================")
    for f_key, data in stats.items():
        target_desc = f"File -> {data['file']}" if output_mode == "txt" else "AI-Omni Portal"
        print(f" - {data['name']}: Berhasil={data['success']}/{len(accounts)}, Gagal={data['failed']} [{target_desc}]")
    print(f"==========================================")

def main():
    parser = argparse.ArgumentParser(description="Multi-Account Google Automation CLI with Camoufox Stealth & Proxy Support")
    parser.add_argument("-f", "--flow", help="Pilih flow target (contoh: kiro_omni, openrouter, unorouter, all)", default=None)
    parser.add_argument("-o", "--output", help="Mode output: 'omni' (Auto add ke AI-Omni) atau 'txt' (Catat email|key ke file txt)", choices=["omni", "txt"], default=None)
    parser.add_argument("--output-file", help=f"Path nama file khusus untuk menyimpan key (default: {DEFAULT_OUTPUT_DIR}/keys_<provider>.txt)", default=None)
    parser.add_argument("-a", "--accounts", help="Path ke file accounts (default: accounts.txt)", default=ACCOUNTS_FILE)
    parser.add_argument("-p", "--proxies", help="Path ke file proxies (default: proxies.txt)", default=PROXIES_FILE)
    parser.add_argument("--proxy", help="Single proxy override (contoh: http://user:pass@host:port)", default=None)
    parser.add_argument("--engine", help="Browser engine ('camoufox' untuk stealth anti-turnstile atau 'chromium')", choices=["camoufox", "chromium"], default=DEFAULT_ENGINE)
    parser.add_argument("--headless", action="store_true", help="Jalankan browser tanpa tampilan GUI")
    parser.add_argument(
        "--status",
        nargs="?",
        const="all",
        help="Tampilkan status akun semua provider atau satu provider tanpa membuka browser",
    )

    args = parser.parse_args()

    if args.status:
        print_provider_status(args.status)
        return

    if args.flow:
        if args.flow.lower() in ["all", "semua", "*"]:
            selected_flows = list(AVAILABLE_FLOWS.keys())
        else:
            selected_flows = [k.strip() for k in args.flow.split(",") if k.strip()]
    else:
        selected_flows = select_flow_interactive()

    if args.output:
        selected_output = args.output
    else:
        selected_output = select_output_mode_interactive()

    asyncio.run(run_automation(
        flow_keys=selected_flows,
        accounts_path=args.accounts,
        proxies_path=args.proxies,
        output_mode=selected_output,
        custom_output_file=args.output_file,
        headless_override=args.headless if args.headless else None,
        single_proxy=args.proxy,
        engine=args.engine
    ))

if __name__ == "__main__":
    main()
