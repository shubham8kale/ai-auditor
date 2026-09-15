"""Tests never connect to the user's configured cloud database or AI account."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATABASE_PASSWORD"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
