# MotionPet no notebook

O pet se chama **Piu-piu**. A interface gráfica substitui a apresentação do LCD físico e usa a montagem já testada: ESP32, HC-SR04 e TCRT5000. Não é necessário trocar os fios para usar o aplicativo.

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m terminal.web
```

Abra **http://127.0.0.1:8767/**. No controle de conexão, escolha a porta da ESP32 (COM3 nesta bancada) e clique em **Conectar**. Feche o monitor serial anterior com Ctrl+C antes: apenas um programa pode usar a porta por vez. A página não abre uma porta automaticamente ao carregar.

## Telas e controles

| Tela | Sensores | Controles na tela |
|---|---|---|
| Meu Pet | Aproximar o cartão do IR alimenta; aproximar a mão do ultrassom faz carinho | Alimentar, brincar, descansar, curar, carinho, salvar e carregar |
| Pet Launch | Aproximar e afastar o cartão confirma as etapas; segurar perto do IR carrega e afastar lança. A distância da mão no ultrassom ajusta o ângulo entre 20° e 70° | Preparar, carregar, lançar, ajuste de ângulo e loja |
| Música | Distância escolhe uma nota; aproximar o cartão do IR alterna o silêncio | Ativar som, volume e desativar som |
| Slides | Mão perto avança, longe volta; aproximar o cartão do IR avança | Anterior e próximo |

O TCRT5000 precisa de um alvo a poucos milímetros. O ultrassom responde a uma mão ou superfície na sua frente. Não confundir esses dois alcances. Na música, é necessário clicar em **Ativar som**; o navegador exige essa ação para liberar o áudio. Os slides são uma apresentação interna do aplicativo.

## Estado, progresso e origem

A interface reutiliza os motores existentes de pet, evolução, física de lançamento, moedas e melhorias. O estado do pet e os comandos de cuidado continuam sincronizados com a ESP32 pelo protocolo JSON Lines. O nome **Piu-piu** é o nome de apresentação no notebook, preservando o nome e as estatísticas do save legado da placa; não é necessária uma gravação de firmware para isso.

O controle dos modos gráficos usa regras explícitas de distância e transições do IR. Os eventos do classificador embarcado continuam visíveis nos detalhes, sem substituir esses controles nem declarar um modelo TinyML treinado com dados reais.

Desconexão ou leituras com mais de dois segundos bloqueiam ações e silenciam a música. Não há leituras inventadas quando a ESP32 está desconectada. A versão padrão oferece somente portas físicas.

Para testar o software sem a placa, inicie explicitamente com `--demo` e escolha a porta **DEMO**. A interface identifica essa origem como demonstração. O save dessa demonstração fica separado em `data/saves/web_demo.save.json`.

O aplicativo funciona no próprio notebook, escuta somente em 127.0.0.1 e não precisa de conta, nuvem ou dependências de frontend. O servidor usa o ambiente Python do projeto e a dependência pyserial já existente. Ctrl+C no terminal do servidor encerra e libera a porta.

## Limites da verificação

As tensões da montagem e a precisão metrológica do ultrassom não foram medidas. Uma leitura de distância na interface não substitui essas verificações. O LCD físico foi retirado do escopo; os quadros lógicos 20×4 podem continuar disponíveis nos detalhes do protocolo.
