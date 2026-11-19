"""Text drafting and confirmation endpoints for stock intake."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from stock_manager.api.db import get_session
from stock_manager.api.intake_schemas import ConfirmRequest, ConfirmResponse, ParseRequest, ParseResponse
from stock_manager.api.intake_services import confirm_intake, parse_intake, prepare_parse

router = APIRouter()


@router.post("/parse", response_model=ParseResponse)
async def parse(
    payload: ParseRequest,
    db: Session = Depends(get_session),
    accept_language: str | None = Header(None),
):
    prepared = await run_in_threadpool(prepare_parse, db, payload, accept_language)
    return await parse_intake(payload, prepared)


@router.post("/confirm", response_model=ConfirmResponse, status_code=201)
async def confirm(payload: ConfirmRequest, db: Session = Depends(get_session)):
    return await run_in_threadpool(confirm_intake, db, payload)
