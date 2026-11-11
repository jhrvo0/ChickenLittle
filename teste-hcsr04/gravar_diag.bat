@echo off
cd /d "%~dp0"
echo Gravando o firmware de DIAGNOSTICO do HC-SR04 na ESP32 (COM3)...
echo.
echo ANTES DE CONTINUAR, coloque a ESP32 em modo de gravacao:
echo   1. Segure o botao BOOT da ESP32.
echo   2. Enquanto segura o BOOT, aperte e solte o botao EN (RST).
echo   3. Solte o BOOT.
echo.
pause
echo Compilando e gravando...
"%USERPROFILE%\.platformio\penv\Scripts\pio.exe" run -d . -e diag -t upload --upload-port COM3 > gravar_diag_saida.txt 2>&1
if errorlevel 1 (
  echo FALHOU. Veja teste-hcsr04\gravar_diag_saida.txt e avise no chat.
) else (
  echo OK: gravado. Avise no chat "gravei".
)
echo.
pause
