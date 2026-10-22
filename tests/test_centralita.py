"""Pruebas unitarias y de integración de la Centralita (sin red y sin tocar C:\\Pedidos)."""
import datetime
import io
import json
import os
import pathlib
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import sys
AQUI = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent / "produccion"))
sys.path.insert(0, str(AQUI.parent / "tienda" / "herramientas"))

import carpetas
from servicio import app
from servicios import archivos, audio, clientes, costos, locales, retoque, servidor


@pytest.fixture
def entorno_centralita(tmp_path, monkeypatch):
    # Carpetas temporales aisladas
    pedidos_dir = tmp_path / "Pedidos"
    pedidos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(carpetas, "PEDIDOS", pedidos_dir)
    monkeypatch.setattr(locales, "ruta_pedidos", lambda: pedidos_dir)

    # Base de datos o servidor falso
    pedidos_falsos = [
        {
            "id": "RF-0001", "marca": "rf", "producto": "rf-foto-1", "precio": 5000,
            "estado": "pagado", "nombre": "Laura Gómez", "email": "laura@gmail.com",
            "whatsapp": "5491155550001", "creado": "2026-10-14T00:00:00+00:00",
            "pagado": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "datos": {"color": "A color"}, "vista_n": 0
        },
        {
            "id": "TC-0001", "marca": "tc", "producto": "tc-cancion", "precio": 27000,
            "estado": "pagado", "nombre": "Carlos Gómez", "email": "carlos@gmail.com",
            "whatsapp": "5491155550002", "creado": "2026-10-14T00:00:00+00:00",
            "pagado": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "datos": {"para_quien": "Marta"}, "vista_n": 0
        }
    ]

    bot_estado = {}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")
    (pedidos_dir / "bot.log").write_text("2026-10-14 00:00:00,000 Bot iniciado.\n", encoding="utf-8")

    monkeypatch.setattr(servidor, "obtener_pedidos", lambda estado=None: pedidos_falsos)
    monkeypatch.setattr(servidor, "obtener_pedido", lambda pid: next((p for p in pedidos_falsos if p["id"] == pid), None))
    monkeypatch.setattr(servidor, "obtener_costos", lambda: {"productos": {}, "proveedores": {"publicaciones": []}})
    monkeypatch.setattr(servidor, "obtener_pagos", lambda desde=None: [])

    c = TestClient(app, base_url="http://127.0.0.1:8790")
    return c, pedidos_dir, pedidos_falsos, bot_estado


def test_seguridad_x_centralita_y_host(entorno_centralita):
    c, _, _, _ = entorno_centralita

    # Falta encabezado X-Centralita -> 403
    r = c.get("/api/hoy")
    assert r.status_code == 403

    # Con encabezado X-Centralita: 1 -> 200
    r = c.get("/api/hoy", headers={"X-Centralita": "1"})
    assert r.status_code == 200


def test_rutas_fuera_de_carpeta_devuelven_400(entorno_centralita):
    c, pedidos_dir, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    # Crear carpeta del pedido
    p_dir = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    p_dir.mkdir(parents=True, exist_ok=True)
    (p_dir / "historial.txt").write_text("Creado", encoding="utf-8")

    # Intentar subir con ..
    r = c.get("/api/pedidos/RF-0001/archivo?ruta=../secreto.txt", headers=adm)
    assert r.status_code == 400

    # Intentar ruta absoluta de Windows
    r = c.get("/api/pedidos/RF-0001/archivo?ruta=C:/Windows/win.ini", headers=adm)
    assert r.status_code == 400


