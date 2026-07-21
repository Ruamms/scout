@echo off
REM ============================================================================
REM  Ciclo completo, um clique:
REM    1) atualiza a base (CVM + B3)
REM    2) SO ENTAO le em lote com IA (Ollama) sobre dados frescos
REM    3) commita e da push do que mudou (leituras + taxas de ETF)
REM  atualizar e ler_relatorios NUNCA rodam juntos (disputariam FNET/SQLite).
REM ============================================================================
setlocal
cd /d "%~dp0"

echo.
echo === [1/3] Atualizando a base (CVM + B3)... ===
call ".venv\Scripts\scout.exe" atualizar
if errorlevel 1 (
    echo.
    echo [ERRO] A atualizacao falhou com codigo %errorlevel%. O lote de IA NAO foi executado.
    pause
    exit /b 1
)

echo.
echo === [2/3] Leitura em lote por IA local (Ollama)... ===
call ".venv\Scripts\scout.exe" ia-lote

echo.
echo === [3/3] Commit e push do que mudou... ===
git add leituras dados/taxas_etfs.csv
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "leituras + taxas: rodada automatica (atualizar + ia-lote) %DATE% %TIME%"
    git push origin main
) else (
    echo Nada novo para commitar.
)

echo.
echo === Concluido: base atualizada, lote lido e publicado. ===
pause
