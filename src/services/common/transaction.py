"""Transaction boundaries for services that wait on Raport.

Every SELECT autobegins a transaction and the session keeps it open until commit or
rollback. Postgres kills a backend that sits «idle in transaction» longer than
`idle_in_transaction_session_timeout`, so a service must not hold one while it paginates
Raport — a large housing takes minutes there. Ending the transaction before the wait lets
the connection go back to the pool; the next query begins a fresh one.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def end_transaction(db: AsyncSession) -> None:
    """End the current transaction before a long wait on an external system.

    Implemented as a commit: services that read reference data have nothing to write, so
    the commit only releases the connection. Callers with pending writes must not use it —
    the pattern is «fetch first, then write in one short transaction».
    """
    await db.commit()
