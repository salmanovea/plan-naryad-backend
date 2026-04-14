from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional

from ..database import get_session
from ..models import contractor as contractor_models
from ..schemas import contractor as schemas


router = APIRouter(prefix="/api/v1/contractors", tags=["contractors"])


@router.get("/", response_model=List[schemas.Contractor])
async def get_contractors(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Получить список подрядчиков"""
    result = await session.execute(
        select(contractor_models.Contractor)
        .offset(skip)
        .limit(limit)
        .order_by(contractor_models.Contractor.name)
    )
    contractors = result.scalars().all()
    return contractors


@router.get("/assignments/{housing_id}", response_model=schemas.ContractorAssignmentsResponse)
async def get_contractor_assignments(
    housing_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить привязки подрядчиков для корпуса"""
    # Проверяем существование корпуса
    from ..models import housing
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Housing not found")
    
    # Получаем привязки
    result = await session.execute(
        select(contractor_models.ContractorAssignment)
        .where(contractor_models.ContractorAssignment.housing_id == housing_id)
    )
    assignments = result.scalars().all()
    
    # Загружаем связанные подрядчики
    for assignment in assignments:
        result = await session.execute(
            select(contractor_models.Contractor).where(contractor_models.Contractor.id == assignment.contractor_id)
        )
        assignment.contractor = result.scalar_one_or_none()
    
    return schemas.ContractorAssignmentsResponse(
        housing_id=housing_id,
        assignments=assignments
    )


@router.get("/{contractor_id}", response_model=schemas.Contractor)
async def get_contractor(
    contractor_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить подрядчика по ID"""
    result = await session.execute(
        select(contractor_models.Contractor).where(contractor_models.Contractor.id == contractor_id)
    )
    contractor = result.scalar_one_or_none()
    
    if not contractor:
        raise HTTPException(status_code=404, detail="Contractor not found")
    
    return contractor


@router.post("/", response_model=schemas.Contractor)
async def create_contractor(
    contractor_data: schemas.ContractorCreate,
    session: AsyncSession = Depends(get_session)
):
    """Создать нового подрядчика"""
    db_contractor = contractor_models.Contractor(**contractor_data.dict())
    session.add(db_contractor)
    await session.commit()
    await session.refresh(db_contractor)
    return db_contractor


@router.put("/{contractor_id}", response_model=schemas.Contractor)
async def update_contractor(
    contractor_id: str,
    contractor_update: schemas.ContractorUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Обновить данные подрядчика"""
    result = await session.execute(
        select(contractor_models.Contractor).where(contractor_models.Contractor.id == contractor_id)
    )
    db_contractor = result.scalar_one_or_none()
    
    if not db_contractor:
        raise HTTPException(status_code=404, detail="Contractor not found")
    
    update_data = contractor_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_contractor, field, value)
    
    await session.commit()
    await session.refresh(db_contractor)
    return db_contractor


@router.post("/assignments", response_model=schemas.ContractorAssignment)
async def create_contractor_assignment(
    assignment_data: schemas.ContractorAssignmentCreate,
    session: AsyncSession = Depends(get_session)
):
    """Создать привязку подрядчика к работам"""
    # Проверяем существование подрядчика и корпуса
    result = await session.execute(
        select(contractor_models.Contractor).where(contractor_models.Contractor.id == assignment_data.contractor_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Contractor not found")
    
    from ..models import housing
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == assignment_data.housing_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Housing not found")
    
    # Проверяем секцию (если указана)
    if assignment_data.section_id:
        result = await session.execute(
            select(housing.Section).where(housing.Section.id == assignment_data.section_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Section not found")
    
    # Проверяем группу работ (если указана)
    if assignment_data.work_group_id:
        from ..models import work
        result = await session.execute(
            select(work.WorkGroup).where(work.WorkGroup.id == assignment_data.work_group_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Work group not found")
    
    db_assignment = contractor_models.ContractorAssignment(**assignment_data.dict())
    session.add(db_assignment)
    await session.commit()
    await session.refresh(db_assignment)
    
    # Загружаем связанного подрядчика
    result = await session.execute(
        select(contractor_models.Contractor).where(contractor_models.Contractor.id == db_assignment.contractor_id)
    )
    db_assignment.contractor = result.scalar_one_or_none()
    
    return db_assignment