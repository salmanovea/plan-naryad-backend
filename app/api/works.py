from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional

from ..database import get_session
from ..models import work as work_models
from ..schemas import work as schemas


router = APIRouter(prefix="/api/v1/works", tags=["works"])


@router.get("/", response_model=List[schemas.WorkType])
async def get_work_types(
    skip: int = 0,
    limit: int = 100,
    group_id: Optional[str] = Query(None, description="Фильтр по группе работ"),
    session: AsyncSession = Depends(get_session)
):
    """Получить список видов работ"""
    query = select(work_models.WorkType)
    
    if group_id:
        query = query.where(work_models.WorkType.group_id == group_id)
    
    result = await session.execute(
        query.offset(skip).limit(limit)
    )
    work_types = result.scalars().all()
    
    # Загружаем связанные группы для каждого вида работ
    for wt in work_types:
        result = await session.execute(
            select(work_models.WorkGroup).where(work_models.WorkGroup.id == wt.group_id)
        )
        wt.group = result.scalar_one_or_none()
    
    return work_types


@router.get("/groups", response_model=List[schemas.WorkGroup])
async def get_work_groups(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Получить список групп работ"""
    result = await session.execute(
        select(work_models.WorkGroup)
        .offset(skip)
        .limit(limit)
        .order_by(work_models.WorkGroup.order)
    )
    groups = result.scalars().all()
    return groups


@router.get("/tech-sequence/{housing_id}", response_model=schemas.TechSequence)
async def get_tech_sequence(
    housing_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить технологическую последовательность для корпуса"""
    # Проверяем существование корпуса
    from ..models import housing
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    housing_obj = result.scalar_one_or_none()
    
    if not housing_obj:
        raise HTTPException(status_code=404, detail="Housing not found")
    
    # Получаем технологическую последовательность
    result = await session.execute(
        select(work_models.TechSequenceItem)
        .where(work_models.TechSequenceItem.housing_id == housing_id)
        .order_by(work_models.TechSequenceItem.order)
    )
    items = result.scalars().all()
    
    # Загружаем связанные виды работ для каждого элемента
    for item in items:
        result = await session.execute(
            select(work_models.WorkType).where(work_models.WorkType.id == item.work_type_id)
        )
        item.work_type = result.scalar_one_or_none()
    
    return schemas.TechSequence(
        housing_id=housing_id,
        housing_name=housing_obj.name,
        sequence=[
            {
                "id": str(item.id),
                "work_type_id": str(item.work_type_id),
                "work_type_name": item.work_type.name if item.work_type else None,
                "order": item.order,
                "depends_on": item.depends_on,
                "dependency_type": item.dependency_type
            }
            for item in items
        ]
    )


@router.get("/{work_type_id}", response_model=schemas.WorkType)
async def get_work_type(
    work_type_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить вид работ по ID"""
    result = await session.execute(
        select(work_models.WorkType).where(work_models.WorkType.id == work_type_id)
    )
    work_type = result.scalar_one_or_none()
    
    if not work_type:
        raise HTTPException(status_code=404, detail="Work type not found")
    
    # Загружаем группу
    result = await session.execute(
        select(work_models.WorkGroup).where(work_models.WorkGroup.id == work_type.group_id)
    )
    work_type.group = result.scalar_one_or_none()
    
    return work_type


@router.post("/groups", response_model=schemas.WorkGroup)
async def create_work_group(
    group_data: schemas.WorkGroupBase,
    session: AsyncSession = Depends(get_session)
):
    """Создать новую группу работ"""
    db_group = work_models.WorkGroup(**group_data.dict())
    session.add(db_group)
    await session.commit()
    await session.refresh(db_group)
    return db_group


@router.post("/", response_model=schemas.WorkType)
async def create_work_type(
    work_type_data: schemas.WorkTypeCreate,
    session: AsyncSession = Depends(get_session)
):
    """Создать новый вид работ"""
    db_work_type = work_models.WorkType(**work_type_data.dict())
    session.add(db_work_type)
    await session.commit()
    await session.refresh(db_work_type)
    return db_work_type


@router.post("/tech-sequence", response_model=schemas.TechSequenceItem)
async def create_tech_sequence_item(
    item_data: schemas.TechSequenceItemCreate,
    session: AsyncSession = Depends(get_session)
):
    """Добавить элемент в технологическую последовательность"""
    # Проверяем существование корпуса и вида работ
    from ..models import housing
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == item_data.housing_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Housing not found")
    
    result = await session.execute(
        select(work_models.WorkType).where(work_models.WorkType.id == item_data.work_type_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Work type not found")
    
    db_item = work_models.TechSequenceItem(**item_data.dict())
    session.add(db_item)
    await session.commit()
    await session.refresh(db_item)
    
    # Загружаем связанный вид работ
    result = await session.execute(
        select(work_models.WorkType).where(work_models.WorkType.id == db_item.work_type_id)
    )
    db_item.work_type = result.scalar_one_or_none()
    
    return db_item