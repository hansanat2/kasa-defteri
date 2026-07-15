#!/usr/bin/env python3
"""Kasa Defteri uygulamasını başlatmak için giriş noktası.

Kullanım:
    python main.py
    python main.py --db /baska/bir/yol/kasa.db
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from kasa_defteri.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
