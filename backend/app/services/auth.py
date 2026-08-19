from datetime import datetime, timedelta
import hashlib

import bcrypt
from jose import JWTError, jwt

SECRET_KEY = "digitaldrm_secret_key_rml_ecd"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480


def _safe_password(p: str) -> str:
    if len(p.encode("utf-8")) > 72:
        return hashlib.sha256(p.encode("utf-8")).hexdigest()
    return p


def hash_password(password: str):
    password = _safe_password(password)
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str):
    plain_password = _safe_password(plain_password)

    if not hashed_password:
        return False

    if isinstance(hashed_password, str) and hashed_password.startswith("$2"):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    if isinstance(hashed_password, str) and hashed_password.startswith("$pbkdf2-sha256$"):
        try:
            import passlib.hash

            return passlib.hash.pbkdf2_sha256.verify(plain_password, hashed_password)
        except Exception:
            return False

    return plain_password == hashed_password


def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user_token(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

def get_current_admin(payload: dict = Depends(get_current_user_token)):
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not enough privileges")
    return payload