# Copyright 2026 Terradue
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

"""Directional CWL type assignability with an explicit unknown result."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .normalize import PRIMITIVES, local_fields

if TYPE_CHECKING:
    from collections.abc import Callable


def all_results(values: list[bool | None]) -> bool | None:
    return False if False in values else None if None in values else True


def any_result(values: list[bool | None]) -> bool | None:
    return True if True in values else None if None in values else False


def resolve(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value.endswith("?"):
            return ["null", resolve(value[:-1], definitions)]
        if value.endswith("[]"):
            return {"type": "array", "items": resolve(value[:-2], definitions)}
        return definitions.get(value, value)
    if isinstance(value, dict) and set(value) == {"type"}:
        return resolve(value["type"], definitions)
    return value


def nullable(value: Any, definitions: dict[str, Any]) -> bool:
    value = resolve(value, definitions)
    return value == "null" or (
        isinstance(value, list) and any(nullable(v, definitions) for v in value)
    )


def omittable(parameter: dict[str, Any], definitions: dict[str, Any]) -> bool:
    return "default" in parameter or nullable(parameter["type"], definitions)


def assignable(
    source: Any,
    target: Any,
    source_definitions: dict[str, Any],
    target_definitions: dict[str, Any],
    active: frozenset[tuple[str, str]] = frozenset(),
) -> bool | None:
    """Return whether every source value fits the target, or None when unknown."""
    source = resolve(source, source_definitions)
    target = resolve(target, target_definitions)
    pair = (json.dumps(source, sort_keys=True), json.dumps(target, sort_keys=True))
    if pair in active:
        return True
    active = active | {pair}

    def check(a: Any, b: Any) -> bool | None:
        return assignable(a, b, source_definitions, target_definitions, active)

    if isinstance(source, list):
        return all_results([check(item, target) for item in source])
    if isinstance(target, list):
        return any_result([check(source, item) for item in target])
    if isinstance(source, dict) and isinstance(target, dict):
        return _structured_assignable(source, target, source_definitions, target_definitions, check)
    return _scalar_assignable(source, target)


def _scalar_assignable(source: object, target: object) -> bool | None:
    """Compare primitive types, including numeric promotions and unresolved names."""
    if any(isinstance(value, str) and value not in PRIMITIVES for value in (source, target)):
        return None
    if target == "Any":
        # CWL Any is a non-null value. Null must be included explicitly.
        return not isinstance(source, str) or source != "null"
    if source == "Any":
        return isinstance(target, str) and target == "Any"
    if isinstance(source, str) and isinstance(target, str):
        promotions = {
            "int": {"long", "float", "double"},
            "long": {"float", "double"},
            "float": {"double"},
        }
        return source == target or target in promotions.get(source, set())
    return False


def _structured_assignable(
    source: dict[str, Any],
    target: dict[str, Any],
    source_definitions: dict[str, Any],
    target_definitions: dict[str, Any],
    check: Callable[[Any, Any], bool | None],
) -> bool | None:
    kind = source.get("type")
    if kind != target.get("type"):
        return False
    if kind == "array":
        return check(source["items"], target["items"])
    if kind == "enum":
        # Keep scoped enum symbol identity; namespaces are meaningful.
        return set(source["symbols"]) <= set(target["symbols"])
    if kind == "record":
        return _record_assignable(source, target, source_definitions, target_definitions, check)
    return None


def _record_assignable(
    source: dict[str, Any],
    target: dict[str, Any],
    source_definitions: dict[str, Any],
    target_definitions: dict[str, Any],
    check: Callable[[Any, Any], bool | None],
) -> bool | None:
    """Check target record fields and omission guarantees against the source."""
    source_fields = local_fields(source.get("fields", []))
    target_fields = local_fields(target.get("fields", []))
    results: list[bool | None] = []
    for name, field in target_fields.items():
        if name not in source_fields:
            results.append(omittable(field, target_definitions))
        else:
            old = source_fields[name]
            if omittable(old, source_definitions) and not omittable(field, target_definitions):
                results.append(False)
            results.append(check(old["type"], field["type"]))
    # Extra record fields are structurally tolerated; behavioral effects
    # of field removal/default changes are reported separately.
    return all_results(results)
