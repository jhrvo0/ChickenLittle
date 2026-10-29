# MCPs de CAD eletronico — avaliacao, escolha e estado real

> **Estado honesto:** o MCP escolhido esta **configurado** (`.mcp.json`) e o preparo esta **scriptado**
> (`python -m hardware.tools.setup_fritzing_mcp`), mas **NAO foi instalado nem chamado** no ambiente onde este trabalho foi gerado:
> o sistema de permissoes negou a execucao de codigo externo (instalar dependencias de terceiros e rodar o servidor).
> Portanto **nao ha chamadas MCP testadas**. O `.fzz` foi produzido por gerador proprio (`hardware/export_fz.py`) e verificado por
> reextracao independente das redes e por conferencia com os barramentos reais do `breadboard2` do Fritzing.

## Candidatos lidos (README + codigo, sem executar nada)

| Candidato | Licenca | Roda sem o app Fritzing? | Windows / ARM64 | Pecas na protoboard (furos) | Saida | Observacoes |
|---|---|---|---|---|---|---|
| [lestealthy/fritzing-mcp](https://github.com/lestealthy/fritzing-mcp) (WattLab) | GPL-2.0+ | **Nao** (exige Fritzing.exe e `pywin32`) | Somente Windows; ARM64 nao declarado | nao claro | `.fz/.fzz`, SVG (sem PNG) | Melhor postura de seguranca (sem shell/FS arbitrario, politica em JSON, 15 ferramentas); 3 commits, 0 estrelas. **Segunda opcao** se voce tiver Fritzing no Windows. |
| [fedoragobrowse-design/fritzing-mcp](https://github.com/fedoragobrowse-design/fritzing-mcp) | MIT | **Sim** para criar/colocar/ligar/validar (`fz` e so biblioteca padrao Python) | Python+uv: multiplataforma; render precisa do Fritzing compilado | **Nao**: `wire` liga conector a conector e desenha entre origens das pecas | `.fzz`, SVG/PNG (render exige Fritzing + ImageMagick) | **ESCOLHIDO** como MCP editor/inspetor/validador (14 ferramentas: buscar pecas, conectores, new/place/wire/move/show/check/render/open). Codigo revisado: so `subprocess` com argv fixo para `fz`/Fritzing/ImageMagick, sem rede. |
| [LeonFedotov/fritzing-render](https://github.com/LeonFedotov/fritzing-render) | GPL-3.0 | **Sim** (renderizador proprio, sem o app) | Imagem Docker `linux/arm64`+`amd64`; build local exige Qt6 | renderiza protoboard de `.fzz`/JSON | **SVG/PNG** (300 ppi) | Melhor candidato para **renderizar o `.fzz` como o Fritzing** (4 ferramentas MCP). Nao testado: `ghcr.io` bloqueado no ambiente de geracao. |
| Wokwi MCP / `wokwi-cli` (oficial) | MIT | n/a (simulador) | binario oficial; ARM64 nao declarado | n/a | simulacao | Exige `WOKWI_CLI_TOKEN`; download do binario **negado** aqui e `wokwi.com` bloqueado. Exemplo inativo em `wokwi.mcp.example.json`. |
| Outros (busca web) | — | — | — | — | — | Nada mais maduro com netlist+protoboard encontrado: ferramentas web/proprietarias (ex.: geradores online) e uma skill de desenho em canvas HTML sem netlist. |

## Por que o fedoragobrowse e nao o resto
1. Roda localmente sem Fritzing para o essencial (criar/inspecionar/validar `.fzz`) — compativel com Windows ARM64 via Python/uv.
2. Menor superficie de risco entre os que rodam sem o app (MIT, ~1,5 mil linhas, sem rede).
3. **Limite conhecido:** nao modela pecas encaixadas nos furos da protoboard. Por isso a geometria exata e as conexoes por furo vem do gerador proprio (`export_fz.py`), que usa o mesmo formato de arquivo.

## Configuracao no Claude Code (escopo de projeto)
`.mcp.json` na raiz (formato documentado em https://code.claude.com/docs/en/mcp): servidor `fritzing`, `command: uv`, `args: run --project <repo>/tools/fritzing-mcp fritzing-mcp`, `FRITZING_APP_ROOT=<repo>/tools/fritzing_root`.

```powershell
python -m hardware.tools.setup_fritzing_mcp --dry-run     # mostra cada comando externo
python -m hardware.tools.setup_fritzing_mcp               # clona no commit fixo, `uv sync`, indexa as pecas
claude mcp list                                           # deve mostrar fritzing: Connected
```
O Claude Code pede aprovacao do servidor de projeto na primeira vez. O `parts.db` gerado por `hardware/tools/build_parts_db.py` e um indice **equivalente** (nao o oficial do app): contem as pecas core (breadboard2, HC-SR04, resistor) e as pecas genericas do MotionPet.

## O que ainda precisa ser feito por voce (ou autorizado)
- Rodar o setup acima e uma chamada real (`fritzing_check` no `hardware/out/MotionPet_estagioB.fzz`, `fritzing_show_sketch`).
- Abrir os `.fzz` no Fritzing 1.0.x e conferir visualmente (nao foi possivel aqui).
