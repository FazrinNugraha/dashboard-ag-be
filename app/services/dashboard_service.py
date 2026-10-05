import logging
from typing import Dict, Any
from app.domain.snapshot import SnapshotCache
from app.domain.metrics import calculate_kpi, get_trend, get_expense_breakdown
from app.core.clock import now_local

logger = logging.getLogger(__name__)

class DashboardService:
    def __init__(self, cache: SnapshotCache):
        self.cache = cache

    async def get_dashboard_summary(self, month: str) -> Dict[str, Any]:
        # get data from cache
        projects, payments, expenses = await self.cache.get_data()
        
        # All time stats
        all_time_omzet = sum(p.nilai_proyek for p in projects)
        
        # Calculate KPI for current month
        kpi_current = calculate_kpi(projects, payments, expenses, month)
        
        # Calculate KPI for previous month (simplified logic for month-1)
        try:
            year, m = map(int, month.split('-'))
            if m == 1:
                prev_month = f"{year-1}-12"
            else:
                prev_month = f"{year}-{m-1:02d}"
                
            kpi_prev = calculate_kpi(projects, payments, expenses, prev_month)
            
            # Enrich KPI with delta
            for key in ["omzet", "kas_masuk", "pengeluaran"]:
                curr_val = kpi_current[key]["value"]
                prev_val = kpi_prev[key]["value"]
                delta = curr_val - prev_val
                delta_pct = round((delta / prev_val * 100), 1) if prev_val > 0 else None
                
                kpi_current[key]["prev"] = prev_val
                kpi_current[key]["delta"] = delta
                kpi_current[key]["delta_pct"] = delta_pct

            # Laba bersih: prev/delta, margin dipertahankan
            curr_laba = kpi_current["laba_bersih"]["value"]
            prev_laba = kpi_prev["laba_bersih"]["value"]
            laba_delta = curr_laba - prev_laba
            kpi_current["laba_bersih"]["prev"] = prev_laba
            kpi_current["laba_bersih"]["delta"] = laba_delta
            kpi_current["laba_bersih"]["delta_pct"] = (
                round((laba_delta / prev_laba * 100), 1) if prev_laba > 0 else None
            )
                
        except Exception as e:
            # Bulan lalu tidak bisa dihitung (mis. format bulan salah); delta dilewati.
            logger.warning("Gagal menghitung delta bulan sebelumnya untuk %s: %s", month, e)
            
        trend = get_trend(projects, payments, expenses, month)
        expense_breakdown = get_expense_breakdown(expenses, month)
        
        return {
            "month": month,
            "generated_at": now_local().isoformat(),
            "all_time": {
                "omzet": all_time_omzet,
                "jumlah_proyek": len(projects)
            },
            "kpi": kpi_current,
            "trend": trend,
            "expense_breakdown": expense_breakdown
        }
