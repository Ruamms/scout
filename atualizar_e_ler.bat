@echo off
REM ============================================================================
REM  Atualiza a base (CVM + B3) e SO ENTAO le em lote com IA (Ollama).
REM  Rodar isto garante que o lote de leitura roda sobre dados FRESCOS.
REM  Sequencial de proposito: atualizar e ler_relatorios NUNCA rodam juntos
REM  (disputariam o mesmo FNET e o mesmo SQLite).
REM ============================================================================
setlocal
cd /d "%~dp0"

echo.
echo === [1/2] Atualizando a base (CVM + B3)... ===
call ".venv\Scripts\scout.exe" atualizar
if errorlevel 1 (
    echo.
    echo [ERRO] A atualizacao falhou com codigo %errorlevel%. O lote de IA NAO foi executado.
    pause
    exit /b 1
)

echo.
echo === [2/2] Leitura em lote por IA local (Ollama)... ===
call ".venv\Scripts\scout.exe" ia-lote

echo.
echo === Concluido: base atualizada + leitura em lote. ===
pause
