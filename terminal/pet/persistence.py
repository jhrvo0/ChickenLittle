"""Persistência atômica em JSON para o progresso do MotionPet."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from terminal.pet.state import PetState

SAVE_SCHEMA_VERSION = 1


class PersistenceError(RuntimeError):
    """Erro ao salvar ou carregar o arquivo de progresso do pet."""


class PetPersistence:
    """Gerencia salvamento e carregamento atômico do estado do pet em disco."""

    def __init__(self, save_path: str | Path) -> None:
        self.save_path = Path(save_path)

    def exists(self) -> bool:
        return self.save_path.is_file()

    def save(self, state: PetState) -> Path:
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SAVE_SCHEMA_VERSION,
            "saved_at_unix": int(time.time()),
            "pet": state.to_dict(),
        }
        tmp_path = self.save_path.with_suffix(self.save_path.suffix + ".tmp")
        try:
            content = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, self.save_path)
        except OSError as exc:
            raise PersistenceError(f"Falha ao gravar save em '{self.save_path}': {exc}") from exc
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return self.save_path

    def load(self) -> PetState:
        if not self.exists():
            raise PersistenceError(f"Arquivo de save não encontrado: '{self.save_path}'")
        try:
            raw = json.loads(self.save_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistenceError(f"Arquivo de save inválido ou corrompido: {exc}") from exc

        if not isinstance(raw, dict):
            raise PersistenceError("Estrutura raiz do save deve ser um objeto JSON")

        version = raw.get("schema_version")
        if version != SAVE_SCHEMA_VERSION:
            raise PersistenceError(
                f"Versão de save incompatível: {version!r} (esperado {SAVE_SCHEMA_VERSION})"
            )

        pet_data = raw.get("pet")
        if not isinstance(pet_data, dict):
            raise PersistenceError("Campo 'pet' ausente ou inválido no arquivo de save")

        try:
            return PetState.from_dict(pet_data)
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceError(f"Dados de estado do pet inválidos no save: {exc}") from exc

    def load_or_create(self, default_name: str = "Pip") -> tuple[PetState, bool]:
        """Carrega o save existente ou retorna um novo `PetState` (`loaded=False`)."""
        if not self.exists():
            return PetState(name=default_name), False
        return self.load(), True
