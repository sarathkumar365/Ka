"""Drive statement inbox: list PDFs in one folder and download them. Read-only."""

import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


@dataclass
class DriveFile:
    id: str
    name: str
    modified: str


class DriveClient(Protocol):
    def list_pdfs(self, folder_id: str) -> list[DriveFile]: ...
    def download(self, file_id: str, dest: Path) -> Path: ...


class ApiDrive:
    """Drive API v3. An MCP implementation can replace this behind DriveClient."""

    def __init__(self, creds=None, http=None) -> None:
        kwargs = {"http": http} if http is not None else {"credentials": creds}
        self.service = build("drive", "v3", cache_discovery=False, **kwargs)

    def list_pdfs(self, folder_id: str) -> list[DriveFile]:
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
        files: list[DriveFile] = []
        token = None
        while True:
            resp = (
                self.service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, modifiedTime)",
                    pageSize=100,
                    pageToken=token,
                )
                .execute()
            )
            files += [
                DriveFile(f["id"], f["name"], f.get("modifiedTime", "")) for f in resp["files"]
            ]
            token = resp.get("nextPageToken")
            if not token:
                return files

    def download(self, file_id: str, dest: Path) -> Path:
        request = self.service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(buf.getvalue())
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return dest
