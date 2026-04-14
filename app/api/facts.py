from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import Optional, List
import json

from ..database import get_db
from ..models.fact import WorkFact, FactSource
from ..models.housing import Housing, Section, Floor
from ..models.work import WorkType
from ..models.contractor import Contractor
from ..schemas.fact import Fact as FactSchema, FactCreate, FactUpdate, FactWithDetails

router = APIRouter(prefix="/api/v1/work-facts", tags=["work-facts"])

@router.post("/", response_model=FactSchema)
async def create_work_fact(
    fact_data: FactCreate,
    db: AsyncSession = Depends(get_db)
):
    """Создать запись о фактическом выполнении работ"""
    # Проверяем существование связанных сущностей
    housing_result = await db.execute(
        select(Housing).where(Housing.id == fact_data.housing_id)
    )
    if not housing_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Корпус не найден")
    
    section_result = await db.execute(
        select(Section).where(
            Section.id == fact_data.section_id,
            Section.housing_id == fact_data.housing_id
        )
    )
    if not section_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Секция не найдена")
    
    floor_result = await db.execute(
        select(Floor).where(
            Floor.id == fact_data.floor_id,
            Floor.section_id == fact_data.section_id
        )
    )
    if not floor_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Этаж не найден")
    
    work_type_result = await db.execute(
        select(WorkType).where(WorkType.id == fact_data.work_type_id)
    )
    if not work_type_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Вид работ не найден")
    
    contractor_result = await db.execute(
        select(Contractor).where(Contractor.id == fact_data.contractor_id)
    )
    if not contractor_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Подрядчик не найден")
    
    # Проверяем не является ли факт дубликатом
    existing_result = await db.execute(
        select(WorkFact).where(
            WorkFact.date == fact_data.date,
            WorkFact.housing_id == fact_data.housing_id,
            WorkFact.section_id == fact_data.section_id,
            WorkFact.floor_id == fact_data.floor_id,
            WorkFact.work_type_id == fact_data.work_type_id,
            WorkFact.contractor_id == fact_data.contractor_id
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Факт выполнения уже существует на эту дату для данной работы")
    
    # Создаём новую запись
    
    fact = WorkFact(
        date=fact_data.date,
        housing_id=fact_data.housing_id,
        section_id=fact_data.section_id,
        floor_id=fact_data.floor_id,
        work_type_id=fact_data.work_type_id,
        contractor_id=fact_data.contractor_id,
        actual_volume=fact_data.actual_volume,
        unit=fact_data.unit,
        submitted_by=fact_data.submitted_by or "contractor",
        source=FactSource.CONTRACTOR_WEB,
        comment=fact_data.comment,
    )
    
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    
    return fact

@router.get("/")
async def get_work_facts(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    housing_id: Optional[UUID] = None,
    contractor_id: Optional[UUID] = None,
    work_type_id: Optional[UUID] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Получить факты выполнения работ с фильтрами"""
    query = select(WorkFact)
    
    # Применяем фильтры
    if start_date:
        query = query.where(WorkFact.date >= start_date)
    if end_date:
        query = query.where(WorkFact.date <= end_date)
    if housing_id:
        query = query.where(WorkFact.housing_id == housing_id)
    if contractor_id:
        query = query.where(WorkFact.contractor_id == contractor_id)
    if work_type_id:
        query = query.where(WorkFact.work_type_id == work_type_id)
    
    # Пагинация
    query = query.order_by(WorkFact.date.desc(), WorkFact.submitted_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    facts = result.scalars().all()
    
    # Загружаем детали
    detailed_facts = []
    for fact in facts:
        # Получаем связанные данные
        housing_result = await db.execute(select(Housing).where(Housing.id == fact.housing_id))
        housing = housing_result.scalar_one()
        
        section_result = await db.execute(select(Section).where(Section.id == fact.section_id))
        section = section_result.scalar_one()
        
        floor_result = await db.execute(select(Floor).where(Floor.id == fact.floor_id))
        floor = floor_result.scalar_one()
        
        work_type_result = await db.execute(select(WorkType).where(WorkType.id == fact.work_type_id))
        work_type = work_type_result.scalar_one()
        
        contractor_result = await db.execute(select(Contractor).where(Contractor.id == fact.contractor_id))
        contractor = contractor_result.scalar_one()
        
        fact_dict = {
            "id": fact.id,
            "date": fact.date,
            "housing_id": fact.housing_id,
            "housing_name": housing.name,
            "section_id": fact.section_id,
            "section_name": section.name,
            "floor_id": fact.floor_id,
            "floor_name": f"Этаж {floor.floor_number}",
            "work_type_id": fact.work_type_id,
            "work_type_name": work_type.name,
            "contractor_id": fact.contractor_id,
            "contractor_name": contractor.name,
            "actual_volume": fact.actual_volume,
            "unit": fact.unit,
            "submitted_by": fact.submitted_by,
            "source": fact.source.value if hasattr(fact.source, 'value') else str(fact.source),
            "comment": fact.comment,
            "submitted_at": fact.submitted_at,
        }
        
        detailed_facts.append(fact_dict)
    
    return detailed_facts