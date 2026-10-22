"""Servicio de cálculo de costos, comisiones reales y simulaciones para Centralita.

Solo datos reales:
- Mercado Pago (de /admin/pagos)
- Mercado Libre (de la API listing_prices con token de ML)
- Costos de cuadros cargados a mano (C:\\Pedidos\\costos-proveedor.json)
- Precios publicados hoy leídos por el vigilante (de /admin/costos)
"""
import datetime
import json
import logging
import math
import os
import pathlib
import sys
from typing import Any

AQUI = pathlib.Path(__file__).resolve().parent
CENTRALITA_DIR = AQUI.parent
TIENDA_DIR = CENTRALITA_DIR.parent / "tienda" / "herramientas"
sys.path.insert(0, str(TIENDA_DIR))
sys.path.insert(0, str(CENTRALITA_DIR.parent / "produccion"))

import carpetas  # noqa: E402
import ml_api  # noqa: E402

log = logging.getLogger("centralita.costos")

DATOS_DIR = CENTRALITA_DIR / "datos"
CACHE_ML_RUTA = DATOS_DIR / "ml-cargos.json"
CATEGORIAS_RUTA = CENTRALITA_DIR / "categorias-ml.json"


def ruta_costos_proveedor() -> pathlib.Path:
    return carpetas.PEDIDOS / "costos-proveedor.json"


# ---------------- COSTOS PROVEEDOR (C:\Pedidos\costos-proveedor.json) ----------------
def leer_costos_proveedor() -> dict[str, dict[str, Any]]:
    ruta = ruta_costos_proveedor()
    if not ruta.is_file():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("No se pudo leer costos-proveedor.json: %s", e)
        return {}


def guardar_costo_proveedor(pid: str, pagado: int) -> tuple[int | None, int]:
    """Guarda atómicamente el monto pagado por el cuadro.

    Devuelve (monto_anterior, monto_nuevo).
    """
    ruta = ruta_costos_proveedor()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = leer_costos_proveedor()
    pid_norm = pid.upper()
    anterior = None
    if pid_norm in datos and isinstance(datos[pid_norm], dict):
        anterior = datos[pid_norm].get("pagado")

    ahora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    datos[pid_norm] = {
        "pagado": int(pagado),
        "fecha": ahora_iso,
        "fuente": "cargado a mano",
    }

    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ruta)
    return anterior, int(pagado)


