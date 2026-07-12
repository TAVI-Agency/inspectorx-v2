"""Supabase-клиенты: Inspector X (rw, service key) и JurisBase lexportal (ro)."""
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(".env.importer")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"нет переменной окружения {name} (см. .env.importer.example)")
    return value


def ix_client() -> Client:
    return create_client(_env("IX_SUPABASE_URL"), _env("IX_SUPABASE_SERVICE_KEY"))


def jb_client() -> Client:
    return create_client(_env("JB_SUPABASE_URL"), _env("JB_SUPABASE_KEY"))
