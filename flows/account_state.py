import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List


def derive_username(email: str) -> str:
    local_part = email.split("@", 1)[0].lower()
    return re.sub(r"[^a-z0-9_]", "_", local_part)


class AccountState:
    def __init__(self, provider: str):
        self.provider = provider
        self.state_file = os.path.join("state", f"{provider}.json")
        self._data = self._load()

    def _load(self) -> Dict[str, Dict]:
        if not os.path.exists(self.state_file):
            return {"accounts": {}}

        with open(self.state_file, "r", encoding="utf-8") as state_file:
            return json.load(state_file)

    def _save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        tmp_file = f"{self.state_file}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as state_file:
            json.dump(self._data, state_file, indent=2, ensure_ascii=False)
        os.replace(tmp_file, self.state_file)

    def get(self, email: str) -> Dict:
        accounts = self._data.setdefault("accounts", {})
        if email not in accounts:
            accounts[email] = {
                "username": derive_username(email),
                "status": "new",
                "stage": "register",
                "error": None,
                "retryable": True,
                "attempts": 0,
                "key_hint": None,
                "registered_at": None,
                "key_created_at": None,
                "updated_at": None,
            }
        return accounts[email]

    def update(self, email: str, **fields):
        record = self.get(email)
        record.update(fields)
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return record

    def all(self) -> Dict[str, Dict]:
        return self._data.get("accounts", {})

    def summary(self) -> List[str]:
        lines = []
        for email, record in self.all().items():
            status = record.get("status", "new")
            stage = record.get("stage", "register")
            error = record.get("error") or "-"
            retry_label = "bisa diulang otomatis" if record.get("retryable") else "tidak bisa diulang otomatis"
            attempts = record.get("attempts", 0)
            key_created_at = record.get("key_created_at")
            key_hint = record.get("key_hint")

            if status == "success":
                key_info = f" ({key_hint})" if key_hint else ""
                lines.append(
                    f"Akun {email}: SUKSES — key dibuat {key_created_at or '-'}{key_info}"
                )
            elif status == "failed":
                lines.append(
                    f"Akun {email}: GAGAL di {stage} — {error} — {retry_label} (percobaan: {attempts})"
                )
            else:
                lines.append(
                    f"Akun {email}: BELUM SELESAI di {stage} — {error} — {retry_label} (percobaan: {attempts})"
                )
        return lines
