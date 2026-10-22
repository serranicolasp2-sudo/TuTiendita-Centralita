"""Servicio principal de la Centralita (FastAPI en 127.0.0.1:8790): `uvicorn servicio:app`.

No se llama app.py porque taparía al paquete tienda/app, que importan pedidos.py y proveedores.py.

Seguridad:
- Solo 127.0.0.1:8790
- Requiere encabezado X-Centralita: 1 y Host localhost:8790 o 127.0.0.1:8790 en todas las rutas /api.
- Rutas de archivo validadas estrictamente con Path.resolve dentro del pedido.
- Ninguna llave o token sale al navegador ni a los logs.
"""
import datetime
import logging
import os
import pathlib
import re
import sys
import tempfile
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

AQUI = pathlib.Path(__file__).resolve().parent
TIENDA_DIR = AQUI.parents[0] / "tienda" / "herramientas"

sys.path.insert(0, str(AQUI.parents[0] / "tienda"))
sys.path.insert(0, str(TIENDA_DIR))
sys.path.insert(0, str(AQUI.parents[0] / "produccion"))
sys.path.insert(0, str(AQUI))

from app import catalogo  # noqa: E402
import carpetas  # noqa: E402
from servicios import archivos, audio, clientes, costos, locales, ml_meta, retoque, servidor, sistema  # noqa: E402

from proveedores import link_compra  # noqa: E402  (el mismo link que usa el bot para "Comprar cuadro")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("centralita")

app = FastAPI(title="Centralita tutienditaia", docs_url=None, redoc_url=None, openapi_url=None)
STATIC_DIR = AQUI / "static"
HOSTS = {"127.0.0.1:8790", "localhost:8790"}
OCULTOS = ("cliente_token", "mp_preferencia", "mp_pago", "drive_carpeta")   # no van al navegador
DIAS_ENTREGADOS = 30


# ---------------- SEGURIDAD ----------------
@app.middleware("http")
async def validar_seguridad(request: Request, call_next):
    # Host exacto: frena páginas de otros dominios que apunten a 127.0.0.1 (DNS rebinding)
    if request.headers.get("host", "").lower() not in HOSTS:
        return JSONResponse({"error": "Host no permitido"}, status_code=403)

    if request.url.path.startswith("/api"):
        # En pytest o requests directos requerimos X-Centralita: 1
        x_centralita = request.headers.get("x-centralita")
        if x_centralita != "1":
            return JSONResponse({"error": "Falta encabezado X-Centralita: 1"}, status_code=403)

    response = await call_next(request)
    return response


