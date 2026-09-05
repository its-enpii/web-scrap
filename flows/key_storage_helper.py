import os
from typing import Optional

def append_key_to_file(file_path: str, email: str, api_key: str, provider_name: Optional[str] = None):
    """
    Menyimpan baris email|api_key ke file .txt (format: email|key).
    """
    # Pastikan folder target ada jika dalam path subdirektori
    dir_name = os.path.dirname(file_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    line = f"{email}|{api_key}\n"
    with open(file_path, "a", encoding="utf-8-sig") as f:
        f.write(line)
    
    print(f"[+] [Key Storage] Berhasil dicatat ke '{file_path}': {email}|{api_key[:8]}...")
