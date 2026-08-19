"""Scheduled jobs as endpoints — Raport's taskiq calls them on its own schedule.

plan-naryad deliberately runs no scheduler of its own: Raport already has one, and a second
one would mean two things to configure, two clocks and two places to look when a night is
missed. The logic lives in src/services/task/service.py; these handlers only wrap it.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from src.api.schemes import DataResponseSchema, ResponseGroup
from src.services.common import current_actor
from src.services.task import TaskService, get_task_service
from src.utils.helpers import catch_all_exceptions, get_responses

task_router = APIRouter(prefix="/tasks", tags=["Scheduled jobs"])


@task_router.post(
    "/nightly-plan",
    summary="Nightly job: pull facts, then autogenerate the day plan",
    description="Called by Raport's scheduler at 03:00 МСК. Runs every housing that has a "
    "technological sequence, each in isolation, and reports a per-housing breakdown so a "
    "partial failure is visible. Pass `housing_raport_id` to run a single housing.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def nightly_plan(
    target_date: date | None = Query(None, alias="date", description="Defaults to the Р3 rule"),
    housing_raport_id: str | None = Query(None, description="Limit the run to one housing"),
    service: TaskService = Depends(get_task_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[dict]:
    result = await service.run_nightly_plan(target_date=target_date, housing_raport_id=housing_raport_id, actor=actor)
    return DataResponseSchema(data=result)


@task_router.post(
    "/transfer",
    summary="Cutoff job: hand the day's positions to the contractors",
    description="Called by Raport's scheduler at the transfer cutoff. Moves both draft and "
    "confirmed positions to `transferred`, as the spec requires. Idempotent.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def transfer(
    target_date: date | None = Query(None, alias="date", description="Defaults to today"),
    service: TaskService = Depends(get_task_service),
) -> DataResponseSchema[dict]:
    result = await service.run_transfer(target_date=target_date)
    return DataResponseSchema(data=result)
