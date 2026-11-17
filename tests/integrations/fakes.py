from pathlib import Path

from server.integrations.google.drive import DriveFile


class FakeDrive:
    def __init__(self, files: dict[str, tuple[str, bytes]]) -> None:
        self.files = files  # id -> (name, content)
        self.downloads: list[str] = []

    def list_pdfs(self, folder_id: str) -> list[DriveFile]:
        return [DriveFile(i, name, "") for i, (name, _) in self.files.items()]

    def download(self, file_id: str, dest: Path) -> Path:
        self.downloads.append(file_id)
        dest.write_bytes(self.files[file_id][1])
        return dest


class FakeSheets:
    def __init__(self, fail: Exception | None = None) -> None:
        self.tabs: dict[str, list[list[str]]] = {}
        self.fail = fail

    def replace_tab(self, sheet_id, tab, header, rows) -> None:
        if self.fail:
            raise self.fail
        self.tabs[tab] = [header, *rows]
