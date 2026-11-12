# Evidências técnicas para o checkpoint de Sistemas Embarcados

Preparação em 11/11/2026, horário de Fortaleza (UTC−3). Entrega do documento em **12/11/2026**, conforme informação do grupo. O modelo e o enunciado mantêm **17/11/2026** como data do checkpoint; não foi presumido que a avaliação também mudou de data.

Este pacote contém inventário, evidências e tarefas de preenchimento humano. **Não contém o relatório acadêmico redigido nem um DOCX preenchido.** A restrição de IA à revisão textual com declaração consta na página 5 do enunciado de Embarcados. O grupo precisa observar essa regra na redação e confirmar a admissibilidade dos materiais técnicos de apoio. Nenhuma declaração de uso foi assinada pelo grupo.

## Por onde começar

| Material | Uso no documento |
|---|---|
| [Checklist de todos os campos](01_checklist_campos.md) | Percorrer as páginas 1 a 6 do modelo sem omitir campos; a página 6 é dos docentes |
| [Hardware e firmware](02_hardware_firmware.md) | Tabela de componentes, GPIOs, circuito, FreeRTOS e limites das validações |
| [Arquitetura e MQTT](03_arquitetura_mqtt.md) | Figura 3, fluxo, tópicos, publishers, subscribers e payloads verificáveis |
| [Dashboard e evidências](04_dashboard_evidencias.md) | Dados exibidos, tecnologias, roteiro de demonstração e capturas manuais |
| [Pendências e validação futura](05_pendencias_validacao.md) | Prioridade para amanhã, informações do grupo e ensaios físicos posteriores |
| [Figura 1 — circuito atual em PNG](figuras/figura-1-circuito-atual.png) / [SVG editável](figuras/figura-1-circuito-atual.svg) | Esquemático derivado da netlist vigente; não é fotografia nem simulação elétrica |
| [Figura 3 — arquitetura em PNG](figuras/figura-3-arquitetura.png) / [SVG editável](figuras/figura-3-arquitetura.svg) | Separa USB, MQTT de software e Wi-Fi/MQTT da ESP32 pendente |
| [Índice das evidências e hashes](evidencias/manifesto.json) | Conferir integridade, origem e resultados usados neste pacote |

Os PNGs podem ser inseridos manualmente nas áreas de figuras do modelo. A Figura 2 requer **foto real da protoboard**, ausente nos arquivos de projeto inspecionados. As Figuras 4 e 5 requerem **capturas manuais do dashboard/protótipo**; a captura automática foi bloqueada pela ferramenta de navegação. Há evidência HTTP, que não substitui screenshot.

## Estado que pode ser sustentado

| Frente | Evidência | Limite |
|---|---|---|
| Aquisição ESP32 → USB serial | Código C++/FreeRTOS, JSON Lines v1, build aprovado; registros anteriores de bancada | Não houve acesso à COM3 nesta preparação; resposta dos sensores é relato histórico documentado |
| HC-SR04 + TCRT5000 juntos | Registro de 10/11 em `docs/bench_verified_wiring.md` e `hardware/wokwi/montagem_atual/README.md` | Sem medição de tensão ou exatidão; não é nova validação física |
| MQTT → persistência → Airflow → MLflow → API | [Verificador da Fase C](evidencias/fase-c-integracao.json), corpus e publicação identificados | Dados simulados; stack completa não foi reiniciada nesta preparação |
| Dashboard e API existentes | HTTP 200 em `state`, `live`, `lab`, `ml/status`, `ml/evaluations`, `ml/predictions`; 6 previsões DEMO | Verificação HTTP atual; screenshot de funcionamento continua pendente |
| Wi-Fi/MQTT na ESP32 | Ausente do firmware vigente | Implementação suspensa por prioridade do relatório; sem validação física |
| GitHub | [Consulta autenticada de visibilidade](evidencias/github.json) | **Privado**; requisito de repositório público ainda não atendido |
| IPv6 fim a fim | Sem evidência de operação | Ambiguidade no enunciado: funcionamento obrigatório e bônus mencionam IPv6 |

### Atualização posterior à preparação (12/11/2026)

As evidências desta pasta são um retrato de 11/11/2026 e foram mantidas sem alteração. Desde então:

