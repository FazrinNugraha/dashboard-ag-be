"""Pembuat ID urut dengan format PREFIX-YYMM-NNN."""


def next_sequential_id(prefix: str, existing_ids: set[str], start: int = 1) -> str:
    """Cari NNN berikutnya yang belum terpakai (aman terhadap suffix non-numerik)."""
    max_nnn = 0
    for item_id in existing_ids:
        if item_id.startswith(prefix):
            suffix = item_id[len(prefix):]
            if suffix.isdigit():
                max_nnn = max(max_nnn, int(suffix))
    nnn = max(max_nnn + 1, start)
    while f"{prefix}{nnn:03d}" in existing_ids:
        nnn += 1
    return f"{prefix}{nnn:03d}"
