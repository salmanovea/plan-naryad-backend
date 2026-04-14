"""
Сервис расчёта показателей управления численностью.
v2: поддержка уровня объектов (ProjectObject) + план от стройки (HeadcountPlan)
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from collections import defaultdict
import math

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workforce import (
    Project, ProjectObject, WorkforceNorm, BudgetPeriod, BudgetItem,
    HeadcountFact, HeadcountPlan,
    WfContractor, WfContractorAssignment,
    Challenge, ChallengeItem, MobilizationPlan, MobilizationCheckpoint,
    Violation, CheckpointStatus, ViolationType,
)
from ..schemas.workforce import (
    WorkTypeRow, ObjectDashboardItem, ProjectRow,
    DashboardResponse, ProjectDetailResponse, ProjectOut,
    ForecastRow, ForecastResponse,
    ContractorHeadcountRow,
    ContractorRatingRow,
    SystemProblemRow, SystemProblemsResponse,
)


def _traffic_light(coverage_pct: Optional[float]) -> str:
    if coverage_pct is None:
        return "grey"
    if coverage_pct >= 85:
        return "green"
    if coverage_pct >= 60:
        return "yellow"
    return "red"


def _trend(fact_7d: float, fact_30d: float) -> str:
    if fact_30d == 0 and fact_7d == 0:
        return "no_data"
    if fact_30d == 0:
        return "up"
    ratio = fact_7d / fact_30d
    if ratio > 1.05:
        return "up"
    if ratio < 0.95:
        return "down"
    return "stable"


async def _get_headcount_avg(
    db: AsyncSession, project_id: UUID, days: int,
    object_id: Optional[UUID] = None,
) -> Dict[str, float]:
    since = date.today() - timedelta(days=days)
    q = (
        select(HeadcountFact.work_type, func.avg(HeadcountFact.count).label("avg"))
        .where(HeadcountFact.project_id == project_id, HeadcountFact.fact_date >= since)
        .group_by(HeadcountFact.work_type)
    )
    if object_id is not None:
        q = q.where(HeadcountFact.object_id == object_id)
    result = await db.execute(q)
    return {r.work_type: float(r.avg) for r in result.all()}


async def _get_plans(
    db: AsyncSession, project_id: UUID, period_month: date,
    object_id: Optional[UUID] = None,
) -> Dict[str, int]:
    q = (
        select(HeadcountPlan.work_type, HeadcountPlan.planned_count)
        .where(HeadcountPlan.project_id == project_id, HeadcountPlan.period_month == period_month)
    )
    if object_id is not None:
        q = q.where(HeadcountPlan.object_id == object_id)
    result = await db.execute(q)
    return {r.work_type: r.planned_count for r in result.all()}


def _build_work_type_rows(
    items: List[BudgetItem],
    norms: Dict[str, WorkforceNorm],
    fact_30d: Dict[str, float],
    fact_7d: Dict[str, float],
    plans: Dict[str, int],
) -> List[WorkTypeRow]:
    # Агрегируем строки бюджета по work_type — после внедрения детальных
    # статей бюджета (detailed_article) на один work_type может приходиться
    # несколько строк (разные коды статей маппятся в один укрупнённый вид).
    from collections import namedtuple
    Aggregated = namedtuple("Aggregated", ["work_type", "bdr_amount", "management_completion_amount"])
    agg: Dict[str, list] = {}
    for it in items:
        if it.work_type not in agg:
            agg[it.work_type] = [Decimal(0), Decimal(0)]
        agg[it.work_type][0] += it.bdr_amount
        agg[it.work_type][1] += it.management_completion_amount
    aggregated_items = [Aggregated(wt, vals[0], vals[1]) for wt, vals in agg.items()]

    rows = []
    for item in aggregated_items:
        net_bdr = item.bdr_amount - item.management_completion_amount
        uv_pct = float(item.management_completion_amount / item.bdr_amount * 100) if item.bdr_amount else 0.0

        norm = norms.get(item.work_type)
        norm_day = norm.median_day_bdr if norm else None
        norm_month = float(norm.median_month_bdr) if norm and norm.median_month_bdr else (float(norm_day) * 22 if norm_day else None)
        required = float(net_bdr) / norm_month if norm_month and norm_month > 0 else None

        f30 = fact_30d.get(item.work_type, 0.0)
        f7 = fact_7d.get(item.work_type, 0.0)
        plan = plans.get(item.work_type)

        coverage = f30 / required * 100 if required and required > 0 else None
        cov_report = f30 / plan * 100 if plan and plan > 0 else None

        rows.append(WorkTypeRow(
            work_type=item.work_type,
            bdr_amount=item.bdr_amount,
            management_completion_amount=item.management_completion_amount,
            uv_pct=round(uv_pct, 1),
            net_bdr=net_bdr,
            norm_day=norm_day,
            required_headcount=round(required, 1) if required is not None else None,
            plan_report=plan,
            fact_30d=round(f30, 1),
            fact_7d=round(f7, 1),
            coverage_pct=round(coverage, 1) if coverage is not None else None,
            coverage_report_pct=round(cov_report, 1) if cov_report is not None else None,
            trend=_trend(f7, f30),
            traffic_light=_traffic_light(coverage),
            traffic_light_report=_traffic_light(cov_report),
        ))
    return rows


async def calc_project_detail(
    db: AsyncSession, project: Project, period_month: Optional[date] = None,
) -> ProjectDetailResponse:
    """Детализация проекта с уровнем объектов."""
    # Budget period
    bp_q = (
        select(BudgetPeriod).where(BudgetPeriod.project_id == project.id)
        .order_by(BudgetPeriod.period_month.desc())
    )
    if period_month:
        bp_q = bp_q.where(BudgetPeriod.period_month == period_month)
    bp = (await db.execute(bp_q.limit(1))).scalar_one_or_none()
    if not bp:
        return ProjectDetailResponse(project=ProjectOut.model_validate(project), period_month=None, objects=[], work_types=[])

    # Items
    all_items = (await db.execute(select(BudgetItem).where(BudgetItem.budget_period_id == bp.id))).scalars().all()
    # Norms
    norms_result = await db.execute(select(WorkforceNorm).where(WorkforceNorm.project_class == project.project_class))
    norms = {n.work_type: n for n in norms_result.scalars().all()}
    # Objects
    objs_result = await db.execute(select(ProjectObject).where(ProjectObject.project_id == project.id))
    objects = objs_result.scalars().all()

    # Group items by object
    items_by_obj: Dict[Optional[UUID], List[BudgetItem]] = defaultdict(list)
    for it in all_items:
        items_by_obj[it.object_id].append(it)

    obj_dashboard_items = []
    for obj in objects:
        obj_items = items_by_obj.get(obj.id, [])
        if not obj_items:
            continue
        f30 = await _get_headcount_avg(db, project.id, 30, obj.id)
        f7 = await _get_headcount_avg(db, project.id, 7, obj.id)
        plans = await _get_plans(db, project.id, bp.period_month, obj.id)
        wt_rows = _build_work_type_rows(obj_items, norms, f30, f7, plans)

        obj_net = sum(r.net_bdr for r in wt_rows)
        obj_req = sum(r.required_headcount for r in wt_rows if r.required_headcount) or None
        obj_plan = sum(r.plan_report for r in wt_rows if r.plan_report) or None
        obj_f30 = sum(r.fact_30d for r in wt_rows)
        obj_f7 = sum(r.fact_7d for r in wt_rows)
        obj_cov = obj_f30 / obj_req * 100 if obj_req and obj_req > 0 else None
        obj_cov_r = obj_f30 / obj_plan * 100 if obj_plan and obj_plan > 0 else None

        top_p = None
        covered = [r for r in wt_rows if r.coverage_pct is not None]
        if covered:
            worst = min(covered, key=lambda r: r.coverage_pct)
            if worst.coverage_pct is not None and worst.coverage_pct < 85:
                top_p = worst.work_type

        obj_dashboard_items.append(ObjectDashboardItem(
            id=obj.id, name=obj.name,
            net_bdr=obj_net,
            required_headcount=round(obj_req, 1) if obj_req else None,
            plan_report=obj_plan,
            fact_30d=round(obj_f30, 1), fact_7d=round(obj_f7, 1),
            coverage_pct=round(obj_cov, 1) if obj_cov else None,
            coverage_report_pct=round(obj_cov_r, 1) if obj_cov_r else None,
            trend=_trend(obj_f7, obj_f30),
            traffic_light=_traffic_light(obj_cov),
            traffic_light_report=_traffic_light(obj_cov_r),
            top_problem=top_p,
            work_types=wt_rows,
        ))

    # Aggregated work types (backward compat + items without object)
    agg_f30 = await _get_headcount_avg(db, project.id, 30)
    agg_f7 = await _get_headcount_avg(db, project.id, 7)
    agg_plans = await _get_plans(db, project.id, bp.period_month)
    agg_rows = _build_work_type_rows(all_items, norms, agg_f30, agg_f7, agg_plans)

    # Project KPIs
    p_net = sum(r.net_bdr for r in agg_rows)
    p_req = sum(r.required_headcount for r in agg_rows if r.required_headcount) or None
    p_plan = sum(r.plan_report for r in agg_rows if r.plan_report) or None
    p_f30 = sum(r.fact_30d for r in agg_rows)
    p_f7 = sum(r.fact_7d for r in agg_rows)
    p_cov = p_f30 / p_req * 100 if p_req and p_req > 0 else None
    p_cov_r = p_f30 / p_plan * 100 if p_plan and p_plan > 0 else None

    return ProjectDetailResponse(
        project=ProjectOut.model_validate(project),
        period_month=bp.period_month,
        net_bdr=p_net,
        required_headcount=round(p_req, 1) if p_req else None,
        plan_report=p_plan,
        fact_30d=round(p_f30, 1),
        fact_7d=round(p_f7, 1),
        coverage_pct=round(p_cov, 1) if p_cov else None,
        coverage_report_pct=round(p_cov_r, 1) if p_cov_r else None,
        trend=_trend(p_f7, p_f30),
        traffic_light=_traffic_light(p_cov),
        traffic_light_report=_traffic_light(p_cov_r),
        objects=obj_dashboard_items,
        work_types=agg_rows,
    )


async def calc_dashboard(db: AsyncSession) -> DashboardResponse:
    projects = (await db.execute(select(Project))).scalars().all()
    rows = []
    total_net = Decimal("0")
    total_req = 0.0
    total_f30 = 0.0
    has_req = False

    for proj in projects:
        detail = await calc_project_detail(db, proj)
        pn = detail.net_bdr or Decimal("0")
        pr = detail.required_headcount or 0.0
        pf = detail.fact_30d or 0.0
        cov = detail.coverage_pct

        total_net += pn
        total_f30 += pf
        if pr:
            total_req += pr
            has_req = True

        top_p = None
        if detail.objects:
            worst_objs = [o for o in detail.objects if o.coverage_pct is not None]
            if worst_objs:
                wo = min(worst_objs, key=lambda o: o.coverage_pct)
                if wo.coverage_pct < 85:
                    top_p = f"{wo.name}: {wo.top_problem or '?'}"
        if not top_p and detail.work_types:
            covered = [r for r in detail.work_types if r.coverage_pct is not None]
            if covered:
                w = min(covered, key=lambda r: r.coverage_pct)
                if w.coverage_pct < 85:
                    top_p = w.work_type

        rows.append(ProjectRow(
            id=proj.id, name=proj.name, project_class=proj.project_class,
            net_bdr=pn,
            required_headcount=round(pr, 1) if pr else None,
            fact_30d=round(pf, 1),
            coverage_pct=round(cov, 1) if cov else None,
            trend=detail.trend or "no_data",
            top_problem=top_p,
            traffic_light=detail.traffic_light or "grey",
        ))

    rows.sort(key=lambda r: r.coverage_pct if r.coverage_pct is not None else 9999)
    port_cov = round(total_f30 / total_req * 100, 1) if has_req and total_req > 0 else None

    return DashboardResponse(
        total_net_bdr=total_net,
        total_required=round(total_req, 1) if has_req else None,
        total_fact_30d=round(total_f30, 1),
        portfolio_coverage_pct=port_cov,
        projects=rows,
    )


# ── Forecast ──────────────────────────────────────────────────────────────────

async def calc_forecast(db: AsyncSession, project_id: UUID) -> ForecastResponse:
    """
    Прогноз завершения по объектам × видам работ.
    forecast_date = today + (remaining_amount / (fact_30d * norm_month))
    delay_months = (forecast_date - planned_end_date).days / 30
    """
    today = date.today()

    # Get all objects for project
    objects = (await db.execute(
        select(ProjectObject).where(ProjectObject.project_id == project_id)
    )).scalars().all()
    obj_map = {o.id: o for o in objects}

    # Get norms
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    norms_result = await db.execute(select(WorkforceNorm))
    norms = {(n.work_type, n.project_class): n for n in norms_result.scalars().all()}

    # Get latest budget period items with remaining_amount
    bp = (await db.execute(
        select(BudgetPeriod)
        .where(BudgetPeriod.project_id == project_id)
        .order_by(BudgetPeriod.period_month.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not bp:
        return ForecastResponse(project_id=project_id, rows=[])

    items = (await db.execute(
        select(BudgetItem).where(BudgetItem.budget_period_id == bp.id)
    )).scalars().all()

    # Fact avg per object × work_type for last 30d
    since = today - timedelta(days=30)
    fact_rows = (await db.execute(
        select(
            HeadcountFact.object_id,
            HeadcountFact.work_type,
            func.avg(HeadcountFact.count).label("avg"),
        )
        .where(HeadcountFact.project_id == project_id, HeadcountFact.fact_date >= since)
        .group_by(HeadcountFact.object_id, HeadcountFact.work_type)
    )).all()
    fact_map: Dict[Tuple, float] = {(r.object_id, r.work_type): float(r.avg) for r in fact_rows}

    rows = []
    for item in items:
        if item.object_id is None:
            continue
        obj = obj_map.get(item.object_id)
        if obj is None:
            continue

        proj_class = project.project_class if project else "Комфорт"
        norm = norms.get((item.work_type, proj_class))
        norm_month = float(norm.median_month_bdr) if norm else None

        f30 = fact_map.get((item.object_id, item.work_type), 0.0)
        remaining = item.remaining_amount
        planned_end = item.planned_end_date or obj.planned_end_date

        forecast_date = None
        months_needed = None
        delay_months = None

        if remaining is not None and norm_month and norm_month > 0 and f30 > 0:
            months_needed = float(remaining) / (f30 * norm_month)
            days_needed = int(months_needed * 30)
            forecast_date = today + timedelta(days=days_needed)
            if planned_end:
                delay_months = round((forecast_date - planned_end).days / 30, 1)

        rows.append(ForecastRow(
            object_id=obj.id,
            object_name=obj.name,
            work_type=item.work_type,
            remaining_amount=remaining,
            planned_end_date=planned_end,
            fact_30d=round(f30, 1),
            norm_month=round(norm_month, 0) if norm_month else None,
            months_needed=round(months_needed, 1) if months_needed else None,
            forecast_date=forecast_date,
            delay_months=delay_months,
        ))

    return ForecastResponse(project_id=project_id, rows=rows)


# ── WfContractor headcount by object ────────────────────────────────────────────

async def calc_object_contractors(
    db: AsyncSession, object_id: UUID,
) -> List[ContractorHeadcountRow]:
    """Численность по подрядчикам на объекте."""
    today = date.today()
    since = today - timedelta(days=30)

    # Get the period for plans
    period = today.replace(day=1)

    # Facts per contractor × work_type
    fact_rows = (await db.execute(
        select(
            HeadcountFact.contractor_id,
            HeadcountFact.work_type,
            func.avg(HeadcountFact.count).label("avg"),
        )
        .where(HeadcountFact.object_id == object_id, HeadcountFact.fact_date >= since)
        .group_by(HeadcountFact.contractor_id, HeadcountFact.work_type)
    )).all()

    # Plans per contractor × work_type
    plan_rows = (await db.execute(
        select(
            HeadcountPlan.contractor_id,
            HeadcountPlan.work_type,
            HeadcountPlan.planned_count,
        )
        .where(HeadcountPlan.object_id == object_id, HeadcountPlan.period_month == period)
    )).all()
    plan_map = {(r.contractor_id, r.work_type): r.planned_count for r in plan_rows}

    # WfContractor names
    contractor_ids = {r.contractor_id for r in fact_rows if r.contractor_id}
    contractors: Dict[UUID, str] = {}
    if contractor_ids:
        c_rows = (await db.execute(
            select(WfContractor).where(WfContractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c.name for c in c_rows}

    result = []
    for r in fact_rows:
        f30 = float(r.avg)
        plan = plan_map.get((r.contractor_id, r.work_type))
        cov = round(f30 / plan * 100, 1) if plan and plan > 0 else None
        cname = contractors.get(r.contractor_id, "Без подрядчика") if r.contractor_id else "Без подрядчика"
        result.append(ContractorHeadcountRow(
            contractor_id=r.contractor_id,
            contractor_name=cname,
            work_type=r.work_type,
            plan=plan,
            fact_30d=round(f30, 1),
            coverage_pct=cov,
        ))
    return result


# ── Analytics ─────────────────────────────────────────────────────────────────

async def calc_system_problems(
    db: AsyncSession,
    threshold_pct: float = 50.0,
    min_objects: int = 3,
) -> SystemProblemsResponse:
    """
    Виды работ с < threshold_pct% обеспечением в min_objects+ объектах.
    """
    today = date.today()
    since = today - timedelta(days=30)

    # Avg fact per object × work_type
    fact_rows = (await db.execute(
        select(
            HeadcountFact.object_id,
            HeadcountFact.work_type,
            func.avg(HeadcountFact.count).label("avg"),
        )
        .where(HeadcountFact.fact_date >= since)
        .group_by(HeadcountFact.object_id, HeadcountFact.work_type)
    )).all()

    # Get norms
    norms_result = await db.execute(select(WorkforceNorm))
    norms_list = norms_result.scalars().all()

    # Get all budget items (latest period per project)
    projects = (await db.execute(select(Project))).scalars().all()
    required_map: Dict[Tuple, float] = {}  # (object_id, work_type) -> required

    for proj in projects:
        bp = (await db.execute(
            select(BudgetPeriod)
            .where(BudgetPeriod.project_id == proj.id)
            .order_by(BudgetPeriod.period_month.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not bp:
            continue
        norms = {n.work_type: n for n in norms_list if n.project_class == proj.project_class}
        items = (await db.execute(
            select(BudgetItem).where(BudgetItem.budget_period_id == bp.id)
        )).scalars().all()
        for item in items:
            if item.object_id is None:
                continue
            norm = norms.get(item.work_type)
            if not norm:
                continue
            nm = float(norm.median_month_bdr)
            net = float(item.bdr_amount - item.management_completion_amount)
            if nm > 0:
                required_map[(item.object_id, item.work_type)] = net / nm

    fact_by_key: Dict[Tuple, float] = {(r.object_id, r.work_type): float(r.avg) for r in fact_rows}

    # Get object names
    objects = (await db.execute(select(ProjectObject))).scalars().all()
    obj_names = {o.id: o.name for o in objects}

    # Coverage per work_type → list of (object_id, coverage_pct)
    coverage_by_wt: Dict[str, List[Tuple]] = defaultdict(list)
    for (obj_id, wt), req in required_map.items():
        if req <= 0:
            continue
        fact = fact_by_key.get((obj_id, wt), 0.0)
        cov = fact / req * 100
        coverage_by_wt[wt].append((obj_id, cov))

    problems = []
    for wt, entries in coverage_by_wt.items():
        below = [(oid, cov) for oid, cov in entries if cov < threshold_pct]
        if len(below) >= min_objects:
            avg_cov = round(sum(c for _, c in below) / len(below), 1)
            problems.append(SystemProblemRow(
                work_type=wt,
                affected_objects=len(below),
                avg_coverage_pct=avg_cov,
                object_names=[obj_names.get(oid, str(oid)) for oid, _ in below],
            ))

    problems.sort(key=lambda r: r.avg_coverage_pct or 9999)
    return SystemProblemsResponse(
        threshold_pct=threshold_pct,
        min_objects=min_objects,
        problems=problems,
    )


async def calc_contractor_rating(db: AsyncSession) -> List[ContractorRatingRow]:
    """
    Рейтинг подрядчиков:
    - Средняя обеспеченность (факт/план) за 3 мес
    - Количество нарушений
    - Количество пропущенных КТ
    """
    today = date.today()
    since_3m = today - timedelta(days=90)
    period = today.replace(day=1)

    contractors = (await db.execute(select(WfContractor))).scalars().all()

    rows = []
    for c in contractors:
        # Coverage: avg(fact) / avg(plan) for last 3 months
        fact_avg = (await db.execute(
            select(func.avg(HeadcountFact.count))
            .where(HeadcountFact.contractor_id == c.id, HeadcountFact.fact_date >= since_3m)
        )).scalar()

        plan_sum = (await db.execute(
            select(func.sum(HeadcountPlan.planned_count))
            .where(
                HeadcountPlan.contractor_id == c.id,
                HeadcountPlan.period_month >= since_3m.replace(day=1),
            )
        )).scalar()

        avg_cov = None
        if fact_avg is not None and plan_sum:
            avg_cov = round(float(fact_avg) / (float(plan_sum) / 3) * 100, 1)

        # Violations
        v_count = (await db.execute(
            select(func.count(Violation.id)).where(Violation.contractor_id == c.id)
        )).scalar() or 0

        # Missed checkpoints
        missed = (await db.execute(
            select(func.count(MobilizationCheckpoint.id))
            .join(MobilizationPlan, MobilizationCheckpoint.mobilization_plan_id == MobilizationPlan.id)
            .join(ChallengeItem, MobilizationPlan.challenge_item_id == ChallengeItem.id)
            .join(Challenge, ChallengeItem.challenge_id == Challenge.id)
            .join(ProjectObject, Challenge.object_id == ProjectObject.id)
            .join(WfContractorAssignment, (
                WfContractorAssignment.object_id == ProjectObject.id
            ))
            .where(
                WfContractorAssignment.contractor_id == c.id,
                MobilizationCheckpoint.status == CheckpointStatus.MISSED,
            )
        )).scalar() or 0

        # Rating score: coverage_pct * 0.5 - violations * 10 - missed * 5
        cov_score = (avg_cov or 0.0) * 0.5
        rating = round(cov_score - v_count * 10 - missed * 5, 1)

        rows.append(ContractorRatingRow(
            contractor_id=c.id,
            contractor_name=c.name,
            avg_coverage_pct=avg_cov,
            violation_count=v_count,
            missed_checkpoints=missed,
            rating_score=rating,
        ))

    rows.sort(key=lambda r: r.rating_score, reverse=True)
    return rows


async def check_challenge_checkpoints(db: AsyncSession, challenge_id: UUID) -> int:
    """
    Проверяет контрольные точки у плана мобилизации.
    Обновляет статус КТ и создаёт нарушения если нужно.
    Возвращает количество обновлённых записей.
    """
    today = date.today()

    # Get challenge
    challenge = (await db.execute(
        select(Challenge).where(Challenge.id == challenge_id)
    )).scalar_one_or_none()
    if not challenge:
        return 0

    # Get all checkpoints due today or earlier
    checkpoints = (await db.execute(
        select(MobilizationCheckpoint)
        .join(MobilizationPlan, MobilizationCheckpoint.mobilization_plan_id == MobilizationPlan.id)
        .join(ChallengeItem, MobilizationPlan.challenge_item_id == ChallengeItem.id)
        .where(
            ChallengeItem.challenge_id == challenge_id,
            MobilizationCheckpoint.check_date <= today,
            MobilizationCheckpoint.status == CheckpointStatus.PENDING,
        )
    )).scalars().all()

    updated = 0
    for cp in checkpoints:
        if cp.actual_cumulative is None:
            cp.status = CheckpointStatus.MISSED
        elif cp.actual_cumulative >= cp.expected_cumulative:
            cp.status = CheckpointStatus.MET
        else:
            cp.status = CheckpointStatus.MISSED

        if cp.status == CheckpointStatus.MISSED and not cp.violation_recorded:
            cp.violation_recorded = True
            # Get work_type from parent chain
            mp = (await db.execute(
                select(MobilizationPlan).where(MobilizationPlan.id == cp.mobilization_plan_id)
            )).scalar_one_or_none()
            if mp:
                ci = (await db.execute(
                    select(ChallengeItem).where(ChallengeItem.id == mp.challenge_item_id)
                )).scalar_one_or_none()
                if ci:
                    db.add(Violation(
                        project_id=challenge.project_id,
                        object_id=challenge.object_id,
                        work_type=ci.work_type,
                        violation_date=today,
                        violation_type=ViolationType.MOBILIZATION_MISSED,
                        description=f"Пропущена контрольная точка мобилизации: ожидалось {cp.expected_cumulative}, факт {cp.actual_cumulative or 0}",
                        plan_count=cp.expected_cumulative,
                        fact_count=cp.actual_cumulative or 0,
                    ))
        updated += 1

    await db.commit()
    return updated


# ── Violation auto-scan ───────────────────────────────────────────────────────

async def scan_violations(db: AsyncSession) -> list:
    """
    Scan all objects for violations:
    - coverage_critical: coverage < 60%
    - plan_not_met: fact_30d < plan_report
    Returns list of newly created violations.
    """
    from datetime import date as date_type
    projects = (await db.execute(select(Project))).scalars().all()
    new_violations = []
    today = date_type.today()

    for proj in projects:
        detail = await calc_project_detail(db, proj)
        for obj in (detail.objects or []):
            for wt in (obj.work_types or []):
                # Check coverage_critical
                if wt.coverage_pct is not None and wt.coverage_pct < 60 and wt.required_headcount and wt.required_headcount > 0:
                    # Check if violation already exists for this object+work_type this month
                    existing = await db.execute(
                        select(Violation).where(
                            Violation.object_id == obj.id,
                            Violation.work_type == wt.work_type,
                            Violation.violation_type == "coverage_critical",
                            Violation.violation_date >= today.replace(day=1),
                            Violation.resolved == False,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        v = Violation(
                            project_id=proj.id, object_id=obj.id,
                            work_type=wt.work_type,
                            violation_date=today,
                            violation_type="coverage_critical",
                            description=f"Обеспеченность {wt.coverage_pct:.0f}% (критично < 60%). Нужно {wt.required_headcount:.0f}, факт {wt.fact_30d:.0f}",
                            plan_count=int(wt.required_headcount),
                            fact_count=int(wt.fact_30d),
                        )
                        db.add(v)
                        new_violations.append(v)

                # Check plan_not_met
                if wt.plan_report and wt.fact_30d < wt.plan_report * 0.8:  # more than 20% below plan
                    existing = await db.execute(
                        select(Violation).where(
                            Violation.object_id == obj.id,
                            Violation.work_type == wt.work_type,
                            Violation.violation_type == "plan_not_met",
                            Violation.violation_date >= today.replace(day=1),
                            Violation.resolved == False,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        v = Violation(
                            project_id=proj.id, object_id=obj.id,
                            work_type=wt.work_type,
                            violation_date=today,
                            violation_type="plan_not_met",
                            description=f"Факт {wt.fact_30d:.0f} < План рапорта {wt.plan_report} (невыполнение > 20%)",
                            plan_count=wt.plan_report,
                            fact_count=int(wt.fact_30d),
                        )
                        db.add(v)
                        new_violations.append(v)

    if new_violations:
        await db.commit()
    return new_violations


async def enrich_violations(db: AsyncSession, violations: list) -> list:
    """Add project_name, object_name, contractor_name to violations."""
    # Cache lookups
    proj_cache = {}
    obj_cache = {}
    contr_cache = {}

    result = []
    for v in violations:
        if v.project_id not in proj_cache:
            p = (await db.execute(select(Project).where(Project.id == v.project_id))).scalar_one_or_none()
            proj_cache[v.project_id] = p.name if p else "?"
        if v.object_id not in obj_cache:
            o = (await db.execute(select(ProjectObject).where(ProjectObject.id == v.object_id))).scalar_one_or_none()
            obj_cache[v.object_id] = o.name if o else "?"
        if v.contractor_id and v.contractor_id not in contr_cache:
            c = (await db.execute(select(WfContractor).where(WfContractor.id == v.contractor_id))).scalar_one_or_none()
            contr_cache[v.contractor_id] = c.name if c else None

        from ..schemas.workforce import ViolationOut
        result.append(ViolationOut(
            id=v.id, project_id=v.project_id, object_id=v.object_id,
            work_type=v.work_type, contractor_id=v.contractor_id,
            violation_date=v.violation_date, violation_type=v.violation_type,
            description=v.description, plan_count=v.plan_count, fact_count=v.fact_count,
            escalated=v.escalated, escalated_to=v.escalated_to, resolved=v.resolved,
            project_name=proj_cache.get(v.project_id),
            object_name=obj_cache.get(v.object_id),
            contractor_name=contr_cache.get(v.contractor_id) if v.contractor_id else None,
        ))
    return result


async def auto_escalate_violations(db: AsyncSession) -> int:
    """
    Автоэскалация нарушений по таймеру:
    - >7 дней без эскалации → Руководитель по строительству
    - >14 дней на уровне Рук. стр-ва → Директор по строительству
    - >21 день на уровне Дир. стр-ва → Директор проекта
    """
    from datetime import date as date_type, timedelta
    today = date_type.today()
    escalated_count = 0

    # Get all open (unresolved) violations
    result = await db.execute(
        select(Violation).where(Violation.resolved == False)
    )
    violations = result.scalars().all()

    for v in violations:
        days_open = (today - v.violation_date).days

        if not v.escalated and days_open >= 7:
            v.escalated = True
            v.escalated_to = "Руководитель по строительству"
            escalated_count += 1
        elif v.escalated_to == "Руководитель по строительству" and days_open >= 14:
            v.escalated_to = "Директор по строительству"
            escalated_count += 1
        elif v.escalated_to == "Директор по строительству" and days_open >= 21:
            v.escalated_to = "Директор проекта"
            escalated_count += 1

    if escalated_count:
        await db.commit()

    return escalated_count
