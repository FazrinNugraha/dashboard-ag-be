from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from app.core.dependencies import get_snapshot_cache
from app.core.errors import AppError
from app.domain.snapshot import SnapshotCache
from app.services.report_service import ReportService
from app.core.config import get_settings
from app.core.security import get_current_admin

SUPPORTED_PERIODS = {"month", "year"}
SUPPORTED_FORMATS = {"xlsx", "pdf"}
import re

_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_admin)],
)

@router.get("/export")
async def export_report(
    period: str = Query(..., description="'month' or 'year'"),
    value: str = Query(..., description="e.g. '2026-10' or '2026'"),
    format: str = Query(..., description="'xlsx' or 'pdf'"),
    cache: SnapshotCache = Depends(get_snapshot_cache)
):
    if period not in SUPPORTED_PERIODS:
        raise AppError(
            "VALIDATION_ERROR",
            "Parameter 'period' harus 'month' atau 'year'.",
            422,
            {"period": period},
        )
    expected = _MONTH_RE if period == "month" else _YEAR_RE
    if not expected.match(value or ""):
        raise AppError(
            "VALIDATION_ERROR",
            f"Nilai 'value' tidak sesuai untuk period '{period}'.",
            422,
            {"period": period, "value": value},
        )
    if format not in SUPPORTED_FORMATS:
        raise AppError(
            "VALIDATION_ERROR",
            "Parameter 'format' harus 'xlsx' atau 'pdf'.",
            422,
            {"format": format},
        )

    service = ReportService(cache)
    kpi, projects, expenses, receivables = await service.get_report_data(period, value)

    if format == "xlsx":
        content = service.generate_excel(kpi, projects, expenses, receivables)
        headers = {
            "Content-Disposition": f"attachment; filename=Laporan_Agungjaya_{value}.xlsx"
        }
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

    title = f"Laporan Keuangan Agungjaya Aluminium - {value}"
    content = service.generate_pdf(title, kpi, projects, expenses, receivables)
    headers = {
        "Content-Disposition": f"attachment; filename=Laporan_Agungjaya_{value}.pdf"
    }
    return Response(content=content, media_type="application/pdf", headers=headers)

@router.get("/spreadsheet-link")
def get_spreadsheet_link():
    settings = get_settings()
    return {"url": settings.SPREADSHEET_URL}
