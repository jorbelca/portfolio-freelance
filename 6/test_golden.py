"""Falla si `reglas.py` cambió cualquier salida respecto al baseline congelado
(30k+ casos, barrido cartesiano). Red de seguridad del refactor del motor.

    python3 test_golden.py

Si el generador de casos cambia a propósito: `python3 eval/golden_motor.py --write`
y revisa el diff a mano antes de dar por bueno el nuevo baseline.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "eval"))

from golden_motor import comprobar  # noqa: E402

if __name__ == "__main__":
    comprobar()
    print("test_golden.py: TODO OK")
