"""
Seed data для модуля управления численностью.
v2: с объектами + план от стройки
v3: с подрядчиками, челленджами, нарушениями
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workforce import (
    Project, ProjectObject, WorkforceNorm, BudgetPeriod, BudgetItem,
    HeadcountFact, HeadcountPlan,
    WfContractor, WfContractorAssignment,
    Challenge, ChallengeItem, MobilizationPlan, MobilizationCheckpoint,
    Violation, ChallengeStatus, CheckpointStatus, ViolationType,
)

NORMS = [
    # (work_type, class, day, month)
    ("Монолитные работы", "Комфорт", 37447, 824000),
    ("Кладка", "Комфорт", 15438, 340000),
    ("Отделочные работы", "Комфорт", 16216, 357000),
    ("ЭМР", "Комфорт", 31179, 686000),
    ("Сантехника", "Комфорт", 19060, 419000),
    ("Вентиляция и кондиционирование", "Комфорт", 27735, 610000),
    ("Фасад", "Комфорт", 22762, 501000),
    ("Кровля", "Комфорт", 35557, 782000),
    ("Светопрозрачные конструкции", "Комфорт", 39536, 870000),
    ("Металлоконструкции", "Комфорт", 19997, 440000),
    ("Наружные сети", "Комфорт", 53085, 1168000),
    ("Подготовка стройплощадки", "Комфорт", 54026, 1189000),
    ("Благоустройство", "Комфорт", 43170, 950000),
    ("Земляные работы", "Комфорт", 301831, 6640000),
    ("Гидроизоляция", "Комфорт", 106867, 2351000),
    ("СС", "Комфорт", 19555, 430000),
    ("Вертикальный транспорт", "Комфорт", 66430, 1461000),
    ("СТК", "Комфорт", 837353, 18422000),
    ("Монолитные работы", "Бизнес", 33597, 739000),
    ("Кладка", "Бизнес", 15220, 335000),
    ("Отделочные работы", "Бизнес", 22421, 493000),
    ("ЭМР", "Бизнес", 28011, 616000),
    ("Сантехника", "Бизнес", 17732, 390000),
    ("Вентиляция и кондиционирование", "Бизнес", 25538, 562000),
    ("Фасад", "Бизнес", 26262, 578000),
    ("Кровля", "Бизнес", 165587, 3643000),
    ("Светопрозрачные конструкции", "Бизнес", 46317, 1019000),
    ("Металлоконструкции", "Бизнес", 60739, 1336000),
    ("Наружные сети", "Бизнес", 13489, 297000),
    ("Подготовка стройплощадки", "Бизнес", 12262, 270000),
    ("Благоустройство", "Бизнес", 40497, 891000),
    ("Земляные работы", "Бизнес", 55251, 1216000),
    ("Гидроизоляция", "Бизнес", 26784, 589000),
    ("СС", "Бизнес", 37793, 831000),
    ("Вертикальный транспорт", "Бизнес", 29785, 655000),
]

DEMO_PROJECTS = [
    {
        "name": "ЖК Уютный Комфорт",
        "class": "Комфорт",
        "objects": ["Корпус 1.1", "Корпус 1.2", "Корпус 2.1"],
    },
    {
        "name": "ЖК Солнечный Берег",
        "class": "Комфорт",
        "objects": ["Корпус А", "Корпус Б"],
    },
    {
        "name": "ЖК Бизнес-Квартал",
        "class": "Бизнес",
        "objects": ["Корпус 1", "Корпус 2"],
    },
]

WORK_TYPES_MAIN = [
    "Монолитные работы", "Кладка", "Отделочные работы",
    "ЭМР", "Сантехника", "Фасад",
]

DEMO_CONTRACTORS = [
    {"name": "СтройМонтаж ООО", "inn": "7701234567"},
    {"name": "ПромКладка", "inn": "7709876543"},
    {"name": "ОтделкаПрофи", "inn": "7712345678"},
    {"name": "ЭлектроМонтажСервис", "inn": "7787654321"},
    {"name": "СантехГрупп", "inn": "7756789012"},
    {"name": "ФасадСтрой", "inn": "7723456789"},
    {"name": "МонолитБригада", "inn": "7734567890"},
]


async def seed_workforce(db: AsyncSession):
    """Заполняет БД демо-данными для workforce модуля."""
    # Check if norms exist
    existing = await db.execute(select(WorkforceNorm).limit(1))
    if existing.scalar_one_or_none():
        return  # Already seeded

    print("Seeding workforce data...")
    random.seed(42)

    # 1. Norms
    for wt, cls, day, month in NORMS:
        db.add(WorkforceNorm(
            work_type=wt, project_class=cls,
            median_day_bdr=Decimal(str(day)), median_month_bdr=Decimal(str(month)),
        ))
    await db.flush()

    today = date.today()
    period = today.replace(day=1)

    # 2. WfContractors
    contractors = []
    for cd in DEMO_CONTRACTORS:
        c = WfContractor(name=cd["name"], inn=cd["inn"])
        db.add(c)
        await db.flush()
        contractors.append(c)

    # Map work_type -> contractor (assign each work type to a primary contractor)
    wt_contractor_map = {wt: contractors[i % len(contractors)] for i, wt in enumerate(WORK_TYPES_MAIN)}

    # 3. Projects, Objects, Budgets, Headcount
    all_project_objects = []  # (proj, obj) pairs for later use

    for proj_def in DEMO_PROJECTS:
        proj = Project(name=proj_def["name"], project_class=proj_def["class"])
        db.add(proj)
        await db.flush()

        # Create objects with planned_end_date and budget remaining
        obj_list = []
        for i, obj_name in enumerate(proj_def["objects"]):
            # Stagger planned end dates
            planned_end = today + timedelta(days=random.randint(60, 365))
            total_remaining = Decimal(str(random.randint(50, 300) * 1_000_000))
            obj = ProjectObject(
                project_id=proj.id, name=obj_name,
                planned_end_date=planned_end,
                total_budget_remaining=total_remaining,
            )
            db.add(obj)
            await db.flush()
            obj_list.append(obj)
            all_project_objects.append((proj, obj))

        # Budget period
        bp = BudgetPeriod(project_id=proj.id, period_month=period)
        db.add(bp)
        await db.flush()

        # Get norms for this class
        norms_map = {wt: month for wt, cls, day, month in NORMS if cls == proj_def["class"]}

        for obj in obj_list:
            for wt in WORK_TYPES_MAIN:
                norm_month = norms_map.get(wt, 550000)
                contractor = wt_contractor_map[wt]

                # Random BDR 5-40M per object per work type
                bdr = random.randint(5, 40) * 1_000_000
                uv = int(bdr * random.uniform(0.05, 0.35))
                net = bdr - uv
                required = net / norm_month if norm_month else 0

                # remaining_amount (30-80% of net)
                remaining_pct = random.uniform(0.3, 0.8)
                remaining = Decimal(str(int(net * remaining_pct)))
                wt_planned_end = today + timedelta(days=random.randint(30, 300))

                # Budget item
                db.add(BudgetItem(
                    budget_period_id=bp.id, object_id=obj.id,
                    work_type=wt,
                    bdr_amount=Decimal(str(bdr)),
                    management_completion_amount=Decimal(str(uv)),
                    contractor_id=contractor.id,
                    remaining_amount=remaining,
                    planned_end_date=wt_planned_end,
                ))

                # Plan from construction (70-95% of required)
                plan_ratio = random.uniform(0.7, 0.95)
                plan_count = max(1, int(required * plan_ratio))
                db.add(HeadcountPlan(
                    project_id=proj.id, object_id=obj.id,
                    work_type=wt, period_month=period, planned_count=plan_count,
                    contractor_id=contractor.id,
                ))

                # Headcount facts for last 35 days (some with contractor_id)
                base_count = max(1, int(required * random.uniform(0.3, 0.9)))
                for d in range(35):
                    fact_date = today - timedelta(days=d)
                    drift = 0.02 * (35 - d) / 35 if random.random() > 0.5 else -0.01 * (35 - d) / 35
                    daily = max(0, int(base_count * (1 + drift + random.uniform(-0.15, 0.15))))
                    if daily > 0:
                        db.add(HeadcountFact(
                            project_id=proj.id, object_id=obj.id,
                            work_type=wt, fact_date=fact_date,
                            count=daily, source="manual",
                            contractor_id=contractor.id,
                        ))

                # WfContractor assignment
                db.add(WfContractorAssignment(
                    contractor_id=contractor.id,
                    object_id=obj.id,
                    work_type=wt,
                ))

    await db.flush()

    # 4. Demo challenges (use first project's objects)
    if all_project_objects:
        proj1, obj1 = all_project_objects[0]
        proj1_obj2 = all_project_objects[1] if len(all_project_objects) > 1 else None

        # Challenge 1: approved with mobilization plan
        ch1 = Challenge(
            project_id=proj1.id,
            object_id=obj1.id,
            period_month=period,
            status=ChallengeStatus.APPROVED,
            approved_by="Иванов И.И.",
            approved_at=today,
            comment="Требуется срочная мобилизация монолитчиков",
        )
        db.add(ch1)
        await db.flush()

        ci1 = ChallengeItem(
            challenge_id=ch1.id,
            work_type="Монолитные работы",
            system_baseline=12,
            requested_count=20,
            approved_count=18,
            requires_mobilization_plan=True,
        )
        db.add(ci1)
        await db.flush()

        mp1 = MobilizationPlan(
            challenge_item_id=ci1.id,
            planned_date=today + timedelta(days=7),
            action="Вывод новой бригады",
            headcount_delta=6,
            contractor_name="МонолитБригада",
        )
        db.add(mp1)
        await db.flush()

        # Checkpoints
        db.add(MobilizationCheckpoint(
            mobilization_plan_id=mp1.id,
            check_date=today + timedelta(days=7),
            expected_cumulative=6,
            actual_cumulative=None,
            status=CheckpointStatus.PENDING,
        ))
        db.add(MobilizationCheckpoint(
            mobilization_plan_id=mp1.id,
            check_date=today + timedelta(days=14),
            expected_cumulative=12,
            actual_cumulative=None,
            status=CheckpointStatus.PENDING,
        ))

        # Challenge 2: pending, second object
        if proj1_obj2:
            _, obj2 = proj1_obj2
            ch2 = Challenge(
                project_id=proj1.id,
                object_id=obj2.id,
                period_month=period,
                status=ChallengeStatus.PENDING,
                comment="Заявка на увеличение численности отделочников",
            )
            db.add(ch2)
            await db.flush()

            ci2 = ChallengeItem(
                challenge_id=ch2.id,
                work_type="Отделочные работы",
                system_baseline=8,
                requested_count=15,
                requires_mobilization_plan=False,
            )
            db.add(ci2)

    await db.flush()

    # 5. Demo violations
    if all_project_objects:
        proj1, obj1 = all_project_objects[0]
        c0 = contractors[0]
        c1 = contractors[1]

        violations_data = [
            {
                "project_id": proj1.id, "object_id": obj1.id,
                "work_type": "Монолитные работы",
                "contractor_id": c0.id,
                "violation_date": today - timedelta(days=5),
                "violation_type": ViolationType.COVERAGE_CRITICAL,
                "description": "Обеспеченность по монолиту упала ниже 40% на протяжении 5 дней",
                "plan_count": 20, "fact_count": 8,
                "escalated": False,
            },
            {
                "project_id": proj1.id, "object_id": obj1.id,
                "work_type": "Кладка",
                "contractor_id": c1.id,
                "violation_date": today - timedelta(days=12),
                "violation_type": ViolationType.PLAN_NOT_MET,
                "description": "Фактическая численность кладчиков ниже плана за последние 2 недели",
                "plan_count": 15, "fact_count": 9,
                "escalated": True, "escalated_to": "Директор по строительству",
            },
            {
                "project_id": proj1.id, "object_id": obj1.id,
                "work_type": "ЭМР",
                "contractor_id": None,
                "violation_date": today - timedelta(days=20),
                "violation_type": ViolationType.MOBILIZATION_MISSED,
                "description": "Не выведена бригада электриков согласно плану мобилизации",
                "plan_count": 10, "fact_count": 3,
                "escalated": False,
                "resolved": True,
            },
        ]

        for vd in violations_data:
            resolved = vd.pop("resolved", False)
            escalated = vd.pop("escalated", False)
            escalated_to = vd.pop("escalated_to", None)
            v = Violation(**vd, escalated=escalated, escalated_to=escalated_to, resolved=resolved)
            db.add(v)

        # Extra violations for different objects
        if len(all_project_objects) > 2:
            proj2, obj3 = all_project_objects[2]
            db.add(Violation(
                project_id=proj2.id, object_id=obj3.id,
                work_type="Сантехника",
                contractor_id=contractors[4].id,
                violation_date=today - timedelta(days=3),
                violation_type=ViolationType.COVERAGE_CRITICAL,
                description="Критическое снижение численности сантехников на объекте",
                plan_count=12, fact_count=4,
            ))
            db.add(Violation(
                project_id=proj2.id, object_id=obj3.id,
                work_type="Фасад",
                contractor_id=contractors[5].id,
                violation_date=today - timedelta(days=8),
                violation_type=ViolationType.PLAN_NOT_MET,
                description="Не выполнен план по фасадным работам",
                plan_count=8, fact_count=5,
            ))

    await db.commit()
    print("Workforce seed complete (v3).")
