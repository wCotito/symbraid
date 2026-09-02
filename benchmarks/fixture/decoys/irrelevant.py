"""A deliberately similar-looking decoy that should not satisfy judgments."""


def refresh_cache_snapshot(cache_key: str) -> str:
    """Refresh a cache snapshot; this is not a credential or session refresh."""
    return f"cache:{cache_key}"

