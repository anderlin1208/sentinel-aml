import httpx
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from .db import get_db
from .models import Profile
from .config import settings

async def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Profile:
    cfg = settings()
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Se requiere iniciar sesión')
    if not cfg.supabase_url or not cfg.supabase_anon_key:
        raise HTTPException(503, 'Configura SUPABASE_URL y SUPABASE_ANON_KEY en el servidor')
    token = authorization.removeprefix('Bearer ').strip()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(f'{cfg.supabase_url.rstrip("/")}/auth/v1/user', headers={'apikey': cfg.supabase_anon_key, 'Authorization': f'Bearer {token}'})
        if response.status_code != 200:
            raise HTTPException(401, 'Sesión inválida o expirada')
        payload = response.json()
    except httpx.HTTPError:
        raise HTTPException(503, 'No se pudo verificar la sesión con Supabase')
    user_id, email = payload.get('id'), (payload.get('email') or '').lower()
    if not user_id or not email or not payload.get('email_confirmed_at'):
        raise HTTPException(403, 'La cuenta requiere correo verificado')
    profile = db.get(Profile, user_id)
    if not profile:
        profile = Profile(id=user_id, email=email, role='admin' if cfg.admin_email and email == cfg.admin_email.lower() else 'pending')
        db.add(profile)
        db.commit()
        db.refresh(profile)
    if profile.role == 'pending':
        raise HTTPException(403, 'Tu cuenta está pendiente de aprobación por un administrador')
    return profile

def require_role(*roles):
    async def check(user: Profile = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, 'Permisos insuficientes')
        return user
    return check
