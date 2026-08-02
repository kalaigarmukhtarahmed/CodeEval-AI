"""Safe archive validation and extraction. Uploaded source is never executed here."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import uuid
import zipfile

from fastapi import HTTPException, UploadFile, status

from ..config import (
    MAX_ARCHIVE_FILES,
    MAX_COMPRESSION_RATIO,
    MAX_UNCOMPRESSED_BYTES,
    MAX_UPLOAD_BYTES,
    UPLOAD_DIR,
    WORKSPACE_DIR,
)


@dataclass
class SafeArchive:
    archive_path: Path
    workspace_path: Path
    archive_size_bytes: int
    file_count: int
    uncompressed_size_bytes: int


def reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _is_unsafe_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    windows_path = PureWindowsPath(info.filename)
    mode = info.external_attr >> 16
    return (
        path.is_absolute()
        or windows_path.is_absolute()
        or ".." in path.parts
        or stat.S_ISLNK(mode)
        or "\\" in info.filename
    )


def _validate_archive(path: Path) -> tuple[int, int]:
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                reject(f"ZIP integrity validation failed near '{bad_member}'.")
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                reject(f"ZIP contains more than {MAX_ARCHIVE_FILES} entries.")
            total_uncompressed = 0
            for info in members:
                if _is_unsafe_member(info):
                    reject("ZIP contains an unsafe path or symlink.")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    reject(f"ZIP expands beyond the {MAX_UNCOMPRESSED_BYTES} byte limit.")
                if info.file_size and (info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
                    reject("ZIP contains a suspicious compression ratio.")
            return len(members), total_uncompressed
    except zipfile.BadZipFile:
        reject("Uploaded file is not a valid ZIP archive.")


async def save_and_extract_upload(upload: UploadFile) -> SafeArchive:
    filename = upload.filename or "project.zip"
    if not filename.lower().endswith(".zip"):
        reject("Only .zip project uploads are accepted.")

    upload_id = str(uuid.uuid4())
    archive_path = UPLOAD_DIR / f"{upload_id}.zip"
    workspace_path = WORKSPACE_DIR / upload_id
    bytes_written = 0
    try:
        with archive_path.open("wb") as destination:
            while chunk := await upload.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    reject(f"Upload exceeds the {MAX_UPLOAD_BYTES} byte limit.")
                destination.write(chunk)

        file_count, uncompressed_size = _validate_archive(archive_path)
        workspace_path.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(archive_path) as archive:
            # Members were validated before extraction; no project code is executed.
            archive.extractall(workspace_path)
        return SafeArchive(archive_path, workspace_path, bytes_written, file_count, uncompressed_size)
    except HTTPException:
        if archive_path.exists():
            archive_path.unlink()
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        raise
    except (OSError, zipfile.BadZipFile) as error:
        if archive_path.exists():
            archive_path.unlink()
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        raise HTTPException(status_code=500, detail="Upload could not be stored safely.") from error
    finally:
        await upload.close()