def test_columnas_y_que_falta_segun_tabla(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, bot_estado = entorno_centralita
    adm = {"X-Centralita": "1"}

    # Caso 1: est.intentos >= 3 -> "El bot se frenó"
    p_dir1 = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    p_dir1.mkdir(parents=True, exist_ok=True)
    (p_dir1 / "historial.txt").write_text("[14/10/2026 10:00] Error al conectar\n", encoding="utf-8")

    bot_estado["RF-0001"] = {"intentos": 3}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    pedidos = c.get("/api/pedidos", headers=adm).json()
    p1 = next(p for p in pedidos if p["id"] == "RF-0001")
    assert p1["col"] == "turno"
    assert "El bot se frenó" in p1["falta"]

    # Caso 2: RF en cambio y est.cambio_en_espera == p.cambios -> "El bot no entendió el cambio"
    pedidos_falsos[0]["estado"] = "cambio"
    pedidos_falsos[0]["cambios"] = 1
    pedidos_falsos[0]["nota_cambio"] = "aclarar el suéter"
    bot_estado["RF-0001"] = {"intentos": 0, "cambio_en_espera": 1}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    pedidos = c.get("/api/pedidos", headers=adm).json()
    p1 = next(p for p in pedidos if p["id"] == "RF-0001")
    assert p1["col"] == "turno"
    assert "El bot no entendió el cambio: «aclarar el suéter»" in p1["falta"]

    # Caso 3: TC en pagado o cambio y est.letra_n > est.previa_subida -> "Letra vN lista..."
    bot_estado["TC-0001"] = {"letra_n": 2, "previa_subida": 1}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    pedidos = c.get("/api/pedidos", headers=adm).json()
    p2 = next(p for p in pedidos if p["id"] == "TC-0001")
    assert p2["col"] == "turno"
    assert "Letra v2 lista" in p2["falta"]

    # Caso 4: TC en aprobado sin MP3 en 4-entrega -> "Aprobó: falta la descarga oficial de Suno"
    pedidos_falsos[1]["estado"] = "aprobado"
    bot_estado["TC-0001"] = {"letra_n": 2, "previa_subida": 2}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")
    p_dir2 = pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez"
    p_dir2.mkdir(parents=True, exist_ok=True)
    (p_dir2 / "4-entrega").mkdir(exist_ok=True)

    pedidos = c.get("/api/pedidos", headers=adm).json()
    p2 = next(p for p in pedidos if p["id"] == "TC-0001")
    assert p2["col"] == "turno"
    assert "Aprobó: falta la descarga oficial de Suno" in p2["falta"]

    # Caso 5: RF entregado con "Falta comprar el cuadro" en el historial y sin "Cuadro comprado"
    pedidos_falsos[0]["estado"] = "entregado"
    pedidos_falsos[0]["producto"] = "rf-cuadro-ecocuero-20x30"
    (p_dir1 / "historial.txt").write_text("[14/10/2026 12:00] Entregado. Falta comprar el cuadro.\n", encoding="utf-8")
    bot_estado["RF-0001"] = {"intentos": 0}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    pedidos = c.get("/api/pedidos", headers=adm).json()
    p1 = next(p for p in pedidos if p["id"] == "RF-0001")
    assert p1["col"] == "turno"
    assert "Comprar el cuadro" in p1["falta"]


def test_plazos(entorno_centralita):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    # Pedido RF creado hace 10 minutos (plazo 2 h -> nivel "ok")
    ahora_dt = datetime.datetime.now(datetime.timezone.utc)
    pedidos_falsos[0]["estado"] = "pagado"
    pedidos_falsos[0]["pagado"] = (ahora_dt - datetime.timedelta(minutes=10)).isoformat()
    pedidos_falsos[0]["vista_n"] = 0

    r = c.get("/api/pedidos", headers=adm).json()
    p = next(x for x in r if x["id"] == "RF-0001")
    assert p["plazo"]["plazo_h"] == 2
    assert p["plazo"]["nivel"] == "ok"

    # Pedido RF creado hace 80 minutos (más del 60% de 2 h -> nivel "aviso")
    pedidos_falsos[0]["pagado"] = (ahora_dt - datetime.timedelta(minutes=80)).isoformat()
    r = c.get("/api/pedidos", headers=adm).json()
    p = next(x for x in r if x["id"] == "RF-0001")
    assert p["plazo"]["nivel"] == "aviso"

    # Pedido RF creado hace 150 minutos (vencido -> nivel "critico")
    pedidos_falsos[0]["pagado"] = (ahora_dt - datetime.timedelta(minutes=150)).isoformat()
    r = c.get("/api/pedidos", headers=adm).json()
    p = next(x for x in r if x["id"] == "RF-0001")
    assert p["plazo"]["nivel"] == "critico"
    assert "Vencido" in p["plazo"]["texto"]


def test_sincronizacion_suno_y_letras(entorno_centralita):
    c, pedidos_dir, pedidos_falsos, bot_estado = entorno_centralita
    adm = {"X-Centralita": "1"}

    p_dir = pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez"
    carpeta_letra = p_dir / "2-letra"
    carpeta_letra.mkdir(parents=True, exist_ok=True)

    # Letra versión 1 existente
    bot_estado["TC-0001"] = {"letra_n": 1}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    v1 = {
        "titulo": "Para Marta",
        "letra": "Marta querida\nsiempre en mi vida",
        "estilo": "Argentine bolero, 75 bpm",
        "excluir": "drums, synths",
        "foneticas": ""
    }
    (carpeta_letra / "letra-v1.txt").write_text(v1["letra"], encoding="utf-8")
    (carpeta_letra / "version-v1.json").write_text(json.dumps({**v1, "revisor": "Claude", "correcciones": []}), encoding="utf-8")
    (carpeta_letra / "suno.txt").write_text(
        f"TÍTULO: {v1['titulo']}\n\nSTYLE OF MUSIC:\n{v1['estilo']}\n\nLYRICS:\n{v1['letra']}\n\nFONÉTICA: -",
        encoding="utf-8"
    )

    # Modificar suno.txt cambiando la letra y el estilo
    suno_modificado = (
        "TÍTULO: Para Marta\n\nSTYLE OF MUSIC:\nArgentine zamba, 60 bpm\n\n"
        "EXCLUDE STYLES (en Más opciones):\nelectric guitar\n\n"
        "LYRICS:\nMarta querida\nhoy te cantamos esta zamba\n\nFONÉTICA: -"
    )
    r = c.put("/api/pedidos/TC-0001/archivo?ruta=2-letra/suno.txt", headers=adm,
              json={"contenido": suno_modificado})
    assert r.status_code == 200 and r.json()["ok"] is True

    # Verificar que letra-v1.txt y version-v1.json se hayan actualizado sincronizados
    assert (carpeta_letra / "letra-v1.txt").read_text(encoding="utf-8") == "Marta querida\nhoy te cantamos esta zamba"
    v1_actual = json.loads((carpeta_letra / "version-v1.json").read_text(encoding="utf-8"))
    assert v1_actual["estilo"] == "Argentine zamba, 60 bpm"
    assert v1_actual["excluir"] == "electric guitar"
    assert v1_actual["revisor"] == "Claude"  # conservó metadato extra
    assert "Editaste a mano suno.txt" in (p_dir / "historial.txt").read_text(encoding="utf-8")


def test_clasificacion_archivos_y_solo_lectura_entregado(entorno_centralita):
    c, pedidos_dir, pedidos_falsos, bot_estado = entorno_centralita
    adm = {"X-Centralita": "1"}

    p_dir = pedidos_dir / "TC" / "Listos" / "TC-0001 - Carlos Gómez"
    p_dir.mkdir(parents=True, exist_ok=True)
    (p_dir / "historial.txt").write_text("Historial", encoding="utf-8")
    (p_dir / "2-letra").mkdir(exist_ok=True)
    (p_dir / "2-letra" / "suno.txt").write_text("suno", encoding="utf-8")

    pedidos_falsos[1]["estado"] = "entregado"

    archs = c.get("/api/pedidos/TC-0001/archivos", headers=adm).json()
    suno = next(a for a in archs if a["ruta"] == "2-letra/suno.txt")
    assert suno["editable"] is False  # pedido entregado: solo lectura

    # Si intenta guardar archivo en pedido entregado -> 400
    r = c.put("/api/pedidos/TC-0001/archivo?ruta=2-letra/suno.txt", headers=adm, json={"contenido": "nuevo"})
    assert r.status_code == 400


def test_retoque_mueve_version_vieja_a_anteriores(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    pedidos_falsos[0]["estado"] = "vista_previa"   # con el pedido en pagado el bot está trabajando: 409

    p_dir = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    codex_dir = p_dir / "2-codex"
    codex_dir.mkdir(parents=True, exist_ok=True)

    # Crear foto original simulada
    (p_dir / "1-original").mkdir(parents=True, exist_ok=True)
    im_orig = Image.new("RGB", (200, 200), (255, 0, 0))
    im_orig.save(p_dir / "1-original" / "foto-01.jpg")

    # Crear versión previa foto-01.png
    im_previa = Image.new("RGB", (200, 200), (0, 255, 0))
    im_previa.save(codex_dir / "foto-01.png")

    # Mockear fotos.procesar para no requerir Real-ESRGAN
    procesadas = []
    import fotos
    monkeypatch.setattr(fotos, "procesar", lambda pedido, estado="Pendientes", solo=None: procesadas.append((pedido, solo)))

    # Subir retoque en PNG
    im_retoque = Image.new("RGB", (200, 200), (0, 0, 255))
    buf = io.BytesIO()
    im_retoque.save(buf, format="PNG")
    buf.seek(0)

    r = c.post("/api/pedidos/RF-0001/retoque", headers=adm,
               data={"foto_stem": "foto-01"},
               files={"imagen": ("retoque.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200

    # Verificar que foto-01-v1.png está en 2-codex/anteriores/
    assert (codex_dir / "anteriores" / "foto-01-v1.png").exists()
    assert (codex_dir / "foto-01.png").exists()
    assert len(procesadas) == 1
    assert procesadas[0][1] == ["foto-01"]


def test_numeracion_vistas_previas(entorno_centralita, tmp_path):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    p_dir = pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez"
    p_dir.mkdir(parents=True, exist_ok=True)

    # Generar un archivo WAV sintético usando ffmpeg
    wav_path = tmp_path / "audio_test.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", "2", str(wav_path)], check=True, capture_output=True)

    # Primera subida -> v1-previa.mp3
    with open(wav_path, "rb") as f:
        r = c.post("/api/pedidos/TC-0001/audio", headers=adm, files={"archivo_subido": ("p1.wav", f, "audio/wav")})
    assert r.status_code == 200
    assert r.json()["k"] == 1
    assert (p_dir / "3-vistas-previas" / "v1-previa.mp3").exists()

    # Segunda subida -> v2-previa.mp3
    with open(wav_path, "rb") as f:
        r = c.post("/api/pedidos/TC-0001/audio", headers=adm, files={"archivo_subido": ("p2.wav", f, "audio/wav")})
    assert r.status_code == 200
    assert r.json()["k"] == 2
    assert (p_dir / "3-vistas-previas" / "v2-previa.mp3").exists()


# ---------------- Correcciones de la revisión de Claude (14/10) ----------------
def test_host_exacto(entorno_centralita):
    c, _, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    assert c.get("/api/hoy", headers={**adm, "Host": "evil.example:8790"}).status_code == 403
    assert c.get("/api/hoy", headers={**adm, "Host": "127.0.0.1:9999"}).status_code == 403
    assert c.get("/api/hoy", headers={**adm, "Host": "localhost:8790"}).status_code == 200


def test_no_manda_token_del_cliente_al_navegador(entorno_centralita):
    c, _, pedidos_falsos, _ = entorno_centralita
    pedidos_falsos[0]["cliente_token"] = "secreto-del-cliente"
    pedidos_falsos[0]["mp_pago"] = "123"
    texto = c.get("/api/pedidos", headers={"X-Centralita": "1"}).text
    assert "secreto-del-cliente" not in texto and "mp_pago" not in texto


def test_entregados_viejos_solo_al_buscar(entorno_centralita):
    c, _, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    pedidos_falsos[0].update(estado="entregado", entregado="2026-08-01T10:00:00+00:00")
    assert "RF-0001" not in [p["id"] for p in c.get("/api/pedidos", headers=adm).json()]
    assert "RF-0001" in [p["id"] for p in c.get("/api/pedidos?q=laura", headers=adm).json()]


def test_retoque_rechaza_nombres_raros_y_pedido_con_bot(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    p_dir = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    (p_dir / "2-codex").mkdir(parents=True)
    Image.new("RGB", (20, 20)).save(p_dir / "2-codex" / "foto-01.png")
    import fotos
    monkeypatch.setattr(fotos, "procesar", lambda *a, **k: None)
    png = io.BytesIO()
    Image.new("CMYK", (20, 20)).save(png, format="JPEG")
    imagen = {"imagen": ("r.jpg", png.getvalue(), "image/jpeg")}

    # Pedido en pagado sin bot frenado: el bot está trabajando
    assert c.post("/api/pedidos/RF-0001/retoque", headers=adm, data={"foto_stem": "foto-01"}, files=imagen).status_code == 409
    pedidos_falsos[0]["estado"] = "vista_previa"
    for raro in (r"..\..\x", "../x", "foto-99"):
        r = c.post("/api/pedidos/RF-0001/retoque", headers=adm, data={"foto_stem": raro}, files=imagen)
        assert r.status_code == 400, raro
    # Un JPEG en CMYK se guarda igual como PNG
    assert c.post("/api/pedidos/RF-0001/retoque", headers=adm, data={"foto_stem": "foto-01"}, files=imagen).status_code == 200
    assert Image.open(p_dir / "2-codex" / "foto-01.png").mode == "RGB"


def test_audio_con_nombre_peligroso_no_sale_de_su_lugar(entorno_centralita, tmp_path):
    c, pedidos_dir, _, _ = entorno_centralita
    (pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez").mkdir(parents=True)
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(wav)],
                   check=True, capture_output=True)
    r = c.post("/api/pedidos/TC-0001/audio", headers={"X-Centralita": "1"},
               files={"archivo_subido": (r"..\..\..\escapado.wav", wav.read_bytes(), "audio/wav")})
    assert r.status_code == 200
    assert not list(tmp_path.rglob("escapado*")) and not list(pedidos_dir.rglob("*escapado*"))


def test_final_limpia_nombre_y_guarda_el_anterior(entorno_centralita, tmp_path):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    pedidos_falsos[1]["estado"] = "aprobado"
    entrega = pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez" / "4-entrega"
    entrega.mkdir(parents=True)
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(wav)],
                   check=True, capture_output=True)
    adm = {"X-Centralita": "1"}
    for para in ("Marta", r"..\..\Ma:rta?"):
        r = c.post("/api/pedidos/TC-0001/audio", headers=adm, data={"para": para},
                   files={"archivo_subido": ("final.wav", wav.read_bytes(), "audio/wav")})
        assert r.status_code == 200, r.text
    assert [f.name for f in entrega.glob("*.mp3")] == ["Tu canción para Marta.mp3"]   # una sola: la que entrega el bot
    assert (entrega / "anteriores" / "Tu canción para Marta-v1.mp3").exists()


def test_suno_campos_vaciados_y_novedad(entorno_centralita):
    c, pedidos_dir, _, bot_estado = entorno_centralita
    carpeta_letra = pedidos_dir / "TC" / "Pendientes" / "TC-0001 - Carlos Gómez" / "2-letra"
    carpeta_letra.mkdir(parents=True)
    bot_estado["TC-0001"] = {"letra_n": 2, "previa_subida": 1}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")
    import letras
    letras.guardar_version(carpeta_letra, 2, {"titulo": "T", "letra": "la la", "estilo": "bolero", "excluir": "drums",
                                              "foneticas": ""}, {"revisor": "Claude"}, "más lento")
    texto = (carpeta_letra / "suno.txt").read_text(encoding="utf-8")
    sin_excluir = texto.replace("\n\nEXCLUDE STYLES (en Más opciones):\ndrums", "")
    r = c.put("/api/pedidos/TC-0001/archivo?ruta=2-letra/suno.txt", headers={"X-Centralita": "1"},
              json={"contenido": sin_excluir})
    assert r.status_code == 200, r.text
    v = json.loads((carpeta_letra / "version-v2.json").read_text(encoding="utf-8"))
    assert v["excluir"] == "" and v["revisor"] == "Claude"
    assert "QUÉ CAMBIA EN LA v2: más lento" in (carpeta_letra / "suno.txt").read_text(encoding="utf-8")
    # Sin las secciones no guarda (no pisa la letra con un texto vacío)
    r = c.put("/api/pedidos/TC-0001/archivo?ruta=2-letra/suno.txt", headers={"X-Centralita": "1"},
              json={"contenido": "cualquier cosa"})
    assert r.status_code == 422
    assert (carpeta_letra / "letra-v2.txt").read_text(encoding="utf-8") == "la la"


def test_reconoce_solo_el_bot_de_la_tienda(monkeypatch):
    from servicios import sistema
    procesos = []

    class R:
        @property
        def stdout(self):
            return json.dumps(procesos)
    monkeypatch.setattr(sistema.subprocess, "run", lambda *a, **k: R())
    otro = {"ProcessId": 11, "CommandLine": r"pythonw.exe C:\otro\roast\bot.py"}
    tests = {"ProcessId": 13, "CommandLine": r"python.exe -m pytest tests\test_bot.py"}
    suelto = {"ProcessId": 14, "CommandLine": r'"C:\Python311\pythonw.exe" bot.py'}
    tienda = {"ProcessId": 12, "CommandLine": r'"C:\Python311\pythonw.exe" C:\RegalosIA\tienda\herramientas\bot.py'}
    procesos[:] = [otro, tests]
    assert sistema.procesos_bot() == []
    procesos[:] = [otro, tests, suelto]
    assert sistema.procesos_bot() == [14]          # arrancado a mano desde tienda\herramientas
    procesos[:] = [otro, suelto, tienda]
    assert sistema.procesos_bot() == [12]          # con la ruta completa no hay dudas
    procesos[:] = [tienda]                          # PowerShell devuelve un objeto suelto cuando hay uno solo
    monkeypatch.setattr(json, "loads", lambda s, _l=json.loads: _l(s)[0] if s.startswith("[") else _l(s))
    assert sistema.procesos_bot() == [12]


# ---------------- FASE 2: PLATA Y COSTOS REALES ----------------
def test_plata_totales_filas_incompletas_y_medios(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    from servicios import costos, servidor

    pedidos_falsos[0]["producto"] = "rf-cuadro-ecocuero-20x30"
    pedidos_falsos[0]["precio"] = 34900

    pagos_falsos = [
        {
            "pedido": "RF-0001", "producto": "rf-cuadro-ecocuero-20x30", "precio": 34900,
            "pago": "1001", "estado": "approved", "detalle": "accredited",
            "medio": "account_money", "tipo_medio": "account_money", "cuotas": 1,
            "monto": 34900.0,
            "comisiones": [{"tipo": "mercadopago_fee", "monto": 1500.70, "a_cargo": "collector"}],
            "neto": 33399.30, "reembolsado": 0.0,
            "liberacion": {"fecha": "2026-11-01T00:00:00+00:00", "estado": "pending"},
            "aprobado": "2026-10-14T10:00:00+00:00"
        },
        {
            "pedido": "TC-0001", "producto": "tc-cancion", "precio": 27000,
            "pago": "1002", "estado": "approved", "detalle": "accredited",
            "medio": "credit_card", "tipo_medio": "credit_card", "cuotas": 1,
            "monto": 27000.0,
            "comisiones": [{"tipo": "mercadopago_fee", "monto": 1750.00, "a_cargo": "collector"}],
            "neto": 25250.00, "reembolsado": 0.0,
            "liberacion": {"fecha": "2026-10-20T00:00:00+00:00", "estado": "released"},
            "aprobado": "2026-10-14T11:00:00+00:00"
        }
    ]
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: pagos_falsos)

    # 1. Consulta sin costo de cuadro cargado a mano
    r = c.get("/api/plata", headers=adm)
    assert r.status_code == 200
    data = r.json()

    filas = data["filas"]
    assert len(filas) == 2

    # Fila de cuadro sin monto cargado: incompleta
    f_cuadro = next(f for f in filas if f["pedido"] == "RF-0001")
    assert f_cuadro["proveedor_texto"] == "sin dato"
    assert "sin dato" in f_cuadro["te_quedo_texto"]
    assert f_cuadro["te_quedo_monto"] is None
    assert f_cuadro["completa"] is False

    # Fila de canción: completa sin proveedor
    f_cancion = next(f for f in filas if f["pedido"] == "TC-0001")
    assert f_cancion["proveedor_texto"] == "—"
    assert f_cancion["te_quedo_monto"] == 25250.0
    assert f_cancion["completa"] is True

    # Totales solo con filas completas: solo suma TC-0001
    tot = data["totales"]
    assert tot["cobrado"] == 27000.0
    assert tot["comisiones"] == 1750.0
    assert tot["te_quedo"] == 25250.0
    assert tot["filas_incompletas"] == 1

    # Resumen agrupado por medio
    rmp = data["resumen_mp"]
    assert len(rmp["grupos"]) == 2
    g_dinero = next(g for g in rmp["grupos"] if g["clave"] == "account_money")
    assert g_dinero["cantidad"] == 1
    assert round(g_dinero["porcentaje_real"], 2) == round((1500.70 / 34900.0) * 100, 2)

    # 2. Cargar costo a mano para el cuadro
    costos.guardar_costo_proveedor("RF-0001", 17999)
    r2 = c.get("/api/plata", headers=adm)
    data2 = r2.json()
    f_cuadro2 = next(f for f in data2["filas"] if f["pedido"] == "RF-0001")
    assert f_cuadro2["completa"] is True
    assert f_cuadro2["proveedor_monto"] == 17999.0
    assert f_cuadro2["te_quedo_monto"] == round(33399.30 - 17999.0, 2)
    assert data2["totales"]["filas_incompletas"] == 0
    assert data2["totales"]["cobrado"] == 34900.0 + 27000.0


def test_costos_sin_dinero_cuenta_simulado_y_cache(entorno_centralita, monkeypatch, tmp_path):
    c, pedidos_dir, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    from servicios import costos, servidor

    # Cache aislada
    datos_tmp = tmp_path / "datos"
    datos_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(costos, "DATOS_DIR", datos_tmp)
    monkeypatch.setattr(costos, "CACHE_ML_RUTA", datos_tmp / "ml-cargos.json")

    # Caso 1: sin pagos de dinero en cuenta -> no calcula a cuánto publicar
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: [])
    monkeypatch.setattr(servidor, "obtener_costos", lambda: {
        "productos": {"rf-pack-5": {"nombre": "Pack 5 fotos", "precio": 15000}},
        "proveedores": {"publicaciones": []}
    })
    r = c.get("/api/costos", headers=adm)
    assert r.status_code == 200
    res = r.json()
    p_pack = res["productos"][0]
    assert p_pack["ml"]["publicar_igual_web"]["clasica"] is None
    assert "hace falta un cobro real" in p_pack["ml"]["publicar_igual_web"]["motivo"]

    # Caso 2: Categoria null (ej: cancion) -> motivo sin dato: falta la categoria
    sim_cancion = c.post("/api/costos/simular", headers=adm, json={"precio": 27000, "producto": "tc-cancion"}).json()
    assert sim_cancion["publicar_igual_web"]["clasica"] is None
    assert "falta la categoría de ML" in sim_cancion["publicar_igual_web"]["motivo"]

    # Caso 3: Simulado con listing_prices y calculo de a cuánto publicar
    pagos_con_dinero = [{
        "pedido": "RF-0001", "monto": 500.0, "estado": "approved",
        "tipo_medio": "account_money", "medio": "account_money", "cuotas": 1,
        "comisiones": [{"tipo": "mercadopago_fee", "monto": 21.51}],
        "neto": 478.49
    }]
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: pagos_con_dinero)

    llamadas_ml = []
    def fake_ml_get(path, **params):
        llamadas_ml.append((path, params))
        p = float(params.get("price", 10000))
        return [
            {
                "listing_type_id": "gold_special",
                "sale_fee_amount": round(p * 0.16 + 2740.0, 2),
                "sale_fee_details": {"percentage_fee": 16.0, "fixed_fee": 2740.0}
            },
            {
                "listing_type_id": "gold_pro",
                "sale_fee_amount": round(p * 0.294 + 2740.0, 2),
                "sale_fee_details": {"percentage_fee": 29.4, "fixed_fee": 2740.0}
            }
        ]
    import ml_api
    monkeypatch.setattr(ml_api, "get", fake_ml_get)

    calc = costos.calcular_precio_publicar_ml(15000, "MLA434385", pct_dinero_cuenta=4.30)
    assert calc["clasica"] is not None
    assert calc["clasica"]["precio_igual_web"] % 1000 == 900
    assert calc["clasica"]["precio_igual_web"] == 20900

    # Caso 4: Caché de 24h y botón actualizar
    costos.borrar_cache_ml()
    llamadas_ml.clear()
    c1 = costos.consultar_cargos_ml(15000, "MLA434385")
    assert len(llamadas_ml) == 1
    c2 = costos.consultar_cargos_ml(15000, "MLA434385")
    assert len(llamadas_ml) == 1  # Vino de caché
    assert (datos_tmp / "ml-cargos.json").is_file()

    # Actualizar desde las APIs invalida la caché
    r_act = c.post("/api/costos/actualizar", headers=adm)
    assert r_act.status_code == 200
    assert not (datos_tmp / "ml-cargos.json").is_file()
    c3 = costos.consultar_cargos_ml(15000, "MLA434385")
    assert len(llamadas_ml) == 2  # Volvió a llamar


