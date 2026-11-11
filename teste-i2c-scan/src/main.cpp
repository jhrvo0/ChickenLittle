// Scanner I2C minimo. Varre 0x08..0x77 a cada 3 s e aponta se o LCD (PCF8574: 0x27 ou 0x3F) responde.
#include <Arduino.h>
#include <Wire.h>

static const uint8_t PIN_SDA = 21;
static const uint8_t PIN_SCL = 22;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(PIN_SDA, PIN_SCL);
  Serial.println("Scanner I2C iniciado: SDA=GPIO21 SCL=GPIO22, faixa 0x08..0x77");
}

void loop() {
  uint8_t encontrados = 0;
  bool lcd = false;

  for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("Dispositivo em 0x%02X\n", addr);
      encontrados++;
      if (addr == 0x27 || addr == 0x3F) lcd = true;
    }
  }

  Serial.printf("Total de dispositivos: %u\n", encontrados);
  Serial.println(lcd ? "LCD DETECTADO (PCF8574)" : "LCD NAO detectado");
  Serial.println("----");
  delay(3000);
}
