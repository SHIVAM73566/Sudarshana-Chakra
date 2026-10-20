"""Unified Tool Registry facade for Sudarshana Chakra AI.

Aggregates every execution surface behind one clean, high-speed API so callers
never need to know whether a capability is a built-in action, a dynamic feature
skill, or a local business vertical:

* **built-in tools**  - declared in ``main.py`` ``TOOL_DECLARATIONS`` and
  dispatched by :func:`agent.executor._call_tool`.
* **dynamic skills**  - hot-loaded from ``features/`` by
  :class:`core.dynamic_registry.DynamicToolRegistry`.
* **business verticals** - manufacturing / procurement / inventory / finance /
  marketing modules under :mod:`core.business`.

The facade is read-mostly and import-safe: it never imports heavyweight modules
at construction time and degrades gracefully when optional pieces are missing.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger("sudarshana.tool_registry")

__all__ = [
    "ToolRegistry",
    "get_registry",
    "register_tool",
    "list_tools",
    "get_declarations",
]

# Business verticals are lightweight and always available.
_VERTICAL_MODULES: dict[str, str] = {
    "inventory_manager": "core.business.inventory",
    "procurement_manager": "core.business.procurement",
    "finance_manager": "core.business.finance",
    "manufacturing_manager": "core.business.manufacturing",
    "marketing_manager": "core.business.marketing",
}


class _ToolEntry:
    __slots__ = ("name", "kind", "description", "executor", "metadata")

    def __init__(
        self,
        name: str,
        kind: str,
        description: str,
        executor: Callable[..., Any] | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self.description = description
        self.executor = executor
        self.metadata = metadata or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "metadata": self.metadata,
        }


class ToolRegistry:
    """Aggregated, lazily-initialized view over all tool sources."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _ToolEntry] = {}
        self._custom: dict[str, Callable[..., Any]] = {}
        self._initialized = False

    # -- discovery ---------------------------------------------------------- #

    def initialize(self, force: bool = False) -> int:
        with self._lock:
            if self._initialized and not force:
                return len(self._entries)
            self._entries.clear()
            self._load_builtins()
            self._load_business_verticals()
            self._load_dynamic_skills()
            for name, fn in self._custom.items():
                self._entries[name] = _ToolEntry(name, "custom", "User-registered tool", fn)
            self._initialized = True
            logger.info("[ToolRegistry] Initialized with %d tools.", len(self._entries))
            return len(self._entries)

    def _load_builtins(self) -> None:
        try:
            import main as _main  # noqa: PLC0415 - intentional lazy import
            declarations = getattr(_main, "TOOL_DECLARATIONS", [])
        except Exception as exc:
            logger.debug("[ToolRegistry] builtins unavailable: %s", exc)
            declarations = []
        for decl in declarations:
            name = decl.get("name") if isinstance(decl, dict) else None
            if not name:
                continue
            self._entries[name] = _ToolEntry(
                name,
                "builtin",
                str(decl.get("description") or ""),
                None,
                {"parameters": decl.get("parameters") or {}},
            )

    def _load_business_verticals(self) -> None:
        import importlib

        for name, module_path in _VERTICAL_MODULES.items():
            try:
                module = importlib.import_module(module_path)
                meta = getattr(module, "FEATURE_METADATA", {}) or {}
                aliases = meta.get("aliases") or []
                entry = _ToolEntry(
                    name,
                    "business",
                    str(meta.get("description") or f"Business vertical {name}"),
                    getattr(module, "execute", None),
                    {"parameters": meta.get("parameters") or {}},
                )
                self._entries[name] = entry
                for alias in aliases:
                    self._entries.setdefault(alias, entry)
            except Exception as exc:
                logger.warning("[ToolRegistry] business vertical '%s' failed: %s", name, exc)

    def _load_dynamic_skills(self) -> None:
        try:
            from core.dynamic_registry import DynamicToolRegistry

            DynamicToolRegistry.initialize()
            for declaration in DynamicToolRegistry.get_tool_declarations():
                name = declaration.get("name")
                if not name:
                    continue
                skill = DynamicToolRegistry.get_skill(name)
                self._entries[name] = _ToolEntry(
                    name,
                    "feature",
                    str(declaration.get("description") or ""),
                    getattr(skill, "execute_sync", None) if skill else None,
                    {"parameters": declaration.get("parameters") or {}},
                )
        except Exception as exc:
            logger.debug("[ToolRegistry] dynamic skills unavailable: %s", exc)

    # -- public API --------------------------------------------------------- #

    def register(self, name: str, executor: Callable[..., Any], *, description: str = "") -> None:
        with self._lock:
            self._custom[name] = executor
            self._entries[name] = _ToolEntry(name, "custom", description or "User-registered tool", executor)

    def list_tools(self) -> list[dict[str, Any]]:
        if not self._initialized:
            self.initialize()
        return [entry.as_dict() for entry in self._entries.values()]

    def names(self) -> list[str]:
        if not self._initialized:
            self.initialize()
        return sorted(self._entries.keys())

    def count(self) -> int:
        return self.initialize()

    def get_tool(self, name: str) -> dict[str, Any] | None:
        if not self._initialized:
            self.initialize()
        entry = self._entries.get(name)
        return entry.as_dict() if entry else None

    def has_tool(self, name: str) -> bool:
        if not self._initialized:
            self.initialize()
        return name in self._entries

    def get_declarations(self) -> list[dict[str, Any]]:
        """Return Gemini-compatible declarations for every tool with a schema."""
        if not self._initialized:
            self.initialize()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in self._entries.values():
            if entry.name in seen:
                continue
            seen.add(entry.name)
            params = entry.metadata.get("parameters")
            if not isinstance(params, dict):
                continue
            schema = dict(params)
            schema.setdefault("type", "OBJECT")
            schema.setdefault("properties", {})
            out.append({"name": entry.name, "description": entry.description, "parameters": schema})
        return out

    def execute(self, name: str, parameters: dict[str, Any] | None = None, *, player: Any = None, speak: Any = None) -> Any:
        """Execute a tool by name, routing to the correct source.

        Business/custom tools run their own ``execute``; everything else is
        delegated to the executor dispatcher so behaviour stays identical to the
        existing call paths.
        """
        if not self._initialized:
            self.initialize()
        entry = self._entries.get(name)
        if entry is not None and entry.executor is not None and entry.kind in ("business", "feature", "custom"):
            return entry.executor(parameters=parameters or {}, player=player)
        from agent.executor import _call_tool

        return _call_tool(name, parameters or {}, speak, player=player)


_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ToolRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ToolRegistry()
        return _registry


def register_tool(name: str, executor: Callable[..., Any], *, description: str = "") -> None:
    get_registry().register(name, executor, description=description)


def list_tools() -> list[dict[str, Any]]:
    return get_registry().list_tools()


def get_declarations() -> list[dict[str, Any]]:
    return get_registry().get_declarations()
