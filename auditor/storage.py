from pathlib import Path

import httpx

from auditor.config import settings


def local_path(key: str) -> Path:
    root = settings().storage_root.resolve()
    target = (root / key).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid storage key")
    return target


async def save_file(key: str, data: bytes, content_type: str):
    config = settings()
    if config.supabase_url and config.supabase_service_role_key:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{config.supabase_url}/storage/v1/object/{config.supabase_storage_bucket}/{key}",
                headers={"apikey": config.supabase_service_role_key, "Content-Type": content_type},
                content=data,
            )
            response.raise_for_status()
    else:
        path = local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


async def read_file(key: str) -> bytes:
    config = settings()
    if config.supabase_url and config.supabase_service_role_key:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{config.supabase_url}/storage/v1/object/{config.supabase_storage_bucket}/{key}",
                headers={"apikey": config.supabase_service_role_key},
            )
            response.raise_for_status()
            return response.content
    return local_path(key).read_bytes()