def test_cuadro_monto_guardar_corregir_y_atomico(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    pedidos_falsos[0]["producto"] = "rf-cuadro-ecocuero-20x30"     # solo los pedidos con cuadro aceptan el monto

    p_dir = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    p_dir.mkdir(parents=True, exist_ok=True)
    historial_file = p_dir / "historial.txt"
    historial_file.write_text("Creado\n", encoding="utf-8")

    # 1. Guardar cuadro comprado con monto
    r1 = c.post("/api/pedidos/RF-0001/cuadro-comprado", headers=adm, json={
        "seguimiento": "MEL-123456",
        "pagado": 25000
    })
    assert r1.status_code == 200
    hist = historial_file.read_text(encoding="utf-8")
    assert "Cuadro comprado. Pagaste $25.000. Seguimiento MEL-123456." in hist

    # Verificar archivo costos-proveedor.json
    costos_file = pedidos_dir / "costos-proveedor.json"
    assert costos_file.is_file()
    assert not (pedidos_dir / "costos-proveedor.tmp").exists()
    data_costos = json.loads(costos_file.read_text(encoding="utf-8"))
    assert data_costos["RF-0001"]["pagado"] == 25000
    assert data_costos["RF-0001"]["fuente"] == "cargado a mano"

    # 2. Corregir monto pagado
    r2 = c.post("/api/pedidos/RF-0001/cuadro-comprado", headers=adm, json={
        "seguimiento": "MEL-123456",
        "pagado": 24500
    })
    assert r2.status_code == 200
    hist2 = historial_file.read_text(encoding="utf-8")
    assert "corregiste lo que pagaste: $25.000 → $24.500." in hist2
    data_costos2 = json.loads(costos_file.read_text(encoding="utf-8"))
    assert data_costos2["RF-0001"]["pagado"] == 24500


def test_reintentar_pedido_frenado(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, bot_estado = entorno_centralita
    adm = {"X-Centralita": "1"}
    import bot

    monkeypatch.setattr(bot, "ESTADO", pedidos_dir / "bot-estado.json")
    monkeypatch.setattr(bot, "PEDIDOS", pedidos_dir)

    p_dir = pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez"
    p_dir.mkdir(parents=True, exist_ok=True)
    historial_file = p_dir / "historial.txt"
    historial_file.write_text("Creado\n", encoding="utf-8")

    # Pedido frenado (intentos >= 3)
    bot_estado["RF-0001"] = {"intentos": 3}
    (pedidos_dir / "bot-estado.json").write_text(json.dumps(bot_estado), encoding="utf-8")

    # Pedir reintento desde la centralita
    r = c.post("/api/pedidos/RF-0001/reintentar", headers=adm)
    assert r.status_code == 200
    reintentar_file = p_dir / "reintentar.txt"
    assert reintentar_file.is_file()
    assert "Reintento pedido desde la centralita" in historial_file.read_text(encoding="utf-8")

    # En la centralita, el estado de falta muestra el aviso de reintento
    pedidos_ui = c.get("/api/pedidos", headers=adm).json()
    p_rf = next(p for p in pedidos_ui if p["id"] == "RF-0001")
    assert "Reintento pedido: el bot lo toma en su próxima vuelta" in p_rf["falta"]
    assert p_rf["bot_frenado"] is False

    # Ahora simular la pasada del bot
    pasos_ejecutados = []
    monkeypatch.setattr(bot, "paso", lambda det, est: pasos_ejecutados.append(det["id"]))

    class FakeCliente:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def get(self, path):
            class Resp:
                def raise_for_status(self):
                    return self
                def json(self):
                    return pedidos_falsos
            return Resp()

    monkeypatch.setattr(bot, "api", lambda: FakeCliente())
    monkeypatch.setattr(bot, "detalle", lambda pid: next(p for p in pedidos_falsos if p["id"] == pid))

    bot.pasada()

    # El bot debe haber reseteado intentos a 0, movido el archivo a 0-analisis y procesado el pedido
    assert not reintentar_file.exists()
    archivos_analisis = list((p_dir / "0-analisis").glob("reintentar-*.txt"))
    assert len(archivos_analisis) == 1
    assert "RF-0001" in pasos_ejecutados


def test_privacidad_sin_datos_pagador_ni_token(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    from servicios import servidor

    pagos_sucios = [{
        "pedido": "RF-0001",
        "monto": 500.0,
        "neto": 478.49,
        "aprobado": "2026-10-14T00:00:00Z",
        "comisiones": [{"tipo": "mercadopago_fee", "monto": 21.51}],
        "payer": {
            "email": "juan_perez_secreto@gmail.com",
            "identification": {"number": "99887766"},
            "first_name": "Juan",
            "last_name": "Pérez"
        },
        "card": {
            "last_four_digits": "4321",
            "cardholder": {"name": "Juan Pérez"}
        },
        "token_mp": "APP_USR-secreto-token-9999"
    }]
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: pagos_sucios)

    for ruta in ("/api/plata", "/api/costos", "/api/hoy", "/api/pedidos", "/api/sistema"):
        res = c.get(ruta, headers=adm)
        assert res.status_code == 200
        texto = res.text
        assert "juan_perez_secreto" not in texto
        assert "99887766" not in texto
        assert "4321" not in texto
        assert "APP_USR" not in texto
        assert "cardholder" not in texto


# ---------------- Correcciones de la revisión de Claude de la fase 2 ----------------
def _pago(pid, producto, monto, fee, tipo="account_money", estado="approved", **extra):
    return {"pedido": pid, "producto": producto, "precio": int(monto), "pago": pid + "-p", "estado": estado,
            "detalle": "accredited", "medio": tipo, "tipo_medio": tipo, "cuotas": 1, "monto": float(monto),
            "comisiones": [{"tipo": "mercadopago_fee", "monto": fee, "a_cargo": "collector"}],
            "neto": round(monto - fee, 2), "reembolsado": 0.0,
            "liberacion": {"fecha": "2026-11-01T00:00:00+00:00", "estado": "pending"},
            "aprobado": "2026-10-14T10:00:00+00:00", **extra}


def test_plata_no_inventa_pagos_con_error_ni_reembolsos(entorno_centralita, monkeypatch):
    c, _, pedidos_falsos, _ = entorno_centralita
    pagos = [
        _pago("TC-0001", "tc-cancion", 500, 21.51),
        _pago("RF-0001", "rf-foto-1", 500, 21.51, estado="refunded", reembolsado=500.0),
        {"pedido": "RF-0002", "producto": "rf-foto-1", "precio": 500, "pago": "9", "error": "Mercado Pago 500"},
    ]
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: pagos)
    data = c.get("/api/plata", headers={"X-Centralita": "1"}).json()
    filas = {f["pedido"]: f for f in data["filas"]}
    assert filas["RF-0002"]["cobrado"] is None and "no respondió" in filas["RF-0002"]["te_quedo_texto"]
    assert filas["RF-0001"]["cobrado"] is None and "refunded" in filas["RF-0001"]["liberacion"]
    assert data["totales"]["cobrado"] == 500.0 and data["totales"]["filas_incompletas"] == 2
    assert data["totales"]["por_liberar"] == 478.49
    # El % real sale solo del cobro aprobado: 21,51 / 500
    assert data["resumen_mp"]["porcentaje_dinero_cuenta"] == pytest.approx(4.302)
    assert data["resumen_mp"]["fuente"].startswith("tus 1 pagos")


def test_costos_cuadro_sin_lectura_del_vigilante_no_resta_cero(entorno_centralita, monkeypatch):
    c, _, _, _ = entorno_centralita
    monkeypatch.setattr(servidor, "obtener_pagos", lambda: [_pago("TC-0001", "tc-cancion", 500, 21.51)])
    monkeypatch.setattr(servidor, "obtener_costos", lambda: {
        "productos": {"rf-cuadro-ecocuero-20x30": {"nombre": "Cuadro", "precio": 34900}},
        "proveedores": {"leido": None, "publicaciones": []}})
    monkeypatch.setattr(costos, "consultar_cargos_ml", lambda precio, cat, forzar=False: {
        "clasica": {"total": 5000.0, "porcentaje": 14.0, "fijo": 0.0, "financiacion": 0.0},
        "premium": {"total": 9000.0, "porcentaje": 26.0, "fijo": 0.0, "financiacion": 12.0}, "leido": "2026-10-14T10:00:00+00:00"})
    p = c.get("/api/costos", headers={"X-Centralita": "1"}).json()["productos"][0]
    assert p["filas_mp"][0]["te_queda"] is None
    assert p["ml"]["queda_clasica"] is None and p["ml"]["queda_premium"] is None
    assert p["proveedor"]["texto"] == "sin dato"


def test_precio_para_ml_frena_si_ml_no_responde(monkeypatch):
    llamadas = []
    monkeypatch.setattr(costos, "consultar_cargos_ml", lambda *a, **k: llamadas.append(a) or None)
    r = costos.calcular_precio_publicar_ml(44900, "MLA1635", 4.302)
    assert r["clasica"] is None and "no pude consultar" in r["motivo"]
    assert len(llamadas) == 1


def test_reintentar_solo_con_bot_frenado_y_monto_valido(entorno_centralita):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}
    (pedidos_dir / "RF" / "Pendientes" / "RF-0001 - Laura Gómez").mkdir(parents=True)
    assert c.post("/api/pedidos/RF-0001/reintentar", headers=adm).status_code == 409
    assert not list(pedidos_dir.rglob("reintentar.txt"))
    # Monto del cuadro: solo pedidos con cuadro y montos con sentido
    assert c.post("/api/pedidos/RF-0001/cuadro-comprado", headers=adm, json={"pagado": 25000}).status_code == 409
    pedidos_falsos[0]["producto"] = "rf-cuadro-ecocuero-20x30"
    for malo in (0, -5, 99_000_000):
        assert c.post("/api/pedidos/RF-0001/cuadro-comprado", headers=adm, json={"pagado": malo}).status_code == 422
    assert c.post("/api/pedidos/RF-0001/cuadro-comprado", headers=adm, json={"pagado": "25.000"}).status_code == 200
    assert json.loads((pedidos_dir / "costos-proveedor.json").read_text(encoding="utf-8"))["RF-0001"]["pagado"] == 25000


