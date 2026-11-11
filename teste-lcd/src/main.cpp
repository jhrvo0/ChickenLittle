// Teste isolado do LCD 2004A com adaptador I2C PCF8574 (backpack). Sem bibliotecas externas.
//   SDA -> GPIO21, SCL -> GPIO22, VCC=3V3 sem conversor (guia atual).
//   Se o painel precisar de 5 V, usar conversor I2C bidirecional; sinais nunca em 5 V direto.
// Mapeamento usual do backpack: P0=RS, P1=RW, P2=E, P3=backlight, P4..P7=D4..D7.
// Escreve 3 linhas de texto e um contador na linha 4, que sobe 1 por segundo.
#include <Arduino.h>
#include <Wire.h>

static const uint8_t PIN_SDA = 21;
static const uint8_t PIN_SCL = 22;

static const uint8_t BIT_RS = 0x01;  // 0 = comando, 1 = dado
static const uint8_t BIT_E = 0x04;   // pulso de habilitacao
static const uint8_t BIT_BL = 0x08;  // backlight ligado

static uint8_t endereco = 0x27;

static void escreveExpansor(uint8_t dado) {
  Wire.beginTransmission(endereco);
  Wire.write(dado | BIT_BL);
  Wire.endTransmission();
}

// Envia 4 bits (D4..D7 nos bits P4..P7) com um pulso de E.
static void enviaNibble(uint8_t nibble, uint8_t modo) {
  uint8_t dado = ((nibble & 0x0F) << 4) | modo;
  escreveExpansor(dado | BIT_E);
  delayMicroseconds(5);  // E alto por mais de 450 ns
  escreveExpansor(dado);  // E baixo
  delayMicroseconds(100);  // tempo de execucao da instrucao
}

static void enviaByte(uint8_t valor, uint8_t modo) {
  enviaNibble(valor >> 4, modo);
  enviaNibble(valor & 0x0F, modo);
}

static void comando(uint8_t c) { enviaByte(c, 0); }
static void escreve(char c) { enviaByte((uint8_t)c, BIT_RS); }

static void escreveLinha(uint8_t linha, const char *texto) {
  static const uint8_t offsets[4] = {0x00, 0x40, 0x14, 0x54};
  comando(0x80 | offsets[linha]);
  bool fim = false;  // depois do '\0' completa a linha com espacos
  for (uint8_t i = 0; i < 20; i++) {
    if (texto[i] == '\0') fim = true;
    escreve(fim ? ' ' : texto[i]);
  }
}

static void iniciaLcd() {
  delay(50);  // tempo para a alimentacao estabilizar

  // Sequencia de reset do HD44780 para entrar no modo de 4 bits
  enviaNibble(0x03, 0);
  delay(5);
  enviaNibble(0x03, 0);
  delayMicroseconds(150);
  enviaNibble(0x03, 0);
  delayMicroseconds(150);
  enviaNibble(0x02, 0);

  comando(0x28);  // 4 bits, 2 linhas, fonte 5x8
  comando(0x08);  // display desligado
  comando(0x01);  // limpa a tela
  delay(3);
  comando(0x06);  // escrita incrementa o cursor
  comando(0x0C);  // display ligado, sem cursor
}

static bool procuraEndereco() {
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("Dispositivo I2C em 0x%02X\n", a);
      if ((a >= 0x20 && a <= 0x27) || (a >= 0x38 && a <= 0x3F)) {
        endereco = a;
        return true;
      }
    }
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_SDA, PIN_SCL);
  if (!procuraEndereco()) {
    Serial.println("Nenhum adaptador I2C encontrado. Confira SDA, SCL, GND, 5V e o conversor de nivel.");
    while (true) delay(1000);
  }
  iniciaLcd();
  escreveLinha(0, "TESTE LCD I2C");
  escreveLinha(1, "Linha 2 OK");
  escreveLinha(2, "Se ver isto, texto OK");
  Serial.println("LCD: quadro inicial enviado");
}

void loop() {
  static uint32_t n = 0;
  char buf[21];
  snprintf(buf, sizeof(buf), "Contador: %lu", (unsigned long)n);
  escreveLinha(3, buf);
  Serial.println(buf);
  n++;
  delay(1000);
}
