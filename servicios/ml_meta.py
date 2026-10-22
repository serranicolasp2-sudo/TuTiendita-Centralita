"""Servicio de integración de Mercado Libre y Meta para la Centralita.

Fase 4:
- Mercado Libre: publicaciones en vivo (precio, visitas, ventas, cargo, preguntas sin responder) con la API oficial.
- Meta: atribución de pedidos por campañas y piezas UTM, estado del píxel y conexión publicitaria.
"""
import concurrent.futures
import datetime
import logging
import pathlib
import re
import sys
import time
from typing import Any

AQUI = pathlib.Path(__file__).resolve().parent
CENTRALITA_DIR = AQUI.parent
TIENDA_DIR = CENTRALITA_DIR.parent / "tienda" / "herramientas"
sys.path.insert(0, str(TIENDA_DIR))

import httpx
import ml_api
from . import costos, servidor

log = logging.getLogger("centralita.ml_meta")

# Caché en memoria para evitar spam a la API de ML
_CACHE_ML: dict[str, Any] = {}
TTL_CACHE_ML = 300  # 5 minutos


def limpiar_cache_ml():
    global _CACHE_ML
    _CACHE_ML.clear()


def obtener_datos_ml(forzar: bool = False) -> dict[str, Any]:
    """Consulta la API de Mercado Libre con la app autorizada."""
    global _CACHE_ML

    ahora = time.time()
    if not forzar and _CACHE_ML.get("expira", 0) > ahora:
        return _CACHE_ML["datos"]

    try:
        tok = ml_api.token()
        headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
        me = ml_api.get("/users/me")
        uid = me["id"]
        nickname = me.get("nickname", "")
        permalink_vendedor = me.get("permalink", "")
    except Exception as e:
        log.warning("No se pudo autenticar con Mercado Libre: %s", e)
        return {
            "conectado": False,
            "error": str(e),
            "vendedor": None,
            "publicaciones": [],
            "resumen": {
                "total_publicaciones": 0,
                "activas": 0,
                "pausadas": 0,
                "visitas_7d_total": 0,
                "ventas_total": 0,
                "preguntas_pendientes_total": 0,
            },
            "preguntas": [],
            "fecha_lectura": None,
        }

    # 1. Obtener IDs de publicaciones
    try:
        r_items = httpx.get(
            f"{ml_api.API}/users/{uid}/items/search",
            headers=headers,
            params={"limit": 50},
            timeout=15,
        )
        item_ids = r_items.json().get("results", []) if r_items.status_code == 200 else []
    except Exception as e:
        log.warning("Error al buscar items de ML: %s", e)
        item_ids = []

    # 2. Consultar preguntas sin responder
    preguntas_map: dict[str, list[dict[str, Any]]] = {}
    preguntas_lista: list[dict[str, Any]] = []
    try:
        rq = httpx.get(
            f"{ml_api.API}/my/received_questions/search",
            headers=headers,
            params={"seller_id": uid, "status": "UNANSWERED", "limit": 50},
            timeout=15,
        )
        if rq.status_code == 200:
            for q in rq.json().get("questions", []):
                iid = q.get("item_id", "")
                preg_obj = {
                    "id": q.get("id"),
                    "item_id": iid,
                    "texto": q.get("text", ""),
                    "fecha": q.get("date_created", ""),
                }
                preguntas_lista.append(preg_obj)
                preguntas_map.setdefault(iid, []).append(preg_obj)
    except Exception as e:
        log.warning("Error al consultar preguntas de ML: %s", e)

    # 3. Detalle de cada publicación y visitas (concurrente)
    def procesar_un_item(iid: str) -> dict[str, Any] | None:
        try:
            ri = httpx.get(f"{ml_api.API}/items/{iid}", headers=headers, timeout=12)
            if ri.status_code != 200:
                return None
            item = ri.json()
            estado = item.get("status", "")
            precio = item.get("price") or 0
            sold = item.get("sold_quantity", 0)

            # Visitas últimos 7 días
            visitas_7d = 0
            try:
                rv = httpx.get(
                    f"{ml_api.API}/items/{iid}/visits/time_window",
                    headers=headers,
                    params={"last": 7, "unit": "day"},
                    timeout=8,
                )
                if rv.status_code == 200:
                    visitas_7d = rv.json().get("total_visits", 0)
            except Exception:
                pass

            # Cargo por venta estimado
            cat_id = item.get("category_id")
            cargo_texto = "sin dato"
            if cat_id and precio > 0:
                try:
                    cargos = costos.consultar_cargos_ml(precio, cat_id)
                    if cargos and "clasica" in cargos:
                        cargo_monto = cargos["clasica"].get("cargo")
                        if cargo_monto is not None:
                            cargo_texto = f"${cargo_monto:,.0f}".replace(",", ".")
                except Exception:
                    pass

            pregs_item = preguntas_map.get(iid, [])

            return {
                "id": iid,
                "titulo": item.get("title", ""),
                "permalink": item.get("permalink", f"https://articulo.mercadolibre.com.ar/{iid}"),
                "precio": precio,
                "estado": estado,
                "stock": item.get("available_quantity", 0),
                "ventas": sold,
                "visitas_7d": visitas_7d,
                "cargo_estimado": cargo_texto,
                "preguntas_sin_responder": len(pregs_item),
                "thumbnail": item.get("thumbnail"),
                "categoria_id": cat_id,
            }
        except Exception as e:
            log.warning("Error al procesar item %s: %s", iid, e)
            return None

    publicaciones = []
    visitas_totales = 0
    ventas_totales = 0
    activas_count = 0
    pausadas_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futuros = [executor.submit(procesar_un_item, iid) for iid in item_ids]
        for f in concurrent.futures.as_completed(futuros):
            res = f.result()
            if res:
                publicaciones.append(res)
                if res["estado"] == "active":
                    activas_count += 1
                elif res["estado"] == "paused":
                    pausadas_count += 1
                visitas_totales += res["visitas_7d"]
                ventas_totales += res["ventas"]

    # Ordenar: primero activas, luego por precio descendente
    publicaciones.sort(key=lambda x: (0 if x["estado"] == "active" else 1, -x["precio"]))

    ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    resultado = {
        "conectado": True,
        "vendedor": {
            "id": uid,
            "nickname": nickname,
            "permalink": permalink_vendedor,
        },
        "publicaciones": publicaciones,
        "resumen": {
            "total_publicaciones": len(publicaciones),
            "activas": activas_count,
            "pausadas": pausadas_count,
            "visitas_7d_total": visitas_totales,
            "ventas_total": ventas_totales,
            "preguntas_pendientes_total": len(preguntas_lista),
        },
        "preguntas": preguntas_lista,
        "fecha_lectura": ahora_iso,
    }

    _CACHE_ML = {
        "expira": ahora + TTL_CACHE_ML,
        "datos": resultado,
    }
    return resultado


