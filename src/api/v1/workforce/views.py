from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.workforce.schemes import (
    ArticleBDRBulkRequest,
    ArticleBDRSchema,
    ArticleMappingSchema,
    ChallengeSchema,
    CreateArticleBDRRequest,
    CreateArticleMappingRequest,
    CreateChallengeRequest,
    CreateViolationRequest,
    CreateWfHeadcountFactRequest,
    CreateWfHeadcountPlanRequest,
    CreateWfProjectObjectRequest,
    CreateWfProjectRequest,
    CreateWfWorkforceNormRequest,
    UpdateChallengeRequest,
    UpdateViolationRequest,
    UpdateWfProjectRequest,
    WfHeadcountFactSchema,
    WfHeadcountPlanSchema,
    WfProjectFilters,
    WfProjectObjectSchema,
    WfViolationFilters,
    WfWorkforceNormSchema,
)
from src.services.workforce.schemas import (
    ContractorHeadcountRow,
    ContractorRatingRow,
    DashboardResponse,
    ForecastResponse,
    ProjectDetailResponse,
    SystemProblemsResponse,
    ViolationOut,
    ViolationScanResult,
    WfProjectOut,
)
from src.services.workforce.service import WorkforceService, get_workforce_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

workforce_router = APIRouter(prefix="/workforce", tags=["Workforce"])


# ── Analytics ─────────────────────────────────────────────────────────────────


