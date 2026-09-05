import os
from typing import Optional, Dict, List
from urllib.parse import urlparse

def parse_proxy(proxy_str: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Mengubah format proxy string ke dictionary format Playwright:
    { "server": "http://ip:port", "username": "...", "password": "..." }
    """
    if not proxy_str or not proxy_str.strip():
        return None

    p = proxy_str.strip()

    # Format 1, 2, 3: URL scheme
    if "://" in p:
        parsed = urlparse(p)
        scheme = parsed.scheme or "http"
        port_part = f":{parsed.port}" if parsed.port else ""
        server = f"{scheme}://{parsed.hostname}{port_part}"
        result = {"server": server}
        if parsed.username:
            result["username"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password
        return result

    # Format 4: host:port:user:pass
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return {
            "server": f"http://{host}:{port}",
            "username": user,
            "password": pwd
        }
    # Format 5: host:port
    elif len(parts) == 2:
        host, port = parts
        return {
            "server": f"http://{host}:{port}"
        }

    return {"server": f"http://{p}"}

def load_proxies_file(file_path: str = "proxies.txt") -> List[Dict[str, str]]:
    """
    Membaca daftar proxy dari file (1 baris 1 proxy).
    Menggunakan utf-8-sig untuk otomatis membersihkan BOM jika ada.
    """
    if not os.path.exists(file_path):
        return []

    proxies = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parsed = parse_proxy(line)
            if parsed:
                proxies.append(parsed)

    return proxies
