from fastapi import APIRouter, Depends
from app.api.v1 import auth, invoices, system, dashboard, projects, receivables, expenses, reports
from app.core.security import csrf_protect

# csrf_protect berlaku untuk semua route (hanya memeriksa method mutasi)
api_router = APIRouter(dependencies=[Depends(csrf_protect)])
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(invoices.router)
api_router.include_router(dashboard.router)
api_router.include_router(projects.router)
api_router.include_router(receivables.router)
api_router.include_router(expenses.router)
api_router.include_router(reports.router)
