from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.models import managers
from src.models.dbo import models as m
from src.services.access.schemes import SCOPE_KEY, AccessScope, PlanRole
from src.services.access.service import AccessService
from src.utils.business_time import business_today


async def test_wrong_project_object_pair_excluded_from_raw_aggregates(access_data):
    db = access_data.db
    db.add(
        m.HeadcountFact(
            project_id=access_data.projects[0].id,
            construction_object_id=access_data.objects[1].id,
            work_id=access_data.work.id,
            fact_date=business_today(),
            count=1000,
        )
    )
    await db.flush()
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    rows = await managers.HeadcountFactManager(db).averages(
        business_today(), ("work_id",), AccessService(db).headcount_fact_ids()
    )
    assert len(rows) == 1
    assert rows[0].avg == 10


@pytest.mark.parametrize(
    "query_method",
    [
        "project_ids",
        "object_ids",
        "housing_ids",
        "section_ids",
        "floor_ids",
        "plan_item_ids",
        "work_fact_ids",
        "result_ids",
        "summary_ids",
        "alert_ids",
        "tech_sequence_ids",
        "contractor_ids",
        "budget_period_ids",
        "budget_item_ids",
        "headcount_fact_ids",
        "headcount_plan_ids",
        "challenge_ids",
        "challenge_item_ids",
        "mobilization_plan_ids",
        "checkpoint_ids",
        "violation_ids",
        "assignment_ids",
        "position_limit_ids",
        "queue_ids",
    ],
)
def test_explicit_assignment_queries_compile(async_session, query_method):
    manager = managers.AccessManager(async_session)
    query = getattr(manager, query_method)({str(uuid4())})
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert "raport_id" in sql
    assert "WHERE" in sql


@pytest.mark.parametrize("shape", ["alias", "subquery"])
async def test_explicit_id_filter_survives_query_composition(access_data, shape):
    from sqlalchemy.orm import aliased

    db = access_data.db
    allowed = managers.AccessManager(db).plan_item_ids({access_data.projects[0].raport_id})
    source = aliased(m.PlanItem) if shape == "alias" else select(m.PlanItem).subquery()
    identifier = source.id if shape == "alias" else source.c.id
    result = await db.execute(select(identifier).where(identifier.in_(allowed)))
    assert set(result.scalars()) == {p.id for p in access_data.plans[0]}
