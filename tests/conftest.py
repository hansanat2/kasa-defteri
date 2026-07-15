import sys
from pathlib import Path

import pytest

# 'src' düzenini test edilebilir kılmak için içe aktarma yolunu ekle.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kasa_defteri import database  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    db_yolu = tmp_path / "test_kasa.db"
    c = database.get_connection(db_yolu)
    database.init_db(c)
    yield c
    c.close()
