@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Scout - gerador de executavel
echo ============================================
echo.

rem localiza um uv utilizavel: PATH, modulo do python ou instalacao por usuario.
rem O uv so e necessario para CRIAR/ATUALIZAR o ambiente .venv; se o ambiente
rem ja existe com o PyInstaller dentro, o build funciona sem uv nenhum -
rem imune a antivirus comendo o uv.exe e a PATH diferente em cmd de admin.
set "UV="
uv --version >nul 2>&1
if not errorlevel 1 set "UV=uv"
if not defined UV python -m uv --version >nul 2>&1
if not defined UV if not errorlevel 1 set "UV=python -m uv"
if not defined UV if exist "%APPDATA%\Python\Python311\Scripts\uv.exe" set "UV=%APPDATA%\Python\Python311\Scripts\uv.exe"

if defined UV (
    echo [1/2] Sincronizando dependencias...
    %UV% sync --group dev
    if errorlevel 1 goto :erro
) else if exist .venv\Scripts\pyinstaller.exe (
    echo [1/2] uv indisponivel -- usando o ambiente .venv ja preparado
) else (
    echo Nao foi possivel preparar o ambiente: o uv nao foi encontrado e o
    echo .venv ainda nao existe. Rode num terminal comum:
    echo    python -m pip install --user --force-reinstall uv
    echo e clique neste gerar_exe.bat de novo.
    goto :erro
)

echo.
echo [2/2] Gerando executavel...
.venv\Scripts\pyinstaller --onefile --console --clean --noconfirm --name scout --icon assets\scout.ico src\scout\__main__.py
if errorlevel 1 goto :erro

echo.
echo ============================================
echo  OK! Executavel gerado em:
echo  %~dp0dist\scout.exe
echo.
echo  Teste rapido (num terminal):
echo  dist\scout.exe analisar ADSH11
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
