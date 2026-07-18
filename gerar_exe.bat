@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Fato Relevante - gerador de executavel
echo ============================================
echo.

rem garante o uv (ja vimos ele instalado so no escopo do usuario e invisivel ao duplo clique)
python -m uv --version >nul 2>&1
if errorlevel 1 (
    echo [0/2] Instalando uv...
    python -m pip install --quiet uv
    if errorlevel 1 python -m pip install --quiet --user uv
    python -m uv --version >nul 2>&1
    if errorlevel 1 (
        echo Nao foi possivel instalar o uv. Rode manualmente: python -m pip install uv
        goto :erro
    )
)

echo [1/2] Sincronizando dependencias (uv sync)...
python -m uv sync --group dev
if errorlevel 1 goto :erro

echo.
echo [2/2] Gerando executavel (PyInstaller)...
python -m uv run pyinstaller --onefile --console --clean --noconfirm --name fato src\fato_relevante\__main__.py
if errorlevel 1 goto :erro

echo.
echo ============================================
echo  OK! Executavel gerado em:
echo  %~dp0dist\fato.exe
echo.
echo  Teste rapido (num terminal):
echo  dist\fato.exe analisar ADSH11
echo ============================================
echo.
pause
exit /b 0

:erro
echo.
echo *** BUILD FALHOU - veja as mensagens acima. ***
echo.
pause
exit /b 1
