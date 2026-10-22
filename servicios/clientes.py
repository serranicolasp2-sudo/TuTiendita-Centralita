"""Servicio de agrupación y métricas de clientes para la centralita.

Agrupa pedidos aprobados/pagados/entregados por email o WhatsApp normalizado.
Calcula totales reales de cobros (o 'sin dato' si falta alguno).
"""
from typing import Any


def normalizar_wa(wa: str | None) -> str:
    """Deja el número en formato internacional argentino sin signos ni espacios."""
    d = "".join(c for c in str(wa or "") if c.isdigit())
    if d.startswith("549"):
        return d
    if d.startswith("54"):
        d = d[2:]
    if d.startswith("0"):
        d = d[1:]
    for area in (4, 3, 2):
        if len(d) == area + 2 + (10 - area) and d[area:area + 2] == "15":
            d = d[:area] + d[area + 2:]
            break
    return "549" + d if len(d) == 10 else d


def agrupar_clientes(pedidos: list[dict[str, Any]], pagos: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa pedidos válidos por email o WhatsApp.
    
    Excluye pedidos en 'pendiente_pago' o 'cancelado'.
    Calcula total_cobrado real a partir de los pagos (debe ser aprobado y completo, sino 'sin dato').
    """
    # 1. Filtrar pedidos válidos
    validos = [p for p in pedidos if p.get("estado") not in ("pendiente_pago", "cancelado")]
    if not validos:
        return {"clientes": [], "volvieron_count": 0, "total_clientes": 0}

    # 2. Indexar pagos por external_reference (pid)
    # Soporta formato de GET /admin/pagos (donde viene 'external_reference', 'monto' o 'transaction_amount', 'estado' o 'status')
    pagos_por_pid: dict[str, dict[str, Any]] = {}
    for pg in pagos:
        pid = pg.get("external_reference") or pg.get("pedido")
        if pid:
            pagos_por_pid[str(pid).upper()] = pg

    # 3. Grafo de pedidos conectados por mismo mail o mismo WhatsApp
    n = len(validos)
    email_to_indices: dict[str, list[int]] = {}
    wa_to_indices: dict[str, list[int]] = {}
    adj: dict[int, set[int]] = {i: set() for i in range(n)}

    for i, p in enumerate(validos):
        e = (p.get("email") or "").strip().lower()
        w = normalizar_wa(p.get("whatsapp"))
        if e:
            email_to_indices.setdefault(e, []).append(i)
        if w:
            wa_to_indices.setdefault(w, []).append(i)

    for indices in email_to_indices.values():
        for k in range(len(indices) - 1):
            adj[indices[k]].add(indices[k + 1])
            adj[indices[k + 1]].add(indices[k])

    for indices in wa_to_indices.values():
        for k in range(len(indices) - 1):
            adj[indices[k]].add(indices[k + 1])
            adj[indices[k + 1]].add(indices[k])

    # 4. Encontrar componentes conectados
    visitados = set()
    componentes = []
    for i in range(n):
        if i not in visitados:
            comp = []
            cola = [i]
            visitados.add(i)
            while cola:
                curr = cola.pop(0)
                comp.append(curr)
                for vecino in adj[curr]:
                    if vecino not in visitados:
                        visitados.add(vecino)
                        cola.append(vecino)
            componentes.append(comp)

    # 5. Construir registros de clientes
    clientes = []
    for comp in componentes:
        ords = sorted([validos[idx] for idx in comp], key=lambda x: str(x.get("creado") or ""))
        ultimo = ords[-1]
        primero = ords[0]

        marcas = []
        if any(o.get("marca") == "rf" or str(o.get("producto") or "").startswith("rf-") for o in ords):
            marcas.append("fotos")
        if any(o.get("marca") == "tc" or str(o.get("producto") or "").startswith("tc-") for o in ords):
            marcas.append("canción")

        # Total cobrado real
        total_valido = True
        suma_cobrada = 0.0
        for o in ords:
            pid = str(o.get("id") or "").upper()
            pg = pagos_por_pid.get(pid)
            if not pg:
                total_valido = False
                break
            if pg.get("error"):
                total_valido = False
                break
            estado_pago = pg.get("status") or pg.get("estado")
            if estado_pago != "approved":
                total_valido = False
                break
            reembolsado = pg.get("transaction_amount_refunded") or pg.get("reembolsado") or 0
            if reembolsado > 0:
                total_valido = False
                break
            monto = pg.get("transaction_amount") if pg.get("transaction_amount") is not None else pg.get("monto")
            if monto is None:
                total_valido = False
                break
            suma_cobrada += float(monto)

        total_cobrado = round(suma_cobrada) if total_valido else "sin dato"

        pedidos_res = []
        for o in ords:
            pedidos_res.append({
                "id": o.get("id"),
                "creado": o.get("creado"),
                "producto": o.get("producto"),
                "precio": o.get("precio"),
                "estado": o.get("estado")
            })

        clientes.append({
            "nombre": ultimo.get("nombre") or primero.get("nombre") or "Sin nombre",
            "email": ultimo.get("email") or primero.get("email") or "",
            "whatsapp": ultimo.get("whatsapp") or primero.get("whatsapp") or "",
            "pedidos_count": len(ords),
            "marcas": marcas,
            "total_cobrado": total_cobrado,
            "primer_pedido": primero.get("creado"),
            "ultimo_pedido": ultimo.get("creado"),
            "pedidos": pedidos_res
        })

    # Ordenar clientes por último pedido descendente
    clientes.sort(key=lambda c: str(c.get("ultimo_pedido") or ""), reverse=True)
    volvieron = sum(1 for c in clientes if c["pedidos_count"] > 1)

    return {
        "clientes": clientes,
        "volvieron_count": volvieron,
        "total_clientes": len(clientes)
    }
