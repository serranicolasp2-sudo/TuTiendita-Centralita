"""Arranca la centralita sin consola (lo usa centralita.bat con pythonw.exe).

Con pythonw no hay consola: sys.stdout y sys.stderr valen None y uvicorn se cae al arrancar (su formato de registro
pregunta sys.stdout.isatty()). Acá se los reemplaza por un archivo de registro, que además sirve para ver errores:
%TEMP%\\centralita.log (solo avisos y errores; sin llaves ni datos de clientes).
"""
import os
import pathlib
import sys
import tempfile

AQUI = pathlib.Path(__file__).resolve().parent
REGISTRO = pathlib.Path(tempfile.gettempdir()) / "centralita.log"

if REGISTRO.exists() and REGISTRO.stat().st_size > 1_000_000:     # que no crezca sin límite
    REGISTRO.replace(REGISTRO.with_suffix(".log.1"))
salida = open(REGISTRO, "a", encoding="utf-8", buffering=1)
if sys.stdout is None:
    sys.stdout = salida
if sys.stderr is None:
    sys.stderr = salida

os.chdir(AQUI)
sys.path.insert(0, str(AQUI))

import uvicorn  # noqa: E402

uvicorn.run("servicio:app", host="127.0.0.1", port=8790, log_level="warning", use_colors=False)
