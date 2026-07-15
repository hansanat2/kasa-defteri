"""Veri modelleri."""

from dataclasses import dataclass, field
from typing import Optional

GELIR = "gelir"
GIDER = "gider"
KAYNAK_MANUEL = "manuel"
KAYNAK_EFATURA = "efatura"

GECERLI_TURLER = (GELIR, GIDER)
GECERLI_KAYNAKLAR = (KAYNAK_MANUEL, KAYNAK_EFATURA)


@dataclass
class Islem:
    """Kasa defterindeki tek bir gelir veya gider satırı."""

    id: Optional[int] = None
    tarih: str = ""  # ISO format: YYYY-MM-DD
    tur: str = GIDER  # "gelir" | "gider"
    tutar: float = 0.0
    kategori: str = ""
    aciklama: str = ""
    karsi_taraf: str = ""
    belge_no: str = ""
    vkn_tckn: str = ""
    kaynak: str = KAYNAK_MANUEL
    efatura_uuid: Optional[str] = None
    olusturma_zamani: Optional[str] = None

    def __post_init__(self) -> None:
        if self.tur not in GECERLI_TURLER:
            raise ValueError(f"Geçersiz işlem türü: {self.tur!r}")
        if self.kaynak not in GECERLI_KAYNAKLAR:
            raise ValueError(f"Geçersiz kaynak: {self.kaynak!r}")
        if self.tutar < 0:
            raise ValueError("Tutar negatif olamaz")

    @classmethod
    def from_row(cls, row) -> "Islem":
        """sqlite3.Row -> Islem"""
        return cls(
            id=row["id"],
            tarih=row["tarih"],
            tur=row["tur"],
            tutar=row["tutar"],
            kategori=row["kategori"] or "",
            aciklama=row["aciklama"] or "",
            karsi_taraf=row["karsi_taraf"] or "",
            belge_no=row["belge_no"] or "",
            vkn_tckn=row["vkn_tckn"] or "",
            kaynak=row["kaynak"],
            efatura_uuid=row["efatura_uuid"],
            olusturma_zamani=row["olusturma_zamani"],
        )
