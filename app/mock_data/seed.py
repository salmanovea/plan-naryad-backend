"""
Мок-данные для системы "План-наряд".
Проект "ЖК Солнечный" — реалистичные тестовые данные.
"""
import logging
import random
from datetime import date, datetime, timedelta
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.housing import Housing, Section, Floor
from app.models.work import WorkGroup, WorkType, TechSequenceItem
from app.models.contractor import Contractor, ContractorAssignment
from app.models.plan import PlanItem
from app.models.fact import WorkFact
from app.models.reconciliation import ReconciliationResult, DailySummary
from app.models.alert import Alert

logger = logging.getLogger(__name__)


async def seed_database(db: AsyncSession) -> None:
    """Заполняет базу мок-данными, если пуста."""
    result = await db.execute(select(Housing).limit(1))
    if result.scalar_one_or_none():
        logger.info("DB already seeded, skipping")
        return

    logger.info("Seeding database...")

    # === 1. Housing ===
    housing = Housing(
        id=uuid4(),
        name="Корпус 1 — ЖК Солнечный",
        complex_name="ЖК Солнечный",
        description="ул. Строителей, 15"
    )
    db.add(housing)

    housing2 = Housing(
        id=uuid4(),
        name="Корпус 2 — ЖК Солнечный",
        complex_name="ЖК Солнечный",
        description="ул. Строителей, 17"
    )
    db.add(housing2)

    # === 2. Sections + Floors ===
    all_sections = []
    all_floors = []
    for h in [housing, housing2]:
        for sec_num in range(1, 3):
            section = Section(
                id=uuid4(),
                housing_id=h.id,
                name=f"Секция {sec_num}",
                section_number=sec_num
            )
            db.add(section)
            all_sections.append(section)
            for fl_num in range(1, 11):
                floor = Floor(
                    id=uuid4(),
                    section_id=section.id,
                    floor_number=fl_num,
                    name=f"{fl_num}-й этаж"
                )
                db.add(floor)
                all_floors.append(floor)

    # === 3. Work Groups + Work Types ===
    groups_data = [
        ("SMR", "СМР (общестроительные)"),
        ("ENG", "Инженерные системы"),
        ("FIN", "Отделочные работы"),
    ]
    groups = {}
    for code, name in groups_data:
        g = WorkGroup(id=uuid4(), name=name, code=code, order=len(groups) + 1)
        db.add(g)
        groups[code] = g

    work_data = [
        # (code, name, unit, group_code)
        ("FND", "Устройство фундамента", "м³", "SMR"),
        ("WLL", "Возведение стен", "м²", "SMR"),
        ("SLB", "Монтаж перекрытий", "м²", "SMR"),
        ("BRK", "Кирпичная кладка", "м²", "SMR"),
        ("ROF", "Монтаж кровли", "м²", "SMR"),
        ("WND", "Установка окон", "шт", "SMR"),
        ("PLB", "Монтаж инженерных систем", "п.м.", "ENG"),
        ("ELC", "Монтаж электропроводки", "п.м.", "ENG"),
        ("PLT", "Штукатурные работы", "м²", "FIN"),
        ("PNT", "Малярные работы", "м²", "FIN"),
        ("FLR", "Укладка напольных покрытий", "м²", "FIN"),
        ("SNT", "Установка сантехники", "шт", "FIN"),
    ]
    work_types = []
    for code, name, unit, group_code in work_data:
        wt = WorkType(
            id=uuid4(),
            group_id=groups[group_code].id,
            name=name,
            code=code,
            unit=unit,
        )
        db.add(wt)
        work_types.append(wt)

    # === 4. Tech Sequence (for housing 1) ===
    norms = [10, 100, 80, 50, 120, 15, 30, 40, 70, 90, 60, 8]
    days = [5, 8, 6, 10, 7, 4, 12, 10, 9, 8, 7, 5]
    tech_items = []
    for i, wt in enumerate(work_types):
        ti = TechSequenceItem(
            id=uuid4(),
            housing_id=housing.id,
            work_type_id=wt.id,
            order=i + 1,
            dependency_type="finish_to_start",
            lag_days=0,
            estimated_days=days[i],
            daily_norm_volume=Decimal(str(norms[i])),
            total_volume=Decimal(str(norms[i] * days[i])),
        )
        db.add(ti)
        tech_items.append(ti)

    # === 5. Contractors ===
    contractors = []
    cdata = [
        ("ООО «СтройМастер»", "СтройМастер", "+7-999-123-45-67"),
        ("ООО «ЭлектроСервис»", "ЭлектроСервис", "+7-999-123-45-68"),
        ("ООО «ОтделкаПро»", "ОтделкаПро", "+7-999-123-45-69"),
    ]
    for name, short, phone in cdata:
        c = Contractor(id=uuid4(), name=name, short_name=short, phone=phone)
        db.add(c)
        contractors.append(c)

    # === 6. Assignments ===
    # СтройМастер → первые 6 видов работ (SMR)
    for wt in work_types[:6]:
        db.add(ContractorAssignment(
            id=uuid4(),
            contractor_id=contractors[0].id,
            housing_id=housing.id,
            work_group_id=groups["SMR"].id,
            work_type_ids=[str(wt.id)],
        ))
    # ЭлектроСервис → инженерные
    for wt in work_types[6:8]:
        db.add(ContractorAssignment(
            id=uuid4(),
            contractor_id=contractors[1].id,
            housing_id=housing.id,
            work_group_id=groups["ENG"].id,
            work_type_ids=[str(wt.id)],
        ))
    # ОтделкаПро → отделочные
    for wt in work_types[8:]:
        db.add(ContractorAssignment(
            id=uuid4(),
            contractor_id=contractors[2].id,
            housing_id=housing.id,
            work_group_id=groups["FIN"].id,
            work_type_ids=[str(wt.id)],
        ))

    # === 7. Plans + Facts for past 5 days ===
    today = date.today()
    # Get floors for first section
    sec1_floors = [f for f in all_floors if f.section_id == all_sections[0].id]

    for day_off in range(5, 0, -1):
        plan_date = today - timedelta(days=day_off)
        for _ in range(3):
            wt = random.choice(work_types[:5])
            floor = random.choice(sec1_floors[:5])
            plan = PlanItem(
                id=uuid4(),
                date=plan_date,
                housing_id=housing.id,
                section_id=all_sections[0].id,
                floor_id=floor.id,
                work_type_id=wt.id,
                contractor_id=contractors[0].id,
                planned_volume=Decimal(str(round(random.uniform(5, 50), 1))),
                unit=wt.unit,
                rs_confirmed=True,
                rs_confirmed_at=datetime.combine(plan_date, datetime.min.time().replace(hour=9)),
                source="auto",
            )
            db.add(plan)

            if random.random() < 0.7:
                fact = WorkFact(
                    id=uuid4(),
                    date=plan_date,
                    housing_id=housing.id,
                    section_id=all_sections[0].id,
                    floor_id=floor.id,
                    work_type_id=wt.id,
                    contractor_id=contractors[0].id,
                    actual_volume=Decimal(str(round(float(plan.planned_volume) * random.uniform(0.5, 1.2), 1))),
                    unit=wt.unit,
                    submitted_at=datetime.combine(plan_date, datetime.min.time().replace(hour=19, minute=30)),
                    submitted_by=str(contractors[0].id),
                    source="contractor_web",
                )
                db.add(fact)

    # === 8. Daily Summary for yesterday ===
    yesterday = today - timedelta(days=1)
    db.add(DailySummary(
        id=uuid4(),
        date=yesterday,
        housing_id=housing.id,
        total_planned=15,
        total_done_full=8,
        total_done_partial=5,
        total_done_over=1,
        total_not_done=1,
        total_no_report=0,
        total_unplanned=2,
        completion_rate=Decimal("60.0"),
        weighted_completion=Decimal("65.5"),
        submission_rate=Decimal("93.3"),
        contractor_details=[
            {"name": c.name, "completion_rate": round(random.uniform(50, 100), 1)}
            for c in contractors
        ],
        alerts=[{"level": "warning", "message": "Подрядчик 'ЭлектроСервис' выполнил 50% плана"}],
    ))

    # === 9. Sample Alert ===
    db.add(Alert(
        id=uuid4(),
        alert_type="A06",
        level="info",
        date=yesterday,
        housing_id=housing.id,
        recipient_id="rs-mock-user-001",
        recipient_role="RS",
        message=f"Сводка за {yesterday} по объекту «Корпус 1» готова.",
        channels_sent=["push"],
        sent_at=datetime.combine(yesterday, datetime.min.time().replace(hour=20, minute=30)),
        acknowledged=False,
        escalation_level=1,
        created_at=datetime.combine(yesterday, datetime.min.time().replace(hour=20, minute=30)),
    ))

    await db.commit()
    logger.info(f"Seeded: 2 housings, {len(all_sections)} sections, "
                f"{len(all_floors)} floors, {len(work_types)} work types, "
                f"{len(contractors)} contractors")