@workforce_router.get("/dashboard", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_workforce_dashboard(
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[DashboardResponse]:
    data = await service.calc_dashboard()
    return DataResponseSchema[DashboardResponse](data=data)


@workforce_router.get("/projects/{project_id}/detail", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_project_detail(
    project_id: UUID,
    period_month: Optional[date] = Query(None),
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ProjectDetailResponse]:
    project = await service.wf_project_manager.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    data = await service.calc_project_detail(project, period_month)
    return DataResponseSchema[ProjectDetailResponse](data=data)


@workforce_router.get("/projects/{project_id}/forecast", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_project_forecast(
    project_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ForecastResponse]:
    data = await service.calc_forecast(project_id)
    return DataResponseSchema[ForecastResponse](data=data)


@workforce_router.get("/objects/{object_id}/contractors", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_object_contractors(
    object_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ContractorHeadcountRow]:
    items = await service.calc_object_contractors(object_id)
    return ListDataResponseSchema[ContractorHeadcountRow].create(list_data=[item.model_dump() for item in items])


@workforce_router.get("/system-problems", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_system_problems(
    threshold_pct: float = Query(50.0, description="Coverage threshold (%)"),
    min_objects: int = Query(3, description="Minimum affected objects"),
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[SystemProblemsResponse]:
    data = await service.calc_system_problems(threshold_pct, min_objects)
    return DataResponseSchema[SystemProblemsResponse](data=data)


@workforce_router.get("/contractor-rating", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_contractor_rating(
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ContractorRatingRow]:
    items = await service.calc_contractor_rating()
    return ListDataResponseSchema[ContractorRatingRow].create(list_data=[item.model_dump() for item in items])


# ── WfProject ─────────────────────────────────────────────────────────────────


@workforce_router.get("/projects", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_projects(
    filters: WfProjectFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[WfProjectOut]:
    filter_data = filters.model_dump(exclude_none=True)
    search_text = filter_data.pop("search", None)
    items = await service.wf_project_manager.search(search=search_text, order_by=["name"], **filter_data)
    total = await service.wf_project_manager.count(search=search_text, **filter_data)
    return ListDataResponseSchema[WfProjectOut].create(
        list_data=[WfProjectOut.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@workforce_router.get("/projects/{project_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_project(
    project_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfProjectOut]:
    item = await service.wf_project_manager.get_by_id(project_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return DataResponseSchema[WfProjectOut](data=WfProjectOut.model_validate(item))


@workforce_router.post("/projects", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_project(
    body: CreateWfProjectRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfProjectOut]:
    item = await service.wf_project_manager.create(body.model_dump())
    return DataResponseSchema[WfProjectOut](data=WfProjectOut.model_validate(item))


@workforce_router.put("/projects/{project_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_project(
    project_id: UUID,
    body: UpdateWfProjectRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfProjectOut]:
    item = await service.wf_project_manager.update_by_id(project_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return DataResponseSchema[WfProjectOut](data=WfProjectOut.model_validate(item))


@workforce_router.delete("/projects/{project_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_project(
    project_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    await service.wf_project_manager.delete_by_id(project_id)
    return DataResponseSchema[dict](data={"deleted": str(project_id)})


# ── WfProjectObject ───────────────────────────────────────────────────────────


@workforce_router.get("/projects/{project_id}/objects", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_project_objects(
    project_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[WfProjectObjectSchema]:
    items = await service.wf_project_object_manager.search(project_id=project_id)
    return ListDataResponseSchema[WfProjectObjectSchema].create(
        list_data=[WfProjectObjectSchema.model_validate(i) for i in items],
    )


@workforce_router.post(
    "/projects/{project_id}/objects",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
    status_code=201,
)
@catch_all_exceptions
async def create_project_object(
    project_id: UUID,
    body: CreateWfProjectObjectRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfProjectObjectSchema]:
    data = body.model_dump()
    data["project_id"] = project_id
    item = await service.wf_project_object_manager.create(data)
    return DataResponseSchema[WfProjectObjectSchema](data=WfProjectObjectSchema.model_validate(item))


@workforce_router.delete("/objects/{object_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_project_object(
    object_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    await service.wf_project_object_manager.delete_by_id(object_id)
    return DataResponseSchema[dict](data={"deleted": str(object_id)})


# ── WorkforceNorm ─────────────────────────────────────────────────────────────


@workforce_router.get("/norms", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_norms(
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[WfWorkforceNormSchema]:
    items = await service.wf_workforce_norm_manager.search(order_by=["work_type_id"])
    return ListDataResponseSchema[WfWorkforceNormSchema].create(
        list_data=[WfWorkforceNormSchema.model_validate(i) for i in items],
    )


@workforce_router.post("/norms", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_norm(
    body: CreateWfWorkforceNormRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfWorkforceNormSchema]:
    item = await service.wf_workforce_norm_manager.create(body.model_dump())
    return DataResponseSchema[WfWorkforceNormSchema](data=WfWorkforceNormSchema.model_validate(item))


@workforce_router.delete("/norms/{norm_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_norm(
    norm_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    await service.wf_workforce_norm_manager.delete_by_id(norm_id)
    return DataResponseSchema[dict](data={"deleted": str(norm_id)})


# ── HeadcountFact ─────────────────────────────────────────────────────────────


@workforce_router.get("/headcount/facts", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_headcount_facts(
    project_id: Optional[UUID] = Query(None),
    object_id: Optional[UUID] = Query(None),
    pagination: PaginationParams = Depends(pagination_params),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[WfHeadcountFactSchema]:
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if object_id:
        filters["object_id"] = object_id
    items = await service.wf_headcount_fact_manager.search(order_by=["-fact_date"], **filters)
    total = await service.wf_headcount_fact_manager.count(**filters)
    return ListDataResponseSchema[WfHeadcountFactSchema].create(
        list_data=[WfHeadcountFactSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@workforce_router.post("/headcount/facts", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_headcount_fact(
    body: CreateWfHeadcountFactRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfHeadcountFactSchema]:
    item = await service.wf_headcount_fact_manager.create(body.model_dump())
    return DataResponseSchema[WfHeadcountFactSchema](data=WfHeadcountFactSchema.model_validate(item))


# ── HeadcountPlan ─────────────────────────────────────────────────────────────


@workforce_router.get("/headcount/plans", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_headcount_plans(
    project_id: Optional[UUID] = Query(None),
    period_month: Optional[date] = Query(None),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[WfHeadcountPlanSchema]:
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if period_month:
        filters["period_month"] = period_month
    items = await service.wf_headcount_plan_manager.search(order_by=["-period_month"], **filters)
    return ListDataResponseSchema[WfHeadcountPlanSchema].create(
        list_data=[WfHeadcountPlanSchema.model_validate(i) for i in items],
    )


@workforce_router.post("/headcount/plans", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_headcount_plan(
    body: CreateWfHeadcountPlanRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[WfHeadcountPlanSchema]:
    item = await service.wf_headcount_plan_manager.create(body.model_dump())
    return DataResponseSchema[WfHeadcountPlanSchema](data=WfHeadcountPlanSchema.model_validate(item))


# ── Challenge ─────────────────────────────────────────────────────────────────


@workforce_router.get("/challenges", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_challenges(
    project_id: Optional[UUID] = Query(None),
    object_id: Optional[UUID] = Query(None),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ChallengeSchema]:
    filters: dict = {}
    if project_id:
        filters["project_id"] = project_id
    if object_id:
        filters["object_id"] = object_id
    items = await service.wf_challenge_manager.search(order_by=["-period_month"], **filters)
    return ListDataResponseSchema[ChallengeSchema].create(
        list_data=[ChallengeSchema.model_validate(i) for i in items],
    )


@workforce_router.post("/challenges", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_challenge(
    body: CreateChallengeRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ChallengeSchema]:
    data = body.model_dump(exclude={"items"})
    challenge = await service.wf_challenge_manager.create(data, commit=False)

    for item_data in body.items:
        item_dict = item_data.model_dump()
        item_dict["challenge_id"] = challenge.id
        await service.wf_challenge_item_manager.create(item_dict, commit=False)

    await service.wf_challenge_manager.db.commit()
    await service.wf_challenge_manager.db.refresh(challenge)

    return DataResponseSchema[ChallengeSchema](data=ChallengeSchema.model_validate(challenge))


@workforce_router.patch("/challenges/{challenge_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_challenge(
    challenge_id: UUID,
    body: UpdateChallengeRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ChallengeSchema]:
    item = await service.wf_challenge_manager.update_by_id(challenge_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return DataResponseSchema[ChallengeSchema](data=ChallengeSchema.model_validate(item))


@workforce_router.post(
    "/challenges/{challenge_id}/check-checkpoints",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def check_challenge_checkpoints(
    challenge_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    count = await service.check_challenge_checkpoints(challenge_id)
    return DataResponseSchema[dict](data={"updated_checkpoints": count})


# ── Violations ────────────────────────────────────────────────────────────────


@workforce_router.get("/violations", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_violations(
    filters: WfViolationFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ViolationOut]:
    filter_data = filters.model_dump(exclude_none=True)
    raw = await service.wf_violation_manager.search(order_by=["-violation_date"], **filter_data)
    enriched = await service.enrich_violations(raw)
    total = await service.wf_violation_manager.count(**filter_data)
    return ListDataResponseSchema[ViolationOut].create(
        list_data=[item.model_dump() for item in enriched],
        pagination=pagination,
        total=total,
    )


@workforce_router.post("/violations", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_violation(
    body: CreateViolationRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ViolationOut]:
    item = await service.wf_violation_manager.create(body.model_dump())
    enriched = await service.enrich_violations([item])
    return DataResponseSchema[ViolationOut](data=enriched[0])


@workforce_router.patch("/violations/{violation_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_violation(
    violation_id: UUID,
    body: UpdateViolationRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ViolationOut]:
    item = await service.wf_violation_manager.update_by_id(violation_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Violation not found")
    enriched = await service.enrich_violations([item])
    return DataResponseSchema[ViolationOut](data=enriched[0])


@workforce_router.post("/violations/scan", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def scan_violations(
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ViolationScanResult]:
    result = await service.scan_violations()
    return DataResponseSchema[ViolationScanResult](data=result)


@workforce_router.post("/violations/auto-escalate", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def auto_escalate_violations(
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    count = await service.auto_escalate_violations()
    return DataResponseSchema[dict](data={"escalated": count})


# ── ArticleBDR ────────────────────────────────────────────────────────────────


@workforce_router.get("/article-bdrs", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_article_bdrs(
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ArticleBDRSchema]:
    items = await service.article_bdr_manager.search(order_by=["code_1c"])
    return ListDataResponseSchema[ArticleBDRSchema].create(
        list_data=[ArticleBDRSchema.model_validate(i) for i in items],
    )


@workforce_router.post("/article-bdrs", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_article_bdr(
    body: CreateArticleBDRRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ArticleBDRSchema]:
    item = await service.article_bdr_manager.create(body.model_dump())
    return DataResponseSchema[ArticleBDRSchema](data=ArticleBDRSchema.model_validate(item))


@workforce_router.post("/article-bdrs/bulk", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def bulk_create_article_bdrs(
    body: ArticleBDRBulkRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    data = [item.model_dump() for item in body.items]
    await service.article_bdr_manager.bulk_insert(data, is_commit=True)
    return DataResponseSchema[dict](data={"created": len(data)})


@workforce_router.delete("/article-bdrs/{article_bdr_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_article_bdr(
    article_bdr_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    await service.article_bdr_manager.delete_by_id(article_bdr_id)
    return DataResponseSchema[dict](data={"deleted": str(article_bdr_id)})


# ── ArticleMapping ────────────────────────────────────────────────────────────


@workforce_router.get("/article-mappings", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_article_mappings(
    article_bdr_id: Optional[UUID] = Query(None),
    service: WorkforceService = Depends(get_workforce_service),
) -> ListDataResponseSchema[ArticleMappingSchema]:
    filters: dict = {}
    if article_bdr_id:
        filters["article_bdr_id"] = article_bdr_id
    items = await service.wf_article_mapping_manager.search(**filters)
    return ListDataResponseSchema[ArticleMappingSchema].create(
        list_data=[ArticleMappingSchema.model_validate(i) for i in items],
    )


@workforce_router.post("/article-mappings", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_article_mapping(
    body: CreateArticleMappingRequest,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[ArticleMappingSchema]:
    item = await service.wf_article_mapping_manager.create(body.model_dump())
    return DataResponseSchema[ArticleMappingSchema](data=ArticleMappingSchema.model_validate(item))


@workforce_router.delete("/article-mappings/{mapping_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_article_mapping(
    mapping_id: UUID,
    service: WorkforceService = Depends(get_workforce_service),
) -> DataResponseSchema[dict]:
    await service.wf_article_mapping_manager.delete_by_id(mapping_id)
    return DataResponseSchema[dict](data={"deleted": str(mapping_id)})