def obtener_datos_meta(pedidos_lista: list[dict[str, Any]], pagos_lista: list[dict[str, Any]]) -> dict[str, Any]:
    """Evalúa la configuración de Meta (Pixel, UTMs de campañas y ventas atribuidas)."""
    # 1. Estado del Pixel en tienda.js
    pixel_id = None
    pixel_configurado = False
    tienda_js_path = CENTRALITA_DIR.parent / "tienda" / "web" / "tienda.js"
    if tienda_js_path.is_file():
        try:
            contenido = tienda_js_path.read_text(encoding="utf-8")
            m = re.search(r'var\s+pixelId\s*=\s*window\.META_PIXEL_ID\s*\|\|\s*["\'](\d+)["\']', contenido)
            if m:
                pixel_id = m.group(1)
                pixel_configurado = True
        except Exception as e:
            log.warning("No se pudo leer tienda.js para verificar el píxel: %s", e)

    # 2. Mapear pagos aprobados por ID de pedido
    pagos_aprobados: dict[str, float] = {}
    for pg in pagos_lista:
        pid = pg.get("pedido_id")
        estado = pg.get("status") or pg.get("estado")
        if pid and estado == "approved":
            neto = pg.get("transaction_details", {}).get("net_received_amount")
            monto = neto if neto is not None else pg.get("transaction_amount", 0)
            pagos_aprobados[pid] = pagos_aprobados.get(pid, 0.0) + float(monto)

    # 3. Atribución de pedidos por UTMs
    campanas_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_pedidos_atribuidos = 0
    total_cobrado_atribuido = 0.0

    for p in pedidos_lista:
        pid = p.get("id")
        datos = p.get("datos") or {}
        origen = datos.get("origen") if isinstance(datos, dict) else None
        if not origen and isinstance(p.get("origen"), dict):
            origen = p["origen"]

        if not origen:
            continue

        src = (origen.get("source") or "").strip().lower()
        med = (origen.get("medium") or "").strip().lower()
        cam = (origen.get("campaign") or "").strip()
        cnt = (origen.get("content") or "").strip()

        # Filtrar orígenes relacionados a Meta / redes / anuncios o con campaña definida
        es_meta = any(k in src for k in ("meta", "facebook", "fb", "ig", "instagram")) or bool(cam or cnt)
        if not es_meta:
            continue

        clave = (cam or "Sin campaña", cnt or "Sin especificar", f"{src}/{med}" if (src or med) else "Directo")
        if clave not in campanas_map:
            campanas_map[clave] = {
                "campana": clave[0],
                "pieza": clave[1],
                "fuente_medio": clave[2],
                "pedidos": 0,
                "cobrado": 0.0,
                "pedidos_ids": [],
            }

        campanas_map[clave]["pedidos"] += 1
        campanas_map[clave]["pedidos_ids"].append(pid)
        total_pedidos_atribuidos += 1

        cobrado_pedido = pagos_aprobados.get(pid, 0.0)
        campanas_map[clave]["cobrado"] += cobrado_pedido
        total_cobrado_atribuido += cobrado_pedido

    filas_campanas = list(campanas_map.values())
    filas_campanas.sort(key=lambda x: -x["pedidos"])

    return {
        "pixel": {
            "activo": pixel_configurado,
            "id_mascarado": f"***{pixel_id[-4:]}" if (pixel_id and len(pixel_id) >= 4) else (pixel_id or None),
            "estado": "Activo y reportando eventos" if pixel_configurado else "Pendiente (a la espera del ID del usuario)",
        },
        "cuenta_publicitaria": {
            "conectada": False,
            "estado": "Desconectada (sin cuenta de Meta Ads)",
            "mensaje": "El gasto y costo por venta (ROAS) requieren conectar la cuenta publicitaria en una etapa posterior.",
        },
        "campanas": filas_campanas,
        "resumen": {
            "total_pedidos_atribuidos": total_pedidos_atribuidos,
            "total_cobrado_atribuido": round(total_cobrado_atribuido, 2),
            "campanas_activas": len(set(c["campana"] for c in filas_campanas)),
        },
    }


def obtener_ml_meta_completo(forzar_ml: bool = False) -> dict[str, Any]:
    """Combina los datos de Mercado Libre y Meta para la vista de Centralita."""
    datos_ml = obtener_datos_ml(forzar=forzar_ml)
    try:
        pedidos_lista = servidor.obtener_pedidos()
        pagos_lista = servidor.obtener_pagos()
    except Exception as e:
        log.warning("No se pudieron obtener pedidos/pagos para Meta: %s", e)
        pedidos_lista, pagos_lista = [], []

    datos_meta = obtener_datos_meta(pedidos_lista, pagos_lista)

    return {
        "ml": datos_ml,
        "meta": datos_meta,
    }