# ---------------- CATEGORÍAS ML ----------------
def leer_categorias_ml() -> dict[str, str | None]:
    if not CATEGORIAS_RUTA.is_file():
        return {}
    try:
        return json.loads(CATEGORIAS_RUTA.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("No se pudo leer categorias-ml.json: %s", e)
        return {}


# ---------------- CACHÉ DE MERCADO LIBRE ----------------
def leer_cache_ml() -> dict[str, Any]:
    if not CACHE_ML_RUTA.is_file():
        return {}
    try:
        return json.loads(CACHE_ML_RUTA.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("No se pudo leer cache ML: %s", e)
        return {}


def guardar_cache_ml(cache: dict[str, Any]):
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_ML_RUTA.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CACHE_ML_RUTA)


def borrar_cache_ml():
    if CACHE_ML_RUTA.is_file():
        try:
            CACHE_ML_RUTA.unlink()
        except Exception as e:
            log.warning("No se pudo borrar cache ML: %s", e)


def consultar_cargos_ml(precio: int, categoria: str | None, forzar: bool = False) -> dict[str, Any] | None:
    if not categoria:
        return None
    clave = f"{int(precio)}|{categoria}"
    cache = leer_cache_ml()

    # Lo que se devuelve lleva "leido" (fecha de la consulta a ML): cada cifra se muestra con su fuente y fecha
    if not forzar and clave in cache:
        entrada = cache[clave]
        leido_str = entrada.get("leido")
        if leido_str:
            try:
                leido_dt = datetime.datetime.fromisoformat(leido_str)
                if (datetime.datetime.now(datetime.timezone.utc) - leido_dt).total_seconds() < 24 * 3600:
                    return {**(entrada.get("cargos") or {}), "leido": leido_str}
            except Exception:
                pass

    try:
        resp = ml_api.get("/sites/MLA/listing_prices", price=precio, category_id=categoria)
        cargos = parsear_listing_prices(resp)
        if not cargos:
            return None
        leido = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cache[clave] = {"cargos": cargos, "leido": leido}
        guardar_cache_ml(cache)
        return {**cargos, "leido": leido}
    except Exception as e:
        log.warning("Error consultando ML listing_prices para %s: %s", clave, e)
        # Si ML no responde y hay una lectura vieja, se usa marcada como vieja (con su fecha)
        if clave in cache and cache[clave].get("cargos"):
            return {**cache[clave]["cargos"], "leido": cache[clave].get("leido"), "vieja": True}
        return None


def parsear_listing_prices(lista_precios: list[dict[str, Any]]) -> dict[str, Any]:
    """Extrae gold_special (Clásica) y gold_pro (Premium)."""
    resultado: dict[str, Any] = {}
    if not isinstance(lista_precios, list):
        return resultado

    for item in lista_precios:
        tipo = item.get("listing_type_id")
        if tipo in ("gold_special", "gold_pro"):
            nombre = "clasica" if tipo == "gold_special" else "premium"
            total = float(item.get("sale_fee_amount") or 0.0)
            detalles = item.get("sale_fee_details") or {}
            porcentaje = float(detalles.get("percentage_fee") or 0.0)
            fijo = float(detalles.get("fixed_fee") or 0.0)
            financiacion = float(detalles.get("financing_add_on_fee") or 0.0)
            resultado[nombre] = {
                "total": total,
                "porcentaje": porcentaje,
                "fijo": fijo,
                "financiacion": financiacion,
            }
    return resultado


# ---------------- CÁLCULO DE PRECIO PARA PUBLICAR EN ML ----------------
def calcular_precio_publicar_ml(
    precio_web: int,
    categoria: str | None,
    pct_dinero_cuenta: float | None,
    forzar: bool = False,
) -> dict[str, Any]:
    """Calcula a cuánto publicar en ML para que te quede lo mismo que en la web."""
    if pct_dinero_cuenta is None:
        return {
            "clasica": None,
            "premium": None,
            "motivo": "sin dato: hace falta un cobro real por la web",
        }
    if not categoria:
        return {
            "clasica": None,
            "premium": None,
            "motivo": "sin dato: falta la categoría de ML",
        }

    # Lo que queda en la web antes de proveedor (el proveedor es idéntico en ambos). pct_dinero_cuenta llega sin
    # redondear (comisiones / montos de los cobros reales).
    queda_web = float(precio_web) * (1.0 - (pct_dinero_cuenta / 100.0))

    start = precio_web if precio_web % 1000 == 900 else (precio_web // 1000) * 1000 + 900
    if start < precio_web:
        start += 1000
    tope = precio_web * 3

    res_clasica = None
    cargo_clasica = None
    res_premium = None
    cargo_premium = None

    p = start
    while p <= tope and (res_clasica is None or res_premium is None):
        cargos = consultar_cargos_ml(p, categoria, forzar=forzar)
        if not cargos:      # ML no responde: no se sigue probando precios (serían decenas de consultas fallidas)
            return {"clasica": None, "premium": None, "motivo": "sin dato: no pude consultar la API de ML"}
        if cargos:
            if res_clasica is None and "clasica" in cargos:
                tot_c = cargos["clasica"]["total"]
                if (p - tot_c) >= queda_web:
                    res_clasica = p
                    cargo_clasica = cargos["clasica"]

            if res_premium is None and "premium" in cargos:
                tot_p = cargos["premium"]["total"]
                if (p - tot_p) >= queda_web:
                    res_premium = p
                    cargo_premium = cargos["premium"]
        p += 1000

    return {
        "clasica": {
            "precio_igual_web": res_clasica,
            "cargo": cargo_clasica,
        } if res_clasica else None,
        "premium": {
            "precio_igual_web": res_premium,
            "cargo": cargo_premium,
        } if res_premium else None,
        "motivo": None if (res_clasica and res_premium) else "No se encontró precio dentro del límite (3x)",
    }


# ---------------- ESTADÍSTICAS DE MERCADO PAGO ----------------
def parsear_fecha_iso(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    try:
        # Formatos comunes ISO
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def agrupar_pagos_por_medio(pagos: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa pagos cobrados por tipo_medio para calcular estadísticas reales."""
    grupos: dict[str, dict[str, Any]] = {}
    total_cobrado = 0.0
    total_comisiones = 0.0
    fechas: list[datetime.datetime] = []

    incluidos = 0
    for p in pagos:
        # Solo cobros aprobados y leídos bien: un reembolso o un error de MP distorsionaría el % real
        if p.get("error") or p.get("estado") != "approved" or float(p.get("reembolsado") or 0) > 0:
            continue
        incluidos += 1
        monto = float(p.get("monto") or 0.0)
        comis_lista = p.get("comisiones") or []
        comision = sum(float(c.get("monto") or 0.0) for c in comis_lista)

        tipo_raw = p.get("tipo_medio") or p.get("medio") or "otro"
        cuotas = int(p.get("cuotas") or 1)

        # Agrupar según descripción amigable
        if tipo_raw == "account_money":
            clave = "account_money"
            nombre = "Dinero en cuenta"
        elif tipo_raw in ("debit_card", "debit"):
            clave = "debit_card"
            nombre = "Tarjeta de débito"
        elif tipo_raw in ("credit_card", "credit"):
            if cuotas <= 1:
                clave = "credit_card_1"
                nombre = "Crédito en 1 cuota"
            else:
                clave = "credit_card_n"
                nombre = f"Crédito en cuotas"
        elif tipo_raw in ("ticket", "atm"):
            clave = "ticket"
            nombre = "Efectivo"
        else:
            clave = tipo_raw
            nombre = tipo_raw.replace("_", " ").capitalize()

        dias_lib = None
        aprobado_dt = parsear_fecha_iso(p.get("aprobado"))
        libera_dt = parsear_fecha_iso((p.get("liberacion") or {}).get("fecha"))
        if aprobado_dt:
            fechas.append(aprobado_dt)
        if aprobado_dt and libera_dt:
            delta = (libera_dt - aprobado_dt).total_seconds() / 86400.0
            if delta >= 0:
                dias_lib = round(delta, 1)

        if clave not in grupos:
            grupos[clave] = {
                "clave": clave,
                "nombre": nombre,
                "cantidad": 0,
                "monto": 0.0,
                "comisiones": 0.0,
                "dias_liberacion": [],
            }

        grupos[clave]["cantidad"] += 1
        grupos[clave]["monto"] += monto
        grupos[clave]["comisiones"] += comision
        if dias_lib is not None:
            grupos[clave]["dias_liberacion"].append(dias_lib)

        total_cobrado += monto
        total_comisiones += comision

    # Calcular promedios y porcentajes reales por grupo
    grupos_resultado = []
    pct_dinero_cuenta = None

    for g in grupos.values():
        m = g["monto"]
        c = g["comisiones"]
        exacto = (c / m) * 100.0 if m > 0 else None
        pct = round(exacto, 2) if exacto is not None else None
        dias_lista = g["dias_liberacion"]
        dias_prom = round(sum(dias_lista) / len(dias_lista)) if dias_lista else None

        item = {
            "clave": g["clave"],
            "nombre": g["nombre"],
            "cantidad": g["cantidad"],
            "monto": round(m, 2),
            "comisiones": round(c, 2),
            "porcentaje_real": pct,
            "porcentaje_exacto": exacto,
            "dias_promedio": dias_prom,
        }
        grupos_resultado.append(item)
        if g["clave"] == "account_money":
            pct_dinero_cuenta = exacto

    # Rango de fechas
    rango_texto = ""
    if fechas:
        fechas.sort()
        f_min = fechas[0].strftime("%d/%m")
        f_max = fechas[-1].strftime("%d/%m")
        rango_texto = f"tus {incluidos} pagos, del {f_min} al {f_max}"

    return {
        "grupos": grupos_resultado,
        "porcentaje_dinero_cuenta": pct_dinero_cuenta,
        "total_cobrado": round(total_cobrado, 2),
        "total_comisiones": round(total_comisiones, 2),
        "porcentaje_total": round((total_comisiones / total_cobrado) * 100.0, 2) if total_cobrado > 0 else 0.0,
        "fuente": rango_texto,
    }
