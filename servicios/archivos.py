"""Manejo seguro de archivos de pedidos en la PC para la centralita.

Listar, clasificar, leer y guardar cumpliendo las reglas de PLAN.md y PROMPT-ANTIGRAVITY-11.md.
"""
import json
import os
import pathlib
import re
import sys
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "produccion"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tienda" / "herramientas"))
import carpetas  # noqa: E402
import letras  # noqa: E402
from . import locales  # noqa: E402

EXT_IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg"}
EXT_VIDEO = {".mp4", ".mov", ".mkv"}
EXT_TXT = {".txt", ".json", ".md", ".log", ".csv"}


def resolver_ruta_segura(pid: str, ruta_relativa: str) -> pathlib.Path:
    """Resuelve la ruta dentro de la carpeta del pedido. Levanta 400 si se sale."""
    base = carpetas.buscar(pid)
    if not base:
        raise HTTPException(404, f"No se encontró la carpeta del pedido {pid}")
    base_res = base.resolve()

    # Limpiar ruta
    limpia = ruta_relativa.replace("\\", "/").strip()
    if limpia.startswith("/") or limpia.startswith("\\"):
        limpia = limpia.lstrip("/\\")

    # Rechazar explícitamente caracteres de drive letters de Windows en la ruta relativa
    if re.match(r"^[a-zA-Z]:", limpia):
        raise HTTPException(400, "Ruta no permitida (ruta absoluta)")

    destino = (base_res / limpia).resolve()
    try:
        destino.relative_to(base_res)
    except ValueError:
        raise HTTPException(400, "Ruta no permitida (fuera de la carpeta del pedido)")
    return destino


def parsear_suno_txt(texto: str) -> dict[str, str]:
    """Campos de suno.txt (formato de letras.guardar_version). Solo devuelve las secciones que están en el texto:
    una sección presente y vacía vale "" (se vació a propósito); una que no está no se toca."""
    texto = texto.replace("\r\n", "\n")
    campos = {}
    if m := re.search(r"^TÍTULO:[ \t]*(.*?)$", texto, re.M | re.I):
        campos["titulo"] = m.group(1).strip()
    if m := re.search(r"^QUÉ CAMBIA EN LA v\d+:[ \t]*(.*?)$", texto, re.M | re.I):
        campos["novedad"] = m.group(1).strip()
    if m := re.search(r"STYLE OF MUSIC:[ \t]*\n(.*?)(?=\n(?:EXCLUDE STYLES|LYRICS:)|\Z)", texto, re.S | re.I):
        campos["estilo"] = m.group(1).strip()
    if m := re.search(r"EXCLUDE STYLES[^\n]*:[ \t]*\n(.*?)(?=\nLYRICS:|\Z)", texto, re.S | re.I):
        campos["excluir"] = m.group(1).strip()
    elif "estilo" in campos:
        campos["excluir"] = ""          # guardar_version no escribe la sección cuando está vacía
    if m := re.search(r"LYRICS:[ \t]*\n(.*?)(?=\nFONÉTICA:|\Z)", texto, re.S | re.I):
        campos["letra"] = m.group(1).strip()
    if m := re.search(r"FONÉTICA:[ \t]*(.*)\Z", texto, re.S | re.I):
        fon = m.group(1).strip()
        campos["foneticas"] = "" if fon == "-" else fon
    return campos


