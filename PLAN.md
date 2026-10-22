# Centralita · plan de acción

App de operaciones de tutienditaia (Restauración de fotos + Tu Canción). Decisiones en `DECISIONES.md` (D-44 a D-47).
Prototipo navegable (referencia visual y de comportamiento): `centralita/prototipo.html` y https://claude.ai/artifact/HvDGFQXoM7G9x3rLcPf37v

## Reglas que no se negocian
1. **Corre en la PC del usuario.** Servicio local en `127.0.0.1:8790` (nunca `0.0.0.0`) y una ventana propia (`msedge --app=http://127.0.0.1:8790`). No se publica en internet.
2. **Las llaves no salen del backend local.** El token de admin, el de ML y el de MP se leen de los archivos del Escritorio (`claves-tienda.txt`, `ml_token.json`) con las funciones que ya existen (`pedidos.claves()`, `ml_api.token()`). Nunca van al navegador, a un log, a un archivo nuevo ni a la salida de consola. Si hay que mostrar algo de una llave: solo el nombre y el largo.
3. **Costos y comisiones: solo datos reales** (API de ML, pagos de MP, lecturas del vigilante). Si no hay dato, se muestra "sin dato". Nunca porcentajes de referencia ni estimados.
4. **No se borra nada de los pedidos.** Lo que se reemplaza va a `anteriores\` con el número de versión siguiente. Toda acción queda en `historial.txt` (`carpetas.anotar`).
5. **La centralita no corre Codex ni Claude.** Deja instrucciones y archivos donde el bot ya los busca, o llama al servidor. El bot sigue siendo el único que produce.
6. **Rutas seguras.** Toda ruta que llega del navegador se resuelve dentro de la carpeta del pedido (`carpetas.buscar(pid)`); si sale de ahí (`..`, rutas absolutas, otra unidad), 400.
7. **Datos de clientes:** quedan en `C:\Pedidos` y en el servidor. Nada de copias en el proyecto ni en carpetas temporales sin borrar.
8. Español rioplatense con voseo en toda la interfaz, igual que el prototipo.

## Piezas que ya existen y hay que reusar (no reescribir)
| Qué | Dónde |
|---|---|
| Carpetas de pedidos (`C:\Pedidos\RF|TC\Pendientes|Listos\<ID> - <comprador>`), `buscar`, `carpeta`, `mover_a_listos`, `listos`, `anotar` (historial) | `produccion/carpetas.py` |
| API del servidor con el token de admin (`cliente()`), llaves (`claves()`), traer un pedido | `tienda/herramientas/pedidos.py` |
| Fotos: Real-ESRGAN + final + vista previa + comparativa (`procesar`) | `produccion/fotos.py` |
| Canciones: vista previa de 1 minuto con fundido, final con metadatos (`previa`, `final`) | `produccion/cancion.py` |
| Versiones de letra (`leer_version`, `guardar_version`, `como_texto`) | `tienda/herramientas/letras.py` |
| Bot: estado por pedido en `C:\Pedidos\bot-estado.json`, registro `C:\Pedidos\bot.log`, candado `C:\Pedidos\bot.lock` | `tienda/herramientas/bot.py` |
| API de Mercado Libre con la app autorizada (`get`, `token`, candado del token) | `tienda/herramientas/ml_api.py` |
| Revisión de mails (formato, "¿quisiste decir…?", DNS) | `tienda/app/correo.py` |
| Servidor: endpoints admin, flujo de mails, base de datos | `tienda/app/main.py`, `flujo.py`, `db.py` |

Qué hace el bot con cada archivo (la centralita se apoya en esto):
- **Fotos, pedido en estado `cambio` que el bot frenó** (`cambio_en_espera` en bot-estado): si aparece `nota-cambio.txt` en la carpeta del pedido, rehace con esa instrucción (es lo que hace `pedidos.py cambio`).
- **Canciones:** sube como vista previa el `3-vistas-previas\v<N>-previa.mp3` de número más alto que `previa_subida`. Cuando el pedido está `aprobado` y hay un MP3 en `4-entrega\`, lo entrega (en el combo arma además el video).
- **Letras:** el próximo cambio parte de `2-letra\version-v<letra_n>.json`.

## Fase 1 · Pedidos y archivos (tarea 11 de Antigravity)
**Hecha y revisada (14/10):** arreglos y pendientes en `centralita/ENTREGA.md` §6. El servicio es `servicio.py` (`uvicorn servicio:app`), no `app.py`: ese nombre tapa el paquete `tienda/app`. Lo arranca `arrancar.py` (desde `centralita.bat` con pythonw, que no tiene consola: sin ese arreglo uvicorn se cae al arrancar; registro en `%TEMP%\centralita.log`).
Detalle completo en `tienda/docs/PROMPT-ANTIGRAVITY-11.md`. Resumen:
1. Servidor: corregir mail/WhatsApp, reenviar el último mail, pedir un cambio en nombre del cliente y dar cambios extra sin costo.
2. Centralita: Hoy, tablero de pedidos, ficha (resumen, historial, archivos, acciones), archivos clicables (pestaña o Explorador con el archivo seleccionado), visor/editor que avisa al bot, soltar audios con renombre, estado del sistema y reinicio del bot.
3. Arranque: `centralita.bat`, acceso directo en el Escritorio, ventana propia.

## Fase 2 · Plata y costos reales (tarea 12 de Antigravity: `tienda/docs/PROMPT-ANTIGRAVITY-12.md`)
Suma también: monto real pagado al proveedor (cargado a mano al marcar el cuadro comprado) y "Reintentar" para pedidos con el bot frenado.
**Hecha y revisada (14/10):** arreglos en `centralita/ENTREGA.md` §8.
- Servidor: `GET /admin/pagos` → por pedido, datos del pago de MP (`fee_details`, `transaction_details.net_received_amount`, `money_release_date`, `money_release_status`, medio y cuotas). La llave de MP queda en el servidor.
- Centralita, ML (desde la PC con `ml_api.get`): `/sites/MLA/listing_prices?price=&category_id=` para simular cualquier precio; categoría con `/sites/MLA/domain_discovery/search`; en ventas reales de ML, el cargo de cada venta de `/orders/{id}` (`order_items[].sale_fee`). Datos ya leídos el 14/10 en `centralita/cargos-ml-2026-10-14.json`.
- Pantallas: Plata (por pedido: canal, precio, comisión real, proveedor, neto, liberación) y Costos por venta (simulador, "te queda por venta" y "a cuánto publicar en ML para ganar lo mismo", con botón "Actualizar desde las APIs"). Lo que no informan las APIs: "sin dato" (envío por ML hasta tener medida y peso; IVA de los cargos).

## Fase 3 · Proveedores, cuadros y clientes (tarea 15 de Antigravity: `tienda/docs/PROMPT-ANTIGRAVITY-15.md`)
**Hecha y revisada (14/10):** arreglos en `centralita/ENTREGA.md` §10.

## Fase 3b · Precios a mano y fechas importantes (tarea 17: `tienda/docs/PROMPT-ANTIGRAVITY-17.md`)
Decisiones del 14/10: precios a mano (cuadros fijos o automáticos con ganancia propia); fechas solo de la persona del regalo, con permiso aparte; recordatorio por mail automático + WhatsApp que manda el usuario. Precios en vivo en las webs: D-51 (tarea 16).
- Servidor: `GET /admin/proveedores` (última lectura e historial de precios del vigilante), `POST /admin/proveedores/{publicacion}/precio` (precio cargado a mano), `POST .../aprobar` y `.../rechazar` (cambios de más de 40 %, que hoy solo avisan). "Revisar ahora" ya existe: `POST /admin/vigilante`.
- Cuadros: marcar comprado con número de seguimiento → el servidor lo guarda y le manda el seguimiento al cliente.
- Clientes: quién volvió a comprar; fechas para recordarles solo si dieron permiso.

## Fase 4 · Mercado Libre y Meta
- Publicaciones de ML (precio, visitas, preguntas sin responder) con la app ya autorizada.
- Campañas de Meta (gasto, ventas, costo por venta): requiere conectar una cuenta publicitaria; se define cuando llegue.

## Cómo se trabaja
- Antigravity construye una fase por vez y frena: deja la entrega en `centralita/ENTREGA.md` (qué hizo, qué probó, qué quedó pendiente, dudas). Claude revisa y corrige antes de la fase siguiente.
- Nada de pedidos de prueba en el servidor ni mails reales a clientes durante el desarrollo.
- Pendiente de antes, independiente de la centralita: tarea 10 (`tienda/docs/PROMPT-ANTIGRAVITY-10.md`, revisión del mail).