- **Wi-Fi/MQTT na ESP32:** implementado no firmware (`firmware/communication/iot_transport.cpp`) e exercitado na bancada; ver [ensaio de bancada IoT](../../motionlab_bancada_iot_2026-11-12.md).
- **GitHub:** o repositório passou a ser **público**; `evidencias/github.json` ainda registra a consulta anterior (privado).
- **Commits:** `evidencias/total-commits.txt` registra 21; o histórico passou a 25 commits, todos do mesmo autor.
- **Fotos e figuras:** as fotos da montagem (Figura 2) estão em [docs/fotos-bancada](../../fotos-bancada/) e as capturas do dashboard (Figuras 4 e 5) em [docs/capturas-motionlab](../../capturas-motionlab/). As figuras finais usadas no relatório e no site estão em [docs/figuras](../../figuras/); a `figura-3-arquitetura` desta pasta ainda mostra o Wi-Fi da ESP32 como pendente.
- **Checklists:** `01_checklist_campos.md` e `03_arquitetura_mqtt.md` descrevem o estado de 11/11 (Wi-Fi/MQTT ausente, README sem equipe e Google Sites) e não foram reescritos.
- **Testes:** os logs versionados registram 594 testes Python (591 aprovados, 3 ignorados) e 20 de interface. Qualquer total maior citado no relatório (por exemplo, 655 aprovados) precisa de um novo `pytest.log`/`pytest.xml` versionado aqui para ter evidência.

## Verificações desta preparação

| Comando | Resultado real | Evidência |
|---|---|---|
| `.\.venv\Scripts\python.exe -m platformio run -d firmware` | SUCCESS, 15,68 s; RAM estática 24.668/327.680 B (7,5%); flash 322.881/1.310.720 B (24,6%) | [build-firmware.log](evidencias/build-firmware.log) |
| `.\.venv\Scripts\python.exe -m pytest -q --junitxml=data/experiments/checkpoint-2026-11-12/pytest.xml` | 594 coletados: **591 passaram, 3 ignorados**, 0 falhas/erros; 54,066 s | [JUnit](evidencias/pytest.xml), [log](evidencias/pytest.log) |
| `node --test tests/test_web_ui.cjs tests/test_guide_ui.cjs tests/test_lab_ui.cjs` | **20 passaram**, 0 falhas; 156,2 ms | [node-ui.log](evidencias/node-ui.log) |
| Compatibilidade do envelope MQTT reconstruído do corpus da Fase C | 191 registros aceitos; repetição reconhecida como duplicata; mesmo hash do recibo histórico | [mqtt-compatibilidade.json](evidencias/mqtt-compatibilidade.json) |
| Conferência de netlist, GPIOs do firmware e resistores Wokwi | Seis verificações estáticas aprovadas | [circuito-conferencia.json](evidencias/circuito-conferencia.json) |

Os três skips são comparações opcionais com `FRITZING_PARTS_DIR`, não definido. O treino de teste emite avisos de convergência do MLP limitado a 80 iterações; MLflow emite um aviso de depreciação do SQLAlchemy. Esses avisos constam no log e não foram convertidos em resultados físicos ou em garantias de generalização.

## Modelo original e paginação

Cópias idênticas às fornecidas, sem preenchimento ou alteração:

- [Modelo do checkpoint](../Relatorio_CheckPoint_Sistemas_Embarcados_CESAR_School_2026.1.docx), SHA-256 `2ec97ec51e08b00f68fdc3f9ae666cd93c40ff803b670fbf3b0cef3e6331aa21`.
- Enunciado de Embarcados (`Projeto-Embarcados_CesarSchool-CSBC (1).pdf`, fornecido pelos professores e não versionado neste repositório), SHA-256 `cf7c517dd67f5491309e5e994f777da5f77adcd1ece2bd9e6c9552009f29dd2f`.

O DOCX foi lido integralmente por OOXML, incluindo todas as tabelas, cabeçalhos e rodapés. A prévia já aberta no Google Drive foi lida para localizar os campos por página: **6 páginas exibidas**, com painel docente na página 6. Os metadados `docProps/app.xml` e os valores em cache do rodapé ainda indicam 7. Isso explica a divergência; o checklist usa a paginação da prévia e também nomes de seção. A paginação pode mudar no editor usado pelo grupo. Não foram corrigidos os campos do modelo. O renderer local não estava disponível (`soffice.exe` ausente do runtime); nenhuma renderização local foi apresentada como concluída.

## Preservação do trabalho

Nenhum arquivo preexistente de código, interface, firmware, netlist ou configuração foi editado. As alterações desta tarefa são novos materiais em `docs/academico/` e evidências locais em `data/experiments/checkpoint-2026-11-12/`. O inventário inicial, os diffs staged/unstaged e hashes ficaram nessa pasta local ignorada pelo Git. A conferência final está em [preservacao.json](evidencias/preservacao.json). Não foram feitos commit, push, merge, reset, clean, instalação global, upload, leitura da COM3 ou mudança elétrica.
