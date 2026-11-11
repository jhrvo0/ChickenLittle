// Teste minimo isolado do HC-SR04 (sem MotionPet, sem LCD).
//   TRIG -> GPIO5  (saida)
//   ECHO -> GPIO34 (entrada; GPIO34 nao possui pull-up/pull-down interno)
// Medicao a cada 500 ms com pulseIn e timeout de 30 ms.
#include <Arduino.h>

static const uint8_t PIN_TRIG = 5;
static const uint8_t PIN_ECHO = 34;
static const unsigned long TIMEOUT_ECHO_US = 30000UL;  // 30 ms
static const unsigned long PERIODO_MS = 500UL;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  delay(500);  // tempo para o sensor estabilizar apos energizar

  Serial.printf("HC-SR04 minimo | TRIG=GPIO%d ECHO=GPIO%d | ECHO em repouso=%d\n",
                (int)PIN_TRIG, (int)PIN_ECHO, digitalRead(PIN_ECHO));
}

void loop() {
  unsigned long inicio = millis();

  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duracaoUs = pulseIn(PIN_ECHO, HIGH, TIMEOUT_ECHO_US);
  if (duracaoUs == 0) {
    Serial.println("SEM ECO");
  } else {
    float distanciaCm = duracaoUs * 0.0343f / 2.0f;
    Serial.printf("Distancia: %.1f cm\n", distanciaCm);
  }

  unsigned long decorrido = millis() - inicio;
  if (decorrido < PERIODO_MS) {
    delay(PERIODO_MS - decorrido);
  }
}
