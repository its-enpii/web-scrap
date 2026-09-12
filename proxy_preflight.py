"""
Pre-flight proxy checker untuk web-scrap.
Cek apakah proxy pool masih hidup (bandwidth tersedia) SEBELUM batch jalan,
dan deteksi proxy mati saat runtime supaya fail loud (tidak retry 200x sia-sia).
"""
import asyncio
import sys
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp


def _proxy_url(p: dict) -> str:
    server = p.get("server", "")
    username = p.get("username")
    password = p.get("password")
    if username and password:
        hostport = server.replace("http://", "").replace("https://", "")
        return f"http://{username}:{password}@{hostport}"
    return server


async def check_proxy(session: aiohttp.ClientSession, p: dict, target: str = "https://unorouter.com/en/login", timeout: int = 15) -> dict:
    """Return {'proxy':..., 'ok':bool, 'status':int, 'reason':str}"""
    url = _proxy_url(p)
    try:
        async with session.get(target, proxy=url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False) as resp:
            status = resp.status
            # 402 = bandwidth habis (Webshare), 407 = auth gagal.
            # 403 dari target = Cloudflare challenge -> proxy hidup (Turnstile bisa solve di browser).
            if status == 402:
                return {"proxy": p.get("server"), "ok": False, "status": status, "reason": "proxy_bandwidth_exhausted"}
            if status == 407:
                return {"proxy": p.get("server"), "ok": False, "status": status, "reason": "proxy_auth_failed"}
            return {"proxy": p.get("server"), "ok": True, "status": status, "reason": "proxy_alive"}
    except asyncio.TimeoutError:
        return {"proxy": p.get("server"), "ok": False, "status": 0, "reason": "proxy_timeout"}
    except Exception as e:
        return {"proxy": p.get("server"), "ok": False, "status": 0, "reason": f"proxy_error:{str(e)[:60]}"}


async def preflight_pool(proxies: List[dict], target: str = "https://unorouter.com/en/login") -> List[dict]:
    """Cek semua proxy paralel. Return list hasil."""
    async with aiohttp.ClientSession() as session:
        tasks = [check_proxy(session, p, target) for p in proxies]
        return await asyncio.gather(*tasks)


def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Event loop yang sedang berjalan di thread ini, atau None."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _alive_from_results(proxies: List[dict], results: List[dict], verbose: bool = True) -> List[dict]:
    """Susun hasil preflight -> list proxy hidup + laporan verbose."""
    alive = [p for p, r in zip(proxies, results) if r and r["ok"]]
    if verbose:
        dead = [(r["proxy"], r["reason"]) for r in results if not (r and r["ok"])]
        print(f"[preflight] Proxy hidup: {len(alive)}/{len(proxies)}")
        for dproxy, reason in dead[:5]:
            print(f"[preflight]   MATI {dproxy}: {reason}")
        if len(dead) > 5:
            print(f"[preflight]   ... dan {len(dead)-5} proxy mati lainnya")
        if alive and not dead:
            pass
        elif not alive:
            print("[preflight] SEMUA PROXY MATI — cek bandwidth Webshare / kredensial!")
    return alive


async def filter_alive_async(proxies: List[dict], verbose: bool = True) -> List[dict]:
    """Async helper: preflight lalu return hanya proxy hidup. Wajib dipakai dari context async."""
    results = await preflight_pool(proxies)
    return _alive_from_results(proxies, results, verbose)


def filter_alive(proxies: List[dict], verbose: bool = True) -> List[dict]:
    """Sync helper: preflight lalu return hanya proxy hidup. Exit-app caller jika kosong.

    Dari dalam coroutine yang sedang jalan, pakai `filter_alive_async()` — di sini
    preflight dilewati (kembalikan semua proxy) supaya caller tidak crash.
    """
    if _running_loop() is not None:  # pragma: no cover
        if verbose:
            print(f"[preflight] preflight dilewati: sudah ada event loop berjalan "
                  f"(pakai filter_alive_async) — semua {len(proxies)} proxy dianggap hidup.")
        return list(proxies)

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(preflight_pool(proxies))
    except Exception as e:  # pragma: no cover
        if verbose:
            print(f"[preflight] preflight dilewati: {type(e).__name__}: {str(e)[:60]} "
                  f"— semua {len(proxies)} proxy dianggap hidup.")
        return list(proxies)
    finally:
        loop.close()
    return _alive_from_results(proxies, results, verbose)


def classify_goto_error(error_message: str) -> Optional[str]:
    """Deteksi error navigasi karena proxy mati -> sinyal fail-loud, bukan retry."""
    msg = error_message.lower()
    if "unknown error" in msg and "page.goto" in msg:
        return "proxy_dead_navigation"
    if "net::err_timed_out" in msg or "net::err_proxy_connection_failed" in msg:
        return "proxy_dead_navigation"
    if "err_name_not_resolved" in msg or "err_tunnel_connection_failed" in msg:
        return "proxy_dead_navigation"
    return None