def test_simulador_valida_la_categoria(entorno_centralita):
    c, _, _, _ = entorno_centralita
    r = c.post("/api/costos/simular", headers={"X-Centralita": "1"}, json={"precio": 30000, "categoria": "../users/me"})
    assert r.status_code == 422


def test_agrupar_clientes_por_mail_o_whatsapp():
    peds = [
        {"id": "RF-0001", "nombre": "Ana", "email": "ana@gmail.com", "whatsapp": "011-15-5555-1111", "estado": "aprobado", "creado": "2026-10-01T10:00:00Z", "producto": "rf-foto-1"},
        {"id": "RF-0002", "nombre": "Ana María", "email": "ana@gmail.com", "whatsapp": "11 5555 2222", "estado": "entregado", "creado": "2026-10-05T10:00:00Z", "producto": "rf-foto-2"},
        {"id": "TC-0003", "nombre": "Ana M.", "email": "otra@gmail.com", "whatsapp": "54 9 11 5555-2222", "estado": "aprobado", "creado": "2026-10-10T10:00:00Z", "producto": "tc-cancion"},
        {"id": "RF-0004", "nombre": "Juan", "email": "juan@gmail.com", "whatsapp": "11 5555 3333", "estado": "pendiente_pago", "creado": "2026-10-12T10:00:00Z", "producto": "rf-foto-1"},
        {"id": "RF-0005", "nombre": "Pedro", "email": "pedro@gmail.com", "whatsapp": "11 5555 4444", "estado": "aprobado", "creado": "2026-10-13T10:00:00Z", "producto": "rf-foto-1"},
    ]
    pagos = [
        {"external_reference": "RF-0001", "status": "approved", "transaction_amount": 10000},
        {"external_reference": "RF-0002", "status": "approved", "transaction_amount": 12000},
        {"external_reference": "TC-0003", "status": "approved", "transaction_amount": 25000},
        {"external_reference": "RF-0005", "status": "approved", "transaction_amount": 15000},
    ]
    res = clientes.agrupar_clientes(peds, pagos)
    assert res["total_clientes"] == 2  # Ana (3 pedidos vinculados) y Pedro (1 pedido). Juan excluido por pendiente_pago
    assert res["volvieron_count"] == 1

    ana = next(c for c in res["clientes"] if "ana" in c["email"].lower() or "otra" in c["email"].lower())
    assert ana["pedidos_count"] == 3
    assert ana["total_cobrado"] == 47000
    assert set(ana["marcas"]) == {"fotos", "canción"}
    assert ana["nombre"] == "Ana M."  # nombre del último pedido


