"""Client Supabase partagé (équivalent de src/lib/supabase.ts)."""
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def get_client():
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    if not url or not key:
        raise ImproperlyConfigured(
            "SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env "
            "(voir .env.example)."
        )
    from supabase import create_client

    return create_client(url, key)
