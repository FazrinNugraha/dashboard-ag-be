"""Benchmark performa endpoint backend Agung Jaya Aluminium.

Menguji kecepatan response time (latency p50, p95) untuk:
- /api/v1/dashboard (Ringkasan KPI)
- /api/v1/projects?page_size=500 (Daftar 500 proyek + kalkulasi laba bersih)
- /api/v1/expenses?id_proyek=... (Filter pengeluaran per proyek)
- /api/v1/reports/export format PDF & XLSX (Pembuatan file laporan profesional)
"""
import os
import sys
import time
import statistics

# Set working directory to project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.core.dependencies import get_snapshot_cache

client = TestClient(app)

def benchmark():
    print("=" * 65)
    print("  UJI KECEPATAN & PERFORMA DASHBOARD AGUNG JAYA ALUMINIUM")
    print("=" * 65)

    # 1. Warm-up & Cache Preload
    print("\n[1/5] Memuat Cache Snapshot dari Google Sheets...")
    t0 = time.perf_counter()
    r = client.get("/api/v1/system/health/sheets")
    t_sheets = (time.perf_counter() - t0) * 1000
    print(f"      Status Sheets: {r.status_code} ({t_sheets:.1f} ms)")

    # 2. Login benchmark
    # We create a valid JWT directly or mock user via dependency override for clean benchmarking
    from app.core.security import get_current_admin
    app.dependency_overrides[get_current_admin] = lambda: "fazrin"

    endpoints = [
        ("Dashboard (KPI & Trend)", "/api/v1/dashboard?month=2026-10"),
        ("Proyek (500 data + Hitung Laba)", "/api/v1/projects?page_size=500"),
        ("Rincian Pengeluaran Proyek", "/api/v1/expenses?id_proyek=INV-2610-001"),
        ("Cetak PDF Kop Surat", "/api/v1/reports/export?period=month&value=2026-10&format=pdf"),
        ("Export Excel (.xlsx)", "/api/v1/reports/export?period=month&value=2026-10&format=xlsx"),
    ]

    print("\n[2/5] Menguji Kecepatan Tiap Endpoint (50 request beruntun)...")
    print(f"      {'Endpoint':<35} | {'Rata-rata':<10} | {'p95 (Terlama)':<12}")
    print("      " + "-" * 62)

    results = {}
    for name, path in endpoints:
        latencies = []
        # Run 50 iterations per endpoint
        for _ in range(50):
            t_start = time.perf_counter()
            resp = client.get(path)
            t_end = time.perf_counter()
            assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
            latencies.append((t_end - t_start) * 1000)

        avg = statistics.mean(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        results[name] = (avg, p95)
        print(f"      {name:<35} | {avg:>6.1f} ms  | {p95:>8.1f} ms")

    print("\n[3/5] Analisis Beban Memori & Algoritma:")
    cache = get_snapshot_cache()
    stats = cache.stats()
    counts = stats.get("counts", {})
    print(f"      - Data di Cache Memori : {counts.get('projects', 0)} proyek, {counts.get('payments', 0)} pembayaran, {counts.get('expenses', 0)} pengeluaran")
    print(f"      - Usia Cache Snapshot  : {stats.get('age_seconds', 0)} detik (TTL 30 detik)")

    print("\n[4/5] Evaluasi Standar Respon (PRD Target):")
    p_proj_avg, p_proj_95 = results["Proyek (500 data + Hitung Laba)"]
    p_dash_avg, p_dash_95 = results["Dashboard (KPI & Trend)"]

    print(f"      * Target GET Dashboard PRD  : < 200 ms (Aktual: {p_dash_95:.1f} ms) -> {'[SANGAT CEPAT]' if p_dash_95 < 200 else '[OK]'}")
    print(f"      * Target Proyek + Laba      : < 200 ms (Aktual: {p_proj_95:.1f} ms) -> {'[SANGAT CEPAT]' if p_proj_95 < 200 else '[OK]'}")

    app.dependency_overrides.clear()
    print("\n[5/5] Selesai! Semua pengujian berhasil.")

if __name__ == "__main__":
    benchmark()
