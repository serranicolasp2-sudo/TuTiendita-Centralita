"""Servicio de retoque de fotos en la centralita.

Reemplaza una foto por un retoque manual y rearma final y vista previa reusando produccion/fotos.py.
"""
import io
import pathlib
import re
import shutil
import sys
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageOps

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "produccion"))
import carpetas  # noqa: E402
import fotos  # noqa: E402


def validar_imagen(contenido_bytes: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(contenido_bytes))
        im.verify()
        return Image.open(io.BytesIO(contenido_bytes))
    except Exception as e:
        raise HTTPException(400, f"El archivo no es una imagen válida: {e}")


def reemplazar_por_retoque(pid: str, foto_stem: str, contenido_bytes: bytes, p: dict[str, Any]) -> dict[str, Any]:
    """Reemplaza 2-codex/{foto_stem}.png por el retoque recibido y rearma final, previa y comparativa."""
    base = carpetas.buscar(pid)
    if not base:
        raise HTTPException(404, f"No existe la carpeta del pedido {pid}")

    carpeta_codex = base / "2-codex"
    destino = carpeta_codex / f"{foto_stem}.png"
    # Solo se reemplaza una versión de Codex que ya existe (el nombre llega del navegador: nada de "..\")
    if not re.fullmatch(r"[\w-]+", foto_stem) or not destino.is_file():
        raise HTTPException(400, f"No existe 2-codex\\{foto_stem}.png en el pedido")

    im = validar_imagen(contenido_bytes)
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")

    carpeta_anteriores = carpeta_codex / "anteriores"
    carpeta_anteriores.mkdir(parents=True, exist_ok=True)

    # Mover versión previa si existe, con la misma numeración que bot.restaurar_una:
    # n = len(anteriores) + 2; previa = anteriores / f"{stem}-v{n - 1}.png"
    n_ant = len(list(carpeta_anteriores.glob(f"{foto_stem}-v*.png")))
    n = n_ant + 2
    previa_nombre = f"{foto_stem}-v{n - 1}.png"
    previa_path = carpeta_anteriores / previa_nombre

    if destino.exists():
        shutil.move(str(destino), str(previa_path))

    # Guardar retoque en destino
    im.save(destino, format="PNG")

    # Rearmar final, vista previa y comparativa con fotos.procesar
    try:
        fotos.procesar(pid, estado="Pendientes", solo=[foto_stem])
    except Exception as e:
        raise HTTPException(500, f"Error al procesar la foto con Real-ESRGAN: {e}")

    # Anotar en el historial
    aviso_historial = (
        f"Reemplazaste {foto_stem}.png por tu retoque manual. "
        + (f"Versión anterior guardada en 2-codex\\anteriores\\{previa_nombre}. " if previa_path.exists() else "")
        + "Final, vista previa y comparativa rearmadas."
    )
    carpetas.anotar(base, aviso_historial)

    puede_mandar_previa = p.get("estado") in ("pagado", "cambio", "vista_previa")

    return {
        "ok": True,
        "archivo": f"2-codex/{destino.name}",
        "anterior": f"2-codex/anteriores/{previa_nombre}" if previa_path.exists() else None,
        "puede_mandar_previa": puede_mandar_previa,
        "aviso": "Retoque guardado. Se rearmaron la final, la vista previa y la comparativa."
    }
