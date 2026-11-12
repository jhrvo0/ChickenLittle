# Organização e preparação para publicação

Auditoria local de 11/11/2026. O repositório contém trabalho rastreado modificado, renomeações preparadas no índice e arquivos ainda não rastreados. A presença local desses arquivos não significa que estejam publicados. Nenhuma alteração de visibilidade ou operação de Git foi feita nesta revisão.

## Organização

O projeto evoluiu de ChickenLittle e MotionPet para MotionLab; identificadores técnicos antigos continuam quando têm função de compatibilidade. `terminal/`, `firmware/` e `hardware/` são usados por imports, testes, PlatformIO, scripts e documentação. Os diretórios `applications/`, `esp32-esp8266/` e `schematics/` contêm índices para esses caminhos, sem cópias ou renomeações. A especificação de Sistemas Embarcados informa que itens por diretório são obrigatórios e que sua insuficiência afeta a avaliação: confirmar com os professores se esses índices satisfazem o requisito ou se será necessária uma migração coordenada.

Os projetos `teste-*` e os arquivos gerados em `hardware/out/` incluem registros de ensaios e artefatos históricos já rastreados; não foram apagados ou movidos. Alguns diagramas incluem LCD, que não integra a montagem atual. Os dados locais de execução, modelos e configurações ficam em grande parte ignorados, conforme `.gitignore`. Ignorar não remove conteúdo já rastreado nem do histórico.

## Antes de abrir o repositório

1. Revisar o conjunto exato que será commitado, inclusive alterações existentes, renomeações já staged e arquivos novos. Conferir o conteúdo remoto depois de autorizado o envio; nada desta revisão o publicou.
2. Endereço do Google Sites informado no README: <https://sites.google.com/view/motionlab-grupo5>. As responsabilidades propostas e os nomes e perfis estão registrados no [README](../README.md). Conferir consentimento e exposição de dados pessoais, autoria e licenças, inclusive das fontes e do material acadêmico. `pyproject.toml` ainda apresenta `MotionPet Engineering` como autor e declara MIT, mas não há arquivo de licença rastreado: o grupo deve confirmar esses metadados e a licença antes de publicá-los como definitivos.
3. Decidir quais arquivos do checkpoint, logs, capturas, notebooks, resultados de bancada, arquivos gerados e documentos da disciplina devem ser publicados. Algumas evidências podem conter nomes, caminhos, metadados ou registros internos; examinar também arquivos binários e anexos.
4. Fazer varredura de segredos no conteúdo de todas as revisões e em binários com ferramenta apropriada, além de revisão humana. A conferência desta fase cobre nomes de arquivos históricos e padrões limitados no conteúdo local, não prova ausência de credenciais no histórico. Se houver segredo exposto, revogá-lo e planejar a correção antes de publicar.
5. Conferir configurações locais, certificados, chaves, arquivos `.env`, dados de participantes e destinos de exportação. `firmware/communication/iot_config.local.h`, `ops/iot/local/` e dados IoT estão ignorados, mas outros nomes ou localizações podem não estar.
6. Revisar caminhos absolutos e informação da máquina, inclusive no [guia de coleta](real_data_collection_guide.md), nos documentos acadêmicos e nas evidências geradas. Substituir ou anonimizar somente após avaliar o contexto e a autorização de uso.
7. Conferir capturas reais, instruções em clone limpo e disponibilidade das evidências: `data/experiments/`, modelos e coletas são ignorados. Não apresentar resultados sintéticos como medições físicas.
8. Resolver posteriormente com os professores a organização por diretório e os demais critérios acadêmicos. Segundo o representante do grupo, o professor autorizou em sala o uso integral de IA no trabalho.

## Escopo da conferência

Foram inspecionados `.gitignore`, nomes de arquivos rastreados e do histórico, o estado local do Git e padrões específicos de chaves/tokens em arquivos de texto locais, com exclusões de dados locais, documentos acadêmicos, arquivos binários e alguns formatos gerados. A análise não abrangeu segredos codificados, todos os formatos nem o conteúdo histórico completo. Não se deve interpretar ausência de correspondências como garantia de segurança.
