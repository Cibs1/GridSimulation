@echo off
rem Simulacao visual no browser (Mesa + Solara).
rem Duplo clique neste ficheiro, ou no terminal: correr_visual.bat
rem Para parar: fechar esta janela (ou Ctrl+C).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv nao encontrado. Ver COMO_CORRER.md, secao "Preparar o ambiente".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m solara run app.py
pause