def test_agrupar_clientes_total_sin_dato_si_falta_pago():
    peds = [
        {"id": "RF-0001", "nombre": "Carlos", "email": "carlos@gmail.com", "whatsapp": "1155551111", "estado": "aprobado", "creado": "2026-10-01T10:00:00Z", "producto": "rf-foto-1"},
        {"id": "RF-0002", "nombre": "Carlos", "email": "carlos@gmail.com", "whatsapp": "1155551111", "estado": "entregado", "creado": "2026-10-05T10:00:00Z", "producto": "rf-foto-2"},
    ]
    # Solo está el pago del primer pedido; el segundo falta
    pagos = [
        {"external_reference": "RF-0001", "status": "approved", "transaction_amount": 10000},
    ]
    res = clientes.agrupar_clientes(peds, pagos)
    assert res["total_clientes"] == 1
    assert res["clientes"][0]["total_cobrado"] == "sin dato"

    # Si hay pago reembolsado o rechazado también es 'sin dato'
    pagos_con_error = [
        {"external_reference": "RF-0001", "status": "approved", "transaction_amount": 10000},
        {"external_reference": "RF-0002", "status": "approved", "transaction_amount": 12000, "transaction_amount_refunded": 2000},
    ]
    res2 = clientes.agrupar_clientes(peds, pagos_con_error)
    assert res2["clientes"][0]["total_cobrado"] == "sin dato"


