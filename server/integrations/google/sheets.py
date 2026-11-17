"""Sheet copy of the finance store: each tab is replaced whole, values written as text."""

from typing import Protocol

from googleapiclient.discovery import build


class SheetsClient(Protocol):
    def replace_tab(
        self, sheet_id: str, tab: str, header: list[str], rows: list[list[str]]
    ) -> None: ...


class ApiSheets:
    """Sheets API v4. An MCP implementation can replace this behind SheetsClient."""

    def __init__(self, creds=None, http=None) -> None:
        kwargs = {"http": http} if http is not None else {"credentials": creds}
        self.service = build("sheets", "v4", cache_discovery=False, **kwargs)

    def replace_tab(
        self, sheet_id: str, tab: str, header: list[str], rows: list[list[str]]
    ) -> None:
        sheets = self.service.spreadsheets()
        meta = sheets.get(spreadsheetId=sheet_id, fields="sheets.properties.title").execute()
        titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
        if tab not in titles:
            body = {"requests": [{"addSheet": {"properties": {"title": tab}}}]}
            sheets.batchUpdate(spreadsheetId=sheet_id, body=body).execute()
        sheets.values().clear(spreadsheetId=sheet_id, range=f"'{tab}'").execute()
        # RAW keeps "-12.30" as typed; USER_ENTERED would turn amounts into floats
        sheets.values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            body={"values": [header, *rows]},
        ).execute()
