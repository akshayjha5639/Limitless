"""
Limitless — POST /generate-pdf Route
Accepts full /analyze JSON + optional branding. Returns binary PDF.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.request import GeneratePDFRequest
from app.services.pdf_service import build_report

router = APIRouter()


@router.post("/generate-pdf")
async def generate_pdf(request: GeneratePDFRequest) -> Response:
    """
    Accepts the full analysis JSON from /analyze and optional branding.
    Returns a binary application/pdf response.
    """
    try:
        pdf_bytes = build_report(
            analysis=request.analysis,
            brand=request.brand.model_dump(),
        )
    except Exception as e:
        # Never return partial PDFs — log and return 500
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=limitless_report.pdf",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
