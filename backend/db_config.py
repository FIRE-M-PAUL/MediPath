import os


def build_database_uri(app_dir):
    """
    Keep current SQLite behavior by default.
    Optionally allow MEDIPATH_DATABASE_URI override for future use.
    """
    default_db = os.path.abspath(os.path.join(app_dir, 'backend', 'instance', 'medipath.db'))
    default_uri = _sqlite_uri_from_path(default_db)
    raw_uri = (os.getenv('MEDIPATH_DATABASE_URI') or '').strip()
    if not raw_uri:
        _ensure_sqlite_parent(default_uri, app_dir)
        return default_uri

    # Allow users to provide relative SQLite URIs and keep them portable after folder moves.
    if raw_uri.startswith('sqlite:///') and not raw_uri.startswith('sqlite:////'):
        rel_path = raw_uri.replace('sqlite:///', '', 1)
        if rel_path and not os.path.isabs(rel_path):
            abs_path = os.path.abspath(os.path.join(app_dir, rel_path))
            raw_uri = _sqlite_uri_from_path(abs_path)

    _ensure_sqlite_parent(raw_uri, app_dir)
    return raw_uri


def resolve_sqlite_path_from_uri(uri, app_dir):
    """Resolve sqlite:/// URI into absolute filesystem path."""
    normalized = (uri or '').strip()
    if not normalized.startswith('sqlite:///'):
        return None

    raw = normalized.replace('sqlite:///', '', 1)
    if os.path.isabs(raw):
        return os.path.abspath(raw)
    return os.path.abspath(os.path.join(app_dir, raw))


def _sqlite_uri_from_path(path):
    # SQLAlchemy accepts forward slashes on Windows as well.
    return f"sqlite:///{path.replace(os.sep, '/')}"


def _ensure_sqlite_parent(uri, app_dir):
    sqlite_path = resolve_sqlite_path_from_uri(uri, app_dir)
    if sqlite_path:
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
