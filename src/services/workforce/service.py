from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import NamedEntitySchema
from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo import models as m
from src.models.dbo.tables.project_structure import Project
from src.models.dbo.tables.workforce import (
    CheckpointStatus,
    HeadcountNorm,
    ViolationType,
)
from src.services.access.service import AccessService
from src.services.common import BaseService
from src.services.workforce.schemas import (
    ContractorHeadcountRow,
    ContractorRatingRow,
    DashboardResponse,
    ForecastResponse,
    ForecastRow,
    ObjectDashboardItem,
    ProjectDetailResponse,
    ProjectRow,
    SystemProblemRow,
    SystemProblemsResponse,
    ViolationOut,
    ViolationScanResult,
    WfProjectOut,
    WorkTypeRow,
)
from src.utils.business_time import business_today


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


class WorkforceService(BaseService):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.access = AccessService(db)
        self.wf_project_manager = managers.ProjectManager(db)
        self.wf_project_object_manager = managers.ConstructionObjectManager(db)
        self.wf_workforce_norm_manager = managers.HeadcountNormManager(db)
        self.wf_budget_period_manager = managers.BudgetPeriodManager(db)
        self.wf_budget_item_manager = managers.BudgetItemManager(db)
        self.wf_headcount_fact_manager = managers.HeadcountFactManager(db)
        self.wf_headcount_plan_manager = managers.HeadcountPlanManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        # Public DTOs retain the historical 'work_type' key, but work_id now references Work.
        self.work_type_manager = managers.WorkManager(db)
        self.wf_contractor_assignment_manager = managers.ContractorAssignmentManager(db)
        self.wf_challenge_manager = managers.ChallengeManager(db)
        self.wf_challenge_item_manager = managers.ChallengeItemManager(db)
        self.wf_mobilization_plan_manager = managers.MobilizationPlanManager(db)
        self.wf_mobilization_checkpoint_manager = managers.MobilizationCheckpointManager(db)
        self.wf_violation_manager = managers.ViolationManager(db)
        self.article_bdr_manager = managers.ArticleBDRManager(db)
        self.wf_article_mapping_manager = managers.ArticleBDRWorkManager(db)

    async def _authorize_selectors(self, filters: dict[str, Any]) -> None:
        project_id = filters.get("project_id")
        object_id = filters.get("construction_object_id")
        if project_id:
            await self.access.require_project_object(project_id, object_id)
        elif object_id:
            await self.access.require_objects([object_id])
        if contractor_id := filters.get("contractor_id"):
            await self.access.require_contractors([contractor_id])

    async def _get_work_types_map(self, work_ids: Iterable[UUID]) -> Dict[UUID, NamedEntitySchema]:
        ids = list(set(work_ids))
        if not ids:
            return {}
        wt_list = await self.work_type_manager.get_by_ids(ids)
        return {wt.id: NamedEntitySchema(id=wt.id, name=wt.name) for wt in wt_list}

    async def _get_headcount_avg(
        self,
        project_id: UUID,
        days: int,
        construction_object_id: Optional[UUID] = None,
    ) -> Dict[UUID, float]:
        since = business_today() - timedelta(days=days)
        rows = await self.wf_headcount_fact_manager.averages(
            since, ("work_id",), self.access.headcount_fact_ids(), project_id, construction_object_id
        )
        return {r.work_id: float(r.avg) for r in rows}

    async def _get_plans(
        self,
        project_id: UUID,
        period_month: date,
        construction_object_id: Optional[UUID] = None,
    ) -> Dict[UUID, int]:
        rows = await self.wf_headcount_plan_manager.planned_rows(
            period_month, self.access.headcount_plan_ids(), project_id, construction_object_id
        )
        return {r.work_id: r.planned_count for r in rows}

    def _build_work_type_rows(
        self,
        items: List,
        norms: Dict[UUID, HeadcountNorm],
        fact_30d: Dict[UUID, float],
        fact_7d: Dict[UUID, float],
        plans: Dict[UUID, int],
    ) -> List[WorkTypeRow]:
        # Build work-type name lookup from the budget items (work_type rel is selectin-loaded)
        wt_named: Dict[UUID, NamedEntitySchema] = {}
        for it in items:
            if it.work_id not in wt_named:
                wt_named[it.work_id] = NamedEntitySchema(
                    id=it.work_id,
                    name=it.work.name if it.work else None,
                )

        agg: Dict[UUID, list] = {}
        for it in items:
            if it.work_id not in agg:
                agg[it.work_id] = [Decimal(0), Decimal(0)]
            agg[it.work_id][0] += it.bdr_amount
            agg[it.work_id][1] += it.management_completion_amount

        rows = []
        for work_id, (bdr, mgmt_completion) in agg.items():
            net_bdr = bdr - mgmt_completion
            uv_pct = float(mgmt_completion / bdr * 100) if bdr else 0.0

            norm = norms.get(work_id)
            norm_day = norm.median_day_bdr if norm else None
            norm_month = (
                float(norm.median_month_bdr)
                if norm and norm.median_month_bdr
                else (float(norm_day) * 22 if norm_day else None)
            )
            required = float(net_bdr) / norm_month if norm_month and norm_month > 0 else None

            f30 = fact_30d.get(work_id, 0.0)
            f7 = fact_7d.get(work_id, 0.0)
            plan = plans.get(work_id)

            coverage = f30 / required * 100 if required and required > 0 else None
            cov_report = f30 / plan * 100 if plan and plan > 0 else None

            rows.append(
                WorkTypeRow(
                    work_type=wt_named.get(work_id, NamedEntitySchema(id=work_id)),
                    bdr_amount=bdr,
                    management_completion_amount=mgmt_completion,
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
                )
            )
        return rows

    async def calc_project_detail(
        self,
        project: Project,
        period_month: Optional[date] = None,
    ) -> ProjectDetailResponse:
        await self.access.require_projects([project.id])
        bp = await self.wf_budget_period_manager.latest(project.id, period_month)

        if not bp:
            return ProjectDetailResponse(
                project=WfProjectOut.model_validate(project),
                period_month=None,
                objects=[],
                work_types=[],
            )

        all_items = await self.wf_budget_item_manager.search(
            id__in=self.access.budget_item_ids(), budget_period_id=bp.id
        )
        norms_list = await self.wf_workforce_norm_manager.search(project_class=project.project_class)
        norms = {n.work_id: n for n in norms_list}
        objects = await self.wf_project_object_manager.search(id__in=self.access.object_ids(), project_id=project.id)

        items_by_obj: Dict[Optional[UUID], List] = defaultdict(list)
        for it in all_items:
            items_by_obj[it.construction_object_id].append(it)

        obj_dashboard_items = []
        for obj in objects:
            obj_items = items_by_obj.get(obj.id, [])
            if not obj_items:
                continue
            f30 = await self._get_headcount_avg(project.id, 30, obj.id)
            f7 = await self._get_headcount_avg(project.id, 7, obj.id)
            plans = await self._get_plans(project.id, bp.period_month, obj.id)
            wt_rows = self._build_work_type_rows(obj_items, norms, f30, f7, plans)

            obj_net = sum((r.net_bdr for r in wt_rows), Decimal(0))
            obj_req = sum(r.required_headcount for r in wt_rows if r.required_headcount) or None
            obj_plan = sum(r.plan_report for r in wt_rows if r.plan_report) or None
            obj_f30 = sum(r.fact_30d for r in wt_rows)
            obj_f7 = sum(r.fact_7d for r in wt_rows)
            obj_cov = obj_f30 / obj_req * 100 if obj_req and obj_req > 0 else None
            obj_cov_r = obj_f30 / obj_plan * 100 if obj_plan and obj_plan > 0 else None

            top_p = None
            covered = [r for r in wt_rows if r.coverage_pct is not None]
            if covered:
                worst = min(covered, key=lambda r: r.coverage_pct or 100)
                if worst.coverage_pct is not None and worst.coverage_pct < 85:
                    top_p = worst.work_type.name

            obj_dashboard_items.append(
                ObjectDashboardItem(
                    id=obj.id,
                    name=obj.name,
                    net_bdr=obj_net,
                    required_headcount=round(obj_req, 1) if obj_req else None,
                    plan_report=obj_plan,
                    fact_30d=round(obj_f30, 1),
                    fact_7d=round(obj_f7, 1),
                    coverage_pct=round(obj_cov, 1) if obj_cov else None,
                    coverage_report_pct=round(obj_cov_r, 1) if obj_cov_r else None,
                    trend=_trend(obj_f7, obj_f30),
                    traffic_light=_traffic_light(obj_cov),
                    traffic_light_report=_traffic_light(obj_cov_r),
                    top_problem=top_p,
                    work_types=wt_rows,
                )
            )

        agg_f30 = await self._get_headcount_avg(project.id, 30)
        agg_f7 = await self._get_headcount_avg(project.id, 7)
        agg_plans = await self._get_plans(project.id, bp.period_month)
        agg_rows = self._build_work_type_rows(all_items, norms, agg_f30, agg_f7, agg_plans)

        p_net = sum((r.net_bdr for r in agg_rows), Decimal(0))
        p_req = sum(r.required_headcount for r in agg_rows if r.required_headcount) or None
        p_plan = sum(r.plan_report for r in agg_rows if r.plan_report) or None
        p_f30 = sum(r.fact_30d for r in agg_rows)
        p_f7 = sum(r.fact_7d for r in agg_rows)
        p_cov = p_f30 / p_req * 100 if p_req and p_req > 0 else None
        p_cov_r = p_f30 / p_plan * 100 if p_plan and p_plan > 0 else None

        return ProjectDetailResponse(
            project=WfProjectOut.model_validate(project),
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

    async def calc_dashboard(self) -> DashboardResponse:
        projects = await self.wf_project_manager.search(id__in=self.access.project_ids())
        rows = []
        total_net = Decimal("0")
        total_req = 0.0
        total_f30 = 0.0
        has_req = False

        for proj in projects:
            detail = await self.calc_project_detail(proj)
            pn = detail.net_bdr or Decimal("0")
            pr = detail.required_headcount or 0.0
            pf = detail.fact_30d or 0.0

            total_net += pn
            total_f30 += pf
            if pr:
                total_req += pr
                has_req = True

            top_p = None
            if detail.objects:
                worst_objs = [o for o in detail.objects if o.coverage_pct is not None]
                if worst_objs:
                    wo = min(worst_objs, key=lambda o: o.coverage_pct or 100)
                    if wo.coverage_pct and wo.coverage_pct < 85:
                        top_p = f"{wo.name}: {wo.top_problem or '?'}"
            if not top_p and detail.work_types:
                covered = [r for r in detail.work_types if r.coverage_pct is not None]
                if covered:
                    w = min(covered, key=lambda r: r.coverage_pct or 100)
                    if w.coverage_pct and w.coverage_pct < 85:
                        top_p = w.work_type.name

            rows.append(
                ProjectRow(
                    id=proj.id,
                    name=proj.name,
                    project_class=proj.project_class,
                    net_bdr=pn,
                    required_headcount=round(pr, 1) if pr else None,
                    fact_30d=round(pf, 1),
                    coverage_pct=round(detail.coverage_pct, 1) if detail.coverage_pct else None,
                    trend=detail.trend or "no_data",
                    top_problem=top_p,
                    traffic_light=detail.traffic_light or "grey",
                )
            )

        rows.sort(key=lambda r: r.coverage_pct if r.coverage_pct is not None else 9999)
        port_cov = round(total_f30 / total_req * 100, 1) if has_req and total_req > 0 else None

        return DashboardResponse(
            total_net_bdr=total_net,
            total_required=round(total_req, 1) if has_req else None,
            total_fact_30d=round(total_f30, 1),
            portfolio_coverage_pct=port_cov,
            projects=rows,
        )

    async def calc_forecast(self, project_id: UUID) -> ForecastResponse:
        await self.access.require_projects([project_id])
        today = business_today()
        project = await self.wf_project_manager.get_by_id(project_id)
        objects = await self.wf_project_object_manager.search(id__in=self.access.object_ids(), project_id=project_id)
        obj_map = {o.id: o for o in objects}

        norms_result = await self.wf_workforce_norm_manager.search()
        norms = {(n.work_id, n.project_class): n for n in norms_result}

        bp = await self.wf_budget_period_manager.latest(project_id)
        if not bp:
            return ForecastResponse(project_id=project_id, rows=[])

        items = await self.wf_budget_item_manager.search(id__in=self.access.budget_item_ids(), budget_period_id=bp.id)

        since = today - timedelta(days=30)
        fact_rows = await self.wf_headcount_fact_manager.averages(
            since, ("construction_object_id", "work_id"), self.access.headcount_fact_ids(), project_id=project_id
        )
        fact_map: Dict[Tuple, float] = {(r.construction_object_id, r.work_id): float(r.avg) for r in fact_rows}

        rows = []
        for item in items:
            if item.construction_object_id is None:
                continue
            obj = obj_map.get(item.construction_object_id)
            if obj is None:
                continue

            proj_class = project.project_class if project else "Комфорт"
            norm = norms.get((item.work_id, proj_class))
            norm_month = float(norm.median_month_bdr) if norm else None

            f30 = fact_map.get((item.construction_object_id, item.work_id), 0.0)
            remaining = item.remaining_amount
            planned_end = item.planned_end_date or obj.planned_end_date

            forecast_date = None
            months_needed = None
            delay_months = None

            if remaining is not None and norm_month and norm_month > 0 and f30 > 0:
                months_needed = float(remaining) / (f30 * norm_month)
                forecast_date = today + timedelta(days=int(months_needed * 30))
                if planned_end:
                    delay_months = round((forecast_date - planned_end).days / 30, 1)

            rows.append(
                ForecastRow(
                    construction_object_id=obj.id,
                    object_name=obj.name,
                    work_type=NamedEntitySchema(
                        id=item.work_id,
                        name=item.work.name if item.work else None,
                    ),
                    remaining_amount=remaining,
                    planned_end_date=planned_end,
                    fact_30d=round(f30, 1),
                    norm_month=round(norm_month, 0) if norm_month else None,
                    months_needed=round(months_needed, 1) if months_needed else None,
                    forecast_date=forecast_date,
                    delay_months=delay_months,
                )
            )

        return ForecastResponse(project_id=project_id, rows=rows)

    async def calc_object_contractors(self, construction_object_id: UUID) -> List[ContractorHeadcountRow]:
        await self.access.require_objects([construction_object_id])
        today = business_today()
        period = today.replace(day=1)
        since = today - timedelta(days=30)

        fact_rows = await self.wf_headcount_fact_manager.averages(
            since,
            ("contractor_id", "work_id"),
            self.access.headcount_fact_ids(),
            construction_object_id=construction_object_id,
        )

        plan_rows = await self.wf_headcount_plan_manager.planned_rows(
            period,
            self.access.headcount_plan_ids(),
            construction_object_id=construction_object_id,
            include_contractor=True,
        )
        plan_map = {(r.contractor_id, r.work_id): r.planned_count for r in plan_rows}

        contractor_ids = {r.contractor_id for r in fact_rows if r.contractor_id}
        contractors: Dict[UUID, str] = {}
        if contractor_ids:
            c_list = await self.contractor_manager.get_by_ids(contractor_ids)
            contractors = {c.id: c.name for c in c_list}

        wt_ids = {r.work_id for r in fact_rows}
        work_types_map = await self._get_work_types_map(wt_ids)

        result = []
        for r in fact_rows:
            f30 = float(r.avg)
            plan = plan_map.get((r.contractor_id, r.work_id))
            cov = round(f30 / plan * 100, 1) if plan and plan > 0 else None
            cname = contractors.get(r.contractor_id, "Без подрядчика") if r.contractor_id else "Без подрядчика"
            result.append(
                ContractorHeadcountRow(
                    contractor_id=r.contractor_id,
                    contractor_name=cname,
                    work_type=work_types_map.get(r.work_id, NamedEntitySchema(id=r.work_id)),
                    plan=plan,
                    fact_30d=round(f30, 1),
                    coverage_pct=cov,
                )
            )
        return result

    async def calc_system_problems(
        self,
        threshold_pct: float = 50.0,
        min_objects: int = 3,
    ) -> SystemProblemsResponse:
        today = business_today()
        since = today - timedelta(days=30)

        fact_rows = await self.wf_headcount_fact_manager.averages(
            since, ("construction_object_id", "work_id"), self.access.headcount_fact_ids()
        )

        norms_list = await self.wf_workforce_norm_manager.search()
        projects = await self.wf_project_manager.search(id__in=self.access.project_ids())

        required_map: Dict[Tuple, float] = {}
        for proj in projects:
            bp = await self.wf_budget_period_manager.latest(proj.id)
            if not bp:
                continue

            norms = {n.work_id: n for n in norms_list if n.project_class == proj.project_class}
            items = await self.wf_budget_item_manager.search(
                id__in=self.access.budget_item_ids(), budget_period_id=bp.id
            )
            for item in items:
                if item.construction_object_id is None:
                    continue
                norm = norms.get(item.work_id)
                if not norm:
                    continue
                nm = float(norm.median_month_bdr)
                net = float(item.bdr_amount - item.management_completion_amount)
                if nm > 0:
                    required_map[(item.construction_object_id, item.work_id)] = net / nm

        fact_by_key = {(r.construction_object_id, r.work_id): float(r.avg) for r in fact_rows}
        objects = await self.wf_project_object_manager.search(id__in=self.access.object_ids())
        obj_names = {o.id: o.name for o in objects}

        coverage_by_wt: Dict[UUID, List[Tuple]] = defaultdict(list)
        for (obj_id, wt_id), req in required_map.items():
            if req <= 0:
                continue
            fact = fact_by_key.get((obj_id, wt_id), 0.0)
            coverage_by_wt[wt_id].append((obj_id, fact / req * 100))

        all_wt_ids = set(coverage_by_wt.keys())
        work_types_map = await self._get_work_types_map(all_wt_ids)

        problems = []
        for wt_id, entries in coverage_by_wt.items():
            below = [(oid, cov) for oid, cov in entries if cov < threshold_pct]
            if len(below) >= min_objects:
                avg_cov = round(sum(c for _, c in below) / len(below), 1)
                problems.append(
                    SystemProblemRow(
                        work_type=work_types_map.get(wt_id, NamedEntitySchema(id=wt_id)),
                        affected_objects=len(below),
                        avg_coverage_pct=avg_cov,
                        object_names=[obj_names.get(oid, str(oid)) for oid, _ in below],
                    )
                )

        problems.sort(key=lambda r: r.avg_coverage_pct or 9999)
        return SystemProblemsResponse(threshold_pct=threshold_pct, min_objects=min_objects, problems=problems)

    async def calc_contractor_rating(self) -> List[ContractorRatingRow]:
        today = business_today()
        since_3m = today - timedelta(days=90)
        contractors = await self.contractor_manager.search(id__in=self.access.contractor_ids())

        rows = []
        for c in contractors:
            fact_avg = await self.wf_headcount_fact_manager.contractor_average(
                c.id, since_3m, self.access.headcount_fact_ids()
            )
            plan_sum = await self.wf_headcount_plan_manager.contractor_total(
                c.id, since_3m.replace(day=1), self.access.headcount_plan_ids()
            )

            avg_cov: Optional[float] = None
            if fact_avg is not None and plan_sum:
                avg_cov = round(float(fact_avg) / (float(plan_sum) / 3) * 100, 1)

            v_count = await self.wf_violation_manager.count(contractor_id=c.id, id__in=self.access.violation_ids())
            missed = await self.wf_mobilization_checkpoint_manager.missed_count(c.id, self.access.checkpoint_ids())

            rating = round((avg_cov or 0.0) * 0.5 - v_count * 10 - missed * 5, 1)
            rows.append(
                ContractorRatingRow(
                    contractor_id=c.id,
                    contractor_name=c.name,
                    avg_coverage_pct=avg_cov,
                    violation_count=v_count,
                    missed_checkpoints=missed,
                    rating_score=rating,
                )
            )

        rows.sort(key=lambda r: r.rating_score, reverse=True)
        return rows

    async def check_challenge_checkpoints(self, challenge_id: UUID) -> int:
        self.access.require_business_write()
        await self.access.require_challenges([challenge_id])
        today = business_today()
        challenge = await self.wf_challenge_manager.get_by_id(challenge_id)
        if not challenge:
            return 0

        checkpoints = await self.wf_mobilization_checkpoint_manager.pending_for_challenge(
            challenge_id, today, self.access.checkpoint_ids()
        )

        updated = 0
        violations_data = []
        for cp in checkpoints:
            if cp.actual_cumulative is None:
                cp.status = CheckpointStatus.MISSED
            elif cp.actual_cumulative >= cp.expected_cumulative:
                cp.status = CheckpointStatus.MET
            else:
                cp.status = CheckpointStatus.MISSED

            if cp.status == CheckpointStatus.MISSED and not cp.violation_recorded:
                cp.violation_recorded = True
                mp = await self.wf_mobilization_plan_manager.get_by_id(cp.mobilization_plan_id)
                if mp:
                    ci = await self.wf_challenge_item_manager.get_by_id(mp.challenge_item_id)
                    if ci:
                        desc = (
                            f"Пропущена КТ мобилизации: ожидалось "
                            f"{cp.expected_cumulative}, факт "
                            f"{cp.actual_cumulative or 0}"
                        )
                        violations_data.append(
                            {
                                "project_id": challenge.project_id,
                                "construction_object_id": challenge.construction_object_id,
                                "work_id": ci.work_id,
                                "violation_date": today,
                                "violation_type": ViolationType.MOBILIZATION_MISSED,
                                "description": desc,
                                "plan_count": cp.expected_cumulative,
                                "fact_count": cp.actual_cumulative or 0,
                            }
                        )
            updated += 1

        if violations_data:
            await self.wf_violation_manager.bulk_insert(violations_data, is_commit=False)
        if updated:
            await self.wf_mobilization_checkpoint_manager.db.commit()

        return updated

    async def scan_violations(self) -> ViolationScanResult:
        self.access.require_business_write()
        today = business_today()
        projects = await self.wf_project_manager.search(id__in=self.access.project_ids())
        new_violations_data = []

        for proj in projects:
            detail = await self.calc_project_detail(proj)
            for obj in detail.objects or []:
                for wt in obj.work_types or []:
                    if wt.coverage_pct is not None and wt.coverage_pct < 60 and wt.required_headcount:
                        existing = await self.wf_violation_manager.search(
                            id__in=self.access.violation_ids(),
                            construction_object_id=obj.id,
                            work_id=wt.work_type.id,
                            violation_type="coverage_critical",
                            violation_date__gte=today.replace(day=1),
                            resolved=False,
                        )
                        if not existing:
                            desc = (
                                f"Обеспеченность {wt.coverage_pct:.0f}% "
                                f"(< 60%). Нужно {wt.required_headcount:.0f}, "
                                f"факт {wt.fact_30d:.0f}"
                            )
                            new_violations_data.append(
                                {
                                    "project_id": proj.id,
                                    "construction_object_id": obj.id,
                                    "work_id": wt.work_type.id,
                                    "violation_date": today,
                                    "violation_type": "coverage_critical",
                                    "description": desc,
                                    "plan_count": int(wt.required_headcount),
                                    "fact_count": int(wt.fact_30d),
                                }
                            )

                    if wt.plan_report and wt.fact_30d < wt.plan_report * 0.8:
                        existing = await self.wf_violation_manager.search(
                            id__in=self.access.violation_ids(),
                            construction_object_id=obj.id,
                            work_id=wt.work_type.id,
                            violation_type="plan_not_met",
                            violation_date__gte=today.replace(day=1),
                            resolved=False,
                        )
                        if not existing:
                            new_violations_data.append(
                                {
                                    "project_id": proj.id,
                                    "construction_object_id": obj.id,
                                    "work_id": wt.work_type.id,
                                    "violation_date": today,
                                    "violation_type": "plan_not_met",
                                    "description": (
                                        f"Факт {wt.fact_30d:.0f} < План {wt.plan_report} (невыполнение > 20%)"
                                    ),
                                    "plan_count": wt.plan_report,
                                    "fact_count": int(wt.fact_30d),
                                }
                            )

        if new_violations_data:
            await self.wf_violation_manager.bulk_insert(new_violations_data, is_commit=True)

        return ViolationScanResult(created=len(new_violations_data), violations=[])

    async def auto_escalate_violations(self) -> int:
        self.access.require_business_write()
        today = business_today()
        violations = await self.wf_violation_manager.search(id__in=self.access.violation_ids(), resolved=False)
        escalated_count = 0

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
            await self.wf_violation_manager.db.commit()

        return escalated_count

    async def enrich_violations(self, violations: List) -> List[ViolationOut]:
        proj_cache: Dict[UUID, str] = {}
        obj_cache: Dict[UUID, str] = {}
        contr_cache: Dict[UUID, Optional[str]] = {}

        result = []
        for v in violations:
            if v.project_id not in proj_cache:
                p = await self.wf_project_manager.get_by_id(v.project_id)
                proj_cache[v.project_id] = p.name if p else "?"
            if v.construction_object_id not in obj_cache:
                o = await self.wf_project_object_manager.get_by_id(v.construction_object_id)
                obj_cache[v.construction_object_id] = o.name if o else "?"
            if v.contractor_id and v.contractor_id not in contr_cache:
                c = await self.contractor_manager.get_by_id(v.contractor_id)
                contr_cache[v.contractor_id] = c.name if c else None

            result.append(
                ViolationOut(
                    id=v.id,
                    project_id=v.project_id,
                    construction_object_id=v.construction_object_id,
                    work_type=NamedEntitySchema(
                        id=v.work_id,
                        name=v.work.name if v.work else None,
                    ),
                    contractor_id=v.contractor_id,
                    violation_date=v.violation_date,
                    violation_type=v.violation_type,
                    description=v.description,
                    plan_count=v.plan_count,
                    fact_count=v.fact_count,
                    escalated=v.escalated,
                    escalated_to=v.escalated_to,
                    resolved=v.resolved,
                    project_name=proj_cache.get(v.project_id),
                    object_name=obj_cache.get(v.construction_object_id),
                    contractor_name=contr_cache.get(v.contractor_id) if v.contractor_id else None,
                )
            )
        return result

    async def search_project(self, **filters: Any) -> list[m.Project]:
        """List project using the operation's explicit assignment filter."""
        allowed_ids = self.access.project_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_project_manager.search(**filters)

    async def count_project(self, **filters: Any) -> int:
        """Count the same records available to the project list."""
        allowed_ids = self.access.project_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_project_manager.count(**filters)

    async def get_project(self, entity_id: UUID) -> m.Project | None:
        """Authorize a selected project before resolving its identity."""
        await self.access.require_projects([entity_id])
        return await self.wf_project_manager.get_by_id(entity_id)

    async def create_project(self, payload: dict[str, Any]) -> m.Project:
        """Create project after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.wf_project_manager.create(payload)

    async def update_project(self, entity_id: UUID, payload: dict[str, Any]) -> m.Project | None:
        """Update an authorized project."""
        self.access.require_business_write()
        await self.access.require_projects([entity_id])
        return await self.wf_project_manager.update_by_id(entity_id, payload)

    async def delete_project(self, entity_id: UUID) -> None:
        """Delete an authorized project."""
        self.access.require_business_write()
        await self.access.require_projects([entity_id])
        await self.wf_project_manager.delete_by_id(entity_id)

    async def search_project_object(self, **filters: Any) -> list[m.ConstructionObject]:
        """List project_object using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.object_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_project_object_manager.search(**filters)

    async def create_project_object(self, payload: dict[str, Any]) -> m.ConstructionObject:
        """Create project_object after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.wf_project_object_manager.create(payload)

    async def delete_project_object(self, entity_id: UUID) -> None:
        """Delete an authorized project_object."""
        self.access.require_business_write()
        await self.access.require_objects([entity_id])
        await self.wf_project_object_manager.delete_by_id(entity_id)

    async def search_norm(self, **filters: Any) -> list[m.HeadcountNorm]:
        """List norm using the operation's explicit assignment filter."""
        return await self.wf_workforce_norm_manager.search(**filters)

    async def create_norm(self, payload: dict[str, Any]) -> m.HeadcountNorm:
        """Create norm after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.wf_workforce_norm_manager.create(payload)

    async def delete_norm(self, entity_id: UUID) -> None:
        """Delete an authorized norm."""
        self.access.require_shared_write()
        await self.wf_workforce_norm_manager.delete_by_id(entity_id)

    async def search_headcount_fact(self, **filters: Any) -> list[m.HeadcountFact]:
        """List headcount_fact using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.headcount_fact_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_headcount_fact_manager.search(**filters)

    async def count_headcount_fact(self, **filters: Any) -> int:
        """Count the same records available to the headcount_fact list."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.headcount_fact_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_headcount_fact_manager.count(**filters)

    async def create_headcount_fact(self, payload: dict[str, Any]) -> m.HeadcountFact:
        """Create headcount_fact after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.wf_headcount_fact_manager.create(payload)

    async def search_headcount_plan(self, **filters: Any) -> list[m.HeadcountPlan]:
        """List headcount_plan using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.headcount_plan_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_headcount_plan_manager.search(**filters)

    async def create_headcount_plan(self, payload: dict[str, Any]) -> m.HeadcountPlan:
        """Create headcount_plan after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.wf_headcount_plan_manager.create(payload)

    async def search_challenge(self, **filters: Any) -> list[m.Challenge]:
        """List challenge using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.challenge_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_challenge_manager.search(**filters)

    async def create_challenge(self, payload: dict[str, Any], items: list[dict[str, Any]]) -> m.Challenge:
        """Create an authorized challenge with its lines in one transaction."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        challenge = await self.wf_challenge_manager.create(payload, commit=False)
        await self.db.flush()
        for item in items:
            await self.wf_challenge_item_manager.create({**item, "challenge_id": challenge.id}, commit=False)
        await self.db.commit()
        return await self.wf_challenge_manager.get_with_items(challenge.id)

    async def bulk_create_article_bdrs(self, payloads: list[dict[str, Any]]) -> None:
        """Import common budget articles after checking administrator access."""
        self.access.require_shared_write()
        await self.article_bdr_manager.bulk_insert(payloads, is_commit=True)

    async def update_challenge(self, entity_id: UUID, payload: dict[str, Any]) -> m.Challenge | None:
        """Update an authorized challenge."""
        self.access.require_business_write()
        await self.access.require_challenges([entity_id])
        await self._authorize_selectors(payload)
        return await self.wf_challenge_manager.update_by_id(entity_id, payload)

    async def search_violation(self, **filters: Any) -> list[m.Violation]:
        """List violation using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.violation_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_violation_manager.search(**filters)

    async def count_violation(self, **filters: Any) -> int:
        """Count the same records available to the violation list."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.violation_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.wf_violation_manager.count(**filters)

    async def create_violation(self, payload: dict[str, Any]) -> m.Violation:
        """Create violation after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.wf_violation_manager.create(payload)

    async def update_violation(self, entity_id: UUID, payload: dict[str, Any]) -> m.Violation | None:
        """Update an authorized violation."""
        self.access.require_business_write()
        await self.access.require_violations([entity_id])
        await self._authorize_selectors(payload)
        return await self.wf_violation_manager.update_by_id(entity_id, payload)

    async def search_article_bdr(self, **filters: Any) -> list[m.ArticleBDR]:
        """List article_bdr using the operation's explicit assignment filter."""
        return await self.article_bdr_manager.search(**filters)

    async def create_article_bdr(self, payload: dict[str, Any]) -> m.ArticleBDR:
        """Create article_bdr after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.article_bdr_manager.create(payload)

    async def delete_article_bdr(self, entity_id: UUID) -> None:
        """Delete an authorized article_bdr."""
        self.access.require_shared_write()
        await self.article_bdr_manager.delete_by_id(entity_id)

    async def search_article_mapping(self, **filters: Any) -> list[m.ArticleBDRWork]:
        """List article_mapping using the operation's explicit assignment filter."""
        return await self.wf_article_mapping_manager.search(**filters)

    async def create_article_mapping(self, payload: dict[str, Any]) -> m.ArticleBDRWork:
        """Create article_mapping after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.wf_article_mapping_manager.create(payload)

    async def delete_article_mapping(self, entity_id: UUID) -> None:
        """Delete an authorized article_mapping."""
        self.access.require_shared_write()
        await self.wf_article_mapping_manager.delete_by_id(entity_id)


async def get_workforce_service(db: AsyncSession = Depends(get_session)) -> WorkforceService:
    return WorkforceService(db=db)
