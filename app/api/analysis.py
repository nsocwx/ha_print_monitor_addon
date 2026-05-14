"""API routes for analyzer history."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, desc

from app.api.schemas import AnalysisResultResponse
from app.core.database import get_session
from app.models.event import AnalysisResult

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _capture_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    filename = path.replace("\\", "/").split("/")[-1]
    return f"/captures/{filename}"


@router.get("/recent", response_model=List[AnalysisResultResponse])
def recent_analysis(
    session: Session = Depends(get_session),
    printer_id: Optional[str] = None,
    limit: int = Query(8, ge=1, le=50),
) -> List[AnalysisResultResponse]:
    """Get recent analyzer results, including clear frames."""
    query = select(AnalysisResult).order_by(desc(AnalysisResult.created_at))
    if printer_id:
        query = query.where(AnalysisResult.printer_id == printer_id)

    rows = session.exec(query.limit(limit)).all()
    return [
        AnalysisResultResponse(
            id=row.id,
            printer_id=row.printer_id,
            created_at=row.created_at,
            result=row.result,
            issue_type=row.issue_type,
            certainty=row.certainty,
            severity=row.severity,
            explanation=row.explanation,
            image_url=_capture_url(row.image_path),
            annotated_image_url=_capture_url(row.annotated_image_path),
        )
        for row in rows
    ]
