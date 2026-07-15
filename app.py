#!/usr/bin/env python3
"""Kasa Defteri WEB arayüzünü başlatır (tarayıcıda localhost:5000).

Kullanım:
    python app.py

Masaüstü (Tkinter) sürümü için bunun yerine main.py kullanın.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from kasa_defteri.webapp import main  # noqa: E402

if __name__ == "__main__":
    main()
