"""Servicios locales de la centralita: carpetas de C:\\Pedidos, bot-estado.json y logs.

Usa produccion/carpetas.py.
"""
import json
import pathlib
import sys
from typing import Any

# Agregar rutas necesarias
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "produccion"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tienda" / "herramientas"))
import carpetas  # noqa: E402


def ruta_pedidos() -> pathlib.Path:
    return carpetas.PEDIDOS


def ruta_bot_estado() -> pathlib.Path:
    return ruta_pedidos() / "bot-estado.json"


def ruta_bot_log() -> pathlib.Path:
    return ruta_pedidos() / "bot.log"


def buscar_carpeta(pid: str) -> pathlib.Path | None:
    return carpetas.buscar(pid)


def leer_bot_estado() -> dict[str, Any]:
    archivo = ruta_bot_estado()
    if not archivo.exists():
        return {}
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except Exception:
        return {}


def leer_historial_lineas(pid: str) -> list[str]:
    base = buscar_carpeta(pid)
    if not base:
        return []
    h = base / carpetas.HISTORIAL
    if not h.exists():
        return []
    try:
        lineas = h.read_text(encoding="utf-8").splitlines()
        return [l for l in lineas if l.strip()]
    except Exception:
        return []


def ultima_linea_historial(pid: str) -> str:
    lineas = leer_historial_lineas(pid)
    # Cada entrada de carpetas.anotar es "[fecha] primera línea" y sigue con líneas sangradas: va la primera línea
    for l in reversed(lineas):
        l_strip = l.strip()
        if l_strip.startswith("[") and "]" in l_strip:
            return l_strip.split("]", 1)[1].strip()
    return lineas[-1].strip() if lineas else ""


def leer_historial_completo(pid: str) -> str:
    base = buscar_carpeta(pid)
    if not base:
        return ""
    h = base / carpetas.HISTORIAL
    if not h.exists():
        return ""
    try:
        return h.read_text(encoding="utf-8")
    except Exception:
        return ""


def anotar_historial(pid: str, texto: str):
    base = buscar_carpeta(pid)
    if base:
        carpetas.anotar(base, texto)


def conteo_carpetas() -> dict[str, int]:
    base = ruta_pedidos()
    conteos = {
        "rf_pendientes": 0,
        "rf_listos": 0,
        "tc_pendientes": 0,
        "tc_listos": 0,
    }
    for t in ("RF", "TC"):
        for e in ("Pendientes", "Listos"):
            clave = f"{t.lower()}_{e.lower()}"
            directorio = base / t / e
            if directorio.exists():
                conteos[clave] = sum(1 for c in directorio.iterdir() if c.is_dir())
    return conteos


def ultima_linea_bot_log() -> tuple[str, str]:
    """Devuelve (hora_iso_o_formateada, linea_completa)."""
    log_path = ruta_bot_log()
    if not log_path.exists():
        return "", ""
    try:
        with open(log_path, "rb") as f:          # el log crece sin límite: alcanza con el final
            f.seek(max(0, f.seek(0, 2) - 16384))
            lineas = f.read().decode("utf-8", errors="replace").splitlines()
        for l in reversed(lineas):
            if l.strip():
                # Formato típico: "2026-10-13 23:37:37,506 Bot iniciado..."
                partes = l.strip().split(" ", 2)
                hora_str = f"{partes[0]} {partes[1].split(',')[0]}" if len(partes) >= 2 else ""
                return hora_str, l.strip()
    except Exception:
        pass
    return "", ""
