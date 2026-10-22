(function () {
  "use strict";

  const ICONO_CARPETA = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3.6l1.8 2h6.6a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5z"/></svg>';

  // Formateadores
  const pesos = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 });
  function $(n) { return pesos.format(Math.round(n || 0)); }
  function coma(n) { return String(n).replace(".", ","); }
  function dosDig(n) { return ("0" + n).slice(-2); }
  function fecha(t) {
    if (!t) return "";
    const d = new Date(t);
    return dosDig(d.getDate()) + "/" + dosDig(d.getMonth() + 1);
  }
  function hora(t) {
    if (!t) return "";
    const d = new Date(t);
    return fecha(t) + " " + dosDig(d.getHours()) + ":" + dosDig(d.getMinutes());
  }
  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Gráfico chispa SVG para historial de precios
  function chispa(historial) {
    const valores = (historial || []).map(h => typeof h === "object" ? h.precio : h).filter(v => typeof v === "number" && !isNaN(v));
    const w = 96, h = 26;
    if (!valores.length) {
      return `<svg class="chispa" viewBox="0 0 ${w} ${h}" role="img" aria-label="Sin lecturas"><line x1="2" y1="${h/2}" x2="${w-2}" y2="${h/2}" stroke="var(--linea)" stroke-dasharray="3,3" stroke-width="1.6"/><circle cx="${w/2}" cy="${h/2}" r="2.6" fill="var(--tinta-2)"/></svg>`;
    }
    if (valores.length === 1) {
      return `<svg class="chispa" viewBox="0 0 ${w} ${h}" role="img" aria-label="Precio: ${$(valores[0])}"><line x1="2" y1="${h/2}" x2="${w-2}" y2="${h/2}" stroke="var(--birome)" stroke-dasharray="2,2" stroke-width="1.6"/><circle cx="${w-4}" cy="${h/2}" r="2.6" fill="var(--malvon)"/></svg>`;
    }
    const min = Math.min(...valores);
    const max = Math.max(...valores);
    const rango = max - min || 1;
    const pts = valores.map((v, i) => [
      2 + i * (w - 4) / (valores.length - 1),
      h - 3 - (v - min) / rango * (h - 6)
    ]);
    const ult = pts[pts.length - 1];
    return `<svg class="chispa" viewBox="0 0 ${w} ${h}" role="img" aria-label="De ${$(valores[0])} a ${$(valores[valores.length - 1])}"><polyline points="${pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ')}"/><circle cx="${ult[0].toFixed(1)}" cy="${ult[1].toFixed(1)}" r="2.6"/></svg>`;
  }

  // Sugerencia de mails (misma lista y regla que tienda.js)
  const DOMINIOS = ["gmail.com", "hotmail.com", "hotmail.com.ar", "hotmail.es", "outlook.com", "outlook.com.ar", "outlook.es",
    "yahoo.com", "yahoo.com.ar", "yahoo.es", "live.com", "live.com.ar", "icloud.com", "me.com", "msn.com", "fibertel.com.ar",
    "speedy.com.ar", "arnet.com.ar", "protonmail.com", "proton.me", "mail.com", "ymail.com"];
  function distancia(a, b) {
    const d = [];
    for (let i = 0; i <= a.length; i++) d[i] = [i];
    for (let j = 0; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
    }
    return d[a.length][b.length];
  }
  function sugerirMail(mail) {
    const at = mail.lastIndexOf("@");
    if (at < 1) return "";
    const u = mail.slice(0, at), dom = mail.slice(at + 1).toLowerCase();
    if (DOMINIOS.includes(dom)) return "";
    let mejor = "", menor = 99;
    DOMINIOS.forEach(x => {
      const n = distancia(dom, x);
      if (n < menor) { menor = n; mejor = x; }
    });
    return menor <= (mejor.length <= 7 ? 1 : 2) ? u + "@" + mejor : "";
  }

  // Tostadas
  function tostada(texto) {
    const t = document.createElement("div");
    t.className = "tostada";
    t.textContent = texto;
    document.getElementById("tostadas").appendChild(t);
    setTimeout(() => { t.remove(); }, 4600);
  }

  // Cliente API
  async function api(ruta, opciones = {}) {
    const opts = { ...opciones };
    opts.headers = {
      "X-Centralita": "1",
      ...(opts.headers || {})
    };
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(ruta, opts);
    if (!res.ok) {
      let errTxt = "Error en la operación";
      const crudo = await res.text();
      try {
        const js = JSON.parse(crudo);
        let d = js.detail !== undefined ? js.detail : js;
        if (typeof d === "string") {          // el error del servidor puede venir como texto con JSON adentro
          const m = d.match(/^Error del servidor: (\{.*\})$/s);
          if (m) { try { d = JSON.parse(m[1]); } catch (e2) { /* queda el texto */ } }
        }
        if (d && typeof d === "object") d = d.error || d.detail || JSON.stringify(d);
        errTxt = String(d);
      } catch (e) {
        errTxt = crudo || errTxt;
      }
      throw new Error(errTxt);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  // Estado global
  let vista = "hoy";
  let filtroTipo = "todos";
  let busqueda = "";
  let filtroPlataMes = "todos";
  let filtroPlataMarca = "todas";
  let simuladorEstado = { producto: "", categoria: "", precio: "", resultado: null };
  let pedidoAbiertoId = null;
  let fichaDatos = null;
  let pestanaFicha = "resumen";

  // Pestañas de archivos
  let abiertos = []; // [{ pid, ruta, nombre, tipo, accion, editable, texto, sucio, cerrando, aviso, original_comparar }]
  let activoIndex = -1; // -1 = vista normal

  const elPrincipal = document.getElementById("principal");
  const elBarraAbiertos = document.getElementById("abiertos");
  const elCuentaHoy = document.getElementById("cuenta-hoy");

  // Navegación
  document.querySelectorAll(".nav button[data-vista]").forEach(b => {
    b.addEventListener("click", () => {
      if (b.disabled) return;
      irVista(b.dataset.vista);
    });
  });

  function irVista(v) {
    vista = v;
    pedidoAbiertoId = null;
    fichaDatos = null;
    activoIndex = -1;
    document.querySelectorAll(".nav button[data-vista]").forEach(b => {
      b.setAttribute("aria-current", b.dataset.vista === v ? "page" : "false");
    });
    render();
  }

  function chipHtml(p) {
    const esRf = p.tipo === "RF" || (p.id && p.id.startsWith("RF"));
    return `<span class="chip ${esRf ? 'rf' : 'tc'}">${esRf ? 'Lado B · Fotos' : 'Lado A · Canción'}</span>`;
  }

  function mencionArchivo(pid, ruta, texto = null) {
    const nombre = ruta.split("/").pop();
    const txt = texto || nombre;
    return `<span class="archivo">` +
      `<button type="button" class="abrir-a" data-abrir-archivo="${esc(pid)}|${esc(ruta)}" title="Abrir en pestaña">${esc(txt)}</button>` +
      `<button type="button" class="en-carpeta" data-mostrar-carpeta="${esc(pid)}|${esc(ruta)}" title="Mostrar en la carpeta" aria-label="Mostrar en carpeta">${ICONO_CARPETA}</button>` +
      `</span>`;
  }

  function enlazarTexto(pid, texto) {
    if (!texto) return "";
    return esc(texto).replace(/((?:[\w-]+\\)*[\w-]+\.(?:txt|mp3|wav|mp4|json|jpg|jpeg|png|webp))/g, (m, archivo) => {
      const ruta = archivo.replace(/\\/g, "/");
      return mencionArchivo(pid, ruta, m);
    });
  }

  // Render principal
  async function render() {
    renderAbiertos();
    if (activoIndex >= 0 && abiertos[activoIndex]) {
      renderVisor(abiertos[activoIndex]);
      return;
    }
    if (pedidoAbiertoId) {
      renderFicha();
      return;
    }

    if (vista === "hoy") await renderHoy();
    else if (vista === "pedidos") await renderPedidos();
    else if (vista === "plata") await renderPlata();
    else if (vista === "costos") await renderCostos();
    else if (vista === "precios") await renderPrecios();
    else if (vista === "proveedores") await renderProveedores();
    else if (vista === "clientes") await renderClientes();
    else if (vista === "fechas") await renderFechas();
    else if (vista === "sistema") await renderSistema();
    else if (vista === "ml-meta") await renderMLMeta();
  }

  // Pestañas de archivos abiertos
  function renderAbiertos() {
    elBarraAbiertos.hidden = !abiertos.length;
    if (!abiertos.length) return;

    const baseNombre = pedidoAbiertoId ? pedidoAbiertoId : { hoy: "Para hacer hoy", pedidos: "Pedidos", plata: "Cobros y comisiones", costos: "Costos por venta", precios: "Precios", proveedores: "Proveedores", clientes: "Clientes", fechas: "Recordatorios", sistema: "Estado del sistema", "ml-meta": "Mercado Libre y Meta" }[vista] || "Tablero";
    let html = `<div class="pest" aria-selected="${activoIndex < 0}">` +
      `<button type="button" role="tab" data-tab-idx="-1">${esc(baseNombre)}</button></div>`;

    abiertos.forEach((t, i) => {
      const sel = activoIndex === i;
      html += `<div class="pest" aria-selected="${sel}">` +
        `<button type="button" role="tab" data-tab-idx="${i}">` +
        (t.sucio ? '<span class="sucio" aria-label="sin guardar"></span>' : "") +
        `${esc(t.nombre)} <span class="pid">${esc(t.pid)}</span></button>` +
        `<button type="button" class="cerrar" data-cerrar-idx="${i}" aria-label="Cerrar">×</button>` +
        `</div>`;
    });

    elBarraAbiertos.innerHTML = html;
  }

  elBarraAbiertos.addEventListener("click", e => {
    const btnTab = e.target.closest("[data-tab-idx]");
    if (btnTab) {
      activoIndex = parseInt(btnTab.dataset.tabIdx, 10);
      render();
      return;
    }
    const btnCerrar = e.target.closest("[data-cerrar-idx]");
    if (btnCerrar) {
      cerrarArchivo(parseInt(btnCerrar.dataset.cerrarIdx, 10));
    }
  });

  async function abrirArchivo(pid, ruta) {
    const clave = `${pid}|${ruta}`;
    const i = abiertos.findIndex(x => x.pid === pid && x.ruta === ruta);
    if (i >= 0) {
      activoIndex = i;
      render();
      return;
    }

    try {
      // Primero la clasificación (tipo, si es editable, con qué comparar); después el contenido según el tipo
      const archivos = await api(`/api/pedidos/${pid}/archivos`);
      const c = archivos.find(a => a.ruta === ruta);
      if (!c) throw new Error(`No existe ${ruta} en el pedido`);
      const nuevo = {
        pid,
        ruta,
        nombre: ruta.split("/").pop(),
        tipo: c.tipo,
        contenido: null,
        url: null,
        urlOriginal: null,
        texto: null,
        sucio: false,
        cerrando: false,
        aviso: null,
        editable: c.editable || false,
        accion: c.accion || "",
        info: c.info || "",
        original_comparar: c.original_comparar || null,
        retocable: !!c.retocable
      };

      if (MEDIOS.includes(c.tipo)) {
        nuevo.url = await urlDeArchivo(pid, ruta);
      } else if (c.tipo === "desconocido") {
        nuevo.contenido = "";
      } else {
        const resp = await api(`/api/pedidos/${pid}/archivo?ruta=${encodeURIComponent(ruta)}`);
        nuevo.tipo = resp.tipo || "texto";
        nuevo.contenido = resp.contenido;
      }

      abiertos.push(nuevo);
      activoIndex = abiertos.length - 1;
      render();
    } catch (err) {
      tostada("Error al abrir archivo: " + err.message);
    }
  }

  // Imágenes, audios y videos: <img>/<audio> no mandan el encabezado X-Centralita, así que se bajan con fetch
  // (que sí lo manda) y se muestran desde una URL local del navegador (blob:), que se libera al cerrar la pestaña.
  const MEDIOS = ["imagen", "comparar", "audio", "video"];
  async function urlDeArchivo(pid, ruta) {
    const res = await fetch(`/api/pedidos/${pid}/archivo?ruta=${encodeURIComponent(ruta)}`, { headers: { "X-Centralita": "1" } });
    if (!res.ok) throw new Error(`No se pudo leer ${ruta} (${res.status})`);
    return URL.createObjectURL(await res.blob());
  }
  function liberarUrls(t) {
    [t.url, t.urlOriginal].forEach(u => { if (u) URL.revokeObjectURL(u); });
  }

  function cerrarArchivo(idx, forzar = false) {
    const t = abiertos[idx];
    if (!t) return;
    if (t.sucio && !forzar) {
      t.cerrando = true;
      activoIndex = idx;
      render();
      return;
    }
    liberarUrls(t);
    abiertos.splice(idx, 1);
    activoIndex = -1;
    render();
  }

  // ---------------- PANTALLA HOY ----------------
  async function renderHoy() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando...</p>";
    try {
      const hoyData = await api("/api/hoy");
      elCuentaHoy.textContent = hoyData.cuenta_turno || 0;

      let html = `<div class="cabeza">` +
        `<div><h2>Para hacer hoy</h2><p class="suave">Pedidos que necesitan tu intervención y plazos de entrega en curso.</p></div>` +
        `</div>`;

      // Sección Tu turno
      html += `<section class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:12px">` +
        `<h3>Necesita tu atención (${hoyData.turno.length})</h3>` +
        `</div>`;

      if (!hoyData.turno.length) {
        html += `<p class="suave">No hay pedidos esperando tu turno. ¡Todo al día!</p>`;
      } else {
        html += `<div class="alertas">`;
        hoyData.turno.forEach(p => {
          html += `<div class="alerta ${p.nivel || 'aviso'}">` +
            `<div>` +
            `<div class="fila"><span class="dato">${esc(p.id)}</span> ${chipHtml(p)} <b>${esc(p.nombre)}</b> <span class="suave">· ${esc(p.producto)}</span></div>` +
            `<div class="falta">${enlazarTexto(p.id, p.falta)}</div>` +
            (p.link_cuadro ? `<div style="margin-top:4px"><a class="btn chico azul" href="${esc(p.link_cuadro)}" target="_blank" rel="noopener">Comprar cuadro en Mercado Libre →</a></div>` : "") +
            `</div>` +
            `<div class="fila">` +
            (p.bot_frenado ? `<button type="button" class="btn chico fuerte" data-reintentar-pedido="${esc(p.id)}">Reintentar</button>` : "") +
            `<button type="button" class="btn chico" data-abrir-pedido="${esc(p.id)}">Ver pedido</button>` +
            `</div>` +
            `</div>`;
        });
        html += `</div>`;
      }
      html += `</section>`;

      // Sección Plazos
      if (hoyData.con_plazo && hoyData.con_plazo.length) {
        html += `<section class="panel">` +
          `<h3>Tiempo para enviar la primera vista previa (${hoyData.con_plazo.length})</h3>` +
          `<div class="grilla-3" style="margin-top:12px">`;
        hoyData.con_plazo.forEach(p => {
          const pl = p.plazo;
          html += `<div class="tarjeta" data-abrir-pedido="${esc(p.id)}">` +
            `<div class="arriba"><span class="dato">${esc(p.id)}</span> ${chipHtml(p)}</div>` +
            `<div><b>${esc(p.nombre)}</b><div class="suave" style="font-size:13px">${esc(p.producto)}</div></div>` +
            `<div class="plazo ${pl.nivel}">` +
            `<div class="riel"><i style="width:${pl.usado_pct}%"></i></div>` +
            `<small>${esc(pl.texto)}</small>` +
            `</div>` +
            `</div>`;
        });
        html += `</div></section>`;
      }

      elPrincipal.innerHTML = html;
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar datos de Hoy: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- PANTALLA PEDIDOS ----------------
  async function renderPedidos() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando pedidos...</p>";
    try {
      const params = new URLSearchParams();
      if (filtroTipo !== "todos") params.set("tipo", filtroTipo);
      if (busqueda) params.set("q", busqueda);

      const [pedidos, anunciosData] = await Promise.all([
        api("/api/pedidos?" + params.toString()),
        api("/api/anuncios").catch(() => ({ anuncios: [], total_pedidos: 0, total_cobrado: 0 }))
      ]);
      const turnoCount = pedidos.filter(p => p.col === "turno").length;
      elCuentaHoy.textContent = turnoCount;

      let html = `<div class="cabeza">` +
        `<div><h2>Pedidos</h2><p class="suave">Flujo completo de pedidos activos y entregados</p></div>` +
        `<div class="filtros">` +
        `<button type="button" data-filtro="todos" aria-pressed="${filtroTipo === 'todos'}">Todos</button>` +
        `<button type="button" data-filtro="rf" aria-pressed="${filtroTipo === 'rf'}">Lado B · Fotos</button>` +
        `<button type="button" data-filtro="tc" aria-pressed="${filtroTipo === 'tc'}">Lado A · Canciones</button>` +
        `<input type="search" id="busqueda-pedidos" placeholder="Buscar por número o nombre…" value="${esc(busqueda)}">` +
        `</div>` +
        `</div>`;

      // Resumen por utm_content (anuncios)
      if (anunciosData && anunciosData.anuncios && anunciosData.anuncios.length) {
        html += `<div class="panel" style="margin-bottom:18px; display:grid; gap:10px">` +
          `<div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px">` +
          `<div><b>Rendimiento por anuncio (UTM)</b> <span class="suave" style="font-size:13px">· resumen por utm_content</span></div>` +
          `<span class="dato suave" style="font-size:13px">${anunciosData.total_pedidos} pedidos pagados · ${$(anunciosData.total_cobrado)} cobrados</span>` +
          `</div>` +
          `<div class="tabla-caja"><table><thead><tr>` +
          `<th>Anuncio (utm_content)</th>` +
          `<th>Campaña</th>` +
          `<th>Fuente</th>` +
          `<th style="text-align:right">Pedidos pagados</th>` +
          `<th style="text-align:right">Monto cobrado</th>` +
          `<th>Pedidos</th>` +
          `</tr></thead><tbody>`;

        anunciosData.anuncios.forEach(a => {
          html += `<tr>` +
            `<td><b>${esc(a.anuncio)}</b></td>` +
            `<td>${esc(a.campana)}</td>` +
            `<td>${esc(a.fuente)}</td>` +
            `<td style="text-align:right"><b>${a.pedidos_pagados}</b></td>` +
            `<td style="text-align:right">${$(a.monto_cobrado)}</td>` +
            `<td><small class="suave">${esc(a.pedidos.join(", "))}</small></td>` +
            `</tr>`;
        });
        html += `</tbody></table></div></div>`;
      }

      const COLS = [
        { id: "turno", titulo: "Tu turno", vacio: "Nada para hacer." },
        { id: "bot", titulo: "El bot trabajando", vacio: "El bot está libre." },
        { id: "cliente", titulo: "Esperando al cliente", vacio: "Nadie está revisando." },
        { id: "listo", titulo: "Entregados", vacio: "Sin entregas recientes." }
      ];

      html += `<div class="columnas">`;
      COLS.forEach(c => {
        const grupo = pedidos.filter(p => p.col === c.id);
        html += `<div class="columna ${c.id}">` +
          `<header><h3>${esc(c.titulo)}</h3> <span class="dato suave">${grupo.length}</span></header>`;
        if (!grupo.length) {
          html += `<div class="vacia">${esc(c.vacio)}</div>`;
        } else {
          grupo.forEach(p => {
            html += `<div class="tarjeta" data-abrir-pedido="${esc(p.id)}">` +
              `<div class="arriba"><span class="dato">${esc(p.id)}</span> ${chipHtml(p)}</div>` +
              `<div><b>${esc(p.nombre)}</b> <span class="suave" style="font-size:13px">· ${esc(p.producto)}</span></div>` +
              (p.origen_texto && p.origen_texto !== "—" ? `<div style="font-size:12px; margin-top:3px"><span class="suave">Origen:</span> <span class="chip" style="font-size:11px; padding:2px 6px; background:var(--fondo-2); border:1px solid var(--linea)">${esc(p.origen_texto)}</span></div>` : "") +
              `<div class="falta">${enlazarTexto(p.id, p.falta)}</div>` +
              (p.bot_frenado ? `<div style="margin-top:4px"><button type="button" class="btn chico fuerte" data-reintentar-pedido="${esc(p.id)}">Reintentar</button></div>` : "") +
              (p.plazo ? `<div class="plazo ${p.plazo.nivel}"><div class="riel"><i style="width:${p.plazo.usado_pct}%"></i></div><small>${esc(p.plazo.texto)}</small></div>` : "") +
              `</div>`;
          });
        }
        html += `</div>`;
      });
      html += `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos de filtro y búsqueda
      document.querySelectorAll("[data-filtro]").forEach(b => {
        b.addEventListener("click", () => {
          filtroTipo = b.dataset.filtro;
          renderPedidos();
        });
      });
      const inputQ = document.getElementById("busqueda-pedidos");
      if (inputQ) {
        inputQ.addEventListener("input", () => {
          busqueda = inputQ.value;
          renderPedidos();
        });
      }
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar pedidos: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- FICHA DE UN PEDIDO ----------------
  async function abrirPedido(pid) {
    pedidoAbiertoId = pid;
    fichaDatos = null;
    pestanaFicha = "resumen";
    activoIndex = -1;
    render();
  }

  async function renderFicha() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando ficha del pedido...</p>";
    try {
      if (!fichaDatos || fichaDatos.pedido.id !== pedidoAbiertoId) {
        fichaDatos = await api(`/api/pedidos/${pedidoAbiertoId}`);
      }
      const p = fichaDatos.pedido;
      const archivos = fichaDatos.archivos;
      const historial = fichaDatos.historial;

      let html = `<button type="button" class="volver" id="volver-tablero">← Volver a pedidos</button>` +
        `<div class="ficha">` +
        `<div style="display:grid;gap:18px">` +
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<div class="fila"><span class="dato" style="font-size:16px">${esc(p.id)}</span> ${chipHtml(p)} <span class="pill ${p.nivel}">${esc(p.estado)}</span></div>` +
        `<span class="dato" style="font-size:15px;font-weight:700">${$(p.precio)}</span>` +
        `</div>` +
        `<h2 style="margin-bottom:4px">${esc(p.nombre)}</h2>` +
        `<p class="suave">${esc(p.producto)} · Creado el ${fecha(p.creado)}</p>` +
        `</div>` +

        // Pestañas de la ficha
        `<div class="pestanas" role="tablist">` +
        `<button type="button" data-pest-ficha="resumen" aria-selected="${pestanaFicha === 'resumen'}">Resumen</button>` +
        `<button type="button" data-pest-ficha="historial" aria-selected="${pestanaFicha === 'historial'}">Historial (${historial.length})</button>` +
        `<button type="button" data-pest-ficha="archivos" aria-selected="${pestanaFicha === 'archivos'}">Archivos (${archivos.length})</button>` +
        `<button type="button" data-pest-ficha="acciones" aria-selected="${pestanaFicha === 'acciones'}">Acciones</button>` +
        `</div>` +
        `<div id="contenido-pestana" class="panel">`;

      if (pestanaFicha === "resumen") {
        html += `<dl class="datos">` +
          `<dt>Cliente</dt><dd>${esc(p.nombre)}</dd>` +
          `<dt>Email</dt><dd>${esc(p.email)}</dd>` +
          `<dt>WhatsApp</dt><dd>${esc(p.whatsapp)}</dd>` +
          `<dt>Origen</dt><dd>${esc(p.origen_texto || '—')}${p.origen ? ` <small class="suave">(${esc(JSON.stringify(p.origen))})</small>` : ''}</dd>` +
          `<dt>Estado</dt><dd>${esc(p.estado)}</dd>` +
          `<dt>Pagado</dt><dd>${p.pagado ? hora(p.pagado) : 'No'}</dd>`;
        if (p.datos && typeof p.datos === "object") {
          for (const [k, v] of Object.entries(p.datos)) {
            if (v !== null && v !== "" && !(Array.isArray(v) && !v.length)) {
              const valTxt = typeof v === "object" ? JSON.stringify(v) : String(v);
              html += `<dt>${esc(k)}</dt><dd>${esc(valTxt)}</dd>`;
            }
          }
        }
        if (p.drive_url) {
          html += `<dt>Drive</dt><dd><a class="enlace" href="${esc(p.drive_url)}" target="_blank" rel="noopener">Abrir carpeta en Google Drive →</a></dd>`;
        }
        if (p.vista_url) {
          html += `<dt>Vista previa</dt><dd><a class="enlace" href="${esc(p.vista_url)}" target="_blank" rel="noopener">Ver link de vista previa →</a></dd>`;
        }
        if (p.entrega_url) {
          html += `<dt>Entrega</dt><dd><a class="enlace" href="${esc(p.entrega_url)}" target="_blank" rel="noopener">Link de entrega final →</a></dd>`;
        }
        html += `</dl>`;
      } else if (pestanaFicha === "historial") {
        html += `<ul class="linea-tiempo">`;
        if (!historial.length) {
          html += `<li class="suave">Sin entradas en el historial.</li>`;
        } else {
          historial.forEach(h => {
            let tTxt = "", msg = h;
            if (h.startsWith("[") && h.includes("]")) {
              tTxt = h.slice(1, h.indexOf("]"));
              msg = h.slice(h.indexOf("]") + 1).trim();
            }
            html += `<li><time>${esc(tTxt)}</time><div>${enlazarTexto(p.id, msg)}</div></li>`;
          });
        }
        html += `</ul>` +
          `<hr style="border:0;border-top:1px solid var(--linea);margin:16px 0">` +
          `<div class="campo"><label for="nota-historial-ficha">Agregar nota al historial</label>` +
          `<input type="text" id="nota-historial-ficha" placeholder="Ej.: coordinado por WhatsApp, retira mañana"></div>` +
          `<div style="margin-top:8px"><button type="button" class="btn" id="btn-guardar-nota">Guardar nota</button></div>`;
      } else if (pestanaFicha === "archivos") {
        html += `<div style="display:grid;gap:16px">`;
        if (p.tipo === "TC" && !["entregado", "cancelado"].includes(p.estado)) {
          const esAprobado = p.estado === "aprobado";
          html += `<div class="soltar" id="zona-soltar-audio">` +
            `<strong>Soltá acá el audio ${esAprobado ? 'FINAL de Suno' : 'de la VISTA PREVIA'}</strong>` +
            `<p class="suave">Se renombra solo y el bot lo procesa automáticamente</p>` +
            `<input type="file" id="input-audio-soltar" accept="audio/*,.mp3,.wav" hidden>` +
            (esAprobado ? `<div class="campo" style="max-width:320px;text-align:left;margin-top:8px"><label>Para quién:</label><input id="para-quien-audio" value="${esc((p.datos && p.datos.para_quien) ? p.datos.para_quien.split(' - ')[0].split(',')[0].trim() : '')}"></div>` : "") +
            `<div class="fila" style="margin-top:8px"><label class="btn azul" for="input-audio-soltar">Elegir archivo de audio</label>` +
            `<button type="button" class="btn" id="btn-grabar-audio">Grabar lo que suena</button></div>` +
            `</div>`;
        }

        html += `<h4>Archivos del pedido</h4><ul class="archivos-lista">`;
        if (!archivos.length) {
          html += `<li class="suave">No se encontraron archivos en la carpeta local.</li>`;
        } else {
          archivos.forEach(a => {
            html += `<li>` +
              `<div class="fila">${mencionArchivo(p.id, a.ruta, a.nombre)} <span class="pill ${a.editable ? 'aviso' : 'info'}">${a.editable ? 'editable' : 'solo lectura'}</span></div>` +
              `<span class="dato suave">${(a.tamano / 1024).toFixed(1)} KB</span>` +
              `</li>`;
          });
        }
        html += `</ul></div>`;
      } else if (pestanaFicha === "acciones") {
        html += `<div class="acciones-lista">` +
          // 1. Instrucción para rehacer
          `<section>` +
          `<h4>Pedir cambio / Instrucción para rehacer</h4>` +
          `<p class="suave">Pide un cambio sin gastarle cambios al cliente o deja la instrucción en nota-cambio.txt.</p>` +
          `<div class="campo"><textarea id="texto-accion-cambio" rows="3" placeholder="Contanos la instrucción concreta"></textarea></div>` +
          `<div><button type="button" class="btn fuerte" id="btn-enviar-cambio">Pedir cambio</button></div>` +
          `</section>` +

          // 2. Dar cambio extra
          `<section>` +
          `<h4>Dar cambios extra sin costo</h4>` +
          `<p class="suave">Suma cambios incluidos para que el cliente pueda pedir otro desde su página de revisión.</p>` +
          `<div class="fila"><select id="sel-cambios-extra" style="width:120px"><option value="1">+1 cambio</option><option value="2">+2 cambios</option><option value="3">+3 cambios</option></select>` +
          `<button type="button" class="btn" id="btn-dar-cambios-extra">Dar cambios</button></div>` +
          `</section>` +

          // 3. Contacto
          `<section>` +
          `<h4>Contacto del cliente</h4>` +
          `<div class="campo"><label>Email:</label><input id="contacto-email" value="${esc(p.email)}"></div>` +
          `<div id="sugerencia-mail-box" hidden></div>` +
          `<div class="campo"><label>WhatsApp:</label><input id="contacto-wa" value="${esc(p.whatsapp)}"></div>` +
          `<div class="fila" style="margin-top:6px">` +
          `<button type="button" class="btn fuerte" id="btn-guardar-contacto">Guardar contacto</button>` +
          `<button type="button" class="btn" id="btn-reenviar-previa">Reenviar vista previa</button>` +
          `<button type="button" class="btn" id="btn-reenviar-entrega">Reenviar entrega</button>` +
          `</div>` +
          `</section>` +

          // 4. Copiar mensaje para WhatsApp
          `<section>` +
          `<h4>Mensaje para WhatsApp</h4>` +
          `<div class="fila"><button type="button" class="btn" id="btn-copiar-wa">Copiar mensaje para WhatsApp al portapapeles</button></div>` +
          `</section>`;

        // 5. Cuadro si aplica
        if (p.link_cuadro) {
          const pagadoPrevio = (p.costo_proveedor && p.costo_proveedor.pagado !== undefined && p.costo_proveedor.pagado !== null) ? p.costo_proveedor.pagado : "";
          const tieneSeg = !!p.seguimiento;
          html += `<section>` +
            `<h4>Cuadro del proveedor</h4>` +
            `<div class="fila"><a class="btn azul" href="${esc(p.link_cuadro)}" target="_blank" rel="noopener">Comprar cuadro en Mercado Libre →</a></div>`;

          if (tieneSeg) {
            html += `<div class="alerta ok" style="margin-top:10px">` +
              `<div><b>Seguimiento actual:</b> <span class="dato">${esc(p.seguimiento)}</span>` +
              (p.empresa ? ` · ${esc(p.empresa)}` : "") +
              (p.seguimiento_url ? ` · <a class="enlace" href="${esc(p.seguimiento_url)}" target="_blank" rel="noopener">Link de seguimiento</a>` : "") +
              (p.cuadro_comprado ? `<br><small class="suave">Guardado el ${hora(p.cuadro_comprado)}</small>` : "") +
              `</div></div>`;
          }

          html += `<div class="grilla-3" style="margin-top:10px;gap:12px">` +
            `<div class="campo"><label for="seguimiento-cuadro">Número de seguimiento (* obligatorio):</label><input id="seguimiento-cuadro" placeholder="Ej.: MEL-12345678" value="${esc(p.seguimiento || '')}"></div>` +
            `<div class="campo"><label for="empresa-cuadro">Empresa (opcional):</label><input id="empresa-cuadro" placeholder="Ej.: Correo Argentino, Andreani" value="${esc(p.empresa || '')}"></div>` +
            `<div class="campo"><label for="url-cuadro">Link de seguimiento (opcional, https://):</label><input id="url-cuadro" placeholder="https://..." value="${esc(p.seguimiento_url || '')}"></div>` +
            `</div>` +
            `<div class="campo" style="margin-top:10px"><label for="pagado-cuadro">¿Cuánto pagaste? (pesos, opcional):</label><input id="pagado-cuadro" type="number" step="1" min="0" placeholder="Ej.: 25000" value="${esc(pagadoPrevio)}"></div>` +
            `<div class="fila" style="margin-top:12px;gap:10px">` +
            `<button type="button" class="btn fuerte" id="btn-mandar-seguimiento">${tieneSeg ? 'Reenviar seguimiento al cliente' : 'Guardar y mandarle el seguimiento al cliente'}</button>` +
            `<button type="button" class="btn" id="btn-solo-pagado">Guardar solo lo que pagaste</button>` +
            `</div>` +
            `</section>`;
        }

        html += `</div>`;
      }

      html += `</div></div>` +

        // Columna lateral con datos rápidos
        `<div class="panel" style="display:grid;gap:14px">` +
        `<h3>Estado rápido</h3>` +
        `<div class="dato"><b>Columna:</b> ${esc(p.col)}</div>` +
        `<div class="dato"><b>Falta:</b> ${esc(p.falta)}</div>` +
        `<div class="dato"><b>Cambios:</b> ${p.cambios || 0} (extra: ${p.cambios_extra || 0})</div>` +
        `<div class="fila"><button type="button" class="btn chico" data-mostrar-carpeta="${esc(p.id)}|historial.txt">Abrir carpeta en Explorador</button></div>` +
        `</div>` +
        `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos de la ficha
      document.getElementById("volver-tablero")?.addEventListener("click", () => {
        pedidoAbiertoId = null;
        render();
      });

      document.querySelectorAll("[data-pest-ficha]").forEach(b => {
        b.addEventListener("click", () => {
          pestanaFicha = b.dataset.pestFicha;
          renderFicha();
        });
      });

      // Guardar nota historial
      document.getElementById("btn-guardar-nota")?.addEventListener("click", async () => {
        const inp = document.getElementById("nota-historial-ficha");
        if (!inp || !inp.value.trim()) return;
        try {
          await api(`/api/pedidos/${p.id}/nota`, { method: "POST", body: { nota: inp.value.trim() } });
          tostada("Nota agregada al historial");
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      // Contacto email con sugerencia en vivo
      const inEmail = document.getElementById("contacto-email");
      const sugBox = document.getElementById("sugerencia-mail-box");
      if (inEmail && sugBox) {
        inEmail.addEventListener("input", () => {
          const sug = sugerirMail(inEmail.value.trim());
          if (sug) {
            sugBox.hidden = false;
            sugBox.innerHTML = `<div class="sugerencia">¿Quisiste decir <b>${esc(sug)}</b>? <button type="button" class="btn chico" id="btn-aplicar-sug">Sí, corregir</button></div>`;
            document.getElementById("btn-aplicar-sug")?.addEventListener("click", () => {
              inEmail.value = sug;
              sugBox.hidden = true;
            });
          } else {
            sugBox.hidden = true;
          }
        });
      }

      document.getElementById("btn-guardar-contacto")?.addEventListener("click", async () => {
        const email = document.getElementById("contacto-email").value.trim();
        const whatsapp = document.getElementById("contacto-wa").value.trim();
        try {
          await api(`/api/pedidos/${p.id}/contacto`, { method: "PATCH", body: { email, whatsapp } });
          tostada("Contacto actualizado en el servidor");
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-reenviar-previa")?.addEventListener("click", async () => {
        try {
          await api(`/api/pedidos/${p.id}/reenviar`, { method: "POST", body: { que: "vista_previa" } });
          tostada("Vista previa reenviada");
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-reenviar-entrega")?.addEventListener("click", async () => {
        try {
          await api(`/api/pedidos/${p.id}/reenviar`, { method: "POST", body: { que: "entrega" } });
          tostada("Entrega reenviada");
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-enviar-cambio")?.addEventListener("click", async () => {
        const txt = document.getElementById("texto-accion-cambio").value.trim();
        if (!txt) { tostada("Escribí la instrucción"); return; }
        try {
          const r = await api(`/api/pedidos/${p.id}/cambio`, { method: "POST", body: { texto: txt, sin_costo: true } });
          tostada(r.mensaje || "Cambio registrado");
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-dar-cambios-extra")?.addEventListener("click", async () => {
        const sel = document.getElementById("sel-cambios-extra");
        try {
          const r = await api(`/api/pedidos/${p.id}/cambios-extra`, { method: "POST", body: { cantidad: parseInt(sel.value, 10) } });
          tostada(`Cambios extra otorgados: le quedan ${r.quedan}`);
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-copiar-wa")?.addEventListener("click", () => {
        const marca = p.tipo === "RF" ? "Restauración de fotos" : "Tu Canción";
        const msg = `¡Hola ${p.nombre}! Te escribo de ${marca} por tu pedido ${p.id}.`;
        navigator.clipboard.writeText(msg).then(() => {
          tostada("Mensaje copiado al portapapeles");
        });
      });

      document.getElementById("btn-mandar-seguimiento")?.addEventListener("click", async () => {
        const seg = document.getElementById("seguimiento-cuadro")?.value.trim() || "";
        const emp = document.getElementById("empresa-cuadro")?.value.trim() || "";
        const url = document.getElementById("url-cuadro")?.value.trim() || "";
        const pagVal = document.getElementById("pagado-cuadro")?.value.trim() || "";

        if (!seg || seg.length < 4 || seg.length > 60 || seg.includes("\n") || seg.includes("\r")) {
          tostada("El número de seguimiento debe tener entre 4 y 60 caracteres sin saltos de línea.");
          return;
        }
        if (url && !url.startsWith("https://")) {
          tostada("El link de seguimiento debe empezar con https://");
          return;
        }

        let pagadoInt = null;
        if (pagVal !== "") {
          const parsed = parseInt(pagVal.replace(/\./g, "").replace(/\$/g, "").trim(), 10);
          if (isNaN(parsed) || parsed < 1 || parsed > 10000000) {
            tostada("Revisá el monto: tiene que ser lo que pagaste, en pesos.");
            return;
          }
          pagadoInt = parsed;
        }

        try {
          const prev = await api(`/api/pedidos/${p.id}/seguimiento/previa`, {
            method: "POST",
            body: { numero: seg, empresa: emp || null, url: url || null }
          });
          const textoExacto = prev.texto;

          mostrarModal(
            p.seguimiento ? `¿Reenviar seguimiento a ${p.nombre}?` : `¿Mandar seguimiento a ${p.nombre}?`,
            `Se enviará el siguiente mail y un aviso con botón para WhatsApp:\n\n«${textoExacto}»`,
            async () => {
              try {
                await api(`/api/pedidos/${p.id}/seguimiento`, {
                  method: "POST",
                  body: {
                    numero: seg,
                    empresa: emp || null,
                    url: url || null,
                    reenviar: !!p.seguimiento,
                    pagado: pagadoInt
                  }
                });
                tostada(`Seguimiento enviado al cliente: ${seg}`);
                fichaDatos = null;
                renderFicha();
              } catch (err) {
                tostada("Error al enviar seguimiento: " + err.message);
              }
            }
          );
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      document.getElementById("btn-solo-pagado")?.addEventListener("click", async () => {
        const seg = document.getElementById("seguimiento-cuadro")?.value.trim() || "";
        const pagVal = document.getElementById("pagado-cuadro")?.value.trim() || "";
        const body = { seguimiento: seg };
        if (pagVal !== "") {
          const parsed = parseInt(pagVal.replace(/\./g, "").replace(/\$/g, "").trim(), 10);
          if (isNaN(parsed) || parsed < 1 || parsed > 10000000) {
            tostada("Revisá el monto: tiene que ser lo que pagaste, en pesos.");
            return;
          }
          body.pagado = parsed;
        }
        try {
          await api(`/api/pedidos/${p.id}/cuadro-comprado`, { method: "POST", body });
          tostada("Monto del cuadro guardado");
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

      // Soltar audio
      const zonaSoltar = document.getElementById("zona-soltar-audio");
      const inAudio = document.getElementById("input-audio-soltar");
      if (zonaSoltar && inAudio) {
        zonaSoltar.addEventListener("dragover", e => { e.preventDefault(); zonaSoltar.classList.add("encima"); });
        zonaSoltar.addEventListener("dragleave", () => { zonaSoltar.classList.remove("encima"); });
        zonaSoltar.addEventListener("drop", e => {
          e.preventDefault();
          zonaSoltar.classList.remove("encima");
          if (e.dataTransfer.files.length) subirAudio(e.dataTransfer.files[0]);
        });
        inAudio.addEventListener("change", () => {
          if (inAudio.files.length) subirAudio(inAudio.files[0]);
        });
      }

      async function subirAudio(archivo) {
        const fd = new FormData();
        fd.append("archivo_subido", archivo);
        const inPara = document.getElementById("para-quien-audio");
        if (inPara) fd.append("para", inPara.value.trim());

        tostada("Procesando audio...");
        try {
          const r = await api(`/api/pedidos/${p.id}/audio`, { method: "POST", body: fd });
          tostada(r.aviso || "Audio guardado con éxito");
          fichaDatos = null;
          renderFicha();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      }

      document.getElementById("btn-grabar-audio")?.addEventListener("click", async () => {
        const boton = document.getElementById("btn-grabar-audio");
        try {
          const r = await api(`/api/pedidos/${p.id}/audio-grabar`, { method: "POST" });
          tostada(r.mensaje);
          boton.disabled = true;
          const TEXTOS = { esperando: "Dale play en Suno…", grabando: "Grabando…" };
          const seguir = setInterval(async () => {
            let e;
            try { e = await api(`/api/pedidos/${p.id}/audio-grabar`); } catch (err) { e = { estado: "error", mensaje: err.message }; }
            const b = document.getElementById("btn-grabar-audio");
            if (TEXTOS[e.estado]) {
              if (b) b.textContent = TEXTOS[e.estado];
              return;
            }
            clearInterval(seguir);
            if (e.estado === "listo") {
              tostada("Vista previa grabada. El bot la sube en su próxima vuelta.");
              if (pedidoAbiertoId === p.id) { fichaDatos = null; renderFicha(); }
            } else if (e.estado === "error") {
              tostada("No se grabó: " + (e.mensaje || "error"));
              if (b) { b.disabled = false; b.textContent = "Grabar lo que suena"; }
            }
          }, 1500);
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });

    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar ficha: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- VISOR DE ARCHIVO EN PESTAÑA ----------------
  function renderVisor(t) {
    let cab = `<div class="visor-cab">` +
      `<div style="display:grid;gap:4px;min-width:0">` +
      `<div class="fila"><span class="dato">${esc(t.pid)}</span> <h2 style="font-size:22px">${esc(t.nombre)}</h2></div>` +
      `<p class="ruta">${esc(t.ruta)}</p>` +
      `</div>` +
      `<div class="fila">` +
      `<button type="button" class="btn" data-mostrar-carpeta="${esc(t.pid)}|${esc(t.ruta)}">${ICONO_CARPETA} Mostrar en la carpeta</button>` +
      `<button type="button" class="btn" data-abrir-externo="${esc(t.pid)}|${esc(t.ruta)}">Abrir con su programa</button>` +
      `<button type="button" class="btn" data-abrir-pedido="${esc(t.pid)}">Ver el pedido</button>` +
      `</div>` +
      `</div>`;

    let infoHtml = t.info ? `<div class="que-pasa"><b>Qué pasa si lo cambiás</b><span>${esc(t.info)}</span></div>` : "";
    let avisoHtml = t.aviso ? `<div class="que-pasa ok"><b>Listo</b><span>${esc(t.aviso)}</span></div>` : "";
    let cerrandoHtml = t.cerrando ? `<div class="que-pasa aviso"><b>Tenés cambios sin guardar en ${esc(t.nombre)}</b>` +
      `<div class="fila"><button type="button" class="btn fuerte" id="btn-guardar-cerrar">Guardar y cerrar</button>` +
      `<button type="button" class="btn" id="btn-descartar-cerrar">Cerrar sin guardar</button>` +
      `<button type="button" class="btn" id="btn-seguir-editando">Seguir editando</button></div></div>` : "";

    let cuerpo = "";
    if (t.tipo === "texto") {
      const val = t.texto !== null ? t.texto : t.contenido;
      if (t.editable) {
        cuerpo = `<label class="etiqueta" for="visor-editor">Editando</label>` +
          `<textarea class="editor" id="visor-editor" spellcheck="true">${esc(val)}</textarea>` +
          `<div class="fila" style="margin-top:10px">` +
          `<button type="button" class="btn fuerte" id="btn-guardar-visor" ${t.sucio ? '' : 'disabled'}>Guardar</button>` +
          `<button type="button" class="btn" id="btn-descartar-visor" ${t.sucio ? '' : 'disabled'}>Descartar cambios</button>` +
          `<span class="suave" id="txt-estado-editor">${t.sucio ? 'Cambios sin guardar' : 'Sin cambios'}</span>` +
          `</div>`;
      } else {
        cuerpo = `<pre class="lectura">${esc(val)}</pre>`;
      }
    } else if (t.tipo === "json") {
      cuerpo = `<pre class="lectura">${esc(typeof t.contenido === "string" ? t.contenido : JSON.stringify(t.contenido, null, 2))}</pre>`;
    } else if (t.tipo === "imagen") {
      if (t.comparando && t.urlOriginal) {
        // Deslizador: a la izquierda la original del cliente, a la derecha la versión de Codex
        cuerpo = `<div class="comparar" style="aspect-ratio:${t.proporcion || "4 / 3"}">` +
          `<img src="${t.url}" alt="Versión restaurada" style="object-fit:contain">` +
          `<img class="tapa" id="tapa-original" src="${t.urlOriginal}" alt="Original del cliente" style="object-fit:contain">` +
          `<div class="raya" id="raya-comparar"></div><span class="izq">Original</span><span class="der">Restaurada</span></div>` +
          `<label class="etiqueta" for="deslizador-comparar" style="margin-top:8px">Deslizá para comparar</label>` +
          `<input type="range" id="deslizador-comparar" min="0" max="100" value="50" style="width:min(640px,100%)">`;
      } else {
        cuerpo = `<div class="foto-contenedor"><img src="${t.url}" alt="${esc(t.nombre)}" id="img-visor"></div>`;
      }
      if (t.accion === "foto-version") {
        cuerpo += `<div class="fila" style="margin-top:10px">` +
          (t.retocable ? `<input type="file" id="input-retoque" accept="image/*" hidden>` +
            `<label class="btn azul" for="input-retoque">Reemplazar por mi retoque</label>` : "") +
          (t.original_comparar ? `<button type="button" class="btn" id="btn-comparar-modo">${t.comparando ? "Ver solo la restaurada" : "Comparar con la original"}</button>` : "") +
          `</div>`;
      }
    } else if (t.tipo === "comparar") {
      cuerpo = `<div class="foto-contenedor"><img src="${t.url}" alt="Comparativa: antes y después"></div>`;
    } else if (t.tipo === "audio") {
      cuerpo = `<audio controls src="${t.url}" style="width:min(640px,100%)"></audio>`;
    } else if (t.tipo === "video") {
      cuerpo = `<video controls src="${t.url}" style="max-width:100%;max-height:70vh;border-radius:6px"></video>`;
    } else {
      cuerpo = `<p class="suave">Este archivo no se puede ver acá. Usá "Abrir con su programa".</p>`;
    }

    elPrincipal.innerHTML = `<div class="visor">${cab}${cerrandoHtml}${avisoHtml}${infoHtml}${cuerpo}</div>`;

    // Eventos del visor
    const ed = document.getElementById("visor-editor");
    if (ed) {
      ed.addEventListener("input", () => {
        t.texto = ed.value;
        t.sucio = ed.value !== t.contenido;
        t.aviso = null;
        document.getElementById("btn-guardar-visor").disabled = !t.sucio;
        document.getElementById("btn-descartar-visor").disabled = !t.sucio;
        document.getElementById("txt-estado-editor").textContent = t.sucio ? "Cambios sin guardar" : "Sin cambios";
        renderAbiertos();
      });

      document.getElementById("btn-guardar-visor")?.addEventListener("click", async () => {
        await guardarVisor(t);
      });
      document.getElementById("btn-descartar-visor")?.addEventListener("click", () => {
        t.texto = null;
        t.sucio = false;
        render();
      });
    }

    document.getElementById("btn-guardar-cerrar")?.addEventListener("click", async () => {
      await guardarVisor(t);
      cerrarArchivo(activoIndex, true);
    });
    document.getElementById("btn-descartar-cerrar")?.addEventListener("click", () => {
      cerrarArchivo(activoIndex, true);
    });
    document.getElementById("btn-seguir-editando")?.addEventListener("click", () => {
      t.cerrando = false;
      render();
    });

    document.getElementById("btn-comparar-modo")?.addEventListener("click", async () => {
      try {
        if (!t.urlOriginal) {
          t.urlOriginal = await urlDeArchivo(t.pid, t.original_comparar);
          const im = new Image();
          im.src = t.url;
          await im.decode();
          t.proporcion = `${im.naturalWidth} / ${im.naturalHeight}`;
        }
        t.comparando = !t.comparando;
        render();
      } catch (e) {
        tostada("No pude abrir la original: " + e.message);
      }
    });
    const deslizador = document.getElementById("deslizador-comparar");
    if (deslizador) {
      deslizador.addEventListener("input", () => {
        const v = deslizador.value;
        document.getElementById("tapa-original").style.clipPath = `inset(0 ${100 - v}% 0 0)`;
        document.getElementById("raya-comparar").style.left = v + "%";
      });
    }

    const inRetoque = document.getElementById("input-retoque");
    if (inRetoque) {
      inRetoque.addEventListener("change", async () => {
        if (!inRetoque.files.length) return;
        const stem = t.nombre.replace(/\.[^/.]+$/, "");
        const fd = new FormData();
        fd.append("foto_stem", stem);
        fd.append("imagen", inRetoque.files[0]);
        tostada("Guardando retoque y rearmando final...");
        try {
          const r = await api(`/api/pedidos/${t.pid}/retoque`, { method: "POST", body: fd });
          tostada(r.aviso || "Retoque aplicado");
          t.aviso = r.aviso;
          liberarUrls(t);                      // mostrar el retoque recién guardado
          t.url = await urlDeArchivo(t.pid, t.ruta);
          t.urlOriginal = null;
          t.comparando = false;
          if (r.puede_mandar_previa) {
            mostrarModal("¿Mandar vista previa?", "¿Querés mandarle la nueva vista previa al cliente ahora?", async () => {
              try {
                await api(`/api/pedidos/${t.pid}/mandar-vista-previa`, { method: "POST" });
                tostada("Vista previa enviada al cliente");
              } catch (err) {
                tostada("Error al mandar vista previa: " + err.message);
              }
            });
          }
          render();
        } catch (e) {
          tostada("Error: " + e.message);
        }
      });
    }
  }

  async function guardarVisor(t) {
    try {
      const resp = await api(`/api/pedidos/${t.pid}/archivo?ruta=${encodeURIComponent(t.ruta)}`, {
        method: "PUT",
        body: { contenido: t.texto }
      });
      t.contenido = t.texto;
      t.texto = null;
      t.sucio = false;
      t.cerrando = false;
      t.aviso = resp.aviso || "Archivo guardado exitosamente";
      tostada("Archivo guardado");
      render();
    } catch (e) {
      tostada("Error al guardar: " + e.message);
    }
  }

  // ---------------- PANTALLA PLATA ----------------
  async function renderPlata() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando datos de cobros y comisiones...</p>";
    try {
      const q = new URLSearchParams();
      if (filtroPlataMes && filtroPlataMes !== "todos") q.set("mes", filtroPlataMes);
      if (filtroPlataMarca && filtroPlataMarca !== "todas") q.set("marca", filtroPlataMarca);

      const data = await api("/api/plata?" + q.toString());
      const tot = data.totales || {};

      let html = `<div class="cabeza">` +
        `<div><h2>Cobros y comisiones</h2><p class="suave">Movimientos reales de Mercado Pago: cuánto se cobró, la comisión y cuánto queda por liberar. El neto descuenta el costo del proveedor cuando está disponible.</p></div>` +
        `<div class="filtros">` +
        `<select id="filtro-plata-mes" class="btn chico">` +
        `<option value="todos"${filtroPlataMes === "todos" ? " selected" : ""}>Todos los meses</option>` +
        (data.meses_disponibles || []).map(m => `<option value="${esc(m)}"${filtroPlataMes === m ? " selected" : ""}>${esc(m)}</option>`).join("") +
        `</select>` +
        `<button type="button" class="btn chico" data-plata-marca="todas" aria-pressed="${filtroPlataMarca === "todas"}">Todas</button>` +
        `<button type="button" class="btn chico" data-plata-marca="rf" aria-pressed="${filtroPlataMarca === "rf"}">Lado B · Fotos</button>` +
        `<button type="button" class="btn chico" data-plata-marca="tc" aria-pressed="${filtroPlataMarca === "tc"}">Lado A · Canciones</button>` +
        `</div>` +
        `</div>`;

      // Panel de totales (solo con filas completas)
      html += `<div class="grilla-3">` +
        `<div class="panel"><p class="etiqueta">Cobrado</p><p class="cifra">${$(tot.cobrado)}</p></div>` +
        `<div class="panel"><p class="etiqueta">Comisiones MP</p><p class="cifra">${$(tot.comisiones)}</p></div>` +
        `<div class="panel"><p class="etiqueta">Proveedores</p><p class="cifra">${tot.proveedor > 0 ? $(tot.proveedor) : '—'}</p></div>` +
        `<div class="panel"><p class="etiqueta">Te quedó</p><p class="cifra">${$(tot.te_quedo)}</p>` +
        (tot.filas_incompletas > 0 ? `<p class="suave" style="font-size:12px;margin-top:4px">${tot.filas_incompletas} pedido(s) quedaron afuera de 'te quedó' por faltar lo que pagaste el cuadro</p>` : "") +
        `</div>` +
        `<div class="panel"><p class="etiqueta">Por liberar</p><p class="cifra">${$(tot.por_liberar)}</p>` +
        (tot.proxima_liberacion ? `<p class="suave" style="font-size:12px;margin-top:4px">${esc(tot.proxima_liberacion)}</p>` : "") +
        `</div>` +
        `</div>`;

      // Tabla de pedidos cobrados
      html += `<div class="panel">` +
        `<div class="tabla-caja">` +
        `<table>` +
        `<thead><tr>` +
        `<th>Pedido</th><th>Fecha</th><th>Marca</th><th>Producto</th><th>Canal</th>` +
        `<th class="num">Cobrado</th><th class="num">Comisión de Mercado Pago</th><th class="num">Proveedor</th><th class="num">Te quedó</th><th>Se libera</th>` +
        `</tr></thead><tbody>`;

      if (!data.filas || !data.filas.length) {
        html += `<tr><td colspan="10" class="suave" style="text-align:center;padding:20px">No hay cobros registrados con los filtros seleccionados.</td></tr>`;
      } else {
        data.filas.forEach(f => {
          const comPctStr = (f.comision_pct || 0).toFixed(2).replace(".", ",");
          html += `<tr>` +
            `<td><button type="button" class="volver" data-abrir-pedido="${esc(f.pedido)}">${esc(f.pedido)}</button></td>` +
            `<td class="dato">${esc(f.fecha)}</td>` +
            `<td><span class="chip ${f.marca === 'rf' ? 'rf' : 'tc'}">${f.marca === 'rf' ? 'Fotos' : 'Canción'}</span></td>` +
            `<td>${esc(f.nombre_producto)}</td>` +
            `<td class="canal">${esc(f.canal)}</td>` +
            `<td class="num">${f.cobrado === null ? '<span class="suave">sin dato</span>' : $(f.cobrado)}</td>` +
            (f.comision === null
              ? `<td class="num suave" title="${esc(f.comision_detalle)}">sin dato</td>`
              : `<td class="num" title="${esc(f.comision_detalle)}">${$(f.comision)} <span class="suave">(${comPctStr} %)</span></td>`) +
            `<td class="num">${f.proveedor_monto !== null && f.proveedor_monto !== undefined && f.proveedor_texto !== "—" ? $(f.proveedor_monto) : `<span class="suave">${esc(f.proveedor_texto)}</span>`}` +
            (f.proveedor_sub ? `<div class="suave" style="font-size:11px">${esc(f.proveedor_sub)}</div>` : '') +
            `</td>` +
            `<td class="num"><b>${f.te_quedo_monto !== null && f.te_quedo_monto !== undefined ? $(f.te_quedo_monto) : `<span class="suave">${esc(f.te_quedo_texto)}</span>`}</b></td>` +
            `<td><span class="pill ${f.liberada ? 'ok' : 'aviso'}">${esc(f.liberacion)}</span></td>` +
            `</tr>`;
        });
      }

      html += `</tbody><tfoot><tr>` +
        `<td colspan="5">Totales (solo filas completas)</td>` +
        `<td class="num">${$(tot.cobrado)}</td>` +
        `<td class="num">${$(tot.comisiones)}</td>` +
        `<td class="num">${tot.proveedor > 0 ? $(tot.proveedor) : '—'}</td>` +
        `<td class="num">${$(tot.te_quedo)}</td>` +
        `<td></td>` +
        `</tr></tfoot></table></div></div>`;

      // Resumen por tipo_medio
      const rmp = data.resumen_mp || {};
      html += `<div class="panel" style="display:grid;gap:12px">` +
        `<h3>Comisión real según el medio de pago</h3>`;

      if (rmp.grupos && rmp.grupos.length) {
        html += `<div class="tabla-caja"><table style="min-width:440px">` +
          `<thead><tr><th>Medio de pago</th><th class="num">Pagos</th><th class="num">% real</th><th class="num">Liberación</th></tr></thead>` +
          `<tbody>`;
        rmp.grupos.forEach(g => {
          const pctStr = (g.porcentaje_real || 0).toFixed(2).replace(".", ",");
          html += `<tr>` +
            `<td><b>${esc(g.nombre)}</b></td>` +
            `<td class="num">${g.cantidad}</td>` +
            `<td class="num"><b>${pctStr} %</b></td>` +
            `<td class="num">${g.dias_promedio !== null && g.dias_promedio !== undefined ? `${g.dias_promedio} días prom.` : 'sin dato'}</td>` +
            `</tr>`;
        });
        html += `</tbody></table></div>`;
        if (rmp.fuente) {
          html += `<p class="suave" style="font-size:12px">Fuente: ${esc(rmp.fuente)}</p>`;
        }
      } else {
        html += `<p class="suave">Todavía no hay cobros registrados.</p>`;
      }
      html += `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos
      document.getElementById("filtro-plata-mes")?.addEventListener("change", e => {
        filtroPlataMes = e.target.value;
        renderPlata();
      });
      document.querySelectorAll("[data-plata-marca]").forEach(b => {
        b.addEventListener("click", () => {
          filtroPlataMarca = b.dataset.plataMarca;
          renderPlata();
        });
      });
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar datos de Plata: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- PANTALLA COSTOS POR VENTA ----------------
  async function renderCostos() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando costos y comisiones...</p>";
    try {
      const data = await api("/api/costos");

      let html = `<div class="cabeza">` +
        `<div><h2>Costos por venta</h2><p class="suave">Compará cuánto te queda por canal. Mercado Pago muestra cobros reales; Mercado Libre usa la simulación de su API. Lo que falta se marca como “sin dato”.</p></div>` +
        `<button type="button" class="btn" id="btn-actualizar-apis">Actualizar desde las APIs</button>` +
        `</div>`;

      // Aviso fijo
      if (data.aviso_fijo) {
        html += `<div class="aviso-fijo">${esc(data.aviso_fijo)}</div>`;
      }

      // De dónde sale cada número
      const horaLectura = data.leido_vigilante ? hora(data.leido_vigilante) : "sin lectura";
      html += `<div class="panel" style="display:grid;gap:12px">` +
        `<h3>De dónde sale cada número</h3>` +
        `<ul class="fuentes">` +
        `<li><b>Mercado Pago</b><span>Cobros reales agrupados por medio. Comisión real y plazo de liberación real.</span></li>` +
        `<li><b>Mercado Libre</b><span>API oficial de Mercado Libre (listing_prices) con las tarifas vigentes por categoría.</span></li>` +
        `<li><b>Proveedores</b><span>Lectura del vigilante en Mercado Libre (${esc(horaLectura)}). Lo que vas a pagar si lo comprás hoy.</span></li>` +
        `<li><b>Sin dato</b><span>Envío por ML de los cuadros (la API lo calcula con medida y peso del paquete; ML no cotiza sin eso) e IVA de los cargos de ML.</span></li>` +
        `</ul></div>`;

      // Bloque por cada producto
      (data.productos || []).forEach(p => {
        html += `<div class="panel" style="display:grid;gap:14px">` +
          `<div class="fila" style="justify-content:space-between">` +
          `<h3>${esc(p.nombre)}</h3>` +
          `<span class="dato" style="font-size:16px"><b>${$(p.precio_web)}</b> en la web</span>` +
          `</div>`;

        // En la web (Mercado Pago)
        html += `<div style="display:grid;gap:6px">` +
          `<h4 style="font-size:13px;text-transform:uppercase;color:var(--tinta-2);letter-spacing:.05em">En la web (Mercado Pago)</h4>` +
          `<div style="background:var(--papel);padding:10px 14px;border-radius:8px;display:grid;gap:6px">`;

        if (p.filas_mp && p.filas_mp.length) {
          p.filas_mp.forEach(f => {
            const pctStr = (f.pct || 0).toFixed(2).replace(".", ",");
            const queda = f.te_queda === null ? `<span class="suave">sin dato (falta el precio del proveedor)</span>` : `<b>${$(f.te_queda)}</b>`;
            html += `<div>si paga con <b>${esc(f.medio)}</b>: te quedan ${queda} <span class="suave">· ${pctStr} % real, ${f.pagos} pago(s)</span></div>`;
          });
        } else {
          html += `<div class="suave">Sin pagos previos por este canal</div>`;
        }

        if (p.proveedor && p.proveedor.aclaracion) {
          html += `<div class="suave" style="font-size:13px;border-top:1px solid var(--linea);padding-top:6px;margin-top:2px">` +
            `Proveedor: <b>${esc(p.proveedor.texto)}</b> (${esc(p.proveedor.aclaracion)})` +
            `</div>`;
        }
        html += `</div></div>`;

        // En Mercado Libre
        html += `<div style="display:grid;gap:6px">` +
          `<h4 style="font-size:13px;text-transform:uppercase;color:var(--tinta-2);letter-spacing:.05em">En Mercado Libre (simulado con la API)</h4>`;

        if (!p.categoria_ml) {
          html += `<p class="suave">sin dato: falta la categoría de ML</p>`;
        } else {
          const ml = p.ml || {};
          const cClasica = ml.cargos && ml.cargos.clasica;
          const cPremium = ml.cargos && ml.cargos.premium;

          html += `<div class="tabla-caja"><table style="min-width:540px">` +
            `<thead><tr><th>Tipo de publicación</th><th class="num">Cargo ML</th><th class="num">Detalle cargo</th><th class="num">Envío ML</th><th class="num">Te queda en ML</th></tr></thead>` +
            `<tbody>` +
            `<tr>` +
            `<td><b>Clásica (gold_special)</b></td>` +
            `<td class="num">${cClasica ? $(cClasica.total) : 'sin dato'}</td>` +
            `<td class="num suave">${cClasica ? `${coma(cClasica.porcentaje)} % + ${$(cClasica.fijo)} fijo` : '—'}</td>` +
            `<td class="num suave">sin dato</td>` +
            `<td class="num"><b>${ml.queda_clasica !== null && ml.queda_clasica !== undefined ? $(ml.queda_clasica) : 'sin dato'}</b></td>` +
            `</tr>` +
            `<tr>` +
            `<td><b>Premium (gold_pro)</b></td>` +
            `<td class="num">${cPremium ? $(cPremium.total) : 'sin dato'}</td>` +
            `<td class="num suave">${cPremium ? `${coma(cPremium.porcentaje)} %` + (cPremium.financiacion ? ` (incluye ${coma(cPremium.financiacion)} % de cuotas sin interés)` : '') + ` + ${$(cPremium.fijo)} fijo` : '—'}</td>` +
            `<td class="num suave">sin dato</td>` +
            `<td class="num"><b>${ml.queda_premium !== null && ml.queda_premium !== undefined ? $(ml.queda_premium) : 'sin dato'}</b></td>` +
            `</tr>` +
            `</tbody></table></div>` +
            `<p class="suave" style="font-size:12px">Cargos: API de ML (listing_prices, categoría ${esc(p.categoria_ml)})` +
            (ml.cargos && ml.cargos.leido ? `, leído el ${esc(hora(ml.cargos.leido))}` : '') +
            (ml.cargos && ml.cargos.vieja ? ` <b>· ML no respondió ahora: es la última lectura guardada</b>` : '') +
            `. Envío e IVA de cargos: sin dato (falta medida/peso del paquete; la API de ML no lo cotiza sin eso).</p>`;

          const pub = ml.publicar_igual_web || {};
          html += `<div style="background:var(--birome-suave);color:var(--birome);padding:10px 14px;border-radius:8px;font-size:13.5px;margin-top:6px">` +
            `<b>A cuánto publicar en ML para que te quede lo mismo que en la web</b> (sin contar el envío):<br>`;

          if (pub.clasica && pub.clasica.precio_igual_web) {
            html += `· Clásica: <b>${$(pub.clasica.precio_igual_web)}</b> (cargo ML: ${$(pub.clasica.cargo.total)})<br>`;
          }
          if (pub.premium && pub.premium.precio_igual_web) {
            html += `· Premium: <b>${$(pub.premium.precio_igual_web)}</b> (cargo ML: ${$(pub.premium.cargo.total)})<br>`;
          }
          if (!pub.clasica && !pub.premium) {
            html += `<span class="suave">${esc(pub.motivo || 'sin dato')}</span>`;
          }
          html += `</div>`;
        }

        html += `</div></div>`;
      });

      // Simulador de precio libre
      html += `<div class="panel" style="display:grid;gap:14px" id="bloque-simulador">` +
        `<h3>Simulador de precio libre</h3>` +
        `<p class="suave">Elegí un producto o cargá una categoría de ML a mano para calcular cargos y a cuánto publicar.</p>` +
        `<div class="fila" style="gap:12px;align-items:flex-end">` +
        `<div class="campo" style="flex:1"><label>Producto:</label>` +
        `<select id="sim-producto">` +
        `<option value="">-- Personalizado / Otro --</option>` +
        (data.productos || []).map(p => `<option value="${esc(p.id)}"${simuladorEstado.producto === p.id ? " selected" : ""}>${esc(p.nombre)} (${$(p.precio_web)})</option>`).join("") +
        `</select></div>` +
        `<div class="campo" style="flex:1"><label>Precio a simular ($):</label>` +
        `<input id="sim-precio" type="number" step="100" min="100" placeholder="Ej.: 25000" value="${esc(simuladorEstado.precio)}"></div>` +
        `<div class="campo" style="flex:1"><label>Categoría ML:</label>` +
        `<input id="sim-categoria" placeholder="Ej.: MLA434385" value="${esc(simuladorEstado.categoria)}"></div>` +
        `<div><button type="button" class="btn fuerte" id="btn-ejecutar-sim">Simular</button></div>` +
        `</div>` +
        `<div id="sim-resultado"></div>` +
        `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos
      document.getElementById("btn-actualizar-apis")?.addEventListener("click", async () => {
        tostada("Actualizando desde las APIs...");
        try {
          await api("/api/costos/actualizar", { method: "POST" });
          tostada("Caché invalidada. Consultando APIs...");
          renderCostos();
        } catch (e) {
          tostada("Error al actualizar: " + e.message);
        }
      });

      const selProd = document.getElementById("sim-producto");
      const inCat = document.getElementById("sim-categoria");
      const inPrecio = document.getElementById("sim-precio");
      selProd?.addEventListener("change", () => {
        simuladorEstado.producto = selProd.value;
        const prodObj = (data.productos || []).find(x => x.id === selProd.value);
        if (prodObj) {
          if (prodObj.categoria_ml) {
            inCat.value = prodObj.categoria_ml;
            simuladorEstado.categoria = prodObj.categoria_ml;
          }
          if (prodObj.precio_web && !inPrecio.value) {
            inPrecio.value = prodObj.precio_web;
            simuladorEstado.precio = prodObj.precio_web;
          }
        }
      });

      document.getElementById("btn-ejecutar-sim")?.addEventListener("click", async () => {
        const precio = parseInt(inPrecio.value, 10);
        const cat = inCat.value.trim();
        const prod = selProd.value;
        if (!precio || isNaN(precio) || precio <= 0) {
          tostada("Ingresá un precio válido mayor a 0.");
          return;
        }
        simuladorEstado.precio = precio;
        simuladorEstado.categoria = cat;
        simuladorEstado.producto = prod;

        const resDiv = document.getElementById("sim-resultado");
        if (resDiv) resDiv.innerHTML = "<p class='suave'>Simulando...</p>";
        try {
          const sim = await api("/api/costos/simular", {
            method: "POST",
            body: { precio, categoria: cat || null, producto: prod || null },
          });
          pintarResultadoSimulador(sim);
        } catch (e) {
          if (resDiv) resDiv.innerHTML = `<p class="negativo">Error: ${esc(e.message)}</p>`;
        }
      });

      if (simuladorEstado.resultado) {
        pintarResultadoSimulador(simuladorEstado.resultado);
      }
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar Costos por venta: ${esc(e.message)}</p>`;
    }
  }

  function pintarResultadoSimulador(sim) {
    simuladorEstado.resultado = sim;
    const resDiv = document.getElementById("sim-resultado");
    if (!resDiv) return;

    if (!sim.cargos_ml) {
      resDiv.innerHTML = `<div class="panel" style="background:var(--papel);margin-top:12px">` +
        `<p class="suave">${esc(sim.publicar_igual_web?.motivo || 'sin dato: falta la categoría de ML para simular')}</p></div>`;
      return;
    }

    const cC = sim.cargos_ml.clasica;
    const cP = sim.cargos_ml.premium;
    const pub = sim.publicar_igual_web || {};

    let html = `<div class="panel" style="background:var(--papel);margin-top:12px;display:grid;gap:12px">` +
      `<h4>Resultado para ${$(sim.precio)} (Categoría ${esc(sim.categoria || '—')})</h4>` +
      `<div class="tabla-caja"><table style="min-width:480px">` +
      `<thead><tr><th>Tipo</th><th class="num">Cargo total</th><th class="num">Detalle</th><th class="num">Te queda (sin envío)</th></tr></thead>` +
      `<tbody>` +
      `<tr><td><b>Clásica</b></td>` +
      `<td class="num">${cC ? $(cC.total) : 'sin dato'}</td>` +
      `<td class="num suave">${cC ? `${cC.porcentaje}% + ${$(cC.fijo)} fijo` : '—'}</td>` +
      `<td class="num"><b>${cC ? $(sim.precio - cC.total) : 'sin dato'}</b></td></tr>` +
      `<tr><td><b>Premium</b></td>` +
      `<td class="num">${cP ? $(cP.total) : 'sin dato'}</td>` +
      `<td class="num suave">${cP ? `${cP.porcentaje}% + ${$(cP.fijo)} fijo` : '—'}</td>` +
      `<td class="num"><b>${cP ? $(sim.precio - cP.total) : 'sin dato'}</b></td></tr>` +
      `</tbody></table></div>`;

    if (pub.clasica || pub.premium) {
      html += `<div style="background:var(--birome-suave);color:var(--birome);padding:10px 14px;border-radius:8px;font-size:13.5px">` +
        `<b>A cuánto publicar en ML para que te quede lo mismo que en la web</b> (sin contar el envío):<br>`;
      if (pub.clasica) html += `· Clásica: <b>${$(pub.clasica.precio_igual_web)}</b> (cargo: ${$(pub.clasica.cargo.total)})<br>`;
      if (pub.premium) html += `· Premium: <b>${$(pub.premium.precio_igual_web)}</b> (cargo: ${$(pub.premium.cargo.total)})<br>`;
      html += `</div>`;
    } else if (pub.motivo) {
      html += `<p class="suave" style="font-size:13px">${esc(pub.motivo)}</p>`;
    }
    html += `</div>`;
    resDiv.innerHTML = html;
  }

  // ---------------- PANTALLA PRECIOS ----------------
  let preciosData = null;
  async function renderPrecios() {
    elPrincipal.innerHTML = "<p class='suave'>Cargando precios...</p>";
    try {
      preciosData = await api("/api/precios");
      const prods = preciosData.productos || [];
      const historial = preciosData.historial || [];
      const resumenMp = preciosData.resumen_mp || {};
      const pctDineroCuenta = resumenMp.porcentaje_dinero_cuenta != null
        ? `${resumenMp.porcentaje_dinero_cuenta.toFixed(2).replace(".", ",")} %`
        : "comisión real";

      let html = `<div class="cabeza">` +
        `<div><h2>Precios de venta</h2>` +
        `<p class="suave">Precios vigentes de todos los productos y servicios. Los pedidos ya creados mantienen su precio. La web se actualiza sola.</p>` +
        `<p class="suave" style="font-size:13px;margin-top:4px">Comisión dinero en cuenta MP: <b>${pctDineroCuenta}</b>` +
        (preciosData.leido_vigilante ? ` · Última lectura proveedor: <b>${hora(preciosData.leido_vigilante)}</b>` : "") +
        `</p></div></div>`;

      // Grupos: Fotos, Cuadros, Canciones
      const grupos = [
        {
          titulo: "Fotos (restauración)",
          filtro: p => p.id.startsWith("rf-") && !p.con_proveedor,
        },
        {
          titulo: "Cuadros con envío (proveedor)",
          filtro: p => p.con_proveedor,
        },
        {
          titulo: "Canciones personalizadas",
          filtro: p => p.id.startsWith("tc-"),
        },
      ];

      grupos.forEach(g => {
        const items = prods.filter(g.filtro);
        if (!items.length) return;

        html += `<div class="panel" style="display:grid;gap:12px">` +
          `<h3>${esc(g.titulo)}</h3>` +
          `<div class="tabla-caja"><table><thead><tr>` +
          `<th>Producto</th>` +
          `<th>Precio vigente</th>` +
          `<th>Modo</th>` +
          `<th>Te queda por venta</th>` +
          `<th>Acción</th>` +
          `</tr></thead><tbody>`;

        items.forEach(p => {
          let modoHtml = "—";
          if (p.con_proveedor) {
            if (p.modo === "fijo") {
              modoHtml = `<span class="pill" title="No varía con el costo del proveedor">Fijo</span>`;
            } else {
              const orig = p.ganancia_origen === "a mano" ? "a mano" : "regla";
              const gan = p.ganancia_neta != null ? `${$(p.ganancia_neta)} (${orig})` : "regla";
              modoHtml = `<span class="pill info" title="Se recalcula con el costo del proveedor">Automático: ${gan}</span>`;
            }
          }

          let quedaHtml = "—";
          if (p.te_queda != null) {
            let detalle = `MP: -${$(p.comision_mp)}`;
            if (p.con_proveedor && p.costo_proveedor != null) {
              const origCosto = p.costo_a_mano ? "a mano" : "leído";
              detalle += ` · Prov: -${$(p.costo_proveedor)} (${origCosto})`;
            }
            quedaHtml = `<b>${$(p.te_queda)}</b> <span class="suave" style="font-size:12px">(${detalle})</span>`;
          } else if (p.con_proveedor) {
            quedaHtml = `<span class="suave">sin dato (falta proveedor)</span>`;
          }

          html += `<tr>` +
            `<td><b>${esc(p.nombre)}</b> <span class="dato suave">${esc(p.id)}</span></td>` +
            `<td class="cifra" style="font-size:16px">${$(p.precio)}</td>` +
            `<td>${modoHtml}</td>` +
            `<td>${quedaHtml}</td>` +
            `<td><button type="button" class="btn chico" data-cambiar-precio="${esc(p.id)}">Cambiar</button></td>` +
            `</tr>`;
        });

        html += `</tbody></table></div></div>`;
      });

      // Historial de cambios
      html += `<div class="panel" style="display:grid;gap:12px">` +
        `<h3>Historial de cambios de precio</h3>`;

      if (historial.length) {
        html += `<div class="tabla-caja"><table><thead><tr>` +
          `<th>Fecha</th>` +
          `<th>Producto</th>` +
          `<th>Antes → Después</th>` +
          `<th>Quién</th>` +
          `</tr></thead><tbody>`;

        historial.forEach(h => {
          const prodObj = prods.find(x => x.id === h.producto);
          const nomProd = prodObj ? prodObj.nombre : h.producto;
          const fechaStr = h.fecha_local || hora(h.fecha);
          const quienPill = h.quien === "a mano" ? `<span class="pill info">a mano</span>`
            : (h.quien === "aprobado" ? `<span class="pill ok">aprobado</span>` : `<span class="pill">vigilante</span>`);

          html += `<tr>` +
            `<td class="suave" style="font-size:13px">${esc(fechaStr)}</td>` +
            `<td><b>${esc(nomProd)}</b> <span class="dato suave" style="font-size:12px">${esc(h.producto)}</span></td>` +
            `<td><span class="suave">${$(h.antes)}</span> → <b>${$(h.despues)}</b></td>` +
            `<td>${quienPill}</td>` +
            `</tr>`;
        });
        html += `</tbody></table></div>`;
      } else {
        html += `<p class="suave">No hay cambios registrados en el historial todavía.</p>`;
      }
      html += `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos cambiar precio
      elPrincipal.querySelectorAll("[data-cambiar-precio]").forEach(btn => {
        btn.addEventListener("click", () => {
          abrirModalCambiarPrecio(btn.dataset.cambiarPrecio);
        });
      });

    } catch (err) {
      elPrincipal.innerHTML = `<div class="alerta critico"><div><b>Error al cargar precios:</b><p>${esc(err.message)}</p></div></div>`;
    }
  }

  function abrirModalCambiarPrecio(prodId) {
    if (!preciosData) return;
    const prods = preciosData.productos || [];
    const prod = prods.find(p => p.id === prodId);
    if (!prod) return;

    const foto1 = (prods.find(p => p.id === "rf-foto-1") || {}).precio || 5000;
    const esCuadro = prod.con_proveedor;
    const esPack = prod.id.startsWith("rf-pack-");
    const cantPack = esPack ? parseInt(prod.id.replace("rf-pack-", ""), 10) || 1 : 1;

    let customHtml = `<div style="display:grid;gap:12px;margin-top:8px">` +
      `<p class="suave" style="font-size:13px;background:var(--papel);padding:8px 12px;border-radius:6px;margin:0">` +
      `Rige en el momento para los pedidos nuevos; los que ya están hechos mantienen su precio. La web se actualiza sola.</p>`;

    if (!esCuadro) {
      customHtml += `<div style="display:grid;gap:4px">` +
        `<label for="modal-input-precio-nuevo"><b>Precio nuevo ($):</b></label>` +
        `<input id="modal-input-precio-nuevo" type="number" min="100" max="1000000" step="100" value="${prod.precio}" style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--linea)">` +
        `</div>`;
    } else {
      const modoActual = prod.modo || "auto";
      customHtml += `<div style="display:grid;gap:10px">` +
        `<div class="fila" style="gap:16px">` +
        `<label style="cursor:pointer"><input type="radio" name="modal-modo-precio" value="fijo" ${modoActual === "fijo" ? "checked" : ""}> <b>Precio fijo</b></label>` +
        `<label style="cursor:pointer"><input type="radio" name="modal-modo-precio" value="auto" ${modoActual !== "fijo" ? "checked" : ""}> <b>Automático</b></label>` +
        `</div>` +
        `<div id="modal-caja-fijo" style="display:${modoActual === "fijo" ? "grid" : "none"};gap:4px">` +
        `<label for="modal-input-precio-fijo">Precio fijo ($):</label>` +
        `<input id="modal-input-precio-fijo" type="number" min="100" max="1000000" step="100" value="${prod.precio}" style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--linea)">` +
        `</div>` +
        `<div id="modal-caja-auto" style="display:${modoActual !== "fijo" ? "grid" : "none"};gap:4px">` +
        `<label for="modal-input-ganancia">Ganancia neta deseada ($):</label>` +
        `<input id="modal-input-ganancia" type="number" min="0" max="1000000" step="100" value="${prod.ganancia_origen === 'a mano' && prod.ganancia_neta != null ? prod.ganancia_neta : ''}" placeholder="Vacío = la regla predeterminada" style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--linea)">` +
        `<small class="suave">Dejá vacío para volver a la regla predeterminada (${prod.ganancia_neta != null ? '$' + prod.ganancia_neta : 'proveedores.json'}).</small>` +
        `</div>` +
        `</div>`;
    }

    if (esPack) {
      customHtml += `<div id="modal-aviso-pack" style="padding:8px 12px;border-radius:6px;background:var(--papel);font-size:13px"></div>`;
    }

    customHtml += `<div id="modal-simulacion" style="border-top:1px solid var(--linea);padding-top:10px;display:grid;gap:6px;font-size:13px">` +
      `<p class="suave">Calculando simulación...</p>` +
      `</div></div>`;

    mostrarModal(`Cambiar precio: ${prod.nombre}`, "", async cont => {
      // Confirmar
      try {
        if (!esCuadro) {
          const inp = cont.querySelector("#modal-input-precio-nuevo");
          const val = parseInt(inp.value, 10);
          if (isNaN(val) || val < 100 || val > 1000000) {
            tostar("El precio debe ser un número entero entre 100 y 1.000.000");
            return false;
          }
          await api(`/api/precios/${prod.id}`, {
            method: "POST",
            body: JSON.stringify({ precio: val })
          });
        } else {
          const modo = cont.querySelector('input[name="modal-modo-precio"]:checked').value;
          if (modo === "fijo") {
            const inp = cont.querySelector("#modal-input-precio-fijo");
            const val = parseInt(inp.value, 10);
            if (isNaN(val) || val < 100 || val > 1000000) {
              tostar("El precio fijo debe ser un número entero entre 100 y 1.000.000");
              return false;
            }
            await api(`/api/precios/${prod.id}`, {
              method: "POST",
              body: JSON.stringify({ precio: val })
            });
          } else {
            const inp = cont.querySelector("#modal-input-ganancia");
            const valStr = inp.value.trim();
            const val = valStr === "" ? null : parseInt(valStr, 10);
            if (val !== null && (isNaN(val) || val < 0 || val > 1000000)) {
              tostar("La ganancia neta debe estar entre 0 y 1.000.000");
              return false;
            }
            await api(`/api/precios/${prod.id}`, {
              method: "POST",
              body: JSON.stringify({ modo: "auto", ganancia_neta: val })
            });
          }
        }
        tostar(`Precio de ${prod.nombre} actualizado`);
        renderPrecios();
        return true;
      } catch (e) {
        tostar(`Error al actualizar: ${e.message}`);
        return false;
      }
    }, customHtml);

    // Cablear simulación y cambios dentro del modal
    const contModal = document.getElementById("modal-contenedor");
    const simBox = contModal.querySelector("#modal-simulacion");
    const packBox = contModal.querySelector("#modal-aviso-pack");

    let timerSim = null;
    async function actualizarSimulacion() {
      let pEst = prod.precio;
      if (!esCuadro) {
        const inp = contModal.querySelector("#modal-input-precio-nuevo");
        if (inp) pEst = parseInt(inp.value, 10) || 0;
      } else {
        const modo = (contModal.querySelector('input[name="modal-modo-precio"]:checked') || {}).value;
        if (modo === "fijo") {
          const inp = contModal.querySelector("#modal-input-precio-fijo");
          if (inp) pEst = parseInt(inp.value, 10) || 0;
        } else {
          const inp = contModal.querySelector("#modal-input-ganancia");
          const valGan = !inp || inp.value.trim() === "" ? (prod.ganancia_neta || 0) : parseInt(inp.value, 10);
          const costo = prod.costo_proveedor || 0;
          const tasa = (prod.pct_mp || 0) / 100;
          pEst = Math.round((costo + valGan) / (1 - tasa));
        }
      }

      // Pack warning
      if (esPack && packBox) {
        const porFoto = Math.round(pEst / cantPack);
        if (porFoto >= foto1) {
          packBox.innerHTML = `Por foto: <b>${$(porFoto)}</b> · <span class="negativo">Aviso: no es menor que el de la foto suelta (${$(foto1)}).</span>`;
        } else {
          packBox.innerHTML = `Por foto: <b>${$(porFoto)}</b> <span class="suave">(menor que foto suelta: ${$(foto1)})</span>`;
        }
      }

      if (pEst <= 0) {
        simBox.innerHTML = `<p class="suave">Ingresá un precio válido para simular.</p>`;
        return;
      }

      try {
        const sim = await api("/api/costos/simular", {
          method: "POST",
          body: JSON.stringify({ producto: prod.id, precio: pEst })
        });
        const pctDinero = (sim.resumen_mp && sim.resumen_mp.porcentaje_dinero_cuenta) || prod.pct_mp || 0;
        const comisMp = Math.round(pEst * (pctDinero / 100));
        const costoProv = esCuadro ? (prod.costo_proveedor || 0) : 0;
        const netoWeb = pEst - comisMp - costoProv;

        let txtSim = `<div><b>En la web (Mercado Pago):</b> te quedan <b>${$(netoWeb)}</b> ` +
          `<span class="suave">(precio ${$(pEst)}, comisión ${pctDinero.toFixed(2).replace('.', ',')}%: -${$(comisMp)}` +
          (esCuadro ? `, costo prov: -${$(costoProv)}` : "") + `)</span></div>`;

        if (sim.cargos_ml && sim.cargos_ml.clasica) {
          const cl = sim.cargos_ml.clasica;
          const netoCl = pEst - cl.total - costoProv;
          txtSim += `<div><b>En Mercado Libre (Clásica):</b> te quedan <b>${$(netoCl)}</b> ` +
            `<span class="suave">(cargos ML: -${$(cl.total)})</span></div>`;
        }
        if (sim.cargos_ml && sim.cargos_ml.premium) {
          const pr = sim.cargos_ml.premium;
          const netoPr = pEst - pr.total - costoProv;
          txtSim += `<div><b>En Mercado Libre (Premium):</b> te quedan <b>${$(netoPr)}</b> ` +
            `<span class="suave">(cargos ML: -${$(pr.total)})</span></div>`;
        }
        txtSim += `<div class="suave" style="font-size:12px;margin-top:4px">Fuentes: Mercado Pago cobros reales · Mercado Libre listing_prices oficiales</div>`;
        simBox.innerHTML = txtSim;
      } catch (err) {
        simBox.innerHTML = `<p class="suave">Simulación no disponible: ${esc(err.message)}</p>`;
      }
    }

    function dispararSim() {
      clearTimeout(timerSim);
      timerSim = setTimeout(actualizarSimulacion, 200);
    }

    if (esCuadro) {
      contModal.querySelectorAll('input[name="modal-modo-precio"]').forEach(r => {
        r.addEventListener("change", () => {
          const modo = r.value;
          contModal.querySelector("#modal-caja-fijo").style.display = modo === "fijo" ? "grid" : "none";
          contModal.querySelector("#modal-caja-auto").style.display = modo === "auto" ? "grid" : "none";
          dispararSim();
        });
      });
      contModal.querySelector("#modal-input-precio-fijo")?.addEventListener("input", dispararSim);
      contModal.querySelector("#modal-input-ganancia")?.addEventListener("input", dispararSim);
    } else {
      contModal.querySelector("#modal-input-precio-nuevo")?.addEventListener("input", dispararSim);
    }

    actualizarSimulacion();
  }

  // ---------------- PANTALLA PROVEEDORES ----------------
  let proveedoresData = null;
  async function renderProveedores() {
    elPrincipal.innerHTML = "<p class='suave'>Consultando proveedores...</p>";
    try {
      const [prov, pedidos] = await Promise.all([
        api("/api/proveedores"),
        api("/api/pedidos")
      ]);
      proveedoresData = prov;

      const pubs = prov.publicaciones || [];
      const prods = prov.productos || {};
      const comisionMp = (prov.comision_mp && typeof prov.comision_mp === "object")
        ? `${prov.comision_mp.porcentaje || (prov.comision_mp.tasa * 100).toFixed(1)} % (${prov.comision_mp.pagos} cobros reales)`
        : (prov.comision_mp ? `${(prov.comision_mp * 100).toFixed(1)} %` : "8 % (D-49)");

      const prodNombres = {
        "rf-cuadro-enmarcado-20x30": "Cuadro enmarcado 20x30",
        "rf-cuadro-enmarcado-30x40": "Cuadro enmarcado 30x40",
        "rf-cuadro-ecocuero-20x30": "Cuadro ecocuero bastidor 20x30",
        "rf-cuadro-ecocuero-40x30": "Cuadro ecocuero bastidor 40x30",
      };

      let html = `<div class="cabeza">` +
        `<div><h2>Proveedores</h2>` +
        `<p class="suave">El servidor lee las publicaciones cada 30 minutos y ajusta el precio de venta solo. Acá lo podés revisar y corregir a mano.</p>` +
        `<p class="suave" style="font-size:13px;margin-top:4px">` +
        (prov.ultima_revision ? `Última revisión: <b>${hora(prov.ultima_revision)}</b> · ` : "") +
        `Comisión MP: <b>${comisionMp}</b></p>` +
        `</div>` +
        `<button type="button" class="btn fuerte" id="btn-revisar-proveedores">Revisar y ajustar ahora</button>` +
        `</div>`;

      // Pendientes de más de 40%
      const prodsConPendiente = Object.entries(prods).filter(([_, info]) => info.pendiente);
      if (prodsConPendiente.length) {
        html += `<div class="alertas">`;
        prodsConPendiente.forEach(([prodId, info]) => {
          const pend = info.pendiente;
          const nomProd = prodNombres[prodId] || prodId;
          html += `<div class="alerta aviso" style="grid-template-columns:6px 1fr auto">` +
            `<div>` +
            `<b>${esc(nomProd)}: el costo pasó a ${$(pend.costo)}</b>` +
            `<p>El precio tendría que ir de ${$(pend.vigente)} a ${$(pend.nuevo)} (más de 40 %). Por regla no se ajustó solo.</p>` +
            `</div>` +
            `<div class="fila">` +
            `<button type="button" class="btn fuerte chico" data-aprobar-pendiente="${esc(prodId)}" data-nuevo="${pend.nuevo}">Aprobar ${$(pend.nuevo)}</button>` +
            `<button type="button" class="btn chico" data-rechazar-pendiente="${esc(prodId)}">Rechazar</button>` +
            `</div>` +
            `</div>`;
        });
        html += `</div>`;
      }

      // Tarjeta por producto
      html += `<div style="display:grid;gap:18px">`;
      Object.entries(prods).forEach(([prodId, info]) => {
        const pubsProd = pubs.filter(p => p.producto === prodId);
        const precioVigente = info.precio_vigente;
        const nomProd = prodNombres[prodId] || prodId;

        let reglaTxt = "";
        if (info.regla) {
          if (info.regla.ganancia_neta) reglaTxt = `Regla: ganancia neta ${$(info.regla.ganancia_neta)}`;
          else if (info.regla.costo_base) reglaTxt = `Regla: base ${$(info.regla.costo_base)} → venta ${$(info.regla.precio_base)}`;
          else if (info.regla.multiplicador) reglaTxt = `Regla: mult x${info.regla.multiplicador}`;
        }

        html += `<div class="panel">` +
          `<div class="fila" style="justify-content:space-between;margin-bottom:12px">` +
          `<div><h3>${esc(nomProd)}</h3>` +
          `<span class="suave">Precio de venta vigente: <b>${$(precioVigente)}</b></span></div>` +
          (reglaTxt ? `<span class="dato suave" style="font-size:12px">${esc(reglaTxt)}</span>` : "") +
          `</div>` +
          `<div class="tabla-caja"><table style="min-width:680px"><thead><tr>` +
          `<th>Publicación</th>` +
          `<th class="num">Costo</th>` +
          `<th>Historial</th>` +
          `<th>Envío</th>` +
          `<th>Lectura</th>` +
          `<th style="text-align:right">Acciones</th>` +
          `</tr></thead><tbody>`;

        if (!pubsProd.length) {
          html += `<tr><td colspan="6" class="suave" style="text-align:center">Sin publicaciones configuradas para este producto</td></tr>`;
        } else {
          pubsProd.forEach(pub => {
            const lect = pub.ultima_lectura || {};
            const costoReal = pub.a_mano ? pub.a_mano.precio : (lect.precio || 0);
            const envioTxt = lect.envio || "Sin dato";
            const envioOk = envioTxt.toLowerCase().includes("llega") || envioTxt.toLowerCase().includes("gratis") || !envioTxt.toLowerCase().includes("sin");

            html += `<tr>` +
              `<td>` +
              `<b>${esc(pub.nombre)}</b>` +
              (pub.marco ? ` <span class="suave">(${esc(pub.marco)})</span>` : "") +
              `<br><span class="suave" style="font-size:12px">${esc(pub.vendedor || lect.vendedor || 'Vendedor')} · ` +
              `<a class="enlace" href="${esc(pub.url)}" target="_blank" rel="noopener">Ver en ML ↗</a></span>` +
              `</td>` +
              `<td class="num">` +
              `<b>${$(costoReal)}</b>` +
              (pub.a_mano ? `<br><span class="pill info" style="font-size:11px" title="El vigilante lee ${$(lect.precio || pub.a_mano.leido_entonces)}">A mano ${fecha(pub.a_mano.fecha)}</span>` +
                `<br><small class="suave" style="font-size:11px">(ML: ${$(lect.precio || pub.a_mano.leido_entonces)})</small>` : "") +
              `</td>` +
              `<td>${chispa(pub.historial)}</td>` +
              `<td><span class="pill ${envioOk ? 'ok' : 'aviso'}">${esc(envioTxt)}</span></td>` +
              `<td class="suave" style="font-size:13px">${lect.fecha ? hora(lect.fecha) : '—'}</td>` +
              `<td style="text-align:right">` +
              `<div class="fila" style="justify-content:flex-end">` +
              (pub.a_mano ? `<button type="button" class="btn chico" data-quitar-a-mano="${esc(pub.nombre)}">Quitar</button>` : "") +
              `<button type="button" class="btn chico" data-corregir-a-mano="${esc(pub.nombre)}" data-costo-actual="${costoReal}">Corregir a mano</button>` +
              `</div></td></tr>`;
          });
        }
        html += `</tbody></table></div></div>`;
      });
      html += `</div>`;

      // Cuadros por comprar
      const cuadrosPendientes = (pedidos || []).filter(p => {
        const prod = p.producto || "";
        const esCuadro = prod.includes("cuadro");
        const faltaCuadro = p.link_cuadro && !p.seguimiento && p.estado !== "cancelado";
        return esCuadro && faltaCuadro;
      });

      html += `<div class="panel" style="display:grid;gap:10px;margin-top:10px">` +
        `<h3>Cuadros por comprar</h3>`;
      if (!cuadrosPendientes.length) {
        html += `<p class="suave">No hay pedidos con cuadros pendientes de compra o seguimiento.</p>`;
      } else {
        html += cuadrosPendientes.map(p =>
          `<div class="fila" style="justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--linea)">` +
          `<span><span class="dato"><b>${esc(p.id)}</b></span> · ${esc(p.nombre || 'Sin nombre')} · ${esc(p.producto)}</span>` +
          `<button type="button" class="btn chico" data-abrir-pedido="${esc(p.id)}">Abrir pedido</button>` +
          `</div>`
        ).join("");
      }
      html += `</div>`;

      elPrincipal.innerHTML = html;

      // Eventos de Proveedores
      document.getElementById("btn-revisar-proveedores")?.addEventListener("click", () => {
        mostrarModal(
          "¿Revisar y ajustar precios ahora?",
          "El servidor consultará en vivo las publicaciones en Mercado Libre y ajustará los precios de venta según las reglas.",
          async () => {
            tostada("Revisando publicaciones de proveedores...");
            try {
              await api("/api/proveedores/revisar", { method: "POST" });
              tostada("Revisión completada");
              renderProveedores();
            } catch (err) {
              tostada("Error al revisar: " + err.message);
            }
          }
        );
      });

      document.querySelectorAll("[data-aprobar-pendiente]").forEach(btn => {
        btn.addEventListener("click", () => {
          const prodId = btn.dataset.aprobarPendiente;
          const nuevo = btn.dataset.nuevo;
          mostrarModal(
            `¿Aprobar nuevo precio para ${prodId}?`,
            `El precio de venta se actualizará a ${$(nuevo)}. ¿Confirmás?`,
            async () => {
              try {
                await api(`/api/proveedores/pendientes/${encodeURIComponent(prodId)}/aprobar`, { method: "POST" });
                tostada(`Precio aprobado para ${prodId}`);
                renderProveedores();
              } catch (err) {
                tostada("Error al aprobar: " + err.message);
              }
            }
          );
        });
      });

      document.querySelectorAll("[data-rechazar-pendiente]").forEach(btn => {
        btn.addEventListener("click", () => {
          const prodId = btn.dataset.rechazarPendiente;
          mostrarModal(
            `¿Rechazar cambio de precio para ${prodId}?`,
            "Se mantendrá el precio de venta actual y se recordará este costo rechazado para no volver a avisar mientras no cambie. ¿Confirmás?",
            async () => {
              try {
                await api(`/api/proveedores/pendientes/${encodeURIComponent(prodId)}/rechazar`, { method: "POST" });
                tostada(`Cambio rechazado para ${prodId}`);
                renderProveedores();
              } catch (err) {
                tostada("Error al rechazar: " + err.message);
              }
            }
          );
        });
      });

      document.querySelectorAll("[data-quitar-a-mano]").forEach(btn => {
        btn.addEventListener("click", () => {
          const nombre = btn.dataset.quitarAMano;
          mostrarModal(
            `¿Quitar precio a mano para ${nombre}?`,
            "El vigilante volverá a usar el costo leído automáticamente de Mercado Libre.",
            async () => {
              try {
                await api(`/api/proveedores/${encodeURIComponent(nombre)}/precio`, { method: "DELETE" });
                tostada(`Precio a mano quitado para ${nombre}`);
                renderProveedores();
              } catch (err) {
                tostada("Error al quitar precio a mano: " + err.message);
              }
            }
          );
        });
      });

      document.querySelectorAll("[data-corregir-a-mano]").forEach(btn => {
        btn.addEventListener("click", () => {
          const nombre = btn.dataset.corregirAMano;
          const costoActual = btn.dataset.costoActual || "0";
          const inputHtml = `<div class="campo" style="margin-top:8px">` +
            `<label for="modal-input-precio">Precio que ves en la publicación (pesos):</label>` +
            `<input id="modal-input-precio" type="number" min="1" max="10000000" step="1" value="${costoActual}">` +
            `</div>` +
            `<p class="suave" style="font-size:13px;margin-top:6px">El vigilante usará este costo para recalcular el precio de venta en el momento. Se descartará automáticamente si el proveedor cambia su precio en Mercado Libre.</p>`;

          mostrarModal(
            `Corregir a mano: ${nombre}`,
            "",
            async cont => {
              const inp = cont.querySelector("#modal-input-precio");
              const val = inp ? parseInt(inp.value.replace(/\./g, "").replace(/\$/g, "").trim(), 10) : NaN;
              if (isNaN(val) || val < 1 || val > 10000000) {
                tostada("El precio debe ser un número entre 1 y 10.000.000");
                return false;
              }
              try {
                await api(`/api/proveedores/${encodeURIComponent(nombre)}/precio`, {
                  method: "POST",
                  body: { precio: val }
                });
                tostada(`Precio a mano guardado para ${nombre}`);
                renderProveedores();
              } catch (err) {
                tostada("Error al guardar precio a mano: " + err.message);
              }
            },
            inputHtml
          );
        });
      });

    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar proveedores: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- PANTALLA CLIENTES ----------------
  let filtroClientesSoloVolvieron = false;
  async function renderClientes() {
    elPrincipal.innerHTML = "<p class='suave'>Consultando clientes y pagos...</p>";
    try {
      const data = await api("/api/clientes");
      const clientesLista = data.clientes || [];
      const mostrados = filtroClientesSoloVolvieron ? clientesLista.filter(c => c.pedidos_count > 1) : clientesLista;

      let html = `<div class="cabeza">` +
        `<div><h2>Clientes</h2>` +
        `<p class="suave">Historial agrupado por email o WhatsApp. Solo cobros reales aprobados.</p></div>` +
        `</div>` +
        `<div class="panel" style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px">` +
        `<div><b>Volvieron a comprar: ${data.volvieron_count} clientes</b> <span class="suave">(de ${data.total_clientes} clientes totales)</span></div>` +
        `<label class="marca-check" style="cursor:pointer;margin:0">` +
        `<input type="checkbox" id="filtro-volvieron"${filtroClientesSoloVolvieron ? ' checked' : ''}> Solo los que volvieron</label>` +
        `</div>`;

      html += `<div class="panel tabla-caja" style="padding:0"><table style="min-width:760px"><thead><tr>` +
        `<th>Cliente</th>` +
        `<th>Contacto</th>` +
        `<th class="num">Pedidos</th>` +
        `<th>Marcas</th>` +
        `<th class="num">Total cobrado</th>` +
        `<th>Primer y último</th>` +
        `<th>Pedidos</th>` +
        `</tr></thead><tbody>`;

      if (!mostrados.length) {
        html += `<tr><td colspan="7" class="suave" style="text-align:center;padding:24px">No hay clientes para mostrar con el filtro actual.</td></tr>`;
      } else {
        mostrados.forEach(c => {
          const marcasChips = (c.marcas || []).map(m =>
            m === "fotos" ? '<span class="chip rf" style="font-size:11px">Fotos</span>' : '<span class="chip tc" style="font-size:11px">Canción</span>'
          ).join(" ");

          const pedidosBotones = (c.pedidos || []).map(p =>
            `<button type="button" class="btn chico" data-abrir-pedido="${esc(p.id)}" title="${esc(p.producto)} · ${fecha(p.creado)}">${esc(p.id)}</button>`
          ).join(" ");

          html += `<tr>` +
            `<td><b>${esc(c.nombre)}</b></td>` +
            `<td><div style="font-size:13px">${esc(c.email || '—')}<br><span class="suave">${esc(c.whatsapp || '—')}</span></div></td>` +
            `<td class="num"><span class="cifra" style="font-size:18px">${c.pedidos_count}</span></td>` +
            `<td>${marcasChips || '—'}</td>` +
            `<td class="num">${c.total_cobrado === "sin dato" ? '<span class="suave">sin dato</span>' : '<b>' + $(c.total_cobrado) + '</b>'}</td>` +
            `<td class="suave" style="font-size:13px">${fecha(c.primer_pedido)} <span style="opacity:.6">→</span> ${fecha(c.ultimo_pedido)}</td>` +
            `<td><div class="fila" style="gap:4px;flex-wrap:wrap">${pedidosBotones}</div></td>` +
            `</tr>`;
        });
      }

      html += `</tbody></table></div>`;
      elPrincipal.innerHTML = html;

      document.getElementById("filtro-volvieron")?.addEventListener("change", e => {
        filtroClientesSoloVolvieron = e.target.checked;
        renderClientes();
      });
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar clientes: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- PANTALLA FECHAS ----------------
  async function renderFechas() {
    elPrincipal.innerHTML = "<p class='suave'>Consultando fechas y recordatorios...</p>";
    try {
      const data = await api("/api/fechas");
      const fechas = data.fechas || [];
      const cant = data.cantidades || {};
      const comerciales = data.fechas_comerciales || [];

      let html = `<div class="cabeza">` +
        `<div><h2>Recordatorios</h2>` +
        `<p class="suave">Fechas especiales registradas con permiso y próximas fechas comerciales.</p>` +
        `</div></div>`;

      // Métricas y conteos
      html += `<div class="grilla-3">` +
        `<div class="panel">` +
        `<span class="etiqueta">Contactos con permiso</span>` +
        `<div class="cifra">${cant.total || 0}</div>` +
        `<span class="suave">con recordatorio activo</span>` +
        `</div>` +
        `<div class="panel">` +
        `<span class="etiqueta">Por tipo de fecha</span>` +
        `<div style="margin-top:6px;display:grid;gap:4px;font-size:14px">` +
        `<div>Cumpleaños: <b>${(cant.por_tipo || {})['Cumpleaños'] || 0}</b></div>` +
        `<div>Aniversario: <b>${(cant.por_tipo || {})['Aniversario'] || 0}</b></div>` +
        `<div>Otra fecha: <b>${(cant.por_tipo || {})['Otra fecha'] || 0}</b></div>` +
        `</div></div>` +
        `<div class="panel">` +
        `<span class="etiqueta">Por vínculo principal</span>` +
        `<div style="margin-top:6px;display:grid;gap:4px;font-size:14px">`;

      const vincs = Object.entries(cant.por_vinculo || {}).sort((a, b) => b[1] - a[1]).slice(0, 4);
      if (vincs.length) {
        vincs.forEach(([v, c]) => {
          html += `<div>${esc(v)}: <b>${c}</b></div>`;
        });
      } else {
        html += `<span class="suave">Sin vínculos registrados</span>`;
      }
      html += `</div></div></div>`;

      // Fechas comerciales
      html += `<div class="panel" style="display:grid;gap:12px">` +
        `<h3>Fechas comerciales 2026</h3>` +
        `<div class="fila" style="gap:12px">`;

      comerciales.forEach(fc => {
        html += `<div style="background:var(--papel);border:1px solid var(--linea);border-radius:8px;padding:12px 14px;flex:1;min-width:180px">` +
          `<div style="font-weight:700">${esc(fc.nombre)}</div>` +
          `<div class="suave" style="font-size:13px">${fc.dia}/${fc.mes}</div>` +
          `<div style="margin-top:6px;font-size:14px"><b>${fc.contactos}</b> contactos vinculados</div>` +
          `</div>`;
      });
      html += `</div></div>`;

      // Próximos 30 días
      const proximas = fechas.filter(f => f.dias_faltan <= 30);
      html += `<div class="panel" style="display:grid;gap:12px">` +
        `<h3>Próximos 30 días (${proximas.length})</h3>`;

      if (proximas.length) {
        html += `<div class="tabla-caja"><table><thead><tr>` +
          `<th>Fecha</th>` +
          `<th>Falta</th>` +
          `<th>Ocasión</th>` +
          `<th>Para quién</th>` +
          `<th>Vínculo</th>` +
          `<th>Comprador y contacto</th>` +
          `<th>Aviso este año</th>` +
          `</tr></thead><tbody>`;

        proximas.forEach(f => {
          const faltaStr = f.dias_faltan === 0 ? `<b style="color:var(--malvon)">Hoy</b>`
            : (f.dias_faltan === 1 ? `<b style="color:var(--aviso)">Mañana</b>` : `en ${f.dias_faltan} días`);
          const tipoStr = f.tipo + (f.otra ? `: ${f.otra}` : "");
          const avisoPill = f.aviso_enviado_este_anio
            ? `<span class="pill ok">Sí</span>`
            : `<span class="pill">No</span>`;

          html += `<tr>` +
            `<td><b>${f.dia}/${f.mes}</b></td>` +
            `<td>${faltaStr}</td>` +
            `<td>${esc(tipoStr)}</td>` +
            `<td><b>${esc(f.para_quien)}</b></td>` +
            `<td>${esc(f.vinculo || '—')}</td>` +
            `<td>${esc(f.nombre)} <span class="suave">(${esc(f.whatsapp)} · ${esc(f.email)})</span></td>` +
            `<td>${avisoPill}</td>` +
            `</tr>`;
        });
        html += `</tbody></table></div>`;
      } else {
        html += `<p class="suave">No hay fechas que caigan en los próximos 30 días.</p>`;
      }
      html += `</div>`;

      elPrincipal.innerHTML = html;
    } catch (err) {
      elPrincipal.innerHTML = `<div class="alerta critico"><div><b>Error al cargar fechas:</b><p>${esc(err.message)}</p></div></div>`;
    }
  }

  // ---------------- PANTALLA SISTEMA ----------------
  async function renderSistema() {
    elPrincipal.innerHTML = "<p class='suave'>Consultando estado del sistema...</p>";
    try {
      const s = await api("/api/sistema");

      let html = `<div class="cabeza">` +
        `<div><h2>Estado del sistema</h2><p class="suave">Estado de las herramientas en esta PC y de los servicios conectados.</p></div>` +
        `</div>` +
        `<div class="estado-grid">` +

        // Bot
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<h3>Bot de producción</h3>` +
        `<span class="pill ${s.bot.vivo ? 'ok' : 'critico'}"><i class="punto ${s.bot.vivo ? '' : 'rojo'}"></i>${s.bot.vivo ? 'Corriendo' : 'Detenido'}</span>` +
        `</div>` +
        `<div class="dato"><b>PID:</b> ${s.bot.pid || 'Ninguno'}</div>` +
        `<div class="dato"><b>Último registro:</b> ${esc(s.bot.ultima_hora) || 'Sin registro reciente'}</div>` +
        (s.bot.ultima_linea ? `<p class="suave" style="font-size:12px;margin-top:6px;word-break:break-all">${esc(s.bot.ultima_linea)}</p>` : "") +
        `<div style="margin-top:14px"><button type="button" class="btn" id="btn-reiniciar-bot">Reiniciar bot</button></div>` +
        `</div>` +

        // Codex
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<h3>Codex CLI</h3>` +
        `<span class="pill ${s.codex.ok ? 'ok' : 'critico'}"><i class="punto ${s.codex.ok ? '' : 'rojo'}"></i>${s.codex.ok ? 'Disponible' : 'No encontrado'}</span>` +
        `</div>` +
        `<p class="suave">App oficial de OpenAI Codex con tu suscripción de ChatGPT.</p>` +
        `</div>` +

        // Claude
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<h3>Claude Code</h3>` +
        `<span class="pill ${s.claude.loggedIn ? 'ok' : 'critico'}"><i class="punto ${s.claude.loggedIn ? '' : 'rojo'}"></i>${s.claude.loggedIn ? 'Sesión activa' : 'Sin sesión'}</span>` +
        `</div>` +
        `<p class="suave">Segunda IA para revisión de letras con tu cuenta de Claude.</p>` +
        `</div>` +

        // Servidor
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<h3>Servidor tienda</h3>` +
        `<span class="pill ${s.servidor.ok ? 'ok' : 'critico'}"><i class="punto ${s.servidor.ok ? '' : 'rojo'}"></i>${s.servidor.ok ? 'Conectado' : 'Error'}</span>` +
        `</div>` +
        `<div class="dato"><b>Modo MP:</b> ${esc(s.servidor.modo || 'desconocido')}</div>` +
        `</div>` +

        // Mercado Libre
        `<div class="panel">` +
        `<div class="fila" style="justify-content:space-between;margin-bottom:8px">` +
        `<h3>Mercado Libre</h3>` +
        `<span class="pill ${s.ml.conectado ? 'ok' : 'aviso'}"><i class="punto ${s.ml.conectado ? '' : 'amarillo'}"></i>${s.ml.conectado ? 'Autorizado' : 'Sin conexión'}</span>` +
        `</div>` +
        (s.ml.nickname ? `<div class="dato"><b>Cuenta:</b> ${esc(s.ml.nickname)}</div>` : `<p class="suave">Autorización pendiente en ml_api.py</p>`) +
        `</div>` +

        // Carpetas
        `<div class="panel">` +
        `<h3>Carpetas C:\\Pedidos</h3>` +
        `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px">` +
        `<div class="dato">RF Pendientes: <b>${s.carpetas.rf_pendientes}</b></div>` +
        `<div class="dato">RF Listos: <b>${s.carpetas.rf_listos}</b></div>` +
        `<div class="dato">TC Pendientes: <b>${s.carpetas.tc_pendientes}</b></div>` +
        `<div class="dato">TC Listos: <b>${s.carpetas.tc_listos}</b></div>` +
        `</div>` +
        `</div>` +

        `</div>`;

      elPrincipal.innerHTML = html;

      document.getElementById("btn-reiniciar-bot")?.addEventListener("click", () => {
        mostrarModal("¿Reiniciar el bot?", "Esto detendrá el proceso actual de bot.py y volverá a arrancarlo en segundo plano.", async () => {
          tostada("Reiniciando bot...");
          try {
            const r = await api("/api/sistema/reiniciar-bot", { method: "POST" });
            tostada(r.mensaje || "Bot reiniciado con éxito");
            setTimeout(renderSistema, 1500);
          } catch (e) {
            tostada("Error al reiniciar bot: " + e.message);
          }
        });
      });
    } catch (e) {
      elPrincipal.innerHTML = `<p class="negativo">Error al cargar estado del sistema: ${esc(e.message)}</p>`;
    }
  }

  // ---------------- MODAL GENÉRICO ----------------
  function mostrarModal(titulo, mensaje, onConfirmar, customHtml = "") {
    const cont = document.getElementById("modal-contenedor");
    cont.innerHTML = `<div class="modal-fondo">` +
      `<div class="modal">` +
      `<h3>${esc(titulo)}</h3>` +
      (mensaje ? `<p style="white-space:pre-wrap">${esc(mensaje)}</p>` : "") +
      customHtml +
      `<div class="fila" style="justify-content:flex-end;margin-top:10px">` +
      `<button type="button" class="btn" id="btn-modal-cancelar">Cancelar</button>` +
      `<button type="button" class="btn fuerte" id="btn-modal-confirmar">Confirmar</button>` +
      `</div>` +
      `</div></div>`;

    document.getElementById("btn-modal-cancelar").addEventListener("click", () => {
      cont.innerHTML = "";
    });
    document.getElementById("btn-modal-confirmar").addEventListener("click", () => {
      const ok = onConfirmar(cont);
      if (ok !== false) {
        cont.innerHTML = "";
      }
    });
  }

  // Delegación de clics globales para enlaces de archivos y tarjetas
  document.addEventListener("click", e => {
    const btnArchivo = e.target.closest("[data-abrir-archivo]");
    if (btnArchivo) {
      const [pid, ruta] = btnArchivo.dataset.abrirArchivo.split("|");
      abrirArchivo(pid, ruta);
      return;
    }

    const btnCarpeta = e.target.closest("[data-mostrar-carpeta]");
    if (btnCarpeta) {
      const [pid, ruta] = btnCarpeta.dataset.mostrarCarpeta.split("|");
      api(`/api/pedidos/${pid}/mostrar?ruta=${encodeURIComponent(ruta)}`, { method: "POST" })
        .then(() => tostada("Mostrando archivo en el Explorador"))
        .catch(err => tostada("Error: " + err.message));
      return;
    }

    const btnExt = e.target.closest("[data-abrir-externo]");
    if (btnExt) {
      const [pid, ruta] = btnExt.dataset.abrirExterno.split("|");
      api(`/api/pedidos/${pid}/abrir?ruta=${encodeURIComponent(ruta)}`, { method: "POST" })
        .then(() => tostada("Abriendo con programa predeterminado"))
        .catch(err => tostada("Error: " + err.message));
      return;
    }

    const btnReintentar = e.target.closest("[data-reintentar-pedido]");
    if (btnReintentar) {
      const pid = btnReintentar.dataset.reintentarPedido;
      mostrarModal(
        `¿Reintentar pedido ${pid}?`,
        "El bot reseteará los intentos y volverá a tomar este pedido en su próxima vuelta (cada 60 s).",
        async () => {
          try {
            await api(`/api/pedidos/${pid}/reintentar`, { method: "POST" });
            tostada(`Reintento pedido para ${pid}`);
            render();
          } catch (err) {
            tostada("Error al pedir reintento: " + err.message);
          }
        }
      );
      return;
    }

    const card = e.target.closest("[data-abrir-pedido]");
    if (card && !e.target.closest("button") && !e.target.closest("a")) {
      abrirPedido(card.dataset.abrirPedido);
      return;
    } else if (card && e.target.tagName === "BUTTON") {
      abrirPedido(card.dataset.abrirPedido);
      return;
    }
  });

  // Mercado Libre y Meta (Fase 4)
  async function renderMLMeta() {
    elPrincipal.innerHTML = "<p class='suave'>Consultando datos de Mercado Libre y Meta...</p>";
    try {
      const data = await api("/api/ml-meta");
      const ml = data.ml || {};
      const meta = data.meta || {};
      const resML = ml.resumen || {};
      const resMeta = meta.resumen || {};
      const vendedor = ml.vendedor || {};
      const pubs = ml.publicaciones || [];
      const pregs = ml.preguntas || [];
      const campanas = meta.campanas || [];
      const pixel = meta.pixel || {};

      let html = `<div class="cabeza">` +
        `<div><h2>Mercado Libre y Meta</h2><p class="suave">Publicaciones activas, métricas en vivo y seguimiento de campañas</p></div>` +
        `<div class="fila">` +
        `<button type="button" class="btn" id="btn-actualizar-ml-meta">Actualizar en vivo</button>` +
        `</div>` +
        `</div>`;

      // Tarjetas de resumen (KPIs)
      html += `<div class="totales">` +
        `<div class="tarjeta-total">` +
        `<span class="etiqueta">Publicaciones ML</span>` +
        `<b class="num">${resML.activas || 0} <small class="suave">activas</small></b>` +
        `<span class="suave">${resML.total_publicaciones || 0} totales en cuenta</span>` +
        `</div>` +
        `<div class="tarjeta-total">` +
        `<span class="etiqueta">Visitas 7 días (ML)</span>` +
        `<b class="num">${resML.visitas_7d_total || 0}</b>` +
        `<span class="suave">vistas en total</span>` +
        `</div>` +
        `<div class="tarjeta-total">` +
        `<span class="etiqueta">Preguntas ML</span>` +
        `<b class="num">${resML.preguntas_pendientes_total || 0}</b>` +
        `<span class="suave">${resML.preguntas_pendientes_total > 0 ? '<span class="pill critico">Requiere respuesta</span>' : 'Al día'}</span>` +
        `</div>` +
        `<div class="tarjeta-total">` +
        `<span class="etiqueta">Píxel de Meta</span>` +
        `<b><span class="pill ${pixel.activo ? 'ok' : 'aviso'}"><i class="punto ${pixel.activo ? '' : 'amarillo'}"></i>${pixel.activo ? 'Activo' : 'Pendiente'}</span></b>` +
        `<span class="suave">${esc(pixel.id_mascarado || 'Sin ID cargado')}</span>` +
        `</div>` +
        `<div class="tarjeta-total">` +
        `<span class="etiqueta">Ventas Meta (UTMs)</span>` +
        `<b class="num">${resMeta.total_pedidos_atribuidos || 0} <small class="suave">pedidos</small></b>` +
        `<span class="suave">$${(resMeta.total_cobrado_atribuido || 0).toLocaleString('es-AR')}</span>` +
        `</div>` +
        `</div>`;

      // Bloque Mercado Libre
      html += `<div class="panel" style="padding:0;overflow:hidden">` +
        `<div style="padding:18px 20px;border-bottom:1px solid var(--linea);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">` +
        `<div>` +
        `<h3>Mercado Libre · Cuenta oficial</h3>` +
        `<p class="suave">Vendedor: <b>${esc(vendedor.nickname || 'TUTIENDITAIA')}</b> (ID ${esc(vendedor.id || '')}) ` +
        (vendedor.permalink ? `· <a href="${esc(vendedor.permalink)}" target="_blank" rel="noopener">Ver perfil vendedor ↗</a>` : '') +
        `</p>` +
        `</div>` +
        `<span class="pill ${ml.conectado ? 'ok' : 'critico'}"><i class="punto ${ml.conectado ? '' : 'rojo'}"></i>${ml.conectado ? 'API conectada' : 'Desconectada'}</span>` +
        `</div>`;

      if (pubs.length === 0) {
        html += `<div style="padding:24px;text-align:center" class="suave">No se encontraron publicaciones en la cuenta.</div>`;
      } else {
        html += `<div class="tabla-caja" style="padding:0;border:0">` +
          `<table><thead><tr>` +
          `<th>Foto</th>` +
          `<th>Publicación</th>` +
          `<th class="num">Precio</th>` +
          `<th>Estado</th>` +
          `<th class="num">Stock</th>` +
          `<th class="num">Visitas (7d)</th>` +
          `<th class="num">Ventas</th>` +
          `<th class="num">Cargo est. Clásica</th>` +
          `<th>Preguntas</th>` +
          `</tr></thead><tbody>`;

        pubs.forEach(p => {
          const thumb = p.thumbnail ? `<img src="${esc(p.thumbnail)}" alt="" style="width:36px;height:36px;object-fit:cover;border-radius:4px">` : `<span class="suave">—</span>`;
          const estPill = p.estado === 'active' ? '<span class="pill ok">Activa</span>' : (p.estado === 'paused' ? '<span class="pill aviso">Pausada</span>' : `<span class="pill info">${esc(p.estado)}</span>`);
          const pregsItem = p.preguntas_sin_responder > 0 ? `<span class="pill critico">${p.preguntas_sin_responder} pend.</span>` : `<span class="suave">0</span>`;

          html += `<tr>` +
            `<td>${thumb}</td>` +
            `<td><a href="${esc(p.permalink)}" target="_blank" rel="noopener" style="font-weight:600;text-decoration:none;color:var(--birome)">${esc(p.titulo)}</a><br><small class="suave dato">${esc(p.id)}</small></td>` +
            `<td class="num font-bold">$${(p.precio || 0).toLocaleString('es-AR')}</td>` +
            `<td>${estPill}</td>` +
            `<td class="num">${p.stock}</td>` +
            `<td class="num">${p.visitas_7d}</td>` +
            `<td class="num">${p.ventas}</td>` +
            `<td class="num">${esc(p.cargo_estimado)}</td>` +
            `<td>${pregsItem}</td>` +
            `</tr>`;
        });

        html += `</tbody></table></div>`;
      }
      html += `</div>`;

      // Bloque Preguntas si hay
      if (pregs.length > 0) {
        html += `<div class="panel">` +
          `<h3>Preguntas de compradores pendientes de respuesta (${pregs.length})</h3>` +
          `<ul class="fuentes" style="margin-top:12px">`;
        pregs.forEach(q => {
          html += `<li><b>Publicación ${esc(q.item_id)}:</b> <span>"${esc(q.texto)}"</span></li>`;
        });
        html += `</ul></div>`;
      }

      // Bloque Meta (Campañas y Píxel)
      html += `<div class="panel" style="padding:0;overflow:hidden">` +
        `<div style="padding:18px 20px;border-bottom:1px solid var(--linea);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">` +
        `<div>` +
        `<h3>Meta · Anuncios y Atribución (Instagram y Facebook)</h3>` +
        `<p class="suave">Seguimiento de compras por enlaces con UTMs y estado del píxel</p>` +
        `</div>` +
        `<span class="pill ${pixel.activo ? 'ok' : 'aviso'}"><i class="punto ${pixel.activo ? '' : 'amarillo'}"></i>Píxel ${pixel.activo ? 'Activo' : 'Pendiente'}</span>` +
        `</div>`;

      // Info del Píxel y Ads
      html += `<div style="padding:16px 20px;background:var(--papel);border-bottom:1px solid var(--linea);display:grid;gap:8px;font-size:13px">` +
        `<div><b>Estado del Píxel:</b> ${esc(pixel.estado)}. ${pixel.id_mascarado ? `(ID configurado: <code>${esc(pixel.id_mascarado)}</code>)` : 'Para activarlo, cargá el ID en <code>tienda/web/tienda.js</code>.'}</div>` +
        `<div class="suave"><b>Conexión con Meta Ads:</b> ${esc(meta.cuenta_publicitaria.mensaje)}</div>` +
        `</div>`;

      if (campanas.length === 0) {
        html += `<div style="padding:24px;text-align:center" class="suave">` +
          `<p>Todavía no ingresaron pedidos con parámetros UTM de Meta.</p>` +
          `<p style="font-size:13px;margin-top:6px">Al publicar tus anuncios en Meta con enlaces como <code>https://tucancion.com.ar/?utm_source=meta&utm_campaign=dia-de-la-madre&utm_content=P014</code>, cada compra aprobada aparecerá acá atribuida a su pieza y campaña correspondiente.</p>` +
          `</div>`;
      } else {
        html += `<div class="tabla-caja" style="padding:0;border:0">` +
          `<table><thead><tr>` +
          `<th>Campaña (utm_campaign)</th>` +
          `<th>Pieza / Creativo (utm_content)</th>` +
          `<th>Fuente / Medio</th>` +
          `<th class="num">Pedidos</th>` +
          `<th class="num">Total cobrado</th>` +
          `</tr></thead><tbody>`;

        campanas.forEach(c => {
          html += `<tr>` +
            `<td><b>${esc(c.campana)}</b></td>` +
            `<td><code>${esc(c.pieza)}</code></td>` +
            `<td class="suave">${esc(c.fuente_medio)}</td>` +
            `<td class="num">${c.pedidos}</td>` +
            `<td class="num font-bold">$${(c.cobrado || 0).toLocaleString('es-AR')}</td>` +
            `</tr>`;
        });

        html += `</tbody></table></div>`;
      }
      html += `</div>`;

      elPrincipal.innerHTML = html;

      // Event listener para botón actualizar
      const btnActualizar = document.getElementById("btn-actualizar-ml-meta");
      if (btnActualizar) {
        btnActualizar.addEventListener("click", async () => {
          btnActualizar.disabled = true;
          btnActualizar.textContent = "Actualizando...";
          try {
            await api("/api/ml-meta/actualizar", { method: "POST" });
            tostada("Datos de Mercado Libre y Meta actualizados");
            await renderMLMeta();
          } catch (err) {
            tostada("Error al actualizar: " + err.message);
            btnActualizar.disabled = false;
            btnActualizar.textContent = "Actualizar en vivo";
          }
        });
      }

    } catch (err) {
      elPrincipal.innerHTML = `<div class="panel"><p class="negativo">Error al cargar datos de Mercado Libre y Meta: ${esc(err.message)}</p></div>`;
    }
  }

  // Navegación por hash
  async function revisarHash() {
    const h = window.location.hash.slice(1);
    if (!h) return;
    if (h.startsWith("pedido-")) {
      await abrirPedido(h.slice(7));
    } else if (h.startsWith("archivo-")) {
      const [pid, ...resto] = h.slice(8).split("|");
      await abrirArchivo(pid, resto.join("|"));
    } else if (["hoy", "pedidos", "plata", "costos", "precios", "proveedores", "clientes", "fechas", "sistema", "ml-meta"].includes(h)) {
      irVista(h);
    }
  }
  window.addEventListener("hashchange", revisarHash);

  // Arranque inicial
  if (window.location.hash) {
    revisarHash();
  } else {
    render();
  }
})();

