@echo off
rem Scout - leitura dos relatorios de TODOS os fundos com IA local (qwen2.5:14b).
rem - Um fundo por vez, salvando ao terminar cada um.
rem - Pode fechar a janela ou dar Ctrl+C a qualquer momento: nada se perde.
rem - Rodar de novo continua de onde parou (documento ja lido nao e relido).
rem - Fundos com erro ficam em leituras\_erros.txt.
setlocal
cd /d "%~dp0"

if not exist dist\scout.exe (
    echo dist\scout.exe nao encontrado - rode gerar_exe.bat primeiro.
    pause
    exit /b 1
)

if exist leituras\_erros.txt (
    echo Existem fundos com ERRO da rodada anterior - veja leituras\_erros.txt
    choice /M "Rodar SOMENTE os que falharam"
    if not errorlevel 2 (
        dist\scout.exe ia-lote --apenas-erros
        goto :fim
    )
)

dist\scout.exe ia-lote

:fim
echo.
echo Para publicar as leituras no site:
echo   git add leituras ^&^& git commit -m "leituras" ^&^& git push
pause
