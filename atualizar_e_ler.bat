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
call :agora T0

echo.
echo === [1/3] Atualizando a base (CVM + B3)... ===
call ".venv\Scripts\scout.exe" atualizar
if errorlevel 1 (
    echo.
    echo [ERRO] A atualizacao falhou com codigo %errorlevel%. O lote de IA NAO foi executado.
    pause
    exit /b 1
)
call :agora T1

echo.
echo === [2/3] Leitura em lote por IA local (Ollama)... ===
call ".venv\Scripts\scout.exe" ia-lote
call :agora T2

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

call :agora T3

echo.
echo === Concluido: base atualizada, lote lido e publicado. ===
call :dur %T0% %T1% D_ATU
call :dur %T1% %T2% D_LER
call :dur %T0% %T3% D_TOT
echo.
echo --- Tempo ---
echo   Atualizar (CVM + B3) : %D_ATU%
echo   Leitura IA (Ollama)  : %D_LER%
echo   TOTAL                : %D_TOT%
pause
exit /b 0

REM --- cronometro (cmd puro): tempo em centesimos desde a meia-noite ---
:agora
setlocal
set "t=%TIME: =0%"
set /a "cs=((1%t:~0,2%-100)*3600 + (1%t:~3,2%-100)*60 + (1%t:~6,2%-100))*100 + (1%t:~9,2%-100)"
endlocal & set "%~1=%cs%"
goto :eof

REM --- duracao formatada (HHh MMm SSs) entre dois instantes; trata virada de dia ---
:dur
setlocal
set /a "d=%2-%1"
if %d% lss 0 set /a "d+=8640000"
set /a "h=d/360000, m=(d/6000)%%60, s=(d/100)%%60"
endlocal & set "%~3=%h%h %m%m %s%s"
goto :eof