def test_proveedores_con_pendiente_y_precio_a_mano(entorno_centralita, monkeypatch):
    c, _, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    estado_prov = {
        "publicaciones": [
            {
                "nombre": "Marco 20x30 ecocuero negro",
                "producto": "rf-cuadro-20x30",
                "marco": "negro",
                "url": "https://articulo.mercadolibre.com.ar/MLA-111",
                "item_id": "MLA111",
                "vendedor": "MOLDURAS",
                "ultima_lectura": {"fecha": "2026-10-14T10:00:00Z", "precio": 8500, "envio": "Llega gratis mañana"},
                "a_mano": None,
                "historial": [{"fecha": "2026-10-14T10:00:00Z", "precio": 8500, "fuente": "vigilante"}]
            }
        ],
        "productos": {
            "rf-cuadro-20x30": {
                "precio_vigente": 24900,
                "pendiente": {
                    "vigente": 24900, "nuevo": 38900, "costo": 13500, "publicacion": "Marco 20x30 ecocuero negro", "fecha": "2026-10-14T10:00:00Z"
                },
                "regla": {"multiplicador": 2.2, "redondeo": 900}
            }
        },
        "comision_mp": 0.08,
        "ultima_revision": "2026-10-14 10:00"
    }

    monkeypatch.setattr(servidor, "obtener_proveedores", lambda: estado_prov)
    monkeypatch.setattr(servidor, "fijar_precio_a_mano", lambda nombre, precio: {"precio": precio, "fecha": "ahora"})
    monkeypatch.setattr(servidor, "quitar_precio_a_mano", lambda nombre: True)
    monkeypatch.setattr(servidor, "aprobar_pendiente", lambda prod: {"precio": 38900})
    monkeypatch.setattr(servidor, "rechazar_pendiente", lambda prod: {"costo": 13500})
    monkeypatch.setattr(servidor, "revisar_vigilante", lambda prueba=False: {"lecturas": []})

    # GET /api/proveedores
    r = c.get("/api/proveedores", headers=adm)
    assert r.status_code == 200
    assert r.json()["publicaciones"][0]["nombre"] == "Marco 20x30 ecocuero negro"
    assert r.json()["productos"]["rf-cuadro-20x30"]["pendiente"]["nuevo"] == 38900

    # POST y DELETE precio a mano
    r_post = c.post("/api/proveedores/Marco 20x30 ecocuero negro/precio", headers=adm, json={"precio": 9200})
    assert r_post.status_code == 200
    assert r_post.json()["precio"] == 9200

    r_del = c.delete("/api/proveedores/Marco 20x30 ecocuero negro/precio", headers=adm)
    assert r_del.status_code == 200

    # Aprobar y rechazar pendiente
    r_aprob = c.post("/api/proveedores/pendientes/rf-cuadro-20x30/aprobar", headers=adm)
    assert r_aprob.status_code == 200
    r_rech = c.post("/api/proveedores/pendientes/rf-cuadro-20x30/rechazar", headers=adm)
    assert r_rech.status_code == 200

    # Revisar vigilante
    r_rev = c.post("/api/proveedores/revisar", headers=adm)
    assert r_rev.status_code == 200


