@echo off
cd /d "%~dp0"
echo Gravando o firmware do MotionPet na ESP32 (COM3)...
echo Pode demorar 1-3 minutos na primeira vez.
"%USERPROFILE%\.platformio\penv\Scripts\pio.exe" run -d firmware -e esp32dev -t upload --upload-port COM3 > gravar_firmware_saida.txt 2>&1
if errorlevel 1 (
  echo FALHOU. Veja gravar_firmware_saida.txt
) else (
  echo OK: firmware gravado. Agora rode teste_bancada.bat
)
echo.
pause
