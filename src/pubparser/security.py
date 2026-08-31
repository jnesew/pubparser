from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecurityLimits:
    max_entries: int = 10_000
    max_total_uncompressed_size: int = 512 * 1024 * 1024
    max_resource_size: int = 128 * 1024 * 1024
    max_xml_size: int = 8 * 1024 * 1024
    max_expansion_ratio: float = 200.0

    def __post_init__(self) -> None:
        if self.max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if self.max_total_uncompressed_size <= 0:
            raise ValueError("max_total_uncompressed_size must be positive")
        if self.max_resource_size <= 0:
            raise ValueError("max_resource_size must be positive")
        if self.max_xml_size <= 0:
            raise ValueError("max_xml_size must be positive")
        if self.max_expansion_ratio <= 0:
            raise ValueError("max_expansion_ratio must be positive")


DEFAULT_LIMITS = SecurityLimits()