def test_seguimiento_confirmacion_manda_exactamente_lo_mostrado(entorno_centralita, monkeypatch):
    c, pedidos_dir, pedidos_falsos, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    # Simulamos orden con cuadro
    pedidos_falsos[0]["producto"] = "rf-cuadro-ecocuero-20x30"
    pedidos_falsos[0]["nombre"] = "Laura Gómez"
    pedidos_falsos[0]["id"] = "RF-0001"
    pedidos_falsos[0]["estado"] = "entregado"

    # Carpeta del pedido para historial local
    carpeta_ped = pedidos_dir / "RF" / "Listos" / "RF-0001 - Laura Gómez"
    carpeta_ped.mkdir(parents=True, exist_ok=True)
    (carpeta_ped / "historial.txt").write_text("2026-10-14 10:00:00,000 Falta comprar el cuadro\n", encoding="utf-8")

    # Mock del servidor enviar_seguimiento
    enviados = []

    def mock_enviar(pid, numero, url=None, empresa=None, reenviar=False, previa=False):
        # Como el servidor real: con previa=True solo arma el texto; sin previa, guarda y manda (se registra el envío)
        partes = [f"Número de seguimiento: {numero}"]
        if empresa:
            partes[0] += f" ({empresa})"
        if url:
            partes.append(f"seguilo acá: {url}")
        texto_seg = ", ".join(partes) if url else partes[0]
        texto_cliente = f"¡Hola Laura Gómez! Tu cuadro del pedido {pid} ya está en camino. {texto_seg}. Cualquier duda, respondé este mail."
        if previa:
            return {"ok": True, "previa": True, "texto": texto_cliente}
        enviados.append(texto_cliente)
        pedidos_falsos[0]["seguimiento"] = numero
        pedidos_falsos[0]["seguimiento_url"] = url
        return {"ok": True, "texto": texto_cliente, "seguimiento": numero}

    monkeypatch.setattr(servidor, "enviar_seguimiento", mock_enviar)

    datos_envio = {
        "numero": "MEL-98765432",
        "empresa": "Correo Argentino",
        "url": "https://correoargentino.com.ar/tracking/MEL-98765432"
    }

    # 1. Obtenemos vista previa
    r_prev = c.post("/api/pedidos/RF-0001/seguimiento/previa", headers=adm, json=datos_envio)
    assert r_prev.status_code == 200
    texto_mostrado = r_prev.json()["texto"]
    assert "Número de seguimiento: MEL-98765432 (Correo Argentino)" in texto_mostrado
    assert "seguilo acá: https://correoargentino.com.ar" in texto_mostrado

    # 2. Enviamos el seguimiento con los mismos datos
    r_envio = c.post("/api/pedidos/RF-0001/seguimiento", headers=adm, json=datos_envio)
    assert r_envio.status_code == 200
    texto_mandado = r_envio.json()["texto"]

    # 3. Exactamente lo que se mostró en la confirmación es lo que se mandó
    assert texto_mostrado == texto_mandado

    # 4. Historial local anotado
    hist_txt = (carpeta_ped / "historial.txt").read_text(encoding="utf-8")
    assert "Seguimiento enviado al cliente: MEL-98765432" in hist_txt

    # 5. Sale de 'Tu turno' en Hoy porque ya tiene seguimiento
    from servicio import procesar_un_pedido
    p_proc = procesar_un_pedido(pedidos_falsos[0], {}, carpeta_ped)
    assert p_proc["col"] != "turno"
    assert p_proc["col"] == "listo"

    assert enviados == [texto_mostrado]          # se mandó una sola vez y exactamente lo que se mostró

    # El monto pagado mal escrito frena antes de mandar nada
    r_mal = c.post("/api/pedidos/RF-0001/seguimiento", headers=adm, json={**datos_envio, "reenviar": True, "pagado": "-3"})
    assert r_mal.status_code == 422 and len(enviados) == 1


def test_centralita_precios_y_fechas(entorno_centralita, monkeypatch):
    c, _, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    from servicios import servidor
    from app import catalogo

    prod_falsos = [
        {"id": pid, "nombre": catalogo.PRODUCTOS[pid].nombre, "marca": catalogo.PRODUCTOS[pid].marca,
         "precio": catalogo.PRODUCTOS[pid].precio, "con_proveedor": pid in ("rf-cuadro-enmarcado-20x30", "rf-cuadro-enmarcado-30x40", "rf-cuadro-ecocuero-20x30", "rf-cuadro-ecocuero-40x30"),
         "modo": "fijo" if pid == "rf-cuadro-ecocuero-20x30" else ("auto" if "cuadro" in pid else None),
         "ganancia_neta": 5000 if "enmarcado" in pid else None,
         "ganancia_origen": "regla" if "enmarcado" in pid else None}
        for pid in catalogo.PRODUCTOS
    ]

    historial_falso = [
        {"fecha": "2026-10-14T10:00:00Z", "producto": "rf-foto-1", "antes": 5000, "despues": 6000, "quien": "a mano"}
    ]

    monkeypatch.setattr(servidor, "obtener_precios", lambda: {"productos": [dict(p) for p in prod_falsos], "historial": list(historial_falso)})

    cambios_recibidos = []
    def mock_cambiar(prod, datos):
        cambios_recibidos.append((prod, datos))
        p = next(x for x in prod_falsos if x["id"] == prod)
        if "precio" in datos:
            p["precio"] = datos["precio"]
            if p["con_proveedor"]:
                p["modo"] = "fijo"
        elif "modo" in datos:
            p["modo"] = datos["modo"]
            p["ganancia_neta"] = datos.get("ganancia_neta")
            p["ganancia_origen"] = "a mano" if datos.get("ganancia_neta") is not None else "regla"
        return p

    monkeypatch.setattr(servidor, "cambiar_precio_producto", mock_cambiar)

    # 1. GET /api/precios
    r = c.get("/api/precios", headers=adm)
    assert r.status_code == 200
    res = r.json()
    assert len(res["productos"]) == 10  # los 10 productos del catálogo
    p_eco = next(p for p in res["productos"] if p["id"] == "rf-cuadro-ecocuero-20x30")
    assert p_eco["modo"] == "fijo"
    assert "te_queda" in p_eco

    p_suelta = next(p for p in res["productos"] if p["id"] == "rf-foto-1")
    assert p_suelta["con_proveedor"] is False
    assert "te_queda" in p_suelta

    # 2. POST /api/precios/{producto} cambiar precio
    r_cambio = c.post("/api/precios/rf-foto-1", headers=adm, json={"precio": 7000})
    assert r_cambio.status_code == 200
    assert cambios_recibidos[-1] == ("rf-foto-1", {"precio": 7000})

    # Cambiar cuadro a auto con ganancia propia
    r_auto = c.post("/api/precios/rf-cuadro-ecocuero-20x30", headers=adm, json={"modo": "auto", "ganancia_neta": 12000})
    assert r_auto.status_code == 200
    assert cambios_recibidos[-1] == ("rf-cuadro-ecocuero-20x30", {"modo": "auto", "ganancia_neta": 12000})

    # 3. GET /api/fechas
    fechas_mock = {
        "fechas": [
            {"id": 1, "pedido": "RF-0001", "nombre": "Laura", "email": "laura@mail.com", "whatsapp": "1123456789",
             "marca": "rf", "para_quien": "María", "vinculo": "mamá", "tipo": "Cumpleaños", "otra": "",
             "dia": 18, "mes": 10, "creado": "2026-10-14T00:00:00", "proxima": "2026-10-18", "dias_faltan": 4,
             "ultimo_aviso_anio": None, "aviso_enviado_este_anio": False}
        ],
        "cantidades": {
            "por_tipo": {"Cumpleaños": 1},
            "por_vinculo": {"mamá": 1},
            "total": 1
        },
        "fechas_comerciales": [
            {"nombre": "Día de la Madre", "fecha": "2026-10-18", "dia": 18, "mes": 10, "contactos": 1},
            {"nombre": "Día del Padre", "fecha": "2026-06-21", "dia": 21, "mes": 6, "contactos": 0},
            {"nombre": "Día del Niño", "fecha": "2026-08-16", "dia": 16, "mes": 8, "contactos": 1},
            {"nombre": "San Valentín", "fecha": "2026-02-14", "dia": 14, "mes": 2, "contactos": 0},
            {"nombre": "Navidad", "fecha": "2026-12-25", "dia": 25, "mes": 12, "contactos": 1}
        ]
    }
    monkeypatch.setattr(servidor, "obtener_fechas", lambda: fechas_mock)

    r_f = c.get("/api/fechas", headers=adm)
    assert r_f.status_code == 200
    res_f = r_f.json()
    assert len(res_f["fechas"]) == 1
    assert res_f["fechas"][0]["dias_faltan"] == 4
    assert res_f["cantidades"]["total"] == 1
    assert len(res_f["fechas_comerciales"]) == 5
    madre = next(fc for fc in res_f["fechas_comerciales"] if fc["nombre"] == "Día de la Madre")
    assert madre["contactos"] == 1


