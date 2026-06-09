"""
Database exception helpers.

Provides :func:`is_connectivity_error` for detecting transient SQLite
connection or lock errors so that operations functions can emit context-specific
error messages rather than generic ones.

Why this exists:
    SQLite can raise ``OperationalError`` with messages like "database is
    locked" under concurrent write load. Distinguishing these from logic
    errors (e.g. constraint violations) allows the operations layer to give
    users more actionable feedback.
"""

from sqlalchemy.exc import OperationalError

# Substrings found in SQLite OperationalError messages that indicate a
# transient connectivity or lock condition rather than a logic error.
_CONNECTIVITY_MESSAGES = frozenset(
    {
        "database is locked",
        "unable to open database",
        "disk i/o error",
        "cannot open database",
    }
)


def is_connectivity_error(exc: BaseException) -> bool:
    """Return ``True`` if *exc* represents a transient SQLite connectivity issue.

    Checks whether the exception is a SQLAlchemy :class:`~sqlalchemy.exc.OperationalError`
    whose message contains one of the known transient SQLite error strings.

    Args:
        exc: The exception to inspect.

    Returns:
        ``True`` if the exception looks like a transient connectivity or lock
        error; ``False`` otherwise.

    Example:
        >>> try:
        ...     async with get_db_session() as session:
        ...         ...
        ... except Exception as e:
        ...     if is_connectivity_error(e):
        ...         print("Temporary database issue. Please retry.")
        ...     raise
    """
    if not isinstance(exc, OperationalError):
        return False
    message = str(exc).lower()
    return any(phrase in message for phrase in _CONNECTIVITY_MESSAGES)
