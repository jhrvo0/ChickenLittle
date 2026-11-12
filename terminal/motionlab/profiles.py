"""Perfis de gestos (gatilho → ação) e ajustes do MotionLab, com validação e persistência local."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re

from terminal.motionlab.actions import CATALOG, CONTEXTS, TRIGGERS

SETTINGS_VERSION = 1
DEFAULT_SETTINGS_PATH = Path("data/motionlab/settings.json")
DRIVERS = ("rules", "ml", "device")
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

# Limites dos ajustes: (mínimo, máximo)
LIMITS = {
    "min_confidence": (0.5, 0.99),
    "cooldown_ms": (200, 5000),
    "near_cm": (2.0, 30.0),
    "far_cm": (15.0, 120.0),
    "ir_hold_ms": (500, 3000),
}

DEFAULT_PROFILES = [
    {"id": "media", "name": "Mídia", "context": "control", "builtin": True, "bindings": {
        "IR_TAP": "media.play_pause", "APPROACH": "media.next", "RETREAT": "media.prev", "IR_HOLD": "lab.toggle_armed"}},
    {"id": "presenter", "name": "Apresentador", "context": "control", "builtin": True, "bindings": {
        "APPROACH": "present.next", "RETREAT": "present.prev", "IR_TAP": "present.next", "IR_HOLD": "lab.toggle_armed"}},
    {"id": "volume", "name": "Volume", "context": "control", "builtin": True, "bindings": {
        "APPROACH": "media.volume_up", "RETREAT": "media.volume_down", "IR_TAP": "media.mute", "IR_HOLD": "lab.toggle_armed"}},
    {"id": "canvas", "name": "Canvas", "context": "canvas", "builtin": True, "bindings": {
        "APPROACH": "canvas.burst", "RETREAT": "canvas.next_palette", "IR_TAP": "canvas.next_style", "IR_HOLD": "canvas.freeze"}},
    # Na música a distância já toca a nota: aproximar/afastar acontece o tempo todo. Por isso o
    # perfil padrão só usa o IR (comando discreto deliberado) e deixa os gestos sem ação.
    {"id": "music", "name": "Música", "context": "music", "builtin": True, "bindings": {
        "IR_TAP": "music.toggle_record", "IR_HOLD": "music.next_timbre"}},
    {"id": "deck", "name": "Deck integrado", "context": "slides", "builtin": True, "bindings": {
        "APPROACH": "slides.next", "RETREAT": "slides.prev", "IR_TAP": "slides.next", "IR_HOLD": "slides.blank"}},
    {"id": "deck-external", "name": "Apresentação externa", "context": "slides", "builtin": True, "bindings": {
        "APPROACH": "present.next", "RETREAT": "present.prev", "IR_TAP": "present.next", "IR_HOLD": "present.blank"}},
]

DEFAULT_SETTINGS = {
    "driver": "rules",
    "min_confidence": 0.70,
    "cooldown_ms": 900,
    "repeat_lock": True,
    "near_cm": 5.0,
    "far_cm": 45.0,
    "ir_hold_ms": 900,
}

DEFAULT_ACTIVE = {"control": "presenter", "canvas": "canvas", "music": "music", "slides": "deck"}


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Perfil inválido.")
    pid = profile.get("id")
    if not isinstance(pid, str) or not _ID.match(pid):
        raise ValueError("Identificador de perfil inválido (use a-z, 0-9, - e _).")
    name = profile.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("O nome do perfil precisa ter de 1 a 40 caracteres.")
    context = profile.get("context")
    if context not in CONTEXTS:
        raise ValueError("Contexto de perfil inválido.")
    bindings = profile.get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("Mapeamentos inválidos.")
    clean = {}
    for trigger, action in bindings.items():
        if trigger not in TRIGGERS:
            raise ValueError(f"Gatilho desconhecido: {trigger}.")
        if action in (None, ""):
            continue
        spec = CATALOG.get(action)
        if spec is None:
            raise ValueError(f"Ação fora da lista permitida: {action}.")
        if context not in spec.contexts:
            raise ValueError(f"A ação {action} não vale no contexto {context}.")
        clean[trigger] = action
    return {"id": pid, "name": name.strip(), "context": context, "builtin": bool(profile.get("builtin", False)), "bindings": clean}


def validate_setting(key: str, value):
    if key == "driver":
        if value not in DRIVERS:
            raise ValueError("Fonte de gestos inválida.")
        return value
    if key == "repeat_lock":
        if not isinstance(value, bool):
            raise ValueError("Valor inválido para a trava de repetição.")
        return value
    if key not in LIMITS:
        raise ValueError(f"Ajuste desconhecido: {key}.")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise ValueError(f"Valor inválido para {key}.")
    lo, hi = LIMITS[key]
    if not lo <= value <= hi:
        raise ValueError(f"{key} precisa ficar entre {lo} e {hi}.")
    return int(value) if key in {"cooldown_ms", "ir_hold_ms"} else float(value)


class ProfileStore:
    """Perfis + ajustes. Salva em JSON; um arquivo corrompido não impede o uso (volta ao padrão)."""

    def __init__(self, path: Path | None = DEFAULT_SETTINGS_PATH) -> None:
        self.path = path
        self.load_error: str | None = None
        self.settings = dict(DEFAULT_SETTINGS)
        self.profiles: dict[str, dict] = {p["id"]: copy.deepcopy(p) for p in DEFAULT_PROFILES}
        self.active = dict(DEFAULT_ACTIVE)
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != SETTINGS_VERSION:
                raise ValueError("versão desconhecida")
            settings = dict(DEFAULT_SETTINGS)
            for key, value in (data.get("settings") or {}).items():
                if key in DEFAULT_SETTINGS:
                    settings[key] = validate_setting(key, value)
            if settings["near_cm"] >= settings["far_cm"]:
                raise ValueError("zona ativa inválida")
            profiles = {p["id"]: copy.deepcopy(p) for p in DEFAULT_PROFILES}
            for raw in data.get("profiles") or []:
                prof = validate_profile(raw)
                profiles[prof["id"]] = prof
            active = dict(DEFAULT_ACTIVE)
            for ctx, pid in (data.get("active") or {}).items():
                if ctx in CONTEXTS and pid in profiles and profiles[pid]["context"] == ctx:
                    active[ctx] = pid
            self.settings, self.profiles, self.active = settings, profiles, active
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            self.load_error = f"Ajustes salvos ignorados ({exc}); usando o padrão."

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": SETTINGS_VERSION, "settings": self.settings,
                "profiles": list(self.profiles.values()), "active": self.active}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def update_settings(self, changes: dict) -> None:
        if not isinstance(changes, dict) or not changes:
            raise ValueError("Nenhum ajuste enviado.")
        new = dict(self.settings)
        for key, value in changes.items():
            if key not in DEFAULT_SETTINGS:
                raise ValueError(f"Ajuste desconhecido: {key}.")
            new[key] = validate_setting(key, value)
        if new["near_cm"] >= new["far_cm"]:
            raise ValueError("A distância 'perto' precisa ser menor que 'longe'.")
        self.settings = new
        self.save()

    def upsert_profile(self, raw: dict) -> dict:
        prof = validate_profile(raw)
        existing = self.profiles.get(prof["id"])
        if existing is not None and existing["context"] != prof["context"]:
            raise ValueError("Não é possível mudar o contexto de um perfil existente.")
        prof["builtin"] = bool(existing and existing.get("builtin"))
        if existing is None and len(self.profiles) >= 40:
            raise ValueError("Limite de perfis atingido.")
        self.profiles[prof["id"]] = prof
        self.save()
        return prof

    def delete_profile(self, pid: str) -> None:
        prof = self.profiles.get(pid)
        if prof is None:
            raise ValueError("Perfil não encontrado.")
        if prof.get("builtin"):
            raise ValueError("Perfis de fábrica não podem ser apagados (edite ou crie uma cópia).")
        del self.profiles[pid]
        if self.active.get(prof["context"]) == pid:
            self.active[prof["context"]] = DEFAULT_ACTIVE[prof["context"]]
        self.save()

    def reset_profile(self, pid: str) -> None:
        default = next((p for p in DEFAULT_PROFILES if p["id"] == pid), None)
        if default is None:
            raise ValueError("Só perfis de fábrica podem ser restaurados.")
        self.profiles[pid] = copy.deepcopy(default)
        self.save()

    def activate(self, context: str, pid: str) -> None:
        prof = self.profiles.get(pid)
        if context not in CONTEXTS or prof is None or prof["context"] != context:
            raise ValueError("Perfil inválido para este módulo.")
        self.active[context] = pid
        self.save()

    def active_profile(self, context: str) -> dict:
        return self.profiles[self.active[context]]

    def to_dict(self) -> dict:
        return {"settings": dict(self.settings), "profiles": copy.deepcopy(list(self.profiles.values())),
                "active": dict(self.active), "load_error": self.load_error}
