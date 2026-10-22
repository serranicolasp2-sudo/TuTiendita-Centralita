"""Manejo de audios en la centralita: validar, soltar previas y finales, y grabar lo que suena.

Reusa produccion/cancion.py.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "produccion"))
import cancion  # noqa: E402
import carpetas  # noqa: E402


def validar_es_audio(ruta_archivo: pathlib.Path) -> bool:
    """Valida con ffprobe que el archivo contenga un stream de audio."""
    try:
        r = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(ruta_archivo)
        ], capture_output=True, text=True, check=True)
        return r.stdout.strip().lower() == "audio"
    except Exception:
        return False


def guardar_vista_previa(pid: str, ruta_audio_origen: pathlib.Path, p: dict[str, Any]) -> dict[str, Any]:
    """Corta y guarda un audio como v{K}-previa.mp3 en 3-vistas-previas."""
    base = carpetas.buscar(pid)
    if not base:
        raise HTTPException(404, f"No existe la carpeta del pedido {pid}")

    if not validar_es_audio(ruta_audio_origen):
        raise HTTPException(400, "El archivo no es un audio válido (falló ffprobe).")

    carpeta_previas = base / "3-vistas-previas"
    carpeta_previas.mkdir(parents=True, exist_ok=True)

    # Determinar K = mayor que ya exista + 1
    existentes = sorted(carpeta_previas.glob("v*-previa.mp3"))
    max_k = 0
    for f in existentes:
        if m := re.search(r"v(\d+)-previa", f.name):
            max_k = max(max_k, int(m.group(1)))
    k = max_k + 1

    salida = carpeta_previas / f"v{k}-previa.mp3"
    segundos = getattr(cancion, "SEGUNDOS", 60)
    fin = segundos - 4

    # Cortar a 60 s con fundidos de entrada (0.3 s) y salida (4 s), 128k
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(ruta_audio_origen),
        "-t", str(segundos),
        "-af", f"afade=t=in:d=0.3,afade=t=out:st={fin}:d=4",
        "-ac", "2", "-b:a", "128k",
        "-metadata", "title=Vista previa · Tu Canción",
        "-metadata", "artist=tucancion.com.ar",
        str(salida)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Error al procesar el audio con ffmpeg: {e.stderr.decode(errors='replace')}")

    aviso_bot = " El bot la subirá en su próxima vuelta." if p.get("estado") in ("pagado", "cambio") \
        else " (Ojo: el bot no la va a subir porque el pedido no está en pagado ni cambio)."
    carpetas.anotar(base, f"Vista previa v{k} guardada ({segundos} s): 3-vistas-previas\\{salida.name}.{aviso_bot}")

    return {
        "ok": True,
        "k": k,
        "archivo": f"3-vistas-previas/{salida.name}",
        "aviso": f"Vista previa v{k} guardada.{aviso_bot}"
    }


def guardar_final(pid: str, ruta_audio_origen: pathlib.Path, para: str, p: dict[str, Any]) -> dict[str, Any]:
    """Copia la descarga oficial de Suno con metadatos a 4-entrega."""
    base = carpetas.buscar(pid)
    if not base:
        raise HTTPException(404, f"No existe la carpeta del pedido {pid}")

    if p.get("estado") != "aprobado":
        raise HTTPException(409, f"El pedido no está aprobado (estado: {p.get('estado')})")

    if not validar_es_audio(ruta_audio_origen):
        raise HTTPException(400, "El archivo no es un audio válido.")

    carpeta_entrega = base / "4-entrega"
    carpeta_entrega.mkdir(parents=True, exist_ok=True)

    # "Para quién" va al nombre del archivo: sin caracteres que Windows no acepta ni separadores de carpeta
    para_limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", para or "").strip(" .")[:60]
    nombre = f"Tu canción para {para_limpio}.mp3" if para_limpio else f"Tu canción {pid}.mp3"
    salida = carpeta_entrega / nombre

    # El bot entrega el primer MP3 de 4-entrega: si ya había uno, pasa a 4-entrega/anteriores (no se borra)
    movidos = []
    for viejo in sorted(carpeta_entrega.glob("*.mp3")):
        anteriores = carpeta_entrega / "anteriores"
        anteriores.mkdir(exist_ok=True)
        n = len(list(anteriores.glob(f"{viejo.stem}-v*.mp3"))) + 1
        shutil.move(str(viejo), str(anteriores / f"{viejo.stem}-v{n}.mp3"))
        movidos.append(f"4-entrega\\anteriores\\{viejo.stem}-v{n}.mp3")

    codec = ["-c:a", "copy"] if ruta_audio_origen.suffix.lower() == ".mp3" else ["-c:a", "libmp3lame", "-b:a", "320k"]
    titulo = f"Para {para_limpio}" if para_limpio else "Tu canción"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(ruta_audio_origen),
        "-map", "0:a", *codec,
        "-metadata", f"title={titulo}",
        "-metadata", "artist=Tu Canción",
        "-metadata", "comment=tucancion.com.ar",
        str(salida)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Error al procesar el audio final con ffmpeg: {e.stderr.decode(errors='replace')}")

    carpetas.anotar(base, f"Versión final guardada con descarga oficial de Suno: 4-entrega\\{nombre}. El bot la entregará automáticamente."
                    + (f"\nLa anterior quedó en {', '.join(movidos)}" if movidos else ""))

    return {
        "ok": True,
        "archivo": f"4-entrega/{nombre}",
        "aviso": f"Versión final guardada como {nombre}. El bot la entregará en su próxima pasada."
    }


GRABACIONES: dict[str, subprocess.Popen] = {}


def _registro_grabacion(pid: str) -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / f"centralita-grabacion-{pid}.txt"


def grabar_lo_que_suena(pid: str) -> dict[str, Any]:
    """Corre `cancion.py previa <pid>` en segundo plano (graba lo que suena por los altavoces). La salida va a un
    archivo temporal para mostrar el estado: con pythonw no hay consola donde verla."""
    actual = GRABACIONES.get(pid)
    if actual and actual.poll() is None:
        raise HTTPException(409, "Ya hay una grabación en curso para este pedido")
    python_exe = pathlib.Path(sys.executable)
    if python_exe.name.lower() == "pythonw.exe":
        python_exe = python_exe.with_name("python.exe")
    script = pathlib.Path(__file__).resolve().parents[2] / "produccion" / "cancion.py"
    with open(_registro_grabacion(pid), "w", encoding="utf-8") as salida:
        GRABACIONES[pid] = subprocess.Popen(
            [str(python_exe), "-u", str(script), "previa", pid], cwd=str(script.parent),
            stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"ok": True, "estado": "esperando", "mensaje": "Dale play en Suno desde el principio…"}


def estado_grabacion(pid: str) -> dict[str, Any]:
    """esperando (a que suene) → grabando → listo / error, con la última línea que escribió cancion.py."""
    proc = GRABACIONES.get(pid)
    if not proc:
        return {"estado": "nada"}
    try:
        texto = _registro_grabacion(pid).read_text(encoding="utf-8", errors="replace")
    except OSError:
        texto = ""
    lineas = [l for l in texto.splitlines() if l.strip()]
    codigo = proc.poll()
    if codigo is None:
        estado = "grabando" if any(l.startswith("Grabando") for l in lineas) else "esperando"
    else:
        estado = "listo" if codigo == 0 else "error"
        GRABACIONES.pop(pid, None)
        _registro_grabacion(pid).unlink(missing_ok=True)
    return {"estado": estado, "mensaje": lineas[-1] if lineas else ""}
