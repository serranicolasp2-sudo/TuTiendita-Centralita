# Tu Tiendita IA · Centralita de Pedidos & Orquestador Local

> **Sitio web oficial:** [tutiendita-ia.store](https://tutiendita-ia.store)  
> Panel de control de escritorio, orquestador de procesos locales y sincronización de pedidos para Tu Tiendita IA.

---

## 🌟 Descripción del Proyecto

**Tu Tiendita IA - Centralita** es el centro de control operativo local (corriendo como servicio FastAPI en `127.0.0.1:8790`). Se encarga de coordinar la producción local en la máquina de trabajo, gestionar las carpetas de pedidos (`C:\Pedidos`), controlar la ejecución de los bots en segundo plano, validar costos y comisiones de MercadoLibre/Mercado Pago, y brindar una interfaz visual interactiva para supervisar todo el flujo en tiempo real.

---

## 🚀 Módulos y Capacidades

1. **Servicio Local Seguro (`servicio.py`)**:
   - Escucha exclusivamente en `127.0.0.1:8790`.
   - Protección estricta con encabezados de seguridad (`X-Centralita: 1`).
   - Resolución de rutas seguras para evitar escape de directorios.

2. **Panel de Control Visual (`prototipo.html` / `static/`)**:
   - Monitoreo en tiempo real de pedidos entrantes, en proceso y listos.
   - Vista rápida de estado de los bots (`bot.py`, vigilante).
   - Acceso a comparativas de fotos antes/después y reproducción de audios.

3. **Servicios Especializados (`servicios/`)**:
   - `archivos.py`: Explorador y gestor de entregas, vistas previas y marcas de agua.
   - `audio.py`: Reproducción, validación y control de archivos MP3 de canciones.
   - `clientes.py`: Búsqueda y fichas de compradores y destinatarios.
   - `costos.py`: Simulador y calculador de costos de impresión, cuadros y márgenes.
   - `locales.py`: Integración con herramientas locales de edición y render.
   - `ml_meta.py`: Auditoría del Píxel de Meta, sincronización con publicaciones de MercadoLibre y cargos.
   - `retoque.py`: Control de versiones y cambios pedidos por los clientes en fotos.
   - `servidor.py`: Comunicación bidireccional con la API central de la tienda.
   - `sistema.py`: Monitoreo del estado de procesos del bot y memoria.

---

## ⚙️ Estructura del Proyecto

```text
centralita/
├── servicio.py             # Servidor FastAPI local (127.0.0.1:8790)
├── arrancar.py             # Script de arranque del servicio y navegador
├── centralita.bat          # Lanzador rápido de un clic para Windows
├── prototipo.html          # Interfaz de usuario interactiva
├── servicios/              # Módulos de lógica de negocio y orquestación
│   ├── archivos.py
│   ├── audio.py
│   ├── clientes.py
│   ├── costos.py
│   ├── locales.py
│   ├── ml_meta.py
│   ├── retoque.py
│   ├── servidor.py
│   └── sistema.py
├── static/                 # CSS, JavaScript e iconografía del panel
├── datos/                  # Caché y esquemas de cargos
├── capturas/               # Capturas de auditoría de procesos
└── tests/                  # Suite de pruebas unitarias y de integración
```

---

## 📦 Puesta en Marcha

1. **Lanzar la centralita:**
   Hacer doble clic en `centralita.bat` o ejecutar:
   ```bash
   python arrancar.py
   ```

2. **Acceso al panel:**
   Abrir en el navegador: `http://127.0.0.1:8790/`

---

## 🌐 Identidad de Marca

Este proyecto forma parte del ecosistema oficial de **Tu Tiendita IA**  
Sitio Web: [tutiendita-ia.store](https://tutiendita-ia.store)
