"""Buat hash bcrypt untuk kata sandi admin.

Pemakaian (dari folder be-dashboard, dengan venv aktif):
    python scripts/hash_password.py

Salin hasilnya ke .env sebagai ADMIN1_PASSWORD_HASH / ADMIN2_PASSWORD_HASH,
dibungkus tanda kutip tunggal karena hash mengandung karakter '$'.
"""
import getpass
import sys

import bcrypt


def main() -> int:
    password = getpass.getpass("Kata sandi: ")
    confirm = getpass.getpass("Ulangi kata sandi: ")
    if password != confirm:
        print("Kata sandi tidak sama.", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("Kata sandi minimal 8 karakter.", file=sys.stderr)
        return 1

    hashed = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")
    print(f"'{hashed}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
