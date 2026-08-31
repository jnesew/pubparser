from __future__ import annotations

from dataclasses import dataclass

from .archive import EpubArchive, normalize_archive_path
from .errors import ContainerError, UnsafeArchiveError
from .xmlutil import local_name, parse_xml_safely

CONTAINER_PATH = "META-INF/container.xml"
EPUB_MEDIA_TYPE = "application/oebps-package+xml"


@dataclass(frozen=True, slots=True)
class Rootfile:
    full_path: str
    media_type: str | None


@dataclass(frozen=True, slots=True)
class Container:
    rootfiles: tuple[Rootfile, ...]

    @property
    def default_rootfile(self) -> Rootfile:
        if not self.rootfiles:
            raise ContainerError("container contains no rootfiles")
        for rootfile in self.rootfiles:
            if rootfile.media_type == EPUB_MEDIA_TYPE:
                return rootfile
        return self.rootfiles[0]


def parse_container(archive: EpubArchive) -> Container:
    if not archive.exists(CONTAINER_PATH):
        raise ContainerError(f"missing {CONTAINER_PATH}")
    try:
        data = archive.read_bytes(CONTAINER_PATH, max_size=archive.limits.max_xml_size)
        root = parse_xml_safely(data, resource=CONTAINER_PATH)
    except Exception as exc:
        raise ContainerError(str(exc)) from exc

    rootfiles: list[Rootfile] = []
    for elem in root.iter():
        if local_name(elem.tag) != "rootfile":
            continue
        raw_path = elem.get("full-path")
        if not raw_path:
            continue
        try:
            path = normalize_archive_path(raw_path)
        except UnsafeArchiveError as exc:
            raise ContainerError(f"unsafe rootfile path: {raw_path!r}") from exc
        rootfiles.append(Rootfile(path, elem.get("media-type")))

    if not rootfiles:
        raise ContainerError("container contains no usable rootfiles")
    return Container(tuple(rootfiles))
