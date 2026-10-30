@echo off
cd /d "%~dp0"
echo Gravando o firmware do MotionPet na ESP32 (COM3)...
echo.
echo ANTES DE CONTINUAR, coloque a ESP32 em modo de gravacao:
echo   1. Segure o botao BOOT da ESP32.
echo   2. Enquanto segura o BOOT, aperte e solte o botao EN (RST).
echo   3. Solte o BOOT.
echo.
pause
echo Compilando e gravando (pode levar 1-3 minutos)...
"%USERPROFILE%\.platformio\penv\Scripts\pio.exe" run -d firmware -e esp32dev -t upload --upload-port COM3 > gravar_firmware_saida.txt 2>&1
if errorlevel 1 (
  echo FALHOU. Veja gravar_firmware_saida.txt
) else (
  echo OK: firmware gravado. Agora rode teste_bancada.bat
)
echo.
pause
