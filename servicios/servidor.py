"""Llamadas al servidor de la tienda desde la centralita (usa pedidos.cliente()).

Nunca expone el token en logs, respuestas ni excepciones.
"""
import logging
import pathlib
import sys
from typing import Any

import httpx
from urllib.parse import quote
from fastapi import HTTPException

# Agregar rutas para importar pedidos.py
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tienda" / "herramientas"))
import pedidos  # noqa: E402

log = logging.getLogger("centralita.servidor")


def _cliente() -> httpx.Client:
    return pedidos.cliente()


def obtener_pedidos(estado: str | None = None) -> list[dict[str, Any]]:
    """Trae la lista de pedidos desde GET /admin/pedidos."""
    try:
        with _cliente() as c:
            params = {"estado": estado} if estado else {}
            r = c.get("/admin/pedidos", params=params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.error("Error al obtener pedidos del servidor: %s", e.response.status_code)
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        log.error("No se pudo conectar con el servidor: %s", e)
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def obtener_pedido(pid: str) -> dict[str, Any]:
    """Trae el detalle de un pedido desde GET /admin/pedidos/{pid}."""
    try:
        with _cliente() as c:
            r = c.get(f"/admin/pedidos/{pid.upper()}")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def actualizar_contacto(pid: str, email: str | None = None, whatsapp: str | None = None) -> dict[str, Any]:
    """Actualiza email y/o whatsapp en el servidor vía PATCH /admin/pedidos/{pid}/contacto."""
    cuerpo = {}
    if email is not None:
        cuerpo["email"] = email
    if whatsapp is not None:
        cuerpo["whatsapp"] = whatsapp
    try:
        with _cliente() as c:
            r = c.patch(f"/admin/pedidos/{pid.upper()}/contacto", json=cuerpo)
            if r.status_code in (400, 422, 404, 409):
                raise HTTPException(r.status_code, r.json())
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def reenviar(pid: str, que: str) -> dict[str, Any]:
    """Reenvía el último mail y aviso vía POST /admin/pedidos/{pid}/reenviar."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/pedidos/{pid.upper()}/reenviar", json={"que": que})
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def pedir_cambio(pid: str, texto: str, sin_costo: bool = True) -> dict[str, Any]:
    """Pide un cambio en nombre del cliente vía POST /admin/pedidos/{pid}/cambio."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/pedidos/{pid.upper()}/cambio", json={"texto": texto, "sin_costo": sin_costo})
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def dar_cambios_extra(pid: str, cantidad: int) -> dict[str, Any]:
    """Otorga cambios extra vía POST /admin/pedidos/{pid}/cambios-extra."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/pedidos/{pid.upper()}/cambios-extra", json={"cantidad": cantidad})
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def subir_vista_previa(pid: str, rutas_archivos: list[pathlib.Path], mensaje: str = "") -> dict[str, Any]:
    """Sube fotos de vista previa al servidor vía POST /admin/pedidos/{pid}/vista-previa."""
    abiertos = []
    try:
        for r in rutas_archivos:
            abiertos.append(("archivos", (r.name, open(r, "rb"), "image/jpeg")))
        with _cliente() as c:
            resp = c.post(f"/admin/pedidos/{pid.upper()}/vista-previa", files=abiertos,
                          data={"mensaje": mensaje}, timeout=300)
            if resp.status_code in (400, 404, 409, 422):
                raise HTTPException(resp.status_code, resp.json())
            resp.raise_for_status()
            return resp.json()
    finally:
        for _, (_, f, *_) in abiertos:
            f.close()


def salud() -> dict[str, Any]:
    """Consulta GET /salud del servidor."""
    try:
        with _cliente() as c:
            r = c.get("/salud", timeout=10)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def obtener_pagos(desde: str | None = None) -> list[dict[str, Any]]:
    """Trae la lista de pagos de Mercado Pago desde GET /admin/pagos."""
    try:
        with _cliente() as c:
            params = {"desde": desde} if desde else {}
            r = c.get("/admin/pagos", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.error("Error al obtener pagos del servidor: %s", e.response.status_code)
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        log.error("No se pudo conectar con el servidor para obtener pagos: %s", e)
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def obtener_costos() -> dict[str, Any]:
    """Trae productos y lecturas del vigilante desde GET /admin/costos."""
    try:
        with _cliente() as c:
            r = c.get("/admin/costos", timeout=30)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.error("Error al obtener costos del servidor: %s", e.response.status_code)
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        log.error("No se pudo conectar con el servidor para obtener costos: %s", e)
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def obtener_proveedores() -> dict[str, Any]:
    """Trae publicaciones, estado, historial y pendientes desde GET /admin/proveedores."""
    try:
        with _cliente() as c:
            r = c.get("/admin/proveedores", timeout=30)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.error("Error al obtener proveedores del servidor: %s", e.response.status_code)
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        log.error("No se pudo conectar con el servidor para obtener proveedores: %s", e)
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def fijar_precio_a_mano(nombre: str, precio: int) -> dict[str, Any]:
    """Carga un precio a mano para una publicación vía POST /admin/proveedores/{nombre}/precio."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/proveedores/{quote(nombre, safe='')}/precio", json={"precio": precio}, timeout=120)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def quitar_precio_a_mano(nombre: str) -> dict[str, Any]:
    """Quita el precio a mano vía DELETE /admin/proveedores/{nombre}/precio."""
    try:
        with _cliente() as c:
            r = c.delete(f"/admin/proveedores/{quote(nombre, safe='')}/precio", timeout=120)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def aprobar_pendiente(producto: str) -> dict[str, Any]:
    """Aprueba un cambio de más de 40% vía POST /admin/proveedores/pendientes/{producto}/aprobar."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/proveedores/pendientes/{quote(producto, safe='')}/aprobar", timeout=120)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def rechazar_pendiente(producto: str) -> dict[str, Any]:
    """Rechaza un cambio de más de 40% vía POST /admin/proveedores/pendientes/{producto}/rechazar."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/proveedores/pendientes/{quote(producto, safe='')}/rechazar", timeout=120)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def revisar_vigilante(prueba: bool = False) -> dict[str, Any]:
    """Ejecuta una revisión del vigilante vía POST /admin/vigilante."""
    try:
        with _cliente() as c:
            r = c.post("/admin/vigilante", params={"prueba": prueba}, timeout=120)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def enviar_seguimiento(pid: str, numero: str, url: str | None = None, empresa: str | None = None, reenviar: bool = False,
                       previa: bool = False) -> dict[str, Any]:
    """Envía el seguimiento del cuadro al cliente vía POST /admin/pedidos/{pid}/seguimiento."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/pedidos/{pid.upper()}/seguimiento", json={
                "numero": numero, "url": url, "empresa": empresa, "reenviar": reenviar, "previa": previa
            }, timeout=30)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def obtener_precios() -> dict[str, Any]:
    """Trae la lista de precios y su historial desde GET /admin/precios."""
    try:
        with _cliente() as c:
            r = c.get("/admin/precios")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def cambiar_precio_producto(producto: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Cambia el precio o modo de un producto vía POST /admin/precios/{producto}."""
    try:
        with _cliente() as c:
            r = c.post(f"/admin/precios/{quote(producto)}", json=datos)
            if r.status_code in (400, 404, 409, 422):
                try:
                    detalle = r.json()
                except Exception:
                    detalle = r.text
                raise HTTPException(r.status_code, detalle)
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")


def obtener_fechas() -> dict[str, Any]:
    """Trae las fechas importantes y comerciales desde GET /admin/fechas."""
    try:
        with _cliente() as c:
            r = c.get("/admin/fechas")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Error del servidor: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con el servidor: {e}")



