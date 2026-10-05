from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from app.core.dependencies import get_snapshot_cache
from app.domain.snapshot import SnapshotCache
from app.services.report_service import ReportService
from app.core.config import get_settings
from app.core.security import get_current_admin

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
    service = ReportService(cache)
    kpi, projects, expenses, receivables = await service.get_report_data(period, value)
    
    if format == "xlsx":
        content = service.generate_excel(kpi, projects, expenses, receivables)
        headers = {
            "Content-Disposition": f"attachment; filename=Laporan_Agungjaya_{value}.xlsx"
        }
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
        
    elif format == "pdf":
        title = f"Laporan Keuangan Agungjaya Aluminium - {value}"
        content = service.generate_pdf(title, kpi, projects, expenses, receivables)
        headers = {
            "Content-Disposition": f"attachment; filename=Laporan_Agungjaya_{value}.pdf"
        }
        return Response(content=content, media_type="application/pdf", headers=headers)
        
    return Response(content="Format not supported", status_code=400)

@router.get("/spreadsheet-link")
def get_spreadsheet_link():
    settings = get_settings()
    return {"url": settings.SPREADSHEET_URL}
