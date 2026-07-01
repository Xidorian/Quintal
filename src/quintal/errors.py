"""Single error type carried through the pipeline (per house standards)."""

from __future__ import annotations


class AppError(Exception):
    """Application error with a status hint and a safe-to-expose flag.

    ``operational`` errors (bad listing, upstream timeout) are expected and handled
    gracefully — the pipeline skips the item and logs a warning. Non-operational
    errors are programmer bugs and should surface with a full traceback.
    """

    def __init__(
        self,
        message: str,
        *,
        operational: bool = True,
        safe: bool = False,
        status: int = 500,
    ) -> None:
        super().__init__(message)
        self.operational = operational
        self.safe = safe
        self.status = status
