from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.core.config import Settings


class SupabaseStore:
    """REST y Storage siempre con el JWT del usuario: RLS sigue siendo la barrera."""

    def __init__(self, settings: Settings, token: str):
        self.client = httpx.AsyncClient(
            base_url=settings.supabase_url.rstrip("/"), timeout=25,
            headers={"apikey": settings.supabase_publishable_key, "Authorization": f"Bearer {token}"},
        )

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, **kwargs):
        response = await self.client.request(method, path, **kwargs)
        if response.status_code in (401, 403):
            raise HTTPException(401 if response.status_code == 401 else 403,
                                "Tu sesión venció. Vuelve a iniciar sesión." if response.status_code == 401 else "No tienes permiso para esta operación.")
        if response.is_error:
            code = response.json().get("code", "") if "application/json" in response.headers.get("content-type", "") else ""
            if code in ("23505", "23503", "23514", "P0001"):
                raise HTTPException(409, "La operación entró en conflicto. Recarga la conversación y vuelve a intentarlo.")
            raise HTTPException(502, "Supabase no pudo completar la operación. Revisa la configuración y las migraciones.")
        return response

    async def user(self):
        return (await self.request("GET", "/auth/v1/user")).json()

    async def rows(self, table, filters=None, *, order=None, limit=None, offset=None, select='*'):
        params = {k: f"in.({','.join(v)})" if isinstance(v, list) else f"{v[0]}.{v[1]}" if isinstance(v, tuple) else f"eq.{v}"
                  for k, v in (filters or {}).items()}
        params["select"] = select
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        if offset:
            params['offset'] = str(offset)
        return (await self.request("GET", f"/rest/v1/{table}", params=params)).json()

    async def one(self, table, filters):
        rows = await self.rows(table, filters, limit=1)
        if not rows:
            raise HTTPException(404, "El recurso no existe o no tienes acceso.")
        return rows[0]

    async def insert(self, table, data):
        return (await self.request("POST", f"/rest/v1/{table}", json=data, headers={"Prefer": "return=representation"})).json()

    async def update(self, table, filters, data):
        return (await self.request("PATCH", f"/rest/v1/{table}", params={k: f"eq.{v}" for k, v in filters.items()},
                                   json=data, headers={"Prefer": "return=representation"})).json()

    async def delete(self, table, filters):
        await self.request("DELETE", f"/rest/v1/{table}", params={k: f"eq.{v}" for k, v in filters.items()})

    async def rpc(self, name, data):
        response = await self.request("POST", f"/rest/v1/rpc/{name}", json=data)
        return response.json() if response.content else None

    async def upload(self, path, data, mime, *, bucket='project-files'):
        await self.request("POST", f"/storage/v1/object/{bucket}/{quote(path, safe='/')}",
                           content=data, headers={"Content-Type": mime, "x-upsert": "false"})

    async def remove_object(self, path, *, bucket='project-files'):
        await self.request("DELETE", f"/storage/v1/object/{bucket}", json={"prefixes": [path]})

    async def download(self, path, *, bucket='project-files', max_bytes=None):
        url = f"/storage/v1/object/authenticated/{bucket}/{quote(path, safe='/')}"
        if max_bytes is None:
            return (await self.request("GET", url)).content
        async with self.client.stream('GET', url) as response:
            if response.is_error:
                raise HTTPException(response.status_code if response.status_code in (401, 403) else 422,
                                    'El archivo privado no está disponible. Revisa tu acceso y su existencia en Storage.')
            output = bytearray()
            async for chunk in response.aiter_bytes():
                if len(output) + len(chunk) > max_bytes:
                    raise HTTPException(413, 'El archivo supera el límite de descarga para esta ejecución.')
                output.extend(chunk)
            return bytes(output)
