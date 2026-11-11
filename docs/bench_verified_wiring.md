# Ligações recuperadas dos testes reais — MotionPet

Registro recuperado em 10/11/2026 do histórico do projeto. Usar esta referência antes de pedir novamente um mapeamento já realizado. Ela descreve o teste anterior; não comprova que os jumpers atuais estejam nos mesmos contatos ou que as tensões atuais sejam iguais.

## LCD I²C — teste de 05/11/2026

### Reteste direto em 10/11/2026 após retirar todos os fios

Observações relatadas pelo usuário, sem medições automáticas: com somente GND=6J e VCC=1J (5 V), SDA/SCL ausentes, a iluminação acendeu normalmente. Movendo apenas VCC para 19J (3V3), a iluminação acendeu mais fraca. Depois, com GND=6J, VCC=19J, SDA=14A e SCL=17A, apareceu texto, mas permaneceu difícil de ler mesmo após o usuário informar ajuste máximo de contraste. A legibilidade em 3V3 não está aprovada. O teste atual em 5 V validou somente a iluminação; não houve teste atual de texto em 5 V. Para operar com backpack em 5 V e ESP32, prever conversão bidirecional dos sinais I²C. Não instruir a mover apenas VCC para 1J mantendo SDA/SCL diretos.

### Registro histórico de 05/11

ESP32 NodeMCU ESP-32S V1.1, 38 pinos, USB para a linha 1, placa ocupando linhas 1–19 da protoboard. Os furos livres usados foram A e J.

| Adaptador LCD | Furo usado no teste | Sinal |
|---|---|---|
| GND | **6J** | GND da ESP32 |
| VCC | **19J** | 3V3 da ESP32 |
| SDA | **14A** | GPIO21 |
| SCL | **17A** | GPIO22 |

Evidências em 05/11, horários de Fortaleza (UTC−3):

- 11:34 e 11:43: a conversa registra explicitamente os quatro furos acima, após o usuário informar que os furos internos ficavam cobertos pela ESP32.
- 12:15: scanner na COM3, sete varreduras em 20 s, adaptador detectado em **0x27**. Projeto: `teste-i2c-scan`.
- 12:16: teste de texto na COM3 registrou `Dispositivo I2C em 0x27`, quadro inicial e contador 0–19. Projeto: `teste-lcd`.
- 12:20: após ajuste do contraste, o usuário confirmou: “po funcionou, tá bem dificil de ver, mas ta funcionando”. Esse relato antecede a mudança da alimentação para 5 V.
- 12:29–12:31: usuário informou mover VCC de 19J para **1J (5 V)** para aumentar o brilho. Essa alteração NÃO é o perfil atual de I²C direto em 3V3. Foi registrada orientação para conversor de nível; não há registro de que ele tenha sido instalado.
- 12:38: usuário confirmou que a animação de boot apareceu. Como a mudança para 5 V ocorreu antes, esse relato não comprova a animação alimentada em 3,3 V.

**GND de referência: 6J.** A indicação posterior de 2J usada durante a montagem integrada de 10/11 não é a ligação registrada no teste bem-sucedido. A revisão atual volta a usar 6J. Não foi comprovado que 2J seja a causa da falha; não reutilizá-lo como alternativa sem conferência específica.

Origem: histórico local Claude do projeto, conversa `2d18fea6-8fc1-4e1b-8919-cd5f33dd3adc`, de 05/11/2026. Este arquivo resume apenas as informações de bancada pertinentes.

## HC-SR04 — registros separados

`teste-hcsr04/audit_topologia.py` preserva a montagem declarada pelo usuário: VCC em 1J, TRIG em 10A, ECHO passando por R1 na linha 22, ponto protegido da linha 26 até 15J, R2/R3 nas linhas 26/29/30 e GND comum pela linha 30. É auditoria de topologia, não medição automática.

Outra conversa de 05/11 (`88a7394d-b434-4a70-8966-4955d432c0c0`) descreveu uma variante experimental: VCC=19J (3V3), GND=6J, TRIG=10A e ECHO=15J direto. Esse relato não autoriza alimentar o sensor em 5 V com ECHO direto. A montagem final atual mantém HC-SR04 em 5 V e divisor no ECHO; não misturar os dois perfis.

Nessa conversa, o assistente registrou ecos a 3,3 V entre aproximadamente 35–49 cm com `SEM ECO` ocasional e, depois, leituras de 53–56 cm no monitor. A captura de movimento foi explicitamente considerada inválida por ruído/reinicialização ao abrir a porta. Portanto há registro de resposta nessa variante, com limitações; não se trata de validação completa da montagem conjunta em 3,3 V.

O funcionamento individual do TCRT5000 foi relatado pelo usuário, mas esta recuperação não encontrou uma tabela histórica independente de seus furos; o firmware usa DO=GPIO35. Não transformar esse relato em medição ou pinagem física adicional inventada.