def clasificar(pid: str, ruta_rel: str, p: dict[str, Any], est: dict[str, Any], col: str) -> dict[str, Any]:
    """Clasifica un archivo según las reglas de la centralita."""
    ruta_norm = ruta_rel.replace("\\", "/")
    nombre = pathlib.Path(ruta_norm).name
    ext = pathlib.Path(ruta_norm).suffix.lower()

    entregado_o_cancelado = p.get("estado") in ("entregado", "cancelado")
    letra_n_actual = est.get("letra_n", 1)

    info: dict[str, Any] = {
        "ruta": ruta_norm,
        "nombre": nombre,
        "tipo": "desconocido",
        "accion": "",
        "editable": False,
        "info": "",
        "original_comparar": None,
    }

    # 1. historial.txt
    if nombre.lower() == "historial.txt":
        info["tipo"] = "texto"
        info["accion"] = "historial"
        info["editable"] = False
        info["info"] = "El historial no se edita: podés sumar una nota tuya abajo."
        return info

    # 2. pedido.txt o 1-datos/pedido.txt
    if nombre.lower() == "pedido.txt":
        info["tipo"] = "texto"
        info["accion"] = "pedido"
        info["editable"] = False
        info["info"] = "Es la copia de lo que pidió el cliente. Para corregir datos usá Acciones."
        return info

    # 3. 2-letra/suno.txt y 2-letra/letra-v{N}.txt (actual)
    if ruta_norm == "2-letra/suno.txt" or ruta_norm == f"2-letra/letra-v{letra_n_actual}.txt":
        info["tipo"] = "texto"
        info["accion"] = "letra-actual"
        info["editable"] = not entregado_o_cancelado
        info["info"] = ("Es la letra actual. Si la cambiás, el bot la toma como base para el próximo cambio y "
                        "actualiza los archivos correspondientes.")
        return info

    # 4. 2-letra/letra-v{k}.txt (vieja)
    if m := re.match(r"^2-letra/letra-v(\d+)\.txt$", ruta_norm):
        k = int(m.group(1))
        if k < letra_n_actual:
            info["tipo"] = "texto"
            info["accion"] = "letra-vieja"
            info["editable"] = not entregado_o_cancelado
            info["info"] = "Es una versión anterior: podés editarla, pero el bot no la usa."
            return info

    # 5. 2-letra/version-v*.json, 0-analisis/*
    if (ruta_norm.startswith("2-letra/version-v") and ext == ".json") or (ruta_norm.startswith("0-analisis/") and ext == ".json"):
        info["tipo"] = "json"
        info["accion"] = "json-lectura"
        info["editable"] = False
        info["info"] = "Análisis o metadatos generados: solo lectura."
        return info

    # 6. 1-original/*
    if ruta_norm.startswith("1-original/") and ext in EXT_IMG:
        info["tipo"] = "imagen"
        info["accion"] = "original"
        info["editable"] = False
        info["info"] = "Es la foto que mandó el cliente: no se modifica."
        return info

    # 7. 2-codex/foto-XX.png (no en anteriores)
    if ruta_norm.startswith("2-codex/") and not ruta_norm.startswith("2-codex/anteriores/") and ext in EXT_IMG:
        info["tipo"] = "imagen"
        info["accion"] = "foto-version"
        info["editable"] = False
        info["retocable"] = not entregado_o_cancelado and col != "bot"   # las mismas reglas que /retoque
        info["info"] = ("Es la versión de Codex. Si la retocás vos, el bot arma la final y la vista previa nuevas, "
                        "y te pregunta si se la manda al cliente.")
        # Buscar foto original correspondiente para comparar
        base = carpetas.buscar(pid)
        if base:
            stem = pathlib.Path(ruta_norm).stem
            for f_orig in (base / "1-original").glob(f"{stem}.*"):
                if f_orig.suffix.lower() in EXT_IMG:
                    info["original_comparar"] = f"1-original/{f_orig.name}"
                    break
        return info

    # 8. anteriores/*, 3-entrega/*.jpg
    if ruta_norm.startswith("2-codex/anteriores/") or ruta_norm.startswith("3-entrega/"):
        if ext in EXT_IMG:
            if "comparativa" in nombre.lower():
                info["tipo"] = "comparar"
                info["accion"] = "comparativa"
                info["info"] = "Revisá las caras: antes y después lado a lado."
            else:
                info["tipo"] = "imagen"
                info["accion"] = "foto-final" if "final" in nombre.lower() else "foto-vista"
                info["info"] = "Imagen generada: solo lectura."
            info["editable"] = False
            return info

    # 9. Audios y videos
    if ext in EXT_AUDIO or ext in EXT_VIDEO:
        info["tipo"] = "audio" if ext in EXT_AUDIO else "video"
        info["accion"] = "reproductor"
        info["editable"] = False
        info["info"] = "Reproductor multimedia."
        return info

    # 10. Otro texto
    if ext in EXT_TXT:
        info["tipo"] = "texto"
        info["accion"] = "texto-lectura"
        info["editable"] = False
        info["info"] = "Documento de texto: solo lectura."
        return info

    info["tipo"] = "desconocido"
    info["accion"] = "externo"
    info["editable"] = False
    info["info"] = "Abrir con su programa."
    return info


def listar_archivos(pid: str, p: dict[str, Any], est: dict[str, Any], col: str) -> list[dict[str, Any]]:
    """Lista todos los archivos del pedido ordenados y clasificados."""
    base = carpetas.buscar(pid)
    if not base or not base.exists():
        return []

    resultados = []
    base_res = base.resolve()

    for elemento in sorted(base.rglob("*")):
        if elemento.is_file():
            # Omitir archivos temporales
            if elemento.name.startswith(".") or elemento.name.endswith(".tmp"):
                continue
            try:
                rel = elemento.relative_to(base_res).as_posix()
            except ValueError:
                continue

            cl = clasificar(pid, rel, p, est, col)
            cl["tamano"] = elemento.stat().st_size
            cl["mtime"] = elemento.stat().st_mtime
            resultados.append(cl)

    return resultados


