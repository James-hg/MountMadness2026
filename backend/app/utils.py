import re

def slugify(name: str) -> str:
    """
    'Housing / Rent' -> 'housing_rent'
    Lowercase, non-alnum -> underscore, collapse, trim.
    """
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        raise ValueError("Category name cannot produce a valid slug.")
    return s