"""Registered API + real PostgreSQL; synthetic profiles, no real users or external calls.

Root conftest recreates DB_TEST_DATABASE_NAME: use a NEW disposable database for this suite.
"""

from unittest.mock import AsyncMock

import pytest

from src.models.dbo import models as m
from src.services.access.schemes import SCOPE_KEY, AccessScope, PlanRole
from src.services.access.service import AccessService
from src.services.plan.service import AutogenerationService
from src.utils.business_time import business_today
from src.utils.exceptions import AccessDenied
from tests.fixtures.access import DAY


async def test_scoped_get_by_id_ignores_session_identity_map(access_data):
    db = access_data.db
    foreign = await db.get(m.PlanItem, access_data.plans[1][0].id)
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    with pytest.raises(AccessDenied):
        await AutogenerationService(db).get_plan_item(foreign.id)


async def test_newly_assigned_contractor_grant_is_request_local(access_data):
    db = access_data.db
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    contractor = access_data.contractors[2]
    from src.services.contractor.service import ContractorService

    manager = ContractorService(db)
    with pytest.raises(AccessDenied):
        await manager.get_contractor(contractor.id)
    AccessService(db).grant_assigned_contractors([contractor.raport_id])
    assert (await manager.get_contractor(contractor.id)).id == contractor.id
    db.info.clear()
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    with pytest.raises(AccessDenied):
        await manager.get_contractor(contractor.id)


async def test_direct_mixed_bulk_service_call_fails_before_logs(access_data):
    db = access_data.db
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    service = AutogenerationService(db)
    service.log_action = AsyncMock()
    with pytest.raises(AccessDenied):
        await service.delete_items([access_data.plans[0][0].id, access_data.plans[1][0].id])
    service.log_action.assert_not_awaited()


async def test_rs_headcount_foreign_parent_denied_before_insert(access_data):
    from src.services.workforce.service import WorkforceService

    db = access_data.db
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    service = WorkforceService(db)
    service.wf_headcount_fact_manager.create = AsyncMock()
    with pytest.raises(AccessDenied):
        await service.create_headcount_fact(
            {
                "project_id": access_data.projects[0].id,
                "construction_object_id": access_data.objects[1].id,
                "work_id": access_data.work.id,
                "fact_date": business_today(),
                "count": 1000,
            }
        )
    service.wf_headcount_fact_manager.create.assert_not_awaited()


async def test_direct_foreign_generation_does_not_write_journal(access_data):
    db = access_data.db
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    service = AutogenerationService(db)
    service.log_action = AsyncMock()
    with pytest.raises(AccessDenied):
        await service.generate_daily_plan(access_data.housings[1].id, DAY, force=True)
    service.log_action.assert_not_awaited()


async def test_generation_bulk_has_bounded_queries(access_data):
    from datetime import timedelta
    from decimal import Decimal
    from uuid import uuid4

    from sqlalchemy import event

    from src.services.contractor_works.service import AssignmentKey, HousingAssignments
    from src.services.report_cells.service import CellKey, CellState, HousingSlice

    # Arrange a full day rather than measuring an isolated insert helper.
    db = access_data.db
    housing, section, work, contractor = (
        access_data.housings[0],
        access_data.sections[0],
        access_data.work,
        access_data.contractors[0],
    )
    floors = [m.Floor(id=uuid4(), section_id=section.id, floor_number=i + 2) for i in range(136)]
    db.add_all(floors)
    db.add(
        m.TechSequenceItem(
            housing_id=housing.id, work_id=work.id, order=1, estimated_days=1, daily_norm_volume=0, total_volume=0
        )
    )
    db.add(m.ContractorPositionLimit(contractor_id=contractor.id, positions_limit=136))
    await db.commit()
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    service = AutogenerationService(db)
    assignments = HousingAssignments(
        by_cell={AssignmentKey(section.id, f.id, work.id): [contractor.id] for f in floors}
    )
    cells = HousingSlice(
        cells={
            CellKey(section.id, f.id, work.id, contractor.id): CellState(Decimal("10"), False, uuid4()) for f in floors
        }
    )
    service.contractor_works.get_housing_assignments = AsyncMock(return_value=assignments)
    service.report_cells.get_housing_slice = AsyncMock(return_value=cells)
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    bind = db.bind.sync_engine
    event.listen(bind, "before_cursor_execute", record)
    try:
        # Act: authorization, generation and the real bulk insert share the real DB.
        items, reasons = await service.generate_daily_plan(housing.id, DAY + timedelta(days=1))
    finally:
        event.remove(bind, "before_cursor_execute", record)

    # Assert: query cost does not grow by five FK checks for each position.
    assert len(items) == 136
    assert reasons == []
    assert sum(s.lstrip().upper().startswith("SELECT") for s in statements) < 30
    assert sum(s.lstrip().upper().startswith("INSERT INTO PLAN_ITEMS") for s in statements) == 1


async def test_existing_plan_check_excludes_mixed_hierarchy(access_data):
    from datetime import timedelta

    db = access_data.db
    target = DAY + timedelta(days=1)
    db.add(
        m.PlanItem(
            date=target,
            housing_id=access_data.housings[0].id,
            section_id=access_data.sections[0].id,
            floor_id=access_data.floors[1].id,
            work_id=access_data.work.id,
            contractor_id=access_data.contractors[0].id,
        )
    )
    await db.flush()
    db.info[SCOPE_KEY] = AccessScope(PlanRole.RS, frozenset({access_data.projects[0].raport_id}))
    assert await AutogenerationService(db).has_plan_for(access_data.housings[0].id, target) is False