def leer_archivo(pid: str, ruta_rel: str) -> tuple[str, Any]:
    """Devuelve (tipo_retorno, contenido) donde tipo_retorno es 'texto', 'json' o 'archivo'."""
    destino = resolver_ruta_segura(pid, ruta_rel)
    if not destino.exists() or not destino.is_file():
        raise HTTPException(404, f"No existe el archivo {ruta_rel}")

    ext = destino.suffix.lower()
    if ext in EXT_IMG or ext in EXT_AUDIO or ext in EXT_VIDEO:
        media_type = "image/jpeg"
        if ext == ".png":
            media_type = "image/png"
        elif ext == ".webp":
            media_type = "image/webp"
        elif ext == ".mp3":
            media_type = "audio/mpeg"
        elif ext == ".wav":
            media_type = "audio/wav"
        elif ext == ".mp4":
            media_type = "video/mp4"
        return "archivo", FileResponse(destino, media_type=media_type)

    if ext == ".json":
        try:
            return "json", json.loads(destino.read_text(encoding="utf-8"))
        except Exception:
            return "texto", destino.read_text(encoding="utf-8", errors="replace")

    # Texto
    if destino.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(413, "El archivo es demasiado grande para editar en el visor")
    return "texto", destino.read_text(encoding="utf-8", errors="replace")


def guardar_archivo(pid: str, ruta_rel: str, contenido: str, p: dict[str, Any], est: dict[str, Any], col: str) -> dict[str, Any]:
    """Guarda un archivo de texto con las reglas de negocio de la centralita."""
    if col == "bot":
        raise HTTPException(409, "El bot está trabajando en este pedido")

    if p.get("estado") in ("entregado", "cancelado"):
        raise HTTPException(400, "El pedido ya fue entregado o cancelado: solo lectura")

    destino = resolver_ruta_segura(pid, ruta_rel)
    ruta_norm = ruta_rel.replace("\\", "/")
    nombre = destino.name
    letra_n_actual = est.get("letra_n", 1)
    base = carpetas.buscar(pid)

    # 1. suno.txt o letra-v{N}.txt actual
    if ruta_norm == "2-letra/suno.txt" or ruta_norm == f"2-letra/letra-v{letra_n_actual}.txt":
        carpeta_letra = base / "2-letra"
        # 1. Leé 2-letra/version-v{N}.json con letras.leer_version
        version_data = letras.leer_version(carpeta_letra, letra_n_actual) or {
            "titulo": "", "letra": "", "estilo": "", "excluir": "", "foneticas": ""
        }
        # Extraer campos 'extra' de version-v{N}.json para conservarlos
        extra = {}
        js_path = carpeta_letra / f"version-v{letra_n_actual}.json"
        if js_path.exists():
            try:
                js_raw = json.loads(js_path.read_text(encoding="utf-8"))
                for k in ("revisor", "correcciones", "observaciones", "cambio"):
                    if k in js_raw:
                        extra[k] = js_raw[k]
            except Exception:
                pass

        novedad = ""
        if ruta_norm == "2-letra/suno.txt":
            parsed = parsear_suno_txt(contenido)
            if "letra" not in parsed or "estilo" not in parsed:
                raise HTTPException(422, "No encuentro las secciones STYLE OF MUSIC: y LYRICS: de suno.txt. "
                                         "Dejalas como estaban (solo cambiá el texto de abajo de cada una).")
            novedad = parsed.pop("novedad", "")
            version_data.update(parsed)
        else:
            version_data["letra"] = contenido
            if m := re.search(r"^QUÉ CAMBIA EN LA v\d+:[ \t]*(.*?)$",
                              (carpeta_letra / "suno.txt").read_text(encoding="utf-8")
                              if (carpeta_letra / "suno.txt").exists() else "", re.M):
                novedad = m.group(1).strip()

        letras.guardar_version(carpeta_letra, letra_n_actual, version_data, extra, novedad)
        aviso = f"Editaste a mano {nombre}: el bot usa esta versión como base del próximo cambio"
        carpetas.anotar(base, aviso)
        return {"ok": True, "aviso": aviso}

    # 2. letra-v{k}.txt vieja (k < letra_n_actual)
    if m := re.match(r"^2-letra/letra-v(\d+)\.txt$", ruta_norm):
        k = int(m.group(1))
        if k < letra_n_actual:
            destino.write_text(contenido, encoding="utf-8")
            return {"ok": True, "aviso": "Versión anterior guardada (el bot no la usa)"}

    # 3. Cualquier otro archivo no editable
    raise HTTPException(400, f"El archivo {nombre} no es editable")
