@echo off
rem Experiencias completas: corre todas as experiencias (30 sementes cada) e refaz
rem as estatisticas e figuras. Resultados: experiments\results\*.csv
rem Figuras: notebooks\figures\*.png   (demora ~15-20 min)
rem Opcoes extra (ver COMO_CORRER.md), por exemplo:
rem     correr_experiencias.bat e1_pricing e4_resilience
rem     correr_experiencias.bat --workers 6
rem     correr_experiencias.bat --figures-only
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv nao encontrado. Ver COMO_CORRER.md, secao "Preparar o ambiente".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m experiments.run_all %*
pause
