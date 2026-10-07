"""Registered API + real PostgreSQL; synthetic profiles, no real users or external calls.

Root conftest recreates DB_TEST_DATABASE_NAME: use a NEW disposable database for this suite.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.main import app
from src.middlewares.raport_auth.authz import AuthzClient
from src.middlewares.raport_auth.backend import RaportUser
from src.middlewares.raport_auth.cache import AuthCache
from src.middlewares.raport_auth.settings import auth_settings
from src.models.dbo import models as m
from src.utils.business_time import business_today

DAY = date(2099, 1, 3)


@pytest.fixture
async def access_data(test_engine):
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
            data = SimpleNamespace(db=db, projects=[], objects=[], housings=[], sections=[], floors=[], plans=[])
            data.contractors = [
                m.Contractor(
                    id=uuid4(), name=f"access-contractor-{i}", short_name=f"access-{i}", raport_id=str(uuid4())
                )
                for i in range(3)
            ]
            kind = m.WorkType(id=uuid4(), name="Access type", code=str(uuid4()))
            data.work = m.Work(
                id=uuid4(),
                name="Access work",
                code=str(uuid4()),
                unit="m2",
                work_type_id=kind.id,
                raport_id=str(uuid4()),
            )
            db.add_all([*data.contractors, kind])
            await db.flush()
            db.add(data.work)
            for i in range(2):
                project = m.Project(id=uuid4(), name=f"access-project-{i}", raport_id=str(uuid4()))
                obj = m.ConstructionObject(id=uuid4(), name=f"access-object-{i}", project_id=project.id)
                house = m.Housing(
                    id=uuid4(),
                    name=f"access-housing-{i}",
                    complex_name="Access",
                    construction_object_id=obj.id,
                    raport_id=str(uuid4()),
                )
                section = m.Section(
                    id=uuid4(),
                    name=f"access-section-{i}",
                    section_number=1,
                    housing_id=house.id,
                    raport_id=str(uuid4()),
                )
                floor = m.Floor(
                    id=uuid4(), name=f"access-floor-{i}", floor_number=1, section_id=section.id, raport_id=str(uuid4())
                )
                for rows, item in (
                    (data.projects, project),
                    (data.objects, obj),
                    (data.housings, house),
                    (data.sections, section),
                    (data.floors, floor),
                ):
                    rows.append(item)
                    db.add(item)
                    await db.flush()
                plans = []
                for status, contractor in (
                    ("draft", data.contractors[0]),
                    ("confirmed", data.contractors[0]),
                    ("transferred", data.contractors[0]),
                    ("transferred", data.contractors[1]),
                    ("cancelled_by_rs", data.contractors[0]),
                ):
                    plan = m.PlanItem(
                        id=uuid4(),
                        date=DAY,
                        housing_id=house.id,
                        section_id=section.id,
                        floor_id=floor.id,
                        work_id=data.work.id,
                        contractor_id=contractor.id,
                        status=status,
                    )
                    db.add(plan)
                    plans.append(plan)
                data.plans.append(plans)
                await db.flush()
                period = m.BudgetPeriod(id=uuid4(), project_id=project.id, period_month=business_today().replace(day=1))
                db.add(period)
                await db.flush()
                db.add_all(
                    [
                        m.BudgetItem(
                            budget_period_id=period.id,
                            construction_object_id=obj.id,
                            work_id=data.work.id,
                            contractor_id=data.contractors[i].id,
                            bdr_amount=1000 + i * 9000,
                            remaining_amount=1000,
                        ),
                        m.WorkFact(
                            work_date=DAY,
                            housing_id=house.id,
                            section_id=section.id,
                            floor_id=floor.id,
                            work_id=data.work.id,
                            contractor_id=data.contractors[i].id,
                            volume=0,
                        ),
                        m.ReconciliationResult(
                            date=DAY,
                            housing_id=house.id,
                            section_id=section.id,
                            floor_id=floor.id,
                            work_id=data.work.id,
                            contractor_id=data.contractors[i].id,
                            status="DONE_FULL",
                            plan_item_id=plans[2].id,
                        ),
                        m.DailySummary(date=DAY, housing_id=house.id),
                        m.Alert(
                            date=DAY,
                            housing_id=house.id,
                            recipient_role="RS",
                            alert_type="A01",
                            message="Access alert",
                            level="critical",
                            contractor_id=data.contractors[i].id,
                        ),
                        m.HeadcountFact(
                            project_id=project.id,
                            construction_object_id=obj.id,
                            work_id=data.work.id,
                            fact_date=business_today(),
                            count=10 + i * 80,
                        ),
                    ]
                )
            await db.commit()
            yield data
        await transaction.rollback()


def profile(data, groups=None, *, projects=None, contractors=None):
    return RaportUser(
        {
            "id": str(uuid4()),
            "groups": groups if groups is not None else ["factgathering_user"],
            "is_active": True,
            "projects": [
                {"id": value} for value in (projects if projects is not None else [data.projects[0].raport_id])
            ],
            "contractors": [
                {"id": value} for value in (contractors if contractors is not None else [data.contractors[0].raport_id])
            ],
        },
        {"sub": "synthetic-access-user"},
    )


@pytest.fixture
async def role_client(access_data, monkeypatch):
    principal = {"user": profile(access_data)}

    async def verify(token, settings, jwks):
        user = principal["user"]
        if user.is_service:
            return {"azp": "api", "preferred_username": "service-account-api"}
        return {"sub": user.data["id"]}

    async def fetch(self, keycloak_id, token):
        return principal["user"].data

    async def session():
        yield access_data.db

    monkeypatch.setattr(auth_settings, "auth_enabled", True)
    monkeypatch.setattr(auth_settings, "auth_service_clients", "api")
    monkeypatch.setattr("src.middlewares.raport_auth.backend.verify_token", verify)
    monkeypatch.setattr(AuthzClient, "fetch", fetch)
    monkeypatch.setattr(AuthCache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(AuthCache, "set", AsyncMock())
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://access-test",
        headers={"Authorization": "Bearer synthetic-access-token"},
    ) as client:
        yield client, principal
    if previous is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous
    access_data.db.info.clear()
