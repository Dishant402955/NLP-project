"""Input validation and conservative request preprocessing."""

from __future__ import annotations


class InvalidRequestError(ValueError):
    """Raised when a request contains no usable text."""


def normalize_request(request: str) -> str:
    """Validate a request and remove only surrounding whitespace.

    Internal whitespace, Unicode code points, punctuation, quotes, paths,
    and shell-like text are preserved. In particular, this function does
    not tokenize, interpret, or execute the request.
    """
    if not isinstance(request, str):
        raise TypeError("request must be a string")

    normalized = request.strip()
    if not normalized:
        raise InvalidRequestError("request must contain non-whitespace text")

    return normalized
