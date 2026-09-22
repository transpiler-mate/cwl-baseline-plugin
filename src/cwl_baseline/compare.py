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

"""CWL public-contract comparison and complete residual field reporting."""

from __future__ import annotations

import json
from typing import Any, Literal

import semver
from transpiler_mate.api import PluginFailureError, TranspilerContext

from .models import BaselineReport, Bump, Finding, FindingCategory
from .normalize import document, index, local_fields, schemas
from .types import assignable, omittable, resolve

BUMP_PRIORITY = {Bump.NONE: 0, Bump.PATCH: 1, Bump.MINOR: 2, Bump.MAJOR: 3}

MISSING = object()
DOCUMENTATION = {
    "label",
    "doc",
    "https://schema.org/name",
    "http://schema.org/name",
    "https://schema.org/description",
    "http://schema.org/description",
}
VERSIONS = {"https://schema.org/softwareVersion", "http://schema.org/softwareVersion"}


def equal(old: Any, new: Any) -> bool:
    """JSON equality must distinguish booleans from numeric literals."""
    if old is MISSING or new is MISSING:
        return old is new
    return json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True)


def path_join(path: str, key: str) -> str:
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def alternatives(
    values: list[Any], definitions: dict[str, Any]
) -> dict[tuple[Any, Any], Any] | None:
    result = {}
    for value in values:
        resolved = resolve(value, definitions)
        key = (
            (resolved.get("type"), resolved.get("name"))
            if isinstance(resolved, dict)
            else (str(resolved), None)
        )
        if key in result:
            return None
        result[key] = value
    return result


