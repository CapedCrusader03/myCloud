"""
Authentication API routes.

Handles user registration and login with strict input validation.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware import rate_limiter
from models.domain import User
from schemas import UserCreate, TokenResponse, MessageResponse
from services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=201,
    dependencies=[Depends(rate_limiter)],
)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await auth_service.get_user_by_email(db, user_in.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user_in.email,
        hashed_password=auth_service.get_password_hash(user_in.password),
    )
    db.add(new_user)
    await db.commit()
    return MessageResponse(message="User created successfully")


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limiter)],
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.get_user_by_email(db, form_data.username)
    if not user or not auth_service.verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_service.create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=access_token)
