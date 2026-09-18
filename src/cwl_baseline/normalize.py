# Copyright 2026 Transpiler-Mate
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Convert cwl-utils DOMs to stable, scoped comparison representations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urldefrag

from transpiler_mate.api import PluginFailureError, TranspilerContext

# Rewrite only CWL identifier/reference slots, never expressions, defaults,
# command arguments, file locations, format URIs, or arbitrary extension values.
IDENTIFIERS = {"id", "name", "source", "outputSource", "run", "scatter", "symbols"}
PRIMITIVES = {
    "null",
    "boolean",
    "int",
    "long",
    "float",
    "double",
    "string",
    "File",
    "Directory",
    "Any",
}


def identifier(value: str, source: str) -> str:
    base, _ = urldefrag(source)
    if value.startswith(base + "#"):
        return value[len(base) + 1 :]
    if value == base:
        return "@document"
    return value.removeprefix("#")


def normalize(value: Any, source: str, key: str = "") -> Any:
    if (
        key
        in {"default", "arguments", "expression", "valueFrom", "outputEval", "hints"}
        or "://" in key
    ):
        return value
    if isinstance(value, Mapping):
        return {k: normalize(v, source, k) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, source, key) for v in value]
    # Anonymous inline Process IDs are generated UUIDs on each load. Their
    # enclosing step/run path provides identity, so the UUID is not a change.
    if key == "id" and isinstance(value, str) and value.startswith("_:"):
        return "@anonymous"
    if isinstance(value, str) and (key in IDENTIFIERS or key in {"type", "items"}):
        return identifier(value, source)
    return value


def document(context: TranspilerContext) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    source = str(context.source)
    for key, process in context.document.items():
        name = identifier(key, source)
        if name in result:
            raise PluginFailureError(f"Duplicate normalized Process identity: {name!r}")
        result[name] = normalize(process.save(relative_uris=False), source)
    return result


def index(values: Any, key: str = "id") -> dict[str, Any]:
    if isinstance(values, dict):
        return values
    result = {}
    for value in values or []:
        name = value if isinstance(value, str) else value[key]
        if name in result:
            raise PluginFailureError(f"Duplicate {key}: {name!r}")
        result[name] = value
    return result


def local_fields(values: Any) -> dict[str, Any]:
    """Record field names are relative to the enclosing named schema."""
    result = {}
    for name, value in index(values, "name").items():
        local = name.rsplit("/", 1)[-1]
        if local in result:
            raise PluginFailureError(f"Ambiguous record field name: {local!r}")
        result[local] = value
    return result


def _collect_schemas(value: Any, result: dict[str, Any]) -> None:
    if isinstance(value, dict):
        if value.get("type") in ("record", "enum") and "name" in value:
            name = value["name"]
            if name in result and result[name] != value:
                raise PluginFailureError(f"Conflicting named schema: {name!r}")
            result[name] = value
        for key, child in value.items():
            # Embedded processes have their own requirement scope.
            if key != "run":
                _collect_schemas(child, result)
    elif isinstance(value, list):
        for child in value:
            _collect_schemas(child, result)


def schemas(process: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    _collect_schemas(process, result)
    # cwl-utils may retain unqualified type references. Resolve a short
    # reference only when it denotes exactly one schema in this Process.
    aliases: dict[str, list[Any]] = {}
    for name, schema in result.items():
        aliases.setdefault(name.rsplit("/", 1)[-1].rsplit("#", 1)[-1], []).append(
            schema
        )
    for name, candidates in aliases.items():
        if len(candidates) == 1 and name not in result:
            result[name] = candidates[0]
    return result
