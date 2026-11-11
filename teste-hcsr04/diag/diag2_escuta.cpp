// Diagnostico v2: escuta o ECHO o tempo todo (qualquer origem) e dispara o TRIG sozinho a cada ~600 ms.
//
// Uso para o teste de TRIG a 5 V: desligue o fio do TRIG do GPIO5 e encoste-o em 5 V.
// Qualquer pulso no ECHO aparece como EVENTO, venha do GPIO5 ou da sua mao.
//
//   [GPIO5 trig=10us] ECHO subiu +NNNN us, largura=NNNN us -> D cm
//   [EXTERNO]         ECHO subiu, largura=NNNN us -> D cm        (nao houve trigger do GPIO5)
//   estado: ADC34=NNN mV  ECHO=0  (a cada 2 s)
#include <Arduino.h>

#define TRIG 5
#define ECHO 34

static uint32_t t_trig = 0;          // instante do ultimo trigger do GPIO5
static bool trig_window = false;     // true ate 80 ms depois do trigger
static uint32_t t_rise = 0;
static bool high = false;
static uint32_t last_trig_ms = 0, last_state_ms = 0;
static uint8_t seq = 0;

static uint32_t adc_mean() {
  analogSetPinAttenuation(ECHO, ADC_11db);
  uint32_t s = 0;
  for (int i = 0; i < 32; i++) {
    s += analogReadMilliVolts(ECHO);
    delayMicroseconds(100);
  }
  pinMode(ECHO, INPUT);
  return s / 32;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);
  digitalWrite(TRIG, LOW);
  pinMode(ECHO, INPUT);
  delay(1500);
  Serial.println();
  Serial.println("DIAG2 escuta | TRIG=GPIO5 ECHO=GPIO34");
}

void loop() {
  uint32_t now_ms = millis();

  if (now_ms - last_trig_ms >= 600 && !high) {
    last_trig_ms = now_ms;
    static const uint32_t W[] = {10, 20, 50};
    uint32_t w = W[seq++ % 3];
    digitalWrite(TRIG, HIGH);
    delayMicroseconds(w);
    digitalWrite(TRIG, LOW);
    t_trig = micros();
    trig_window = true;
  }
  if (trig_window && (uint32_t)(micros() - t_trig) > 80000) trig_window = false;

  int v = digitalRead(ECHO);
  uint32_t now = micros();
  if (v && !high) {
    high = true;
    t_rise = now;
  } else if (!v && high) {
    high = false;
    uint32_t w = now - t_rise;
    if (trig_window) {
      Serial.printf("[GPIO5] ECHO subiu +%lu us, largura=%lu us -> %.1f cm\n",
                    (unsigned long)(t_rise - t_trig), (unsigned long)w, w * 0.0343f / 2.0f);
    } else {
      Serial.printf("[EXTERNO] ECHO largura=%lu us -> %.1f cm\n", (unsigned long)w,
                    w * 0.0343f / 2.0f);
    }
  }

  if (!high && now_ms - last_state_ms >= 2000) {
    last_state_ms = now_ms;
    Serial.printf("estado: ADC34=%lu mV ECHO=%d\n", (unsigned long)adc_mean(), digitalRead(ECHO));
  }
}
