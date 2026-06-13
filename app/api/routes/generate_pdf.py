
"""
Limitless — POST /generate-pdf Route
Accepts full /analyze JSON + optional branding.
Returns binary PDF response.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.request import GeneratePDFRequest
from app.services.pdf_service import build_report

router = APIRouter()


@router.post("/generate-pdf")
async def generate_pdf(request: GeneratePDFRequest) -> Response:
    """
    Generate PDF from analysis response.
    """

    try:

        pdf_bytes = build_report(
            analysis=request.analysis,
            brand=request.brand.model_dump()
            if request.brand
            else {}
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}"
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                "attachment; filename=limitless_report.pdf"
        }
    )