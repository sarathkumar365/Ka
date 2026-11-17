from server.config import Config
from server.integrations.data_repo.schemas.common import KaModel

from .store import FinanceStore


class StatementFile(KaModel):
    name: str
    imported: bool


def list_statement_files(config: Config, store: FinanceStore) -> list[StatementFile]:
    imported = {s.file_name for s in store.statements()}
    folder = config.statements_dir
    if not folder.is_dir():
        return []
    return [
        StatementFile(name=p.name, imported=p.name in imported)
        for p in sorted(folder.glob("*.pdf"))
    ]
