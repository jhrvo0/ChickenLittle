# ml/export — Exportação Estática para C++ e TinyML

Este módulo é responsável por transpilar o modelo treinado em Python para código fonte C++ estático e auto-contido, pronto para inclusão no firmware do ESP32 (Etapa 11 de `docs/ml_pipeline_spec.md`).

---

## 1. Entradas e Saídas do Ciclo 2

- **Entradas**:
  - Modelo vencedor selecionado pela avaliação em `ml/evaluation/` (ex: `DecisionTreeClassifier`).
- **Saídas**:
  - Arquivo de cabeçalho C++ gerado em `firmware/gestures/tinyml_model.h`.
  - Vetor de casos de teste em C++ para verificação de paridade numérica entre a inferência Python e a inferência no ESP32.

---

## 2. Restrições Rígidas de Engenharia de Software Embarcado

O código gerado para o ESP32 deve satisfazer rigorosamente:
1. **Zero Alocação Dinâmica de Heap**:
   - É proibido o uso de `malloc`, `free`, `realloc`, operadores `new` e `delete`, e classes dinâmicas como `std::string` ou `std::vector`.
2. **Constantes Armazenadas na Flash (`const PROGMEM`)**:
   - Todas as tabelas de limiares, nós de árvores ou matrizes de pesos sinápticos devem ser marcadas com qualificadores `const` para que o linker as posicione na memória Flash (ROM), preservando a escassa memória SRAM do ESP32.
3. **Assinatura Padronizada de Inferência**:
   ```cpp
   GestureType tinyml_infer(const float features[GESTURE_FEATURE_COUNT]);
   ```
4. **Verificação de Paridade**:
   - O módulo deve executar testes automatizados comparando os resultados da função Python `.predict()` e da saída da função compilada em C++ sobre uma amostra de teste para garantir equivalência de 100%.
