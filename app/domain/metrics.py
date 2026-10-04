from typing import List, Dict, Any, Optional
from datetime import datetime, date
from collections import defaultdict
from app.schemas.domain import Project, Payment, Expense

def calculate_kpi(
    projects: List[Project],
    payments: List[Payment],
    expenses: List[Expense],
    month: str # Format: YYYY-MM
) -> Dict[str, Any]:
    
    # 1. Omzet bulan M (berdasarkan tanggal invoice)
    omzet = sum(p.nilai_proyek for p in projects if p.bulan_filter == month)
    
    # 2. Kas Masuk bulan M (berdasarkan tanggal bayar)
    kas_masuk = sum(p.nominal for p in payments if p.bulan_filter == month)
    
    # 3. Total Pengeluaran bulan M (berdasarkan tanggal pengeluaran)
    pengeluaran = sum(e.nominal for e in expenses if e.bulan_filter == month)
    
    # 4. Laba Bersih bulan M
    laba_bersih = kas_masuk - pengeluaran
    margin_pct = round((laba_bersih / kas_masuk * 100), 1) if kas_masuk > 0 else None
    
    # 5. Sisa Piutang Global (semua proyek)
    # recalculate sisa piutang from payments just to be safe and accurate
    payments_by_project = defaultdict(int)
    for p in payments:
        payments_by_project[p.id_proyek] += p.nominal
        
    sisa_piutang_global = 0
    piutang_count = 0
    for proj in projects:
        total_dibayar = payments_by_project.get(proj.id_proyek, 0)
        sisa = max(proj.nilai_proyek - total_dibayar, 0)
        if sisa > 0:
            sisa_piutang_global += sisa
            piutang_count += 1
            
    return {
        "omzet": {"value": omzet},
        "kas_masuk": {"value": kas_masuk},
        "pengeluaran": {"value": pengeluaran},
        "laba_bersih": {"value": laba_bersih, "margin_pct": margin_pct},
        "sisa_piutang": {"value": sisa_piutang_global, "jumlah_proyek": piutang_count}
    }

def get_trend(projects: List[Project], current_month: str, months_count: int = 6) -> List[Dict[str, Any]]:
    # This is a simplified trend for omzet by month
    # In a real app we would generate the last N months strings correctly
    # For now, we group by month and just return what we have
    omzet_by_month = defaultdict(int)
    for p in projects:
        omzet_by_month[p.bulan_filter] += p.nilai_proyek
    
    sorted_months = sorted(omzet_by_month.keys())
    trend = [{"month": m, "omzet": omzet_by_month[m]} for m in sorted_months]
    # return last N
    return trend[-months_count:]

def get_expense_breakdown(expenses: List[Expense], month: str) -> List[Dict[str, Any]]:
    breakdown = defaultdict(int)
    for e in expenses:
        if e.bulan_filter == month:
            breakdown[e.kategori] += e.nominal
    
    return [{"kategori": k, "nominal": v} for k, v in breakdown.items() if v > 0]
