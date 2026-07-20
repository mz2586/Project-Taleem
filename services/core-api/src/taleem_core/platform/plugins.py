"""Plugin / bounded-context module registry (pure-stdlib).

The modulith composes bounded-context modules behind facades (docs/08 §2, docs/47 §3). Each
context registers a `Module` describing its name, router mount path, health check, and the
events it publishes. This registry is the composition root's single source of truth and makes
"extraction = move a module", not a rewrite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Module:
    name: str
    mount: str  # e.g. "/v1/sync"
    healthcheck: Callable[[], bool] = lambda: True
    events_published: tuple[str, ...] = ()


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}

    def register(self, module: Module) -> None:
        if module.name in self._modules:
            raise ValueError(f"module already registered: {module.name}")
        # Enforce a boundary invariant: no two modules may claim the same mount.
        for existing in self._modules.values():
            if existing.mount == module.mount:
                raise ValueError(f"mount conflict: {module.mount} ({existing.name} vs {module.name})")
        self._modules[module.name] = module

    def all(self) -> tuple[Module, ...]:
        return tuple(self._modules.values())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._modules))

    def health(self) -> dict[str, bool]:
        return {m.name: bool(m.healthcheck()) for m in self._modules.values()}


_registry = ModuleRegistry()


def registry() -> ModuleRegistry:
    return _registry
