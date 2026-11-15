from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.supabase import SupabaseStore

bearer = HTTPBearer(auto_error=False)


@dataclass
class Identity:
    user_id: str
    store: SupabaseStore


async def authenticated(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Inicia sesión para utilizar el asistente.")
    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Falta configurar Supabase en el backend.")
    store = SupabaseStore(settings, credentials.credentials)
    try:
        user = await store.user()
        yield Identity(user["id"], store)
    except httpx.HTTPError:
        raise HTTPException(503, "No se pudo conectar con Supabase. Inténtalo de nuevo.") from None
    finally:
        await store.close()


CurrentUser = Annotated[Identity, Depends(authenticated)]
