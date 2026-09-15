from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException, Request

from auditor.config import settings


@dataclass
class User:
    id: str
    name: str


async def current_user(request: Request, authorization: str = Header(default="")) -> User:
    config = settings()
    if config.auditor_local_auth and config.auditor_env == "development":
        if request.client and request.client.host in {"127.0.0.1", "::1", "testclient"}:
            return User("local-reviewer", "Local reviewer")
        raise HTTPException(403, "Local development access is restricted to this computer.")
    if not config.supabase_url or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to access this workspace.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                config.supabase_url + "/auth/v1/user",
                headers={
                    "Authorization": authorization,
                    "apikey": config.supabase_anon_key,
                },
            )
        if response.status_code != 200:
            raise HTTPException(401, "Your session has expired. Please sign in again.")
        data = response.json()
        name = data.get("user_metadata", {}).get("full_name") or data.get("email") or data["id"]
        return User(data["id"], name)
    except httpx.HTTPError:
        raise HTTPException(503, "Sign-in service is temporarily unavailable. Please retry.") from None
