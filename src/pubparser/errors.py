class EpubError(Exception):
    """Base class for pubparser failures."""


class ArchiveError(EpubError):
    """Archive-level failure."""


class InvalidArchiveError(ArchiveError):
    """Input is not a valid ZIP/EPUB archive."""


class UnsafeArchiveError(ArchiveError):
    """Archive violates a security limit or contains an unsafe path."""


class ContainerError(EpubError):
    """META-INF/container.xml is missing or unusable."""


class PackageError(EpubError):
    """Package document is missing or unusable."""


class NavigationError(EpubError):
    """Navigation data is unusable."""


class ResourceError(EpubError):
    """A manifest resource cannot be resolved or read."""


class ValidationError(EpubError):
    """Validation failed or strict parsing rejected the publication."""

    def __init__(self, message: str, *, issues=()):
        super().__init__(message)
        self.issues = tuple(issues)


class UnsupportedFeatureError(EpubError):
    """EPUB uses a deliberately unsupported feature."""
