# Documentação do MotionLab

Este índice separa a descrição atual dos registros produzidos ao longo do desenvolvimento. Uma auditoria de fase descreve o que havia sido demonstrado naquele momento; use os documentos posteriores para mudanças de estado.

## Visão geral e arquitetura

- [README principal](../README.md): objetivo, execução, funcionalidades e limites.
- [Arquitetura e migração para MotionLab](motionlab_arquitetura.md): sinais, reconhecedores, ações e decisões. O diagnóstico inicial e o plano são históricos; veja o aviso no próprio documento.
- [Protocolo serial JSON Lines v1](protocol.md): mensagens entre ESP32 e aplicação.
- [Contrato da API de ML](motionlab_ml_api.md): rotas, dados e proveniência.
- [Direção visual](design/motionlab_direcao_visual.md): identidade da interface e marcas de origem.

## Hardware

- [Ligações vigentes da bancada](bench_verified_wiring.md), [netlist sem LCD](../hardware/netlist/motionpet_atual_sem_lcd.json) e [diagrama Wokwi atual](../hardware/wokwi/montagem_atual/diagram.json): referências da montagem atual.
- [Segurança elétrica](hardware_safety.md): restrições e cuidados; partes sobre LCD dizem respeito à montagem histórica.
- [Hardware e CAD](../hardware/README.md): geradores e artefatos de projetos anteriores; confira a montagem antes de usar diagramas com LCD.
- [Transporte IoT na ESP32](motionlab_fase_e.md) e [contrato MQTT por amostra](mqtt_iot_v1.md): implementação e contrato. O [ensaio físico de 12/11](motionlab_bancada_iot_2026-11-12.md) registra a conexão e os descartes observados.

## Machine learning

- [Aprendizado de Máquina: requisitos × repositório](aprendizado_maquina.md): matriz da especificação da disciplina, comandos e resultados de referência.
- [Experimentos e operação de ML/MLOps](motionlab_mlops.md): ambiente, corpus, treinamento, avaliação e rastreabilidade. A tabela inicial registra a fase anterior à integração.
- [Especificação do pipeline](ml_pipeline_spec.md): coleta, processamento, modelos e TinyML.
- [Coleta de dados reais](real_data_collection_guide.md): plano de campanha e cuidados. Caminhos absolutos ou comandos históricos devem ser adaptados ao ambiente.
- [Notebook acadêmico](../notebooks/motionlab_bootstrap.ipynb): análise e resultados identificados por experimento; verificar a origem antes de interpretar métricas.

## MLOps e infraestrutura

- [Fase C: integração simulada](motionlab_fase_c.md): execução em lote, reprodução e evidências; estados da interface são históricos.
- [Fase E: transporte IoT](motionlab_fase_e.md): MQTT opcional da ESP32, fila, segurança e limites.
- [Contrato da API ML](motionlab_ml_api.md): interface entre inferência e dashboard.
- [Infraestrutura local](../ops/): configurações de demonstração e de broker LAN.

## Testes e validação

- [Testes automatizados](../tests/) e comandos no [README](../README.md#testes-e-reprodutibilidade).
- [Checklist de bancada do ciclo 5](cycle5_bench_checklist.md): histórico de ensaios; a montagem atual não usa LCD e as ligações vigentes prevalecem.
- [Pendências de publicação](publicacao.md): auditoria de organização, riscos e pontos a resolver.

## Documentação acadêmica

As fontes e o checkpoint são documentos de trabalho do grupo; o material do checkpoint é um retrato da data em que foi preparado e pode não refletir mudanças posteriores. Segundo o representante do grupo, o professor autorizou em sala o uso integral de IA no trabalho.

## Histórico técnico

- [Arquitetura MotionPet](architecture.md) e [interface anterior](interface_notebook.md): domínio e interface legados.
- [Guia de montagem por etapas](bench_assembly_guide.md), [decisões de CAD](cad_decisions.md) e [guia de LCD](guia_lcd_sem_resistor.md): registros anteriores; não substituem as ligações vigentes.
- [Projetos de bancada](../teste-hcsr04/), [LCD](../teste-lcd/) e [varredura I²C](../teste-i2c-scan/): ensaios específicos e registros históricos.
- [Relatório final (PDF)](Projeto_Embarcados_Grupo5.pdf): artigo no formato SBC, com o `.docx` editável ao lado.
- [Base SBC](relatorio_sbc_base.md): material de trabalho anterior; não é o relatório final e não substitui a revisão e autoria do grupo.
