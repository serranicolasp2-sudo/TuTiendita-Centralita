@echo off
rem Centralita: levanta el servicio local (127.0.0.1:8790) si no esta andando y abre la ventana.
rem Sin acentos ni rutas con la "a" de Nicolas: cmd lee este archivo con otra pagina de codigos.
setlocal
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"

powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8790/' -UseBasicParsing -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% equ 0 goto abrir

start "" "%PYW%" arrancar.py
powershell -NoProfile -Command "for ($i=0; $i -lt 40; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:8790/' -UseBasicParsing -TimeoutSec 1 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if %ERRORLEVEL% neq 0 (
    echo No arranco la centralita. Mira el registro: %TEMP%\centralita.log
    pause
    exit /b 1
)

:abrir
start "" msedge --app=http://127.0.0.1:8790
endlocal
