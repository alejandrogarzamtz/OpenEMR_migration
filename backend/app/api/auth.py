from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import Login, Token
from ..security import create_token, password_hash

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/token", response_model=Token)
def login(body: Login, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not user.active or not password_hash.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return Token(access_token=create_token(user))

