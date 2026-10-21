"""Practice adapter for the neutral serialized-run decoder."""

from ..serialized_rich import decode_rich as _decode
from .models import Run


def decode_rich(value):
    return _decode(value, Run)