# ---------------- CLASIFICACIÓN DE PEDIDOS ----------------
def procesar_un_pedido(p: dict[str, Any], est: dict[str, Any], base_carpeta: pathlib.Path | None) -> dict[str, Any]:
    pid = p["id"]
    tipo = "RF" if pid.startswith("RF") else "TC"
    estado = p.get("estado", "")
    intentos = est.get("intentos", 0)

    historial_raw = locales.leer_historial_completo(pid) if base_carpeta else ""
    ult_linea = locales.ultima_linea_historial(pid) if base_carpeta else ""

    col = "bot"
    falta = ult_linea or "El bot trabajando"
    nivel = "ok"
    link_cuadro_url = None

    reintentando = bool(base_carpeta and (base_carpeta / "reintentar.txt").is_file())
    bot_frenado = False

    prod_id = p.get("producto", "")
    es_cuadro = bool(prod_id in catalogo.PRODUCTOS and catalogo.PRODUCTOS[prod_id].envio)
    if es_cuadro:
        marco = p.get("datos", {}).get("marco") if isinstance(p.get("datos"), dict) else None
        link_cuadro_url = link_compra(prod_id, marco)

    # Columna "Tu turno":
    if reintentando:
        col = "turno"
        falta = "Reintento pedido: el bot lo toma en su próxima vuelta (cada 60 s)"
        nivel = "aviso"
    elif intentos >= 3:
        col = "turno"
        falta = f"El bot se frenó: {ult_linea}" if ult_linea else "El bot se frenó"
        nivel = "critico"
        bot_frenado = True
    elif tipo == "RF" and estado == "cambio" and est.get("cambio_en_espera") == p.get("cambios"):
        col = "turno"
        falta = f"El bot no entendió el cambio: «{p.get('nota_cambio') or ''}»"
        nivel = "aviso"
    elif tipo == "TC" and estado in ("pagado", "cambio") and (
        (est.get("letra_n", 0) > est.get("previa_subida", 0)) or ("previa_subida" not in est)
    ) and est.get("letra_n", 0) > 0:
        letra_n = est.get("letra_n", 1)
        col = "turno"
        falta = f"Letra v{letra_n} lista: pegala en Suno y soltá el audio de la vista previa"
        nivel = "aviso"
    elif tipo == "TC" and estado == "aprobado":
        hay_mp3 = bool(base_carpeta and list((base_carpeta / "4-entrega").glob("*.mp3"))) if base_carpeta else False
        if not hay_mp3:
            col = "turno"
            falta = "Aprobó: falta la descarga oficial de Suno"
            nivel = "critico"
    elif tipo == "RF" and estado == "entregado" and "Falta comprar el cuadro" in historial_raw and "Cuadro comprado" not in historial_raw and not p.get("seguimiento"):
        col = "turno"
        falta = "Comprar el cuadro"
        nivel = "critico"
    elif estado == "vista_previa":
        col = "cliente"
        falta = "Esperando que el cliente apruebe (vista previa enviada)"
        nivel = "info"
    elif estado == "entregado":
        col = "listo"
        falta = "Entregado"
        nivel = "ok"
    else:
        col = "bot"
        falta = ult_linea or "El bot trabajando"
        nivel = "ok"

    # Plazos: desde pagado hasta primera vista previa (vista_n == 0):
    plazo_info = None
    if estado not in ("entregado", "cancelado") and (p.get("vista_n") or 0) == 0 and p.get("pagado"):
        try:
            pagado_str = p["pagado"]
            pagado_dt = datetime.datetime.fromisoformat(pagado_str.replace("Z", "+00:00"))
            if pagado_dt.tzinfo is None:
                pagado_dt = pagado_dt.replace(tzinfo=datetime.timezone.utc)
            ahora_dt = datetime.datetime.now(datetime.timezone.utc)

            prod_id = p.get("producto", "")
            if "combo" in prod_id:
                plazo_h = 72
            elif tipo == "TC":
                plazo_h = 48
            else:
                plazo_h = 2

            total_segundos = plazo_h * 3600
            transcurrido = (ahora_dt - pagado_dt).total_seconds()
            restante_seg = total_segundos - transcurrido
            usado = min(1.0, max(0.0, transcurrido / total_segundos))

            if restante_seg < 0:
                nivel_plazo = "critico"
                m = int(abs(restante_seg) // 60)
                txt = f"Vencido hace {m} min" if m < 60 else f"Vencido hace {m//60} h"
            elif usado > 0.85:
                nivel_plazo = "critico"
                m = int(restante_seg // 60)
                txt = f"Quedan {m} min de {plazo_h} h" if m < 60 else f"Quedan {m//60} h de {plazo_h} h"
            elif usado > 0.60:
                nivel_plazo = "aviso"
                m = int(restante_seg // 60)
                txt = f"Quedan {m//60} h de {plazo_h} h"
            else:
                nivel_plazo = "ok"
                m = int(restante_seg // 60)
                txt = f"Quedan {m//60} h de {plazo_h} h"

            plazo_info = {
                "plazo_h": plazo_h,
                "usado_pct": round(usado * 100),
                "nivel": nivel_plazo,
                "texto": txt
            }
        except Exception:
            pass

    datos = p.get("datos") if isinstance(p.get("datos"), dict) else {}
    origen = datos.get("origen") or p.get("origen")
    origen_texto = "—"
    if isinstance(origen, dict) and origen:
        src = origen.get("source") or ""
        cnt = origen.get("content") or ""
        camp = origen.get("campaign") or ""
        if src and cnt:
            origen_texto = f"{src} · {cnt}"
        elif src and camp:
            origen_texto = f"{src} · {camp}"
        elif cnt:
            origen_texto = cnt
        elif src:
            origen_texto = src
        else:
            origen_texto = " · ".join(str(v) for v in origen.values() if v)

    return {
        **{k: v for k, v in p.items() if k not in OCULTOS},
        "tipo": tipo,
        "col": col,
        "falta": falta,
        "nivel": nivel,
        "link_cuadro": link_cuadro_url,
        "plazo": plazo_info,
        "tiene_carpeta_local": bool(base_carpeta and base_carpeta.exists()),
        "reintentando": reintentando,
        "bot_frenado": bot_frenado,
        "origen": origen if isinstance(origen, dict) else None,
        "origen_texto": origen_texto,
    }


def entregado_hace_mucho(p: dict[str, Any]) -> bool:
    if p.get("estado") != "entregado" or not p.get("entregado"):
        return False
    try:
        cuando = datetime.datetime.fromisoformat(p["entregado"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc) - cuando > datetime.timedelta(days=DIAS_ENTREGADOS)


def traer_pedidos_procesados(con_viejos: bool = False) -> list[dict[str, Any]]:
    todos = servidor.obtener_pedidos()
    bot_estado = locales.leer_bot_estado()
    procesados = []

    for p in todos:
        if p.get("estado") in ("pendiente_pago", "cancelado"):
            continue
        if not con_viejos and entregado_hace_mucho(p):
            continue
        pid = p["id"]
        est = bot_estado.get(pid, {})
        base_carpeta = carpetas.buscar(pid)
        procesados.append(procesar_un_pedido(p, est, base_carpeta))
    return procesados


def calcular_resumen_anuncios(todos_pedidos: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen por utm_content: pedidos pagados y monto cobrado, con datos reales de los pedidos."""
    grupos: dict[str, dict[str, Any]] = {}
    for p in todos_pedidos:
        estado = p.get("estado", "")
        if estado in ("pendiente_pago", "cancelado"):
            continue
        datos = p.get("datos") if isinstance(p.get("datos"), dict) else {}
        orig = datos.get("origen") or p.get("origen")
        content = (orig or {}).get("content") if isinstance(orig, dict) else None
        anuncio_key = content if content else "(sin anuncio)"

        if anuncio_key not in grupos:
            grupos[anuncio_key] = {
                "anuncio": anuncio_key,
                "campana": (orig or {}).get("campaign", "—") if isinstance(orig, dict) else "—",
                "fuente": (orig or {}).get("source", "—") if isinstance(orig, dict) else "—",
                "pedidos_pagados": 0,
                "monto_cobrado": 0,
                "pedidos": []
            }
        grupos[anuncio_key]["pedidos_pagados"] += 1
        grupos[anuncio_key]["monto_cobrado"] += int(p.get("precio") or 0)
        grupos[anuncio_key]["pedidos"].append(p.get("id"))

    items = sorted(
        grupos.values(),
        key=lambda x: (x["anuncio"] == "(sin anuncio)", -x["pedidos_pagados"], -x["monto_cobrado"])
    )
    total_pedidos = sum(x["pedidos_pagados"] for x in items)
    total_cobrado = sum(x["monto_cobrado"] for x in items)

    return {
        "anuncios": items,
        "total_pedidos": total_pedidos,
        "total_cobrado": total_cobrado
    }


# ---------------- RUTAS API ----------------
@app.get("/api/hoy")
def api_hoy():
    pedidos_lista = traer_pedidos_procesados()
    turno = [p for p in pedidos_lista if p["col"] == "turno"]
    con_plazo = [p for p in pedidos_lista if p.get("plazo")]
    return {
        "turno": turno,
        "con_plazo": con_plazo,
        "cuenta_turno": len(turno)
    }


@app.get("/api/anuncios")
@app.get("/api/pedidos/resumen-anuncios")
def api_anuncios():
    todos = servidor.obtener_pedidos()
    return calcular_resumen_anuncios(todos)


@app.get("/api/pedidos")
def api_pedidos(tipo: str | None = None, q: str | None = None):
    pedidos_lista = traer_pedidos_procesados(con_viejos=bool(q))   # buscando, aparecen también los entregados viejos
    if tipo and tipo.lower() in ("rf", "tc"):
        pedidos_lista = [p for p in pedidos_lista if p["tipo"].lower() == tipo.lower()]
    if q:
        q_l = q.lower().strip()
        pedidos_lista = [p for p in pedidos_lista if q_l in p["id"].lower() or q_l in p.get("nombre", "").lower()]
    return pedidos_lista


@app.get("/api/pedidos/{pid}")
def api_pedido_ficha(pid: str):
    pid_u = pid.upper()
    try:
        p_serv = servidor.obtener_pedido(pid_u)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(404, f"No existe el pedido {pid_u}")
        raise

    bot_estado = locales.leer_bot_estado()
    est = bot_estado.get(pid_u, {})
    base = carpetas.buscar(pid_u)

    procesado = procesar_un_pedido(p_serv, est, base)
    lista_archivos = archivos.listar_archivos(pid_u, procesado, est, procesado["col"])
    historial_lineas = locales.leer_historial_lineas(pid_u)
    costo_prov = costos.leer_costos_proveedor().get(pid_u)

    return {
        "pedido": procesado,
        "est": est,
        "archivos": lista_archivos,
        "historial": historial_lineas,
        "resumen": p_serv.get("resumen", ""),
        "costo_proveedor": costo_prov,
    }


@app.get("/api/pedidos/{pid}/archivos")
def api_pedido_archivos(pid: str):
    pid_u = pid.upper()
    p_serv = servidor.obtener_pedido(pid_u)
    bot_estado = locales.leer_bot_estado()
    est = bot_estado.get(pid_u, {})
    base = carpetas.buscar(pid_u)
    procesado = procesar_un_pedido(p_serv, est, base)
    return archivos.listar_archivos(pid_u, procesado, est, procesado["col"])


@app.get("/api/pedidos/{pid}/archivo")
def api_leer_archivo(pid: str, ruta: str = Query(...)):
    tipo, resultado = archivos.leer_archivo(pid.upper(), ruta)
    if tipo == "archivo":
        return resultado
    return {"tipo": tipo, "contenido": resultado}


@app.put("/api/pedidos/{pid}/archivo")
async def api_guardar_archivo(pid: str, request: Request, ruta: str = Query(...)):
    pid_u = pid.upper()
    p_serv = servidor.obtener_pedido(pid_u)
    bot_estado = locales.leer_bot_estado()
    est = bot_estado.get(pid_u, {})
    base = carpetas.buscar(pid_u)
    procesado = procesar_un_pedido(p_serv, est, base)

    try:
        body = await request.json()
        contenido = body.get("contenido", "")
    except Exception:
        raise HTTPException(400, "JSON inválido")

    return archivos.guardar_archivo(pid_u, ruta, contenido, procesado, est, procesado["col"])


@app.post("/api/pedidos/{pid}/mostrar")
def api_mostrar_en_carpeta(pid: str, ruta: str = Query(...)):
    destino = archivos.resolver_ruta_segura(pid.upper(), ruta)
    sistema.mostrar_en_explorador(destino)
    return {"ok": True}


@app.post("/api/pedidos/{pid}/abrir")
def api_abrir_con_programa(pid: str, ruta: str = Query(...)):
    destino = archivos.resolver_ruta_segura(pid.upper(), ruta)
    sistema.abrir_con_programa(destino)
    return {"ok": True}


@app.post("/api/pedidos/{pid}/audio")
async def api_soltar_audio(pid: str, archivo_subido: UploadFile = File(...), para: str = Form(None)):
    pid_u = pid.upper()
    p_serv = servidor.obtener_pedido(pid_u)
    if p_serv.get("estado") in ("entregado", "cancelado"):
        raise HTTPException(409, f"El pedido está {p_serv['estado']}: no se le suman audios")

    # Temporal con nombre propio: el nombre que manda el navegador no se usa como ruta (podría traer "..\")
    ext = pathlib.Path(archivo_subido.filename or "").suffix.lower()
    ext = ext if re.fullmatch(r"\.[a-z0-9]{1,5}", ext) else ".audio"
    fd, tmp = tempfile.mkstemp(prefix=f"centralita-{pid_u}-", suffix=ext)
    tmp_path = pathlib.Path(tmp)
    try:
        with os.fdopen(fd, "wb") as f_out:
            while bloque := await archivo_subido.read(1024 * 1024):
                f_out.write(bloque)

        if p_serv.get("estado") == "aprobado":
            # Es el audio final
            sugerido = para or ""
            if not sugerido and isinstance(p_serv.get("datos"), dict):
                pq = p_serv["datos"].get("para_quien", "")
                sugerido = pq.split(" - ")[0].split(",")[0].strip()
            res = audio.guardar_final(pid_u, tmp_path, sugerido, p_serv)
        else:
            # Es vista previa
            res = audio.guardar_vista_previa(pid_u, tmp_path, p_serv)
        return res
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/pedidos/{pid}/audio-grabar")
def api_grabar_audio(pid: str):
    pid_u = pid.upper()
    p_serv = servidor.obtener_pedido(pid_u)
    if p_serv.get("estado") not in ("pagado", "cambio"):
        raise HTTPException(409, f"El pedido está en {p_serv.get('estado')}: el bot no subiría esa vista previa")
    return audio.grabar_lo_que_suena(pid_u)


@app.get("/api/pedidos/{pid}/audio-grabar")
def api_estado_grabacion(pid: str):
    return audio.estado_grabacion(pid.upper())


def _se_puede_tocar(pid_u: str) -> tuple[dict[str, Any], pathlib.Path]:
    """Para retocar o mandar la vista previa: ni entregado ni con el bot trabajando en el pedido."""
    p_serv = servidor.obtener_pedido(pid_u)
    base = carpetas.buscar(pid_u)
    if not base:
        raise HTTPException(404, "No se encontró la carpeta del pedido")
    procesado = procesar_un_pedido(p_serv, locales.leer_bot_estado().get(pid_u, {}), base)
    if p_serv.get("estado") in ("entregado", "cancelado"):
        raise HTTPException(409, f"El pedido está {p_serv['estado']}: solo lectura")
    if procesado["col"] == "bot":
        raise HTTPException(409, "El bot está trabajando en este pedido")
    return p_serv, base


@app.post("/api/pedidos/{pid}/retoque")
async def api_retoque_foto(pid: str, foto_stem: str = Form(...), imagen: UploadFile = File(...)):
    pid_u = pid.upper()
    p_serv, _ = _se_puede_tocar(pid_u)
    contenido = await imagen.read()
    return retoque.reemplazar_por_retoque(pid_u, foto_stem, contenido, p_serv)


@app.post("/api/pedidos/{pid}/mandar-vista-previa")
def api_mandar_vista_previa(pid: str):
    pid_u = pid.upper()
    p_serv, base = _se_puede_tocar(pid_u)
    if p_serv.get("estado") not in ("pagado", "cambio", "vista_previa"):
        raise HTTPException(409, f"El pedido está en {p_serv.get('estado')}: no se manda una vista previa")
    previas = sorted((base / "3-entrega").glob("*-vista-previa.jpg"))
    if not previas:
        raise HTTPException(400, "No hay archivos *-vista-previa.jpg en 3-entrega")
    res = servidor.subir_vista_previa(pid_u, previas)
    carpetas.anotar(base, f"Vista previa enviada al cliente desde la centralita: {', '.join(p.name for p in previas)}")
    return res


@app.post("/api/pedidos/{pid}/nota")
async def api_agregar_nota(pid: str, request: Request):
    try:
        datos = await request.json()
        nota = datos.get("nota", "").strip()
    except Exception:
        raise HTTPException(400, "JSON inválido")
    if not nota:
        raise HTTPException(422, "La nota no puede estar vacía")
    locales.anotar_historial(pid.upper(), f"Nota tuya: {nota}")
    return {"ok": True}


@app.patch("/api/pedidos/{pid}/contacto")
async def api_contacto(pid: str, request: Request):
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(400, "JSON inválido")
    email = datos.get("email")
    whatsapp = datos.get("whatsapp")
    antes = servidor.obtener_pedido(pid.upper())
    nuevo = servidor.actualizar_contacto(pid.upper(), email, whatsapp)
    for campo, nombre in (("email", "Mail"), ("whatsapp", "WhatsApp")):
        if antes.get(campo) != nuevo.get(campo):
            locales.anotar_historial(pid.upper(), f"{nombre} corregido desde la centralita: {antes.get(campo)} → {nuevo.get(campo)}")
    return {k: v for k, v in nuevo.items() if k not in OCULTOS}


@app.post("/api/pedidos/{pid}/reenviar")
async def api_reenviar(pid: str, request: Request):
    try:
        datos = await request.json()
        que = datos.get("que")
    except Exception:
        raise HTTPException(400, "JSON inválido")
    res = servidor.reenviar(pid.upper(), que)
    que_txt = "la vista previa" if que == "vista_previa" else "la entrega"
    locales.anotar_historial(pid.upper(), f"Reenviaste el mail de {que_txt} desde la centralita")
    return res


@app.post("/api/pedidos/{pid}/cambio")
async def api_cambio(pid: str, request: Request):
    try:
        datos = await request.json()
        texto = (datos.get("texto") or "").strip()
        sin_costo = datos.get("sin_costo", True)
    except Exception:
        raise HTTPException(400, "JSON inválido")
    if len(texto) < 5:
        raise HTTPException(422, "Contanos un poco más sobre el cambio (mínimo 5 caracteres)")

    pid_u = pid.upper()
    p_serv = servidor.obtener_pedido(pid_u)
    bot_estado = locales.leer_bot_estado()
    est = bot_estado.get(pid_u, {})

    # Si es RF en cambio con bot esperando instrucción
    if pid_u.startswith("RF") and p_serv.get("estado") == "cambio" and est.get("cambio_en_espera") == p_serv.get("cambios"):
        base = carpetas.buscar(pid_u)
        if base:
            (base / "nota-cambio.txt").write_text(texto, encoding="utf-8")
            carpetas.anotar(base, f"Instrucción tuya para rehacer: {texto}")
            return {"ok": True, "mensaje": "Instrucción guardada en nota-cambio.txt para el bot"}

    # Caso general: POST /admin/pedidos/{pid}/cambio
    res = servidor.pedir_cambio(pid_u, texto, sin_costo)
    locales.anotar_historial(pid_u, f"Cambio solicitado desde la centralita (sin costo: {sin_costo}): {texto}")
    return res


@app.post("/api/pedidos/{pid}/cambios-extra")
async def api_cambios_extra(pid: str, request: Request):
    try:
        datos = await request.json()
        cantidad = int(datos.get("cantidad", 1))
    except Exception:
        raise HTTPException(400, "JSON inválido")
    res = servidor.dar_cambios_extra(pid.upper(), cantidad)
    locales.anotar_historial(pid.upper(), f"Le diste {cantidad} cambio(s) extra sin costo. Le quedan {res.get('quedan')}.")
    return res


@app.post("/api/pedidos/{pid}/cuadro-comprado")
async def api_cuadro_comprado(pid: str, request: Request):
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(400, "JSON inválido")
    if not isinstance(datos, dict):
        raise HTTPException(400, "JSON inválido")

    seguimiento = (datos.get("seguimiento") or "").strip()
    pagado_raw = datos.get("pagado")

    pid_u = pid.upper()
    if pagado_raw is not None and str(pagado_raw).strip() != "":
        try:
            pagado_int = int(str(pagado_raw).replace(".", "").replace("$", "").strip())
        except (ValueError, TypeError):
            raise HTTPException(400, "El monto pagado debe ser un número entero.")
        if not 1 <= pagado_int <= 10_000_000:
            raise HTTPException(422, "Revisá el monto: tiene que ser lo que pagaste, en pesos.")
        prod = servidor.obtener_pedido(pid_u).get("producto")
        if not (prod in catalogo.PRODUCTOS and catalogo.PRODUCTOS[prod].envio):
            raise HTTPException(409, "Este pedido no lleva cuadro")
        anterior, nuevo = costos.guardar_costo_proveedor(pid_u, pagado_int)
        nuevo_fmt = f"${nuevo:,}".replace(",", ".")
        if anterior is not None:
            ant_fmt = f"${anterior:,}".replace(",", ".")
            txt_monto = f"corregiste lo que pagaste: {ant_fmt} → {nuevo_fmt}."
        else:
            txt_monto = f"Pagaste {nuevo_fmt}."
        locales.anotar_historial(pid_u, f"Cuadro comprado. {txt_monto} Seguimiento {seguimiento or '(sin número)'}.")
    else:
        locales.anotar_historial(pid_u, f"Cuadro comprado. Seguimiento {seguimiento or '(sin número)'}.")
    return {"ok": True}


def _monto_pagado(datos: dict) -> int | None:
    """Lo que pagó el usuario por el cuadro (opcional). Se valida antes de mandar nada."""
    crudo = datos.get("pagado")
    if crudo is None or str(crudo).strip() == "":
        return None
    try:
        monto = int(str(crudo).replace(".", "").replace("$", "").strip())
    except ValueError:
        raise HTTPException(422, "Lo que pagaste tiene que ser un número entero, en pesos.")
    if not 1 <= monto <= 10_000_000:
        raise HTTPException(422, "Revisá el monto: tiene que ser lo que pagaste, en pesos.")
    return monto


def _datos_seguimiento(datos: dict) -> dict:
    return {"numero": str(datos.get("numero") or "").strip(),
            "url": (str(datos.get("url")).strip() or None) if datos.get("url") else None,
            "empresa": (str(datos.get("empresa")).strip() or None) if datos.get("empresa") else None}


@app.post("/api/pedidos/{pid}/seguimiento/previa")
async def api_seguimiento_previa(pid: str, request: Request):
    """El texto exacto que le va a llegar al cliente lo arma el servidor (el mismo que después manda)."""
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(422, "JSON inválido")
    if not isinstance(datos, dict):
        raise HTTPException(422, "JSON inválido")
    _monto_pagado(datos)
    return servidor.enviar_seguimiento(pid.upper(), previa=True, **_datos_seguimiento(datos))


@app.post("/api/pedidos/{pid}/seguimiento")
async def api_seguimiento(pid: str, request: Request):
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(422, "JSON inválido")
    if not isinstance(datos, dict):
        raise HTTPException(422, "JSON inválido")
    pid_u = pid.upper()
    pagado = _monto_pagado(datos)                      # si el monto está mal, no se manda nada
    res = servidor.enviar_seguimiento(pid_u, reenviar=bool(datos.get("reenviar", False)), **_datos_seguimiento(datos))
    # Recién con el seguimiento enviado se guarda lo pagado (si el envío falló, no queda nada a medias)
    texto = f"Seguimiento enviado al cliente: {res.get('seguimiento') or datos.get('numero')}"
    if pagado is not None:
        anterior, nuevo = costos.guardar_costo_proveedor(pid_u, pagado)
        pesos = lambda n: f"${n:,}".replace(",", ".")
        texto += (f". Corregiste lo que pagaste: {pesos(anterior)} → {pesos(nuevo)}" if anterior is not None
                  else f". Pagaste {pesos(nuevo)}")
    locales.anotar_historial(pid_u, texto)
    return res


@app.post("/api/pedidos/{pid}/reintentar")
def api_reintentar_pedido(pid: str):
    pid_u = pid.upper()
    base = carpetas.buscar(pid_u)
    if not base or not base.is_dir():
        raise HTTPException(404, f"No se encontró la carpeta del pedido {pid_u}")

    # Solo con el bot frenado: el bot mira reintentar.txt únicamente en esos pedidos. En otro, el archivo quedaría
    # olvidado y dispararía un reintento solo la próxima vez que el bot se frene.
    if locales.leer_bot_estado().get(pid_u, {}).get("intentos", 0) < 3:
        raise HTTPException(409, "El bot no está frenado en este pedido: no hay nada que reintentar")
    ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (base / "reintentar.txt").write_text(ahora_iso, encoding="utf-8")
    locales.anotar_historial(pid_u, "Reintento pedido desde la centralita")
    return {"ok": True}


def _hora_local(iso: str | None) -> str:
    """Fecha y hora del servidor (UTC) en la hora de la PC: 14/10 13:53."""
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return "sin dato"


def _costo_por_producto(pubs: list[dict[str, Any]]) -> tuple[dict[str, int], set[str]]:
    """Costo de cada producto con proveedor, igual que lo calcula el vigilante: por publicación, el precio cargado a
    mano si hay, si no el leído; por producto, la publicación más cara. Devuelve (costos, productos con precio a mano)."""
    costos_prod: dict[str, int] = {}
    a_mano: set[str] = set()
    for pub in pubs:
        prod_id = pub.get("producto")
        costo = pub.get("a_mano") if pub.get("a_mano") is not None else pub.get("publicado")
        if not prod_id or costo is None:
            continue
        if costo > costos_prod.get(prod_id, 0):
            costos_prod[prod_id] = costo
            a_mano.discard(prod_id)
            if pub.get("a_mano") is not None:
                a_mano.add(prod_id)
    return costos_prod, a_mano


def _texto_costo(prod_id: str, costo: int, a_mano: set[str]) -> str:
    monto = f"${costo:,}".replace(",", ".")
    return f"cargado a mano: {monto}" if prod_id in a_mano else f"publicado hoy a {monto}"


@app.get("/api/plata")
def api_plata(mes: str | None = None, marca: str | None = None):
    pagos_lista = servidor.obtener_pagos()
    pedidos_lista = servidor.obtener_pedidos()
    pedidos_map = {p["id"]: p for p in pedidos_lista}

    costos_prov = costos.leer_costos_proveedor()
    costos_serv = servidor.obtener_costos()
    pubs = (costos_serv.get("proveedores") or {}).get("publicaciones") or []

    vigilante_map, con_a_mano = _costo_por_producto(pubs)

    filas = []
    meses_disponibles = set()

    for pago in pagos_lista:
        pid = pago["pedido"]
        ped = pedidos_map.get(pid, {})
        prod = pago.get("producto") or ped.get("producto") or ""
        m_tipo = ped.get("marca") or ("rf" if str(pid).startswith("RF") else "tc")

        aprobado_str = pago.get("aprobado") or ped.get("pagado") or ped.get("creado") or ""
        if aprobado_str:
            mes_str = aprobado_str[:7]
            meses_disponibles.add(mes_str)
        else:
            mes_str = ""

        if mes and mes != "todos" and mes_str != mes:
            continue
        if marca and marca.lower() not in ("todas", "todos", "") and m_tipo.lower() != marca.lower():
            continue

        es_cuadro = bool(catalogo.PRODUCTOS.get(prod) and catalogo.PRODUCTOS[prod].envio)   # cuadro físico

        if pago.get("error") or pago.get("estado") != "approved":
            # MP no se pudo leer, o el cobro ya no está aprobado (reembolso, contracargo…): nada de $0 inventados
            motivo = "sin dato: Mercado Pago no respondió" if pago.get("error") else f"estado en MP: {pago.get('estado')}"
            filas.append({
                "pedido": pid, "fecha": aprobado_str[:10], "fecha_iso": aprobado_str, "marca": m_tipo, "producto": prod,
                "nombre_producto": catalogo.PRODUCTOS[prod].nombre if prod in catalogo.PRODUCTOS else prod,
                "canal": "Web (Mercado Pago)", "cobrado": None, "comision": None, "comision_pct": None,
                "comision_detalle": pago.get("error") or "", "proveedor_monto": None, "proveedor_texto": "—",
                "proveedor_sub": None, "te_quedo_monto": None, "te_quedo_texto": motivo,
                "liberacion": motivo, "liberada": True, "liberacion_fecha": None, "neto": 0.0, "completa": False,
            })
            continue

        monto = float(pago.get("monto") or 0.0)
        comisiones_lista = pago.get("comisiones") or []
        comision_total = round(sum(float(c.get("monto") or 0.0) for c in comisiones_lista), 2)
        comision_pct = round((comision_total / monto) * 100.0, 2) if monto > 0 else 0.0
        comision_detalles = " + ".join(f"{c.get('tipo', 'fee')}: ${c.get('monto', 0)}" for c in comisiones_lista) or "Comisión MP"

        prov_manual = costos_prov.get(pid, {}).get("pagado")
        vigilante_costo = vigilante_map.get(prod)

        if not es_cuadro:
            proveedor_monto = 0.0
            proveedor_texto = "—"
            proveedor_sub = None
            completa = True
        else:
            if prov_manual is not None:
                proveedor_monto = float(prov_manual)
                proveedor_texto = f"${prov_manual:,}".replace(",", ".")
                proveedor_sub = "cargado a mano"
                completa = True
            else:
                proveedor_monto = None
                proveedor_texto = "sin dato"
                proveedor_sub = _texto_costo(prod, vigilante_costo, con_a_mano) if vigilante_costo else "sin lectura del vigilante"
                completa = False

        neto = float(pago.get("neto") or 0.0)
        if proveedor_monto is not None:
            te_quedo_monto = round(neto - proveedor_monto, 2)
            te_quedo_texto = f"${round(te_quedo_monto):,}".replace(",", ".")
        else:
            te_quedo_monto = None
            te_quedo_texto = "sin dato (falta lo que pagaste el cuadro)"

        lib = pago.get("liberacion") or {}
        lib_estado = lib.get("estado")
        lib_fecha = lib.get("fecha")
        if lib_estado == "released":
            liberacion_texto = "Liberada"
            liberada = True
        elif lib_fecha:
            dt = costos.parsear_fecha_iso(lib_fecha)
            liberacion_texto = f"Se libera el {dt.strftime('%d/%m')}" if dt else "Pendiente"
            liberada = False
        else:
            liberacion_texto = "Pendiente"
            liberada = False

        reembolsado = float(pago.get("reembolsado") or 0.0)
        if reembolsado > 0:
            liberacion_texto += f" · Reembolsado ${round(reembolsado):,}".replace(",", ".")

        filas.append({
            "pedido": pid,
            "fecha": aprobado_str[:10],
            "fecha_iso": aprobado_str,
            "marca": m_tipo,
            "producto": prod,
            "nombre_producto": catalogo.PRODUCTOS.get(prod).nombre if prod in catalogo.PRODUCTOS else prod,
            "canal": "Web (Mercado Pago)",
            "cobrado": monto,
            "comision": comision_total,
            "comision_pct": comision_pct,
            "comision_detalle": comision_detalles,
            "proveedor_monto": proveedor_monto,
            "proveedor_texto": proveedor_texto,
            "proveedor_sub": proveedor_sub,
            "te_quedo_monto": te_quedo_monto,
            "te_quedo_texto": te_quedo_texto,
            "liberacion": liberacion_texto,
            "liberada": liberada,
            "liberacion_fecha": lib_fecha,
            "neto": neto,
            "completa": completa,
        })

    filas.sort(key=lambda r: r.get("fecha_iso") or "", reverse=True)

    filas_completas = [f for f in filas if f["completa"]]
    filas_incompletas_count = len(filas) - len(filas_completas)

    tot_cobrado = round(sum(f["cobrado"] for f in filas_completas), 2)
    tot_comisiones = round(sum(f["comision"] for f in filas_completas), 2)
    tot_proveedor = round(sum(f["proveedor_monto"] for f in filas_completas if f["proveedor_monto"] is not None), 2)
    tot_te_quedo = round(sum(f["te_quedo_monto"] for f in filas_completas if f["te_quedo_monto"] is not None), 2)

    pendientes_liberacion = [f for f in filas if not f["liberada"]]
    tot_por_liberar = round(sum(f["neto"] for f in pendientes_liberacion), 2)
    fechas_lib = [costos.parsear_fecha_iso(f["liberacion_fecha"]) for f in pendientes_liberacion if f["liberacion_fecha"]]
    fechas_lib = [d for d in fechas_lib if d]
    fechas_lib.sort()
    proxima_lib_texto = f"primera el {fechas_lib[0].strftime('%d/%m')}" if fechas_lib else None

    resumen_mp = costos.agrupar_pagos_por_medio(pagos_lista)

    return {
        "filas": filas,
        "totales": {
            "cobrado": tot_cobrado,
            "comisiones": tot_comisiones,
            "proveedor": tot_proveedor,
            "te_quedo": tot_te_quedo,
            "por_liberar": tot_por_liberar,
            "proxima_liberacion": proxima_lib_texto,
            "filas_incompletas": filas_incompletas_count,
        },
        "resumen_mp": resumen_mp,
        "meses_disponibles": sorted(list(meses_disponibles), reverse=True),
    }


@app.get("/api/costos")
def api_costos():
    costos_serv = servidor.obtener_costos()
    pagos_lista = servidor.obtener_pagos()
    resumen_mp = costos.agrupar_pagos_por_medio(pagos_lista)
    pct_dinero_cuenta = resumen_mp.get("porcentaje_dinero_cuenta")

    categorias = costos.leer_categorias_ml()
    pubs = (costos_serv.get("proveedores") or {}).get("publicaciones") or []
    leido_vigilante = (costos_serv.get("proveedores") or {}).get("leido")

    vigilante_map, con_a_mano = _costo_por_producto(pubs)

    productos_res = []
    for prod_id, p_info in (costos_serv.get("productos") or {}).items():
        nombre = p_info["nombre"]
        precio_web = int(p_info["precio"])
        cat_ml = categorias.get(prod_id)
        es_cuadro = bool(catalogo.PRODUCTOS.get(prod_id) and catalogo.PRODUCTOS[prod_id].envio)
        costo_vig = vigilante_map.get(prod_id) if es_cuadro else 0
        falta_proveedor = es_cuadro and costo_vig is None    # sin lectura del vigilante: nada de restar 0

        filas_mp = []
        for g in resumen_mp.get("grupos", []):
            pct_g = g["porcentaje_real"]
            comis_g = round(precio_web * (g["porcentaje_exacto"] / 100.0), 2)
            neto_g = None if falta_proveedor else round(precio_web - comis_g - costo_vig, 2)
            filas_mp.append({
                "medio": g["nombre"],
                "te_queda": neto_g,
                "pct": pct_g,
                "pagos": g["cantidad"],
            })

        if es_cuadro:
            if costo_vig is not None:
                prov_texto = _texto_costo(prod_id, costo_vig, con_a_mano)
                prov_aclaracion = "lo que vas a pagar si lo comprás hoy"
            else:
                prov_texto = "sin dato"
                prov_aclaracion = "sin lectura del vigilante"
        else:
            prov_texto = "—"
            prov_aclaracion = None

        if cat_ml:
            cargos_ml = costos.consultar_cargos_ml(precio_web, cat_ml)
            if cargos_ml and not falta_proveedor:
                queda_clasica = (round(precio_web - cargos_ml["clasica"]["total"] - costo_vig, 2)
                                 if "clasica" in cargos_ml else None)
                queda_premium = (round(precio_web - cargos_ml["premium"]["total"] - costo_vig, 2)
                                 if "premium" in cargos_ml else None)
            elif cargos_ml:
                queda_clasica = None
                queda_premium = None
            else:
                cargos_ml = {}
                queda_clasica = None
                queda_premium = None

            publicar_ml = costos.calcular_precio_publicar_ml(precio_web, cat_ml, pct_dinero_cuenta)
        else:
            cargos_ml = None
            queda_clasica = None
            queda_premium = None
            publicar_ml = {
                "clasica": None,
                "premium": None,
                "motivo": "sin dato: falta la categoría de ML",
            }

        productos_res.append({
            "id": prod_id,
            "nombre": nombre,
            "precio_web": precio_web,
            "categoria_ml": cat_ml,
            "filas_mp": filas_mp,
            "proveedor": {
                "texto": prov_texto,
                "aclaracion": prov_aclaracion,
                "costo": costo_vig,
                "hora_lectura": leido_vigilante,
            },
            "ml": {
                "cargos": cargos_ml,
                "queda_clasica": queda_clasica,
                "queda_premium": queda_premium,
                "publicar_igual_web": publicar_ml,
            },
        })

    # Con qué comisión arma el vigilante los precios de los cuadros (la real de MP, D-49; la guarda en su estado)
    cm = costos_serv.get("comision_mp")
    if cm:
        aviso_fijo = (f"Los precios de los cuadros se calculan con la comisión real de Mercado Pago: "
                      f"{str(cm['porcentaje']).replace('.', ',')} % ({cm['pagos']} cobros del {cm.get('desde') or '?'} "
                      f"al {cm.get('hasta') or '?'}, leído el {_hora_local(cm.get('leido'))}).")
    else:
        aviso_fijo = ("Los precios de los cuadros todavía no se recalcularon con la comisión real de Mercado Pago "
                      "(el vigilante lo hace en su próxima revisión, cada 30 minutos). Mientras no haya dato, no cambia precios.")

    return {
        "productos": productos_res,
        "resumen_mp": resumen_mp,
        "leido_vigilante": leido_vigilante,
        "aviso_fijo": aviso_fijo,
    }


@app.post("/api/costos/simular")
async def api_costos_simular(request: Request):
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(400, "JSON inválido")
    if not isinstance(datos, dict):
        raise HTTPException(400, "JSON inválido")

    try:
        precio = int(datos.get("precio") or 0)
    except (ValueError, TypeError):
        raise HTTPException(400, "El precio debe ser un número entero.")
    if precio <= 0:
        raise HTTPException(400, "El precio debe ser mayor a 0.")

    prod_id = datos.get("producto")
    categoria = (str(datos.get("categoria") or "")).strip().upper() or None
    if categoria and not re.fullmatch(r"MLA\d{1,12}", categoria):
        raise HTTPException(422, "La categoría de ML es MLA seguido de números (por ejemplo MLA1635).")
    categorias = costos.leer_categorias_ml()
    if not categoria and prod_id:
        categoria = categorias.get(prod_id)

    pagos_lista = servidor.obtener_pagos()
    resumen_mp = costos.agrupar_pagos_por_medio(pagos_lista)
    pct_dinero_cuenta = resumen_mp.get("porcentaje_dinero_cuenta")

    cargos_ml = costos.consultar_cargos_ml(precio, categoria) if categoria else None
    publicar_ml = costos.calcular_precio_publicar_ml(precio, categoria, pct_dinero_cuenta) if categoria else {
        "clasica": None,
        "premium": None,
        "motivo": "sin dato: falta la categoría de ML",
    }

    return {
        "precio": precio,
        "producto": prod_id,
        "categoria": categoria,
        "cargos_ml": cargos_ml,
        "publicar_igual_web": publicar_ml,
        "resumen_mp": resumen_mp,
    }


@app.post("/api/costos/actualizar")
def api_costos_actualizar():
    costos.borrar_cache_ml()
    return {"ok": True}


@app.get("/api/sistema")
def api_sistema():
    return sistema.estado_completo()


@app.post("/api/sistema/reiniciar-bot")
def api_reiniciar_bot():
    return sistema.reiniciar_bot()


# ---------------- PROVEEDORES ----------------
@app.get("/api/proveedores")
def api_proveedores():
    return servidor.obtener_proveedores()


@app.post("/api/proveedores/{nombre}/precio")
async def api_proveedores_precio(nombre: str, request: Request):
    try:
        datos = await request.json()
        precio = int(datos.get("precio"))
    except Exception:
        raise HTTPException(422, "Precio inválido")
    return servidor.fijar_precio_a_mano(nombre, precio)


@app.delete("/api/proveedores/{nombre}/precio")
def api_proveedores_quitar_precio(nombre: str):
    return servidor.quitar_precio_a_mano(nombre)


@app.post("/api/proveedores/pendientes/{producto}/aprobar")
def api_proveedores_aprobar(producto: str):
    return servidor.aprobar_pendiente(producto)


@app.post("/api/proveedores/pendientes/{producto}/rechazar")
def api_proveedores_rechazar(producto: str):
    return servidor.rechazar_pendiente(producto)


@app.post("/api/proveedores/revisar")
def api_proveedores_revisar():
    return servidor.revisar_vigilante(prueba=False)


# ---------------- CLIENTES ----------------
@app.get("/api/clientes")
def api_clientes():
    pedidos_lista = servidor.obtener_pedidos()
    pagos_lista = servidor.obtener_pagos()
    return clientes.agrupar_clientes(pedidos_lista, pagos_lista)


# ---------------- PRECIOS ----------------
@app.get("/api/precios")
def api_precios():
    precios_serv = servidor.obtener_precios()
    productos = precios_serv.get("productos", [])
    historial = precios_serv.get("historial", [])

    pagos_lista = servidor.obtener_pagos()
    resumen_mp = costos.agrupar_pagos_por_medio(pagos_lista)
    pct_mp = resumen_mp.get("porcentaje_dinero_cuenta")
    pct_exacto = pct_mp
    for g in resumen_mp.get("grupos", []):
        if "cuenta" in g.get("nombre", "").lower():
            pct_exacto = g.get("porcentaje_exacto", pct_mp)
            break

    try:
        costos_serv = servidor.obtener_costos()
        pubs = (costos_serv.get("proveedores") or {}).get("publicaciones") or []
        vigilante_map, con_a_mano = _costo_por_producto(pubs)
        leido_vig = (costos_serv.get("proveedores") or {}).get("leido")
    except Exception:
        vigilante_map, con_a_mano, leido_vig = {}, set(), None

    for p in productos:
        pid = p["id"]
        precio = p.get("precio") or 0
        es_cuadro = p.get("con_proveedor", False)
        costo_vig = vigilante_map.get(pid) if es_cuadro else 0
        falta_prov = es_cuadro and (costo_vig is None)

        if pct_exacto is not None:
            comision = round(precio * (pct_exacto / 100.0), 2)
        else:
            comision = 0.0

        if falta_prov:
            te_queda = None
        else:
            te_queda = round(precio - comision - (costo_vig or 0), 2)

        p["costo_proveedor"] = costo_vig if es_cuadro else None
        p["costo_a_mano"] = pid in con_a_mano
        p["pct_mp"] = pct_mp
        p["comision_mp"] = comision
        p["te_queda"] = te_queda

    for h in historial:
        h["fecha_local"] = _hora_local(h.get("fecha"))

    return {
        "productos": productos,
        "historial": historial,
        "resumen_mp": resumen_mp,
        "leido_vigilante": leido_vig,
    }


@app.post("/api/precios/{producto}")
async def api_cambiar_precio(producto: str, request: Request):
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(422, "JSON inválido")
    if not isinstance(datos, dict):
        raise HTTPException(422, "JSON inválido")
    return servidor.cambiar_precio_producto(producto, datos)


# ---------------- FECHAS ----------------
@app.get("/api/fechas")
def api_fechas():
    return servidor.obtener_fechas()


# ---------------- MERCADO LIBRE Y META (FASE 4) ----------------
@app.get("/api/ml-meta")
def api_ml_meta():
    return ml_meta.obtener_ml_meta_completo(forzar_ml=False)


@app.post("/api/ml-meta/actualizar")
def api_ml_meta_actualizar():
    return ml_meta.obtener_ml_meta_completo(forzar_ml=True)



# ---------------- ESTÁTICOS Y FRONTEND ----------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"mensaje": "Centralita tutienditaia"}
