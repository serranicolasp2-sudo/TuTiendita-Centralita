"""Servicio de estado del sistema e interacción con Windows para la centralita.

Controla bot, Codex, Claude, servidor, Mercado Libre, explorador de Windows y conteos.
"""
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any

from fastapi import HTTPException

# Agregar rutas necesarias
AQUI = pathlib.Path(__file__).resolve().parent
TIENDA_DIR = AQUI.parents[1] / "tienda" / "herramientas"
sys.path.insert(0, str(TIENDA_DIR))
sys.path.insert(0, str(AQUI.parents[1] / "produccion"))

import codexcli  # noqa: E402
import claudecli  # noqa: E402
import ml_api  # noqa: E402
from . import locales, servidor  # noqa: E402

log = logging.getLogger("centralita.sistema")


def procesos_bot() -> list[int]:
    """PIDs de los Python (python.exe / pythonw.exe) que corren bot.py. Solo esos: un editor o una terminal que
    mencionen bot.py no cuentan (Reiniciar los cerraría a la fuerza)."""
    cmd_ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
              "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd_ps],
                           capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        datos = json.loads(r.stdout or "[]")
    except Exception as e:
        log.warning("No se pudo consultar los procesos: %s", e)
        return []
    if isinstance(datos, dict):
        datos = [datos]
    con_ruta, suelto = [], []
    for d in datos:
        linea = (d.get("CommandLine") or "").replace("/", "\\").lower()
        if "tienda\\herramientas\\bot.py" in linea:
            con_ruta.append(int(d["ProcessId"]))
        elif re.search(r'(^|[\s"])bot\.py("|\s|$)', linea):
            suelto.append(int(d["ProcessId"]))   # arrancado a mano desde tienda\herramientas (pythonw.exe bot.py)
    # Reiniciar lo arranca con la ruta completa: desde ahí no se confunde con otro bot.py de otro proyecto
    return con_ruta or suelto


def estado_bot() -> dict[str, Any]:
    """Proceso del bot (Get-CimInstance) y la última línea de bot.log."""
    pids = procesos_bot()
    hora_log, ultima_linea = locales.ultima_linea_bot_log()
    return {
        "vivo": bool(pids),
        "pid": pids[0] if pids else None,
        "copias": len(pids),
        "ultima_hora": hora_log,
        "ultima_linea": ultima_linea
    }


def reiniciar_bot() -> dict[str, Any]:
    """Frena el bot (todas las copias) y lo vuelve a arrancar con pythonw.exe bot.py, desconectado del servicio."""
    for pid in procesos_bot():
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
        except Exception as e:
            log.warning("No se pudo detener el proceso %s: %s", pid, e)
    for _ in range(20):                      # hasta que Windows libere bot.lock (si no, la copia nueva se cierra sola)
        if not procesos_bot():
            break
        time.sleep(0.5)
    else:
        raise HTTPException(500, "El bot anterior no se cerró: no arranco otro")

    # Buscar pythonw.exe
    python_dir = pathlib.Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = pathlib.Path(r"C:\Users\Nicolás\AppData\Local\Programs\Python\Python311\pythonw.exe")
    if not pythonw.exists():
        pythonw = pathlib.Path(sys.executable)

    bot_script = TIENDA_DIR / "bot.py"
    if not bot_script.exists():
        raise HTTPException(500, f"No se encontró bot.py en {bot_script}")

    DETACHED_PROCESS = 0x00000008
    try:
        proc = subprocess.Popen([str(pythonw), str(bot_script)],
                                cwd=str(TIENDA_DIR),
                                creationflags=DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                close_fds=True)
        return {"ok": True, "pid": proc.pid, "mensaje": "Bot reiniciado"}
    except Exception as e:
        raise HTTPException(500, f"No se pudo arrancar bot.py: {e}")


def estado_codex() -> dict[str, Any]:
    """Verifica si Codex CLI está instalado y localizable."""
    try:
        exe = codexcli.codex_exe()
        return {"ok": bool(exe and pathlib.Path(exe).exists())}
    except Exception:
        return {"ok": False}


def estado_claude() -> dict[str, Any]:
    """Verifica la sesión de Claude Code ('claude auth status' -> solo loggedIn)."""
    exe = claudecli.claude_exe()
    if not exe:
        return {"loggedIn": False}
    try:
        r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            datos = json.loads(r.stdout)
            return {"loggedIn": bool(datos.get("loggedIn"))}
    except Exception:
        pass
    return {"loggedIn": False}


def estado_servidor() -> dict[str, Any]:
    """Consulta GET /salud del servidor."""
    return servidor.salud()


def estado_ml() -> dict[str, Any]:
    """Consulta usuario en Mercado Libre (solo nickname)."""
    try:
        u = ml_api.get("/users/me")
        return {"conectado": True, "nickname": u.get("nickname", "")}
    except Exception:
        return {"conectado": False, "nickname": ""}


def estado_completo() -> dict[str, Any]:
    """Agrupa el estado de todos los componentes del sistema."""
    return {
        "bot": estado_bot(),
        "codex": estado_codex(),
        "claude": estado_claude(),
        "servidor": estado_servidor(),
        "ml": estado_ml(),
        "carpetas": locales.conteo_carpetas()
    }


def mostrar_en_explorador(ruta_completa: str | pathlib.Path):
    """Abre el explorador de Windows con el archivo seleccionado."""
    p = pathlib.Path(ruta_completa).resolve()
    if not p.exists():
        raise HTTPException(404, f"No existe el archivo {ruta_completa}")
    subprocess.Popen(["explorer", f"/select,{str(p)}"])


def abrir_con_programa(ruta_completa: str | pathlib.Path):
    """Abre el archivo con su programa predeterminado en Windows."""
    p = pathlib.Path(ruta_completa).resolve()
    if not p.exists():
        raise HTTPException(404, f"No existe el archivo {ruta_completa}")
    os.startfile(str(p))
