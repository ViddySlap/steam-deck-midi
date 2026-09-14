"""Machine-local bridge identity shared by startup, HTTP settings, and reloads."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from windows.config import ConfigError, validate_preset_section


@dataclass
class BridgeSettings:
    path: Path
    preset_section: str | None = None

    @classmethod
    def load(cls, path: Path, override: str | None = None) -> BridgeSettings:
        """Explicit argv wins; an absent local file keeps legacy presets usable."""
        if override is not None:
            validate_preset_section(override)
            return cls(path, override)
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return cls(path)
        except (OSError, ValueError) as exc:
            raise ConfigError(f"cannot read bridge settings {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"bridge settings must be an object: {path}")
        section = raw.get("preset_section")
        validate_preset_section(section)
        return cls(path, section)

    def save(self, section: str | None) -> None:
        """Persist atomically before changing the running bridge's selection."""
        self._save(section, overwrite=True)

    def save_if_missing(self, section: str) -> bool:
        """Create a complete first-run file without replacing an existing one."""
        if self.path.exists():
            self.preset_section = self.load(self.path).preset_section
            return False
        return self._save(section, overwrite=False)

    def _save(self, section: str | None, *, overwrite: bool) -> bool:
        validate_preset_section(section)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".bridge-", suffix=".tmp", delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
                json.dump({"preset_section": section}, tmp, indent=2)
                tmp.write("\n")
            if overwrite:
                os.replace(tmp_path, self.path)
            else:
                try:
                    os.link(tmp_path, self.path)
                except FileExistsError:
                    self.preset_section = self.load(self.path).preset_section
                    return False
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        self.preset_section = section
        return True
