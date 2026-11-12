# Pendências e procedimentos posteriores

## Prioridade para a entrega de 12/11

| Ordem | Pendência | Quem pode resolver / evidência necessária |
|---:|---|---|
| 1 | Identificação do grupo e autoria | Grupo fornece número, título oficial, representante, nomes completos, usuários GitHub e responsabilidades reais |
| 2 | Redação humana no modelo | Grupo escreve resumo, descrições do fluxo, funcionamento e próximos passos; IA limitada à revisão textual dentro da regra declarada |
| 3 | Fotografia física — Figura 2 | Grupo fotografa a bancada vigente sem inventar montagem ou modificar fios para a imagem |
| 4 | Capturas das telas — Figuras 4 e 5 | Grupo segue [roteiro de captura](04_dashboard_evidencias.md#capturas-manuais-necessárias), mantendo DEMO visível |
| 5 | Figuras técnicas — Figuras 1 e 3 | Conferir e inserir os PNGs deste pacote nas áreas originais; preservar a indicação de esquema técnico e caminho de rede pendente |
| 6 | Percentuais exigidos pelo modelo | Grupo define escopo e cálculo ou consulta como registrar progresso sem percentual medido. Este pacote não atribui números |
| 7 | Datas e paginação | Entrega antecipada informada = 12/11; modelo = checkpoint 17/11; rodapé em cache “de 7”, prévia = 6. Confirmar antes de alterar |
| 8 | GitHub privado e trabalho local não publicado | Grupo decide posteriormente a publicação/visibilidade; nenhuma alteração de Git foi autorizada nesta tarefa |
| 9 | Estrutura de pastas | Mapear `terminal/`/`ml/`→applications, `firmware/`→esp32-esp8266, `hardware/`→schematics; confirmar aceite ou planejar ajuste posterior |
| 10 | Revisão de conformidade | Deixar painel docente em branco; não alegar Wi-Fi físico, IPv6, atuador físico, precisão ou conclusão elétrica; revisar uso de IA |

O prazo informado para amanhã se refere ao relatório de checkpoint. A especificação original também registra documentação final em 03/12 até 23h59 e apresentação em 12/12; não foram alteradas essas datas nem inferido horário de entrega para 12/11.

## Informações que não podem ser deduzidas do código

- Número e composição oficial do grupo, regra específica de Projetos 6 e representante.
- Nome completo e usuário GitHub de cada integrante; responsáveis reais por firmware, backend, frontend, hardware e apresentação.
- Título acadêmico oficial e problema/tema defendido pelo grupo. O software usa o nome MotionLab, mas isso não determina a proposta assinada pelo grupo.
- Percentuais de conclusão, prioridades acordadas, responsáveis e datas de tarefas.
- Quem contribuiu no Git usando outro autor, conta compartilhada ou fora do repositório; uso efetivo de GitHub Projects, mesmo com recurso habilitado.
- Link público de protótipo/Figma/Sites, caso exista fora dos arquivos inspecionados. A URL `127.0.0.1` é local.
- Foto atual e condições do ensaio físico; não substituir por render.
- Confirmação formal das datas, do requisito IPv6, dos nomes obrigatórios de diretório e da admissibilidade dos materiais técnicos de IA.
- Declaração verdadeira do uso de IA e responsabilidade sobre a versão final; não gerar declaração assinada em nome do grupo.

## Pendências técnicas depois do relatório

| Prioridade | Trabalho futuro | Critério de aceite ainda ausente |
|---|---|---|
| Alta | Retomar projeto do transporte Wi-Fi/MQTT da ESP32 | Investigar memória/concorrência; configuração local sem segredos; build; testes de perda/reconexão; preservação USB; evitar bloqueio da aquisição |
| Alta | Tornar broker acessível à LAN da placa | Definir IP/nome alcançável no notebook; caminho WSL/host; autenticação e acesso de rede apropriados; ensaio de conexão pela placa. `127.0.0.1:1883` atual não resolve |
| Alta | Contrato de leituras contínuas e deduplicação | Não enviar cada linha serial como sessão completa; definir identidade de dispositivo/boot/seq e persistência compatível, sem inventar rótulo de treino |
| Alta | Demonstração física USB versus Wi-Fi | Comparar mesma montagem, conteúdo, integridade, gaps/reconexão e resposta ao dashboard; registrar como medições novas |
| Alta | IPv6 | Esclarecer obrigação/bônus e, se necessário, demonstrar endereçamento e tráfego MQTT efetivamente IPv6 |
| Média | Organização/publicação e contribuição do grupo | Resolver requisito público e nomes de diretório; incluir membros e responsabilidades; publicar apenas quando autorizado |
| Média | Documentação do firmware/circuito | Corrigir referências históricas ao LCD/filas estáticas e alinhar README ao estado atual; não confundir guias antigos com bancada vigente |
| Média | Coleta física e desempenho de reconhecimento | Corpus real rotulado e consentido pelo grupo, protocolo de avaliação, separação de treino/teste e limitações; sem promover resultados sintéticos a físicos |

## Procedimento físico posterior com o usuário

**Roteiro, não execução.** Nenhum dos passos que envolve placa foi realizado nesta preparação. Executar pela thread principal, um passo de cada vez com o usuário. Não usar comandos de gravação ou monitores sem uma nova sessão física autorizada.

### A — documentar o que já existe por USB

1. Com o usuário presente, confirmar que a montagem continua sem LCD, potenciômetro e atuador externo. Registrar foto e comparar visualmente com a netlist/figura; não rearranjar fios para combinar com desenho.
2. Confirmar por inspeção a separação de +5 V e +3,3 V, GND comum e divisor no ECHO. Inspeção e leitura digital não são medição elétrica. O usuário não tem multímetro; não exigir tensões inexistentes nem registrar 2,83 V como leitura.
3. Identificar o programa que ocupa a COM3 e escolher **um só** proprietário da serial. Fechar apenas o programa acordado com o usuário; não abrir monitor e dashboard simultaneamente na porta.
4. Conectar a sessão do dashboard à porta física acordada. Confirmar origem física e distinguir de DEMO. Registrar versão `DIAG` se disponível, timestamp e configuração; essa operação precisa ocorrer nessa futura sessão, não agora.
5. Mover um alvo em frente ao HC-SR04 e cartão no IR. Registrar transições e amostras, validade/timeouts e erros de protocolo. Se houver régua/referência fornecida pelo grupo, registrar a comparação; sem referência, descrever apenas resposta, sem alegar exatidão.
6. Verificar continuidade JSON Lines, sequência e integridade; registrar reinicializações quando ocorrerem, sem confundir reset de placa com pacote perdido.
7. Demonstrar o dashboard com fonte real, gravar capturas datadas e preservar o arquivo bruto. Gestos/TinyML treinados em simulação continuam com proveniência sintética, mesmo se a entrada for real.

### B — ensaiar Wi-Fi/MQTT depois de implementar e compilar

8. Antes de usar a placa, concluir os testes de software do novo transporte, incluindo timeout/reconexão, filas limitadas, payload compatível e deduplicação. Esta fase ainda não existe no firmware.
9. Configurar rede/broker em arquivo local ignorado e registrar apenas parâmetros não secretos. Verificar o endereço da LAN do notebook e a acessibilidade do broker; não configurar a ESP32 com `127.0.0.1` ou DNS interno de container.
10. Planejar a gravação com o usuário, quando autorizada, preservando alimentação e pinagem. Confirmar sucesso de boot sem declarar sucesso de MQTT apenas por upload aprovado.
11. Verificar associação Wi-Fi, conexão ao broker, tópico/ID/seq/timestamp e persistência com origem real. Confirmar o recibo da aplicação e um único registro para cada identidade; MQTT entregue não é o mesmo que persistência concluída.
12. Comparar USB e MQTT com a mesma aquisição durante um intervalo acordado. Registrar contagens, gaps, validade de sensores e tempos efetivamente medidos. Não persistir como duas amostras independentes o mesmo evento recebido por dois caminhos.
13. Induzir separadamente indisponibilidade do broker e perda de Wi-Fi de modo acordado. Verificar que aquisição/classificação/USB continuam, que o buffer permanece limitado e que reconexão/reenvio não duplicam registros. Registrar perdas inevitáveis e alcance real do buffer.
14. Confirmar passagem até API e dashboard. Preservar identidade da sessão, hash e origem do modelo. Se o pipeline de treino for demonstrado, usar publicação explícita; não promover `latest` automaticamente.
15. Se IPv6 for confirmado como exigência, registrar endereços e tráfego de transporte real; ter IPv6 habilitado não comprova tráfego por IPv6.
16. Obter um relatório de ensaio separado: data, firmware/hash, montagem, rede, comandos, logs, observações do usuário e falhas. Só então atualizar status físico dos itens efetivamente verificados.

### Limites do ensaio

Não religar o LCD em 5 V com SDA/SCL diretos; não retirar o divisor do ECHO. Não pedir medições de tensão indisponíveis. Nem foto, build, teste com mock, captura DEMO ou disponibilidade HTTP isolada fecha a validação física Wi-Fi/MQTT.
