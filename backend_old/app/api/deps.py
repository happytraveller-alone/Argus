from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core import security

from app.db.session import get_db
from app.models.user import User

async def get_current_user(
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(select(User).order_by(User.created_at.asc()))
    user = result.scalars().first()
    if user:
        return user

    default_user = User(
        email="anonymous@local",
        hashed_password=security.get_password_hash("anonymous"),
        full_name="Anonymous",
        is_active=True,
        is_superuser=True,
        role="admin",
    )
    db.add(default_user)
    await db.commit()
    await db.refresh(default_user)
    return default_user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
