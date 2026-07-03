from fastapi import APIRouter

from backend.models.schemas import QueryRequest
from backend.services import query_service

router = APIRouter(tags=["query"])


@router.post("/query")
async def nl_query(body: QueryRequest):
    return await query_service.natural_language_query(body.query)