def test_centralita_origen_utm_y_resumen_anuncios(entorno_centralita, monkeypatch):
    c, _, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    from servicios import servidor

    pedidos_con_utm = [
        {
            "id": "RF-0001",
            "marca": "rf",
            "producto": "rf-foto-1",
            "precio": 4999,
            "nombre": "Ana Pérez",
            "email": "ana@mail.com",
            "whatsapp": "5491111111111",
            "estado": "pagado",
            "pagado": "2026-10-14T10:00:00Z",
            "datos": {
                "origen": {"source": "meta", "medium": "paid", "campaign": "ddm2026", "content": "P004"}
            }
        },
        {
            "id": "RF-0002",
            "marca": "rf",
            "producto": "rf-pack-5",
            "precio": 14999,
            "nombre": "Carlos Gómez",
            "email": "carlos@mail.com",
            "whatsapp": "5491122222222",
            "estado": "vista_previa",
            "pagado": "2026-10-14T11:00:00Z",
            "datos": {
                "origen": {"source": "meta", "medium": "paid", "campaign": "ddm2026", "content": "P004"}
            }
        },
        {
            "id": "TC-0001",
            "marca": "tc",
            "producto": "tc-cancion",
            "precio": 26999,
            "nombre": "Lucía Morales",
            "email": "lucia@mail.com",
            "whatsapp": "5491133333333",
            "estado": "entregado",
            "pagado": "2026-10-14T09:00:00Z",
            "datos": {
                "origen": {"source": "meta", "medium": "paid", "campaign": "ddm2026", "content": "P005"}
            }
        },
        {
            "id": "TC-0002",
            "marca": "tc",
            "producto": "tc-cancion",
            "precio": 26999,
            "nombre": "Pedro Pendiente",
            "email": "pedro@mail.com",
            "whatsapp": "5491144444444",
            "estado": "pendiente_pago",  # no debe sumar al resumen
            "datos": {
                "origen": {"source": "meta", "medium": "paid", "campaign": "ddm2026", "content": "P005"}
            }
        },
        {
            "id": "RF-0003",
            "marca": "rf",
            "producto": "rf-foto-1",
            "precio": 4999,
            "nombre": "María Directa",
            "email": "maria@mail.com",
            "whatsapp": "5491155555555",
            "estado": "pagado",
            "pagado": "2026-10-14T12:00:00Z",
            "datos": {}  # sin UTM
        }
    ]

    monkeypatch.setattr(servidor, "obtener_pedidos", lambda: [dict(p) for p in pedidos_con_utm])
    monkeypatch.setattr(servidor, "obtener_pedido", lambda pid: next(p for p in pedidos_con_utm if p["id"] == pid))

    # 1. GET /api/pedidos expone origen y origen_texto
    r_pedidos = c.get("/api/pedidos", headers=adm)
    assert r_pedidos.status_code == 200
    peds = r_pedidos.json()
    p_rf1 = next(p for p in peds if p["id"] == "RF-0001")
    assert p_rf1["origen"]["content"] == "P004"
    assert p_rf1["origen_texto"] == "meta · P004"

    p_rf3 = next(p for p in peds if p["id"] == "RF-0003")
    assert p_rf3["origen"] is None
    assert p_rf3["origen_texto"] == "—"

    # 2. GET /api/pedidos/RF-0001 (ficha)
    r_ficha = c.get("/api/pedidos/RF-0001", headers=adm)
    assert r_ficha.status_code == 200
    assert r_ficha.json()["pedido"]["origen_texto"] == "meta · P004"

    # 3. GET /api/anuncios (resumen por utm_content)
    r_anuncios = c.get("/api/anuncios", headers=adm)
    assert r_anuncios.status_code == 200
    res = r_anuncios.json()

    # Total pedidos pagados = 4 (RF-0001, RF-0002, TC-0001, RF-0003)
    # Total cobrado = 4999 + 14999 + 26999 + 4999 = 51996
    assert res["total_pedidos"] == 4
    assert res["total_cobrado"] == 51996

    anuncios = {a["anuncio"]: a for a in res["anuncios"]}
    assert "P004" in anuncios
    assert anuncios["P004"]["pedidos_pagados"] == 2
    assert anuncios["P004"]["monto_cobrado"] == 4999 + 14999
    assert set(anuncios["P004"]["pedidos"]) == {"RF-0001", "RF-0002"}

    assert "P005" in anuncios
    assert anuncios["P005"]["pedidos_pagados"] == 1  # TC-0002 no suma por estar pendiente
    assert anuncios["P005"]["monto_cobrado"] == 26999
    assert anuncios["P005"]["pedidos"] == ["TC-0001"]

    assert "(sin anuncio)" in anuncios
    assert anuncios["(sin anuncio)"]["pedidos_pagados"] == 1
    assert anuncios["(sin anuncio)"]["monto_cobrado"] == 4999

    # Verificar endpoint alternativo
    r_alt = c.get("/api/pedidos/resumen-anuncios", headers=adm)
    assert r_alt.status_code == 200
    assert r_alt.json() == res


def test_centralita_ml_meta(entorno_centralita, monkeypatch):
    c, _, _, _ = entorno_centralita
    adm = {"X-Centralita": "1"}

    from servicios import ml_meta

    # 1. Bloqueo sin X-Centralita
    r_bloq = c.get("/api/ml-meta")
    assert r_bloq.status_code == 403

    r_post_bloq = c.post("/api/ml-meta/actualizar")
    assert r_post_bloq.status_code == 403

    # 2. Mock de ml_meta para pruebas unitarias sin red
    ml_falso = {
        "conectado": True,
        "vendedor": {"id": 12345, "nickname": "TESTSELLER", "permalink": "https://perfil"},
        "publicaciones": [
            {
                "id": "MLA1111",
                "titulo": "Canción con tu historia",
                "permalink": "https://articulo.mercadolibre.com.ar/MLA1111",
                "precio": 26999,
                "estado": "active",
                "stock": 99,
                "ventas": 2,
                "visitas_7d": 15,
                "cargo_estimado": "$4.120",
                "preguntas_sin_responder": 0,
                "thumbnail": "https://img/1.jpg",
                "categoria_id": "MLA1174"
            }
        ],
        "resumen": {
            "total_publicaciones": 1,
            "activas": 1,
            "pausadas": 0,
            "visitas_7d_total": 15,
            "ventas_total": 2,
            "preguntas_pendientes_total": 0,
        },
        "preguntas": [],
        "fecha_lectura": "2026-10-15T10:00:00Z"
    }

    meta_falso = {
        "pixel": {"activo": True, "id_mascarado": "***1234", "estado": "Activo"},
        "cuenta_publicitaria": {"conectada": False, "estado": "Desconectada", "mensaje": "Sin conectar"},
        "campanas": [
            {
                "campana": "ddm2026",
                "pieza": "P004",
                "fuente_medio": "meta/paid",
                "pedidos": 2,
                "cobrado": 19998.0,
                "pedidos_ids": ["RF-0001", "RF-0002"]
            }
        ],
        "resumen": {
            "total_pedidos_atribuidos": 2,
            "total_cobrado_atribuido": 19998.0,
            "campanas_activas": 1
        }
    }

    monkeypatch.setattr(ml_meta, "obtener_ml_meta_completo", lambda forzar_ml=False: {
        "ml": ml_falso,
        "meta": meta_falso
    })

    # 3. GET /api/ml-meta
    r = c.get("/api/ml-meta", headers=adm)
    assert r.status_code == 200
    res = r.json()
    assert "ml" in res
    assert "meta" in res
    assert res["ml"]["conectado"] is True
    assert len(res["ml"]["publicaciones"]) == 1
    assert res["ml"]["resumen"]["activas"] == 1
    assert res["meta"]["pixel"]["activo"] is True
    assert res["meta"]["resumen"]["total_pedidos_atribuidos"] == 2
    assert res["meta"]["campanas"][0]["pieza"] == "P004"

    # 4. POST /api/ml-meta/actualizar
    r_act = c.post("/api/ml-meta/actualizar", headers=adm)
    assert r_act.status_code == 200
    assert r_act.json() == res


