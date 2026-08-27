from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.rag_query_log import RAGQueryLog
from app.schemas.api_rag_schema import RAGMetricsResponse


class MetricsService:
    @staticmethod
    def get_metrics(db: Session) -> RAGMetricsResponse:
        total = db.query(func.count(RAGQueryLog.id)).scalar() or 0
        successful = (
            db.query(func.count(RAGQueryLog.id))
            .filter(RAGQueryLog.success.is_(True))
            .scalar()
            or 0
        )
        failed = total - successful
        average = db.query(func.avg(RAGQueryLog.response_time_ms)).scalar() or 0.0

        return RAGMetricsResponse(
            total_queries=int(total),
            successful_queries=int(successful),
            failed_queries=int(failed),
            average_response_time_ms=round(float(average), 2),
        )
