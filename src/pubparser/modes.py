from enum import StrEnum


class ParsingMode(StrEnum):
    """Controls standards recovery, never security protections."""

    STRICT = "strict"
    NORMAL = "normal"
    COMPATIBILITY = "compatibility"


def coerce_parsing_mode(value: ParsingMode | str) -> ParsingMode:
    if isinstance(value, ParsingMode):
        return value
    try:
        return ParsingMode(value)
    except ValueError as exc:
        choices = ", ".join(mode.value for mode in ParsingMode)
        raise ValueError(f"unknown parsing mode {value!r}; expected one of: {choices}") from exc
