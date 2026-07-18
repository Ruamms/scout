@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Fato Relevante - gerador de executavel
echo ============================================
echo.

echo [1/2] Sincronizando dependencias (uv sync)...
python -m uv sync --group dev
if errorlevel 1 goto :erro

echo.
echo [2/2] Gerando executavel (PyInstaller)...
python -m uv run pyinstaller --onefile --console --clean --noconfirm --name fato src\fato_relevante\__main__.py
if errorlevel 1 goto :erro

echo.
echo ============================================
echo  OK! Executavel gerado em: dist\fato.exe
echo  Teste rapido: dist\fato.exe analisar ADSH11
echo ============================================
exit /b 0

:erro
echo.
echo *** BUILD FALHOU - veja as mensagens acima. ***
exit /b 1
