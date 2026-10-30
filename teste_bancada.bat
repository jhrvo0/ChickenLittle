@echo off
cd /d "%~dp0"
echo Conferindo pyserial...
python -c "import serial" 2>nul || python -m pip install --no-index --find-links hardware\tools\wheels pyserial
echo Rodando testes... (aguarde ~1-2 min)
set PYTHONIOENCODING=utf-8
python hardware\tools\bench_auto.py > teste_bancada_saida.txt 2>&1
echo Pronto. Saida em teste_bancada_saida.txt
pause
