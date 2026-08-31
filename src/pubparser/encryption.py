from __future__ import annotations

from urllib.parse import unquote, urlsplit

from .archive import EpubArchive, normalize_archive_path
from .diagnostics import Diagnostic, Severity
from .errors import EpubError, UnsafeArchiveError
from .models import EncryptedResource, EncryptionInfo
from .xmlutil import local_name, parse_xml_safely

ENCRYPTION_PATH = "META-INF/encryption.xml"
IDPF_FONT_OBFUSCATION = "http://www.idpf.org/2008/embedding"
ADOBE_FONT_OBFUSCATION = "http://ns.adobe.com/pdf/enc#RC"


def _classify_algorithm(algorithm: str | None) -> str:
    if algorithm == IDPF_FONT_OBFUSCATION:
        return "font-obfuscation-idpf"
    if algorithm == ADOBE_FONT_OBFUSCATION:
        return "font-obfuscation-adobe"
    return "unsupported-encryption"


def _container_path(uri: str) -> str | None:
    parts = urlsplit(uri)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    decoded = unquote(parts.path)
    if decoded.startswith("/"):
        return None
    try:
        return normalize_archive_path(decoded)
    except UnsafeArchiveError:
        return None


def parse_encryption(archive: EpubArchive) -> tuple[EncryptionInfo, tuple[Diagnostic, ...]]:
    if not archive.exists(ENCRYPTION_PATH):
        return EncryptionInfo(), ()
    diagnostics: list[Diagnostic] = []
    try:
        root = parse_xml_safely(
            archive.read_bytes(ENCRYPTION_PATH, max_size=archive.limits.max_xml_size),
            resource=ENCRYPTION_PATH,
            max_depth=archive.limits.max_xml_depth,
        )
    except EpubError as exc:
        diagnostics.append(Diagnostic(Severity.ERROR, "EPUB_MALFORMED_ENCRYPTION_XML", str(exc), ENCRYPTION_PATH))
        return EncryptionInfo(), tuple(diagnostics)

    if local_name(root.tag) != "encryption":
        diagnostics.append(Diagnostic(Severity.ERROR, "EPUB_ENCRYPTION_ROOT_INVALID", "encryption.xml root is not <encryption>", ENCRYPTION_PATH))
        return EncryptionInfo(), tuple(diagnostics)

    resources: list[EncryptedResource] = []
    for encrypted in (elem for elem in root.iter() if local_name(elem.tag) == "EncryptedData"):
        method = next((elem for elem in encrypted.iter() if local_name(elem.tag) == "EncryptionMethod"), None)
        cipher = next((elem for elem in encrypted.iter() if local_name(elem.tag) == "CipherReference"), None)
        algorithm = method.get("Algorithm") if method is not None else None
        uri = cipher.get("URI") if cipher is not None else None
        if not uri:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_ENCRYPTED_RESOURCE_URI_MISSING", "EncryptedData has no CipherReference URI", ENCRYPTION_PATH))
            continue
        resolved = _container_path(uri)
        if resolved is None:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_ENCRYPTED_RESOURCE_URI_INVALID", f"Encrypted resource URI is not a safe container path: {uri}", ENCRYPTION_PATH))
        kind = _classify_algorithm(algorithm)
        if kind == "unsupported-encryption":
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_UNSUPPORTED_ENCRYPTION", f"Unsupported encryption algorithm: {algorithm or 'unspecified'}", resolved or uri))
        resources.append(EncryptedResource(uri=uri, resolved_path=resolved, algorithm=algorithm, kind=kind))

    return EncryptionInfo(tuple(resources)), tuple(diagnostics)
