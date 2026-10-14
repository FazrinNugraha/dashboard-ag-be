import io
from typing import Dict, List, Optional
from datetime import datetime
from openpyxl import Workbook
from app.core.clock import today_local
from app.services.report_excel import build_report_excel
from app.services.report_pdf import build_report_pdf
from app.domain.snapshot import SnapshotCache
from app.domain.metrics import calculate_period_kpi, compute_receivables, total_expense_by_project
from app.schemas.domain import Project, Expense

class ReportService:
    def __init__(self, cache: SnapshotCache):
        self.cache = cache

    async def get_report_data(self, period_type: str, period_value: str):
        # period_type: 'month' or 'year'
        # period_value: 'YYYY-MM' or 'YYYY'
        projects, payments, expenses = await self.cache.get_data()

        def matches(bulan: str) -> bool:
            if period_type == "year":
                return bulan.startswith(period_value)
            return bulan == period_value

        filtered_projects = [p for p in projects if matches(p.bulan_filter)]
        filtered_expenses = [e for e in expenses if matches(e.bulan_filter)]
        kpi = calculate_period_kpi(projects, payments, expenses, period_type, period_value)

        # Receivables (global, tidak difilter periode) dari sumber tunggal
        receivables = [
            {
                "id": proj.id_proyek,
                "klien": proj.nama_klien,
                "tanggal": proj.tanggal,
                "nilai": proj.nilai_proyek,
                "sisa": sisa,
            }
            for proj, _, sisa in compute_receivables(projects, payments)
        ]

        return kpi, filtered_projects, filtered_expenses, receivables

    def generate_excel(
        self,
        kpi: dict,
        projects: List[Project],
        expenses: List[Expense],
        receivables: List[dict],
        period_label: Optional[str] = None,
        project_expenses: Optional[Dict[str, int]] = None,
    ) -> bytes:
        """Excel laporan bergaya profesional dengan kop perusahaan (lihat report_excel.py)."""
        return build_report_excel(
            kpi,
            projects,
            expenses,
            receivables,
            label=period_label or "",
            printed_on=today_local(),
            project_expenses=project_expenses,
        )

    async def get_project_expense_totals(self) -> Dict[str, int]:
        """Total pengeluaran SEMUA waktu per id_proyek (untuk laba per proyek di PDF)."""
        _, _, expenses = await self.cache.get_data()
        return dict(total_expense_by_project(expenses))

    def generate_pdf(
        self,
        title: str,
        kpi: dict,
        projects: List[Project],
        expenses: List[Expense],
        receivables: List[dict],
        period_label: Optional[str] = None,
        project_expenses: Optional[Dict[str, int]] = None,
    ) -> bytes:
        """PDF laporan bergaya surat resmi (kop surat). Tata letak ada di report_pdf.py.

        period_label: teks periode, mis. 'Oktober 2026'. Bila kosong dipakai `title`.
        """
        return build_report_pdf(
            kpi, projects, expenses, receivables,
            label=period_label or title,
            printed_on=today_local(),
            project_expenses=project_expenses,
        )
