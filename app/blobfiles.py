"""Private Azure Blob container for the FURP space (owner, 2026-11-11).

Storage account furpstore (resource group np-explorer-us, the one created for FURP), container `space`, NO public
access: every byte is served through the app (app/space.py) so the access rules run on each request, and public items
only through their public route. Reads and writes use the VM's system-assigned managed identity (Storage Blob Data
Contributor on the account, both FURP servers). BLOB_USE_DEFAULT_CREDENTIAL=1 switches to DefaultAzureCredential (a
laptop after `az login`). SPACE_BLOB_DIR=<directory> keeps the files on local disk instead: the tests, or a machine
with no Azure access. Nothing here logs file names or contents.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from typing import IO, Iterator

ACCOUNT_URL = os.environ.get("SPACE_BLOB_ACCOUNT_URL", "https://furpstore.blob.core.windows.net")
CONTAINER = os.environ.get("SPACE_BLOB_CONTAINER", "space")
CHUNK = 1024 * 1024
_cc = None

for _n in ("azure", "azure.core.pipeline.policies.http_logging_policy", "urllib3", "msal"):
    logging.getLogger(_n).setLevel(logging.WARNING)      # the SDK logs every request header at INFO


def local_dir() -> pathlib.Path | None:
    d = os.environ.get("SPACE_BLOB_DIR")
    return pathlib.Path(d) if d else None


def _container():
    global _cc
    if _cc is None:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
        from azure.storage.blob import ContainerClient
        cred = DefaultAzureCredential() if os.environ.get("BLOB_USE_DEFAULT_CREDENTIAL") else ManagedIdentityCredential()
        _cc = ContainerClient(ACCOUNT_URL, CONTAINER, credential=cred, max_single_put_size=64 * 1024 * 1024)
    return _cc


def _safe(path: str) -> str:
    if not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("bad blob path")
    return path


def put(path: str, data: IO[bytes], content_type: str, size: int | None = None) -> None:
    """Store a file object at `path` (overwrite is fine: paths carry the row id)."""
    _safe(path)
    d = local_dir()
    if d:
        target = d / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as out:
            shutil.copyfileobj(data, out)
        return
    from azure.storage.blob import ContentSettings
    _container().upload_blob(path, data, overwrite=True, length=size,
                             content_settings=ContentSettings(content_type=content_type))


def stream(path: str) -> Iterator[bytes]:
    """The file's bytes in chunks."""
    _safe(path)
    d = local_dir()
    if d:
        with open(d / path, "rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk
        return
    yield from _container().download_blob(path, max_concurrency=2).chunks()


def exists(path: str) -> bool:
    _safe(path)
    d = local_dir()
    if d:
        return (d / path).is_file()
    return _container().get_blob_client(path).exists()
