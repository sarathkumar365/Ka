import json

from googleapiclient.http import HttpMockSequence

from server.integrations.google.drive import ApiDrive
from server.integrations.google.sheets import ApiSheets


def ok(body):
    return ({"status": "200"}, json.dumps(body))


def test_list_pdfs_pages_and_filters():
    http = HttpMockSequence(
        [
            ok(
                {"files": [{"id": "a", "name": "a.pdf", "modifiedTime": "t"}], "nextPageToken": "p"}
            ),
            ok({"files": [{"id": "b", "name": "b.pdf", "modifiedTime": "t"}]}),
        ]
    )
    files = ApiDrive(http=http).list_pdfs("FOLDER")
    assert [f.id for f in files] == ["a", "b"]


def test_download_is_atomic(tmp_path):
    http = HttpMockSequence([({"status": "200"}, b"%PDF-1.4 body")])
    dest = tmp_path / "s.pdf"
    ApiDrive(http=http).download("a", dest)
    assert dest.read_bytes() == b"%PDF-1.4 body"
    assert [p.name for p in tmp_path.iterdir()] == ["s.pdf"]


def test_replace_tab_adds_missing_tab_then_writes_raw():
    http = HttpMockSequence(
        [
            ok({"sheets": [{"properties": {"title": "Other"}}]}),
            ok({}),  # batchUpdate addSheet
            ok({}),  # values.clear
            ok({}),  # values.update
        ]
    )
    ApiSheets(http=http).replace_tab("S", "Transactions", ["id", "amount"], [["r1", "-12.30"]])
    seq = http.request_sequence  # (uri, method, body, headers)
    add = json.loads(seq[1][2])
    assert add["requests"][0]["addSheet"]["properties"]["title"] == "Transactions"
    assert "valueInputOption=RAW" in seq[3][0]
    assert json.loads(seq[3][2])["values"][1] == ["r1", "-12.30"]
