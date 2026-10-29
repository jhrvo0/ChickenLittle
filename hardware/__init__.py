"""MotionPet - representacao eletronica canonica (netlist -> protoboard -> CAD -> guia).

Fluxo: firmware (pinout_config.h) -> netlist canonica (JSON) -> modelo fisico da protoboard
-> diagramas / .fzz / Wokwi / guia HTML -> validacao cruzada.

Nenhuma etapa aqui valida o hardware fisico: o status oficial permanece
PENDING_PHYSICAL_VALIDATION ate as medicoes de bancada.
"""

__all__ = ["model"]