class Comparator:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.covered_schemas: set[str] = set()

    def add(
        self,
        rule: str,
        path: str,
        bump: Bump,
        message: str,
        before: Any = MISSING,
        after: Any = MISSING,
        *,
        review: bool = False,
        category: FindingCategory = FindingCategory.INTERFACE,
    ) -> None:
        self.findings.append(
            Finding(
                rule=rule,
                path=path,
                minimum_bump=bump,
                message=message,
                before=None if before is MISSING else before,
                after=None if after is MISSING else after,
                before_present=before is not MISSING,
                after_present=after is not MISSING,
                review_required=review,
                category=category,
            )
        )

    def residual(
        self, old: Any, new: Any, path: str, *, metadata: bool = False
    ) -> None:
        """Account for every remaining changed field without guessing behavior."""
        if equal(old, new):
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                self.residual(
                    old.get(key, MISSING),
                    new.get(key, MISSING),
                    path_join(path, key),
                    metadata=metadata or key in DOCUMENTATION,
                )
            return
        self.add(
            "metadata.changed" if metadata else "behavior.changed",
            path,
            Bump.NONE,
            "Descriptive metadata changed."
            if metadata
            else "Behavioral compatibility requires review.",
            old,
            new,
            review=not metadata,
            category=FindingCategory.METADATA if metadata else FindingCategory.BEHAVIOR,
        )

    def parameters(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
        path: str,
        direction: str,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
        active: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        for name in sorted(old.keys() | new.keys()):
            location = path_join(path, name)
            if name not in new:
                self.add(
                    f"{direction}.removed",
                    location,
                    Bump.MAJOR,
                    "Public parameter removed.",
                    old[name],
                    MISSING,
                )
            elif name not in old:
                required = direction == "input" and not omittable(new[name], new_defs)
                self.add(
                    f"{direction}.added",
                    location,
                    Bump.MAJOR if required else Bump.MINOR,
                    "Required input added without a default."
                    if required
                    else "Public parameter added.",
                    MISSING,
                    new[name],
                )
            else:
                self.parameter(
                    old[name],
                    new[name],
                    location,
                    direction,
                    old_defs,
                    new_defs,
                    active,
                )

    def parameter(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
        path: str,
        direction: str,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
        active: frozenset[tuple[str, str]],
    ) -> None:
        if (
            direction == "input"
            and omittable(old, old_defs)
            and not omittable(new, new_defs)
        ):
            self.add(
                "input.omission_removed",
                path,
                Bump.MAJOR,
                "The input can no longer be omitted.",
                old,
                new,
            )
        if not equal(old.get("default", MISSING), new.get("default", MISSING)):
            self.add(
                "default.changed",
                path_join(path, "default"),
                Bump.NONE,
                "A default changed; omitted/null inputs may behave differently.",
                old.get("default", MISSING),
                new.get("default", MISSING),
                review=True,
                category=FindingCategory.BEHAVIOR,
            )
        self.type_change(
            old["type"],
            new["type"],
            path_join(path, "type"),
            direction,
            old_defs,
            new_defs,
            active,
        )
        self.formats(
            old.get("format", MISSING),
            new.get("format", MISSING),
            path_join(path, "format"),
            direction,
        )
        self.secondary(
            old.get("secondaryFiles", []),
            new.get("secondaryFiles", []),
            path_join(path, "secondaryFiles"),
            direction,
        )
        excluded = {"id", "name", "type", "default", "format", "secondaryFiles"}
        self.residual(
            {k: v for k, v in old.items() if k not in excluded},
            {k: v for k, v in new.items() if k not in excluded},
            path,
        )

    def type_change(
        self,
        old: Any,
        new: Any,
        path: str,
        direction: str,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
        active: frozenset[tuple[str, str]],
    ) -> None:
        previous, current = resolve(old, old_defs), resolve(new, new_defs)
        for value in (previous, current):
            if isinstance(value, dict) and "name" in value:
                self.covered_schemas.add(value["name"])
        pair = (repr(previous), repr(current))
        if pair in active:
            return
        active = active | {pair}
        # Match union alternatives by schema kind/name to inspect nested
        # fields, defaults, and metadata as well as whole-union variance.
        if isinstance(previous, list) and isinstance(current, list):
            a, b = alternatives(previous, old_defs), alternatives(current, new_defs)
            if a is not None and b is not None:
                for key in sorted(a.keys() & b.keys(), key=str):
                    self.type_change(
                        a[key],
                        b[key],
                        path_join(path, str(key[1] or key[0])),
                        direction,
                        old_defs,
                        new_defs,
                        active,
                    )
        if self.structured_type_change(
            previous, current, path, direction, old_defs, new_defs, active
        ):
            return
        self.type_compatibility(
            old, new, previous, current, path, direction, old_defs, new_defs
        )

    def structured_type_change(
        self,
        previous: Any,
        current: Any,
        path: str,
        direction: str,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
        active: frozenset[tuple[str, str]],
    ) -> bool:
        # Even unchanged named references can denote changed definitions.
        if isinstance(previous, dict) and isinstance(current, dict):
            if previous.get("type") == current.get("type") == "record":
                self.parameters(
                    local_fields(previous.get("fields", [])),
                    local_fields(current.get("fields", [])),
                    path_join(path, "fields"),
                    direction,
                    old_defs,
                    new_defs,
                    active,
                )
                self.residual(
                    {k: v for k, v in previous.items() if k not in {"fields", "type"}},
                    {k: v for k, v in current.items() if k not in {"fields", "type"}},
                    path,
                )
                return True
            if previous.get("type") == current.get("type") == "array":
                self.type_change(
                    previous["items"],
                    current["items"],
                    path_join(path, "items"),
                    direction,
                    old_defs,
                    new_defs,
                    active,
                )
                self.residual(
                    {k: v for k, v in previous.items() if k not in {"items", "type"}},
                    {k: v for k, v in current.items() if k not in {"items", "type"}},
                    path,
                )
                return True
            if previous.get("type") == current.get("type") == "enum":
                self.residual(
                    {k: v for k, v in previous.items() if k not in {"symbols", "type"}},
                    {k: v for k, v in current.items() if k not in {"symbols", "type"}},
                    path,
                )
        return False

    @staticmethod
    def ambiguous_union_changed(
        previous: Any,
        current: Any,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
    ) -> bool:
        return (
            isinstance(previous, list)
            and isinstance(current, list)
            and (
                alternatives(previous, old_defs) is None
                or alternatives(current, new_defs) is None
            )
            and sorted(json.dumps(v, sort_keys=True) for v in previous)
            != sorted(json.dumps(v, sort_keys=True) for v in current)
        )

    def type_compatibility(
        self,
        old: Any,
        new: Any,
        previous: Any,
        current: Any,
        path: str,
        direction: str,
        old_defs: dict[str, Any],
        new_defs: dict[str, Any],
    ) -> None:
        if previous == current and old_defs == new_defs:
            return
        forward = assignable(old, new, old_defs, new_defs)
        backward = assignable(new, old, new_defs, old_defs)
        compatible = forward if direction == "input" else backward
        if forward is True and backward is True:
            # Union order and equivalent syntaxes alone are not changes.
            # Ambiguous complex alternative matching still needs review.
            if self.ambiguous_union_changed(previous, current, old_defs, new_defs):
                self.add(
                    "type.union_details",
                    path,
                    Bump.NONE,
                    "Review changed complex union alternatives.",
                    previous,
                    current,
                    review=True,
                )
            return
        if (
            previous == current
            and forward is None
            and backward is None
            and old_defs == new_defs
        ):
            return
        if compatible is False:
            self.add(
                f"{direction}.type_incompatible",
                path,
                Bump.MAJOR,
                "Accepted input values narrowed."
                if direction == "input"
                else "Possible output values widened.",
                previous,
                current,
            )
        elif compatible is None:
            self.add(
                "type.unknown",
                path,
                Bump.NONE,
                "Type compatibility could not be established.",
                previous,
                current,
                review=True,
            )
        else:
            self.add(
                f"{direction}.type_compatible",
                path,
                Bump.MINOR if direction == "input" else Bump.PATCH,
                "Accepted input values widened."
                if direction == "input"
                else "Output type narrowed; verify the behavioral contract.",
                previous,
                current,
                review=direction == "output",
            )
        # Constraints/defaults inside union members cannot be inferred solely
        # from assignability. Report a review when complex union schemas change.
        if (isinstance(previous, list) or isinstance(current, list)) and (
            old_defs != new_defs
            or self.complex_union(previous)
            or self.complex_union(current)
        ):
            self.add(
                "type.union_details",
                path,
                Bump.NONE,
                "Review constraints/defaults inside changed complex union members.",
                previous,
                current,
                review=True,
            )

    @staticmethod
    def complex_union(value: Any) -> bool:
        return isinstance(value, list) and any(isinstance(v, dict) for v in value)

    def formats(self, old: Any, new: Any, path: str, direction: str) -> None:
        if equal(old, new):
            return

        def values(value: Any) -> set[str] | None:
            if value is MISSING:
                return None
            items = value if isinstance(value, list) else [value]
            if not all(
                isinstance(v, str) and "$(" not in v and "${" not in v for v in items
            ):
                raise ValueError
            return set(items)

        try:
            previous, current = values(old), values(new)
        except ValueError:
            self.add(
                "format.expression",
                path,
                Bump.NONE,
                "File format expression changed.",
                old,
                new,
                review=True,
            )
            return
        if previous == current:
            return
        # Literal subset proofs need no ontology lookup; disjoint/different
        # format IRIs might still have an rdfs:subClassOf relationship.
        compatible = (
            (current is None or (previous is not None and previous <= current))
            if direction == "input"
            else (previous is None or (current is not None and current <= previous))
        )
        incompatible = (
            (previous is None and current is not None)
            if direction == "input"
            else (current is None and previous is not None)
        )
        self.add(
            "format.changed",
            path,
            (Bump.MINOR if direction == "input" else Bump.PATCH)
            if compatible
            else Bump.MAJOR
            if incompatible
            else Bump.NONE,
            "File format constraint changed; nontrivial ontology relationships require review.",
            old,
            new,
            review=not compatible and not incompatible,
        )

    def secondary(self, old: Any, new: Any, path: str, direction: str) -> None:
        def patterns(values: Any) -> dict[str, Any]:
            result = {}
            for value in values:
                value = {"pattern": value} if isinstance(value, str) else value
                pattern = value["pattern"]
                if pattern in result:
                    raise PluginFailureError(
                        f"Duplicate secondary file pattern at {path}: {pattern!r}"
                    )
                result[pattern] = value.get("required", direction == "input")
            return result

        previous, current = patterns(old), patterns(new)
        for pattern in sorted(previous.keys() | current.keys()):
            a, b = previous.get(pattern, MISSING), current.get(pattern, MISSING)
            if a == b:
                continue
            location = path_join(path, pattern)
            if (
                "$(" in pattern
                or "${" in pattern
                or any(v is not MISSING and not isinstance(v, bool) for v in (a, b))
            ):
                self.add(
                    "secondary_files.expression",
                    location,
                    Bump.NONE,
                    "Secondary-file expression changed.",
                    a,
                    b,
                    review=True,
                )
                continue
            breaking = (
                (b is True and a is not True)
                if direction == "input"
                else (a is True and b is not True)
            )
            self.add(
                "secondary_files.changed",
                location,
                Bump.MAJOR if breaking else Bump.MINOR,
                "Required file constraint/guarantee changed."
                if breaking
                else "Secondary-file contract changed compatibly.",
                a,
                b,
            )

    def process(self, old: dict[str, Any], new: dict[str, Any], path: str) -> None:
        self.covered_schemas.clear()
        old_defs, new_defs = schemas(old), schemas(new)
        if old.get("id") != new.get("id"):
            self.add(
                "process.id_changed",
                path_join(path, "id"),
                Bump.MAJOR,
                "Public Process identifier changed.",
                old.get("id", MISSING),
                new.get("id", MISSING),
            )
        if old.get("class") != new.get("class"):
            self.add(
                "process.class_changed",
                path_join(path, "class"),
                Bump.NONE,
                "Process implementation class changed; review execution semantics.",
                old.get("class"),
                new.get("class"),
                review=True,
                category=FindingCategory.BEHAVIOR,
            )
        for plural, direction in (("inputs", "input"), ("outputs", "output")):
            self.parameters(
                index(old.get(plural, [])),
                index(new.get(plural, [])),
                path_join(path, plural),
                direction,
                old_defs,
                new_defs,
            )
        self.requirements(
            old.get("requirements", []),
            new.get("requirements", []),
            path_join(path, "requirements"),
        )
        self.steps(old.get("steps", []), new.get("steps", []), path_join(path, "steps"))
        if old.get("cwlVersion") != new.get("cwlVersion"):
            self.add(
                "environment.cwl_version",
                path_join(path, "cwlVersion"),
                Bump.NONE,
                "CWL language version changed; verify runner support.",
                old.get("cwlVersion", MISSING),
                new.get("cwlVersion", MISSING),
                review=True,
                category=FindingCategory.ENVIRONMENT,
            )
        excluded = {
            "id",
            "class",
            "inputs",
            "outputs",
            "requirements",
            "steps",
            "cwlVersion",
        } | VERSIONS
        self.residual(
            {k: v for k, v in old.items() if k not in excluded},
            {k: v for k, v in new.items() if k not in excluded},
            path,
        )

    def requirements(self, old: Any, new: Any, path: str) -> None:
        previous, current = index(old, "class"), index(new, "class")
        for name in sorted(previous.keys() | current.keys()):
            a, b = previous.get(name, MISSING), current.get(name, MISSING)
            if a == b:
                continue
            location = path_join(path, name)
            # Schema definitions are compared through parameter types, with
            # residual review covering unused definitions and binding metadata.
            if name == "SchemaDefRequirement":
                old_requirement = {} if a is MISSING else a
                new_requirement = {} if b is MISSING else b
                old_types = index(old_requirement.get("types", []), "name")
                new_types = index(new_requirement.get("types", []), "name")
                for schema_name in sorted(old_types.keys() | new_types.keys()):
                    if schema_name not in self.covered_schemas:
                        self.residual(
                            old_types.get(schema_name, MISSING),
                            new_types.get(schema_name, MISSING),
                            path_join(location, schema_name),
                        )
                self.residual(
                    {
                        k: v
                        for k, v in old_requirement.items()
                        if k not in {"class", "types"}
                    },
                    {
                        k: v
                        for k, v in new_requirement.items()
                        if k not in {"class", "types"}
                    },
                    location,
                )
            elif a is MISSING:
                self.add(
                    "environment.requirement_added",
                    location,
                    Bump.MAJOR,
                    "New mandatory execution requirement may exclude existing runners.",
                    a,
                    b,
                    category=FindingCategory.ENVIRONMENT,
                )
            else:
                self.residual(a, b, location)

    def steps(self, old: Any, new: Any, path: str) -> None:
        previous, current = index(old), index(new)
        for name in sorted(previous.keys() | current.keys()):
            a, b = previous.get(name, MISSING), current.get(name, MISSING)
            location = path_join(path, name)
            if a is MISSING or b is MISSING:
                self.add(
                    "step.added" if a is MISSING else "step.removed",
                    location,
                    Bump.NONE,
                    "Internal step changed; review observable behavior.",
                    a,
                    b,
                    review=True,
                    category=FindingCategory.BEHAVIOR,
                )
            else:
                self.residual(a, b, location)


def parse_version(value: str, label: str) -> semver.Version:
    try:
        return semver.Version.parse(value)
    except (ValueError, TypeError) as error:
        raise PluginFailureError(
            f"{label} software_version must be a valid SemVer string: {value!r}"
        ) from error


def increment(version: semver.Version, bump: Bump) -> semver.Version:
    if bump == Bump.NONE:
        return version
    return {
        Bump.PATCH: version.bump_patch,
        Bump.MINOR: version.bump_minor,
        Bump.MAJOR: version.bump_major,
    }[bump]()


def baseline(
    previous: TranspilerContext,
    current: TranspilerContext,
    *,
    review_bump: Literal["patch", "minor", "major"] | None = None,
) -> BaselineReport:
    """Compare all declared Processes, taking the maximum bump exactly once."""
    old_version = parse_version(previous.metadata.software_version, "Previous")
    new_version = parse_version(current.metadata.software_version, "Current")
    if old_version.prerelease is not None:
        raise PluginFailureError(
            "The comparison baseline must be a released version, not a prerelease."
        )
    old, new = document(previous), document(current)
    if not old:
        raise PluginFailureError("The previous document contains no Processes.")
    comparator = Comparator()
    for name in sorted(old.keys() | new.keys()):
        path = path_join("/processes", name)
        if name not in new:
            comparator.add(
                "process.removed",
                path,
                Bump.MAJOR,
                "Public Process removed.",
                old[name],
                MISSING,
            )
        elif name not in old:
            comparator.add(
                "process.added",
                path,
                Bump.MINOR,
                "Public Process added.",
                MISSING,
                new[name],
            )
        else:
            comparator.process(old[name], new[name], path)
    findings = comparator.findings
    minimum = max(
        (f.minimum_bump for f in findings),
        key=BUMP_PRIORITY.__getitem__,
        default=Bump.NONE,
    )
    classified_bump = Bump(review_bump) if review_bump is not None else None
    reviews = any(f.review_required for f in findings)
    effective = (
        max(minimum, classified_bump, key=BUMP_PRIORITY.__getitem__)
        if reviews and classified_bump is not None
        else minimum
    )
    unresolved = reviews and review_bump is None
    minimum_version = increment(old_version, minimum)
    suggestion = None if unresolved else increment(old_version, effective)
    return BaselineReport(
        previous_version=str(old_version),
        current_version=str(new_version),
        minimum_bump=minimum,
        minimum_version=str(minimum_version),
        suggested_version=str(suggestion) if suggestion is not None else None,
        review_required=unresolved,
        review_bump=classified_bump,
        declared_version_sufficient=not unresolved
        and new_version >= (suggestion or minimum_version),
        findings=findings,
    )
