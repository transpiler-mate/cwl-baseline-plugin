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

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Literal

import pytest
from conftest import context, process
from transpiler_mate.api import PluginFailureError

from cwl_baseline import baseline
from cwl_baseline.models import BaselineReport, Bump, FindingCategory
from cwl_baseline.normalize import document
from cwl_baseline.types import assignable

if TYPE_CHECKING:
    from collections.abc import Sequence


def compare(
    old: Sequence[object],
    new: Sequence[object],
    *,
    review_bump: Literal["patch", "minor", "major"] | None = None,
) -> BaselineReport:
    """Compare parsed fixtures with distinct source locations."""
    return baseline(
        context(old), context(new, source="file:///current/workflow.cwl"), review_bump=review_bump
    )


@pytest.mark.parametrize(
    "old,new,bump",
    [
        ([process()], [process(), process("extra")], "minor"),
        ([process(), process("extra")], [process()], "major"),
        ([process("old")], [process("new")], "major"),
        ([process()], [], "major"),
    ],
)
def test_process_inventory(old: Sequence[object], new: Sequence[object], bump: str) -> None:
    report = compare(old, new)
    assert report.minimum_bump == Bump(bump)
    assert report.suggested_version == {"major": "2.0.0", "minor": "1.3.0"}[bump]


def test_same_document_different_source_and_order() -> None:
    old = [process(inputs={"a": "string", "b": "int"}), process("other")]
    new = [process("other"), process(inputs={"b": "int", "a": "string"})]
    report = compare(old, new)
    assert report.minimum_bump == Bump.NONE
    assert report.suggested_version == "1.2.3"
    assert report.findings == []


@pytest.mark.parametrize(
    "old,new,bump",
    [
        ({}, {"x": "string"}, "major"),
        ({}, {"x": "string?"}, "minor"),
        ({}, {"x": {"type": "string", "default": "yes"}}, "minor"),
        ({"x": "string?"}, {}, "major"),
        ({"x": "string"}, {"x": "string?"}, "minor"),
        ({"x": "string?"}, {"x": "string"}, "major"),
        ({"x": "int"}, {"x": "long"}, "minor"),
        ({"x": "long"}, {"x": "int"}, "major"),
        ({"x": {"type": "string", "default": "yes"}}, {"x": "string"}, "major"),
    ],
)
def test_input_changes(old: object, new: object, bump: str) -> None:
    report = compare([process(inputs=old)], [process(inputs=new)])
    assert report.minimum_bump == Bump(bump)


@pytest.mark.parametrize(
    "old,new,bump,review",
    [
        ({}, {"x": "string"}, "minor", False),
        ({"x": "string"}, {}, "major", False),
        ({"x": "string"}, {"x": "string?"}, "major", False),
        ({"x": "string?"}, {"x": "string"}, "patch", True),
        ({"x": "int"}, {"x": "long"}, "major", False),
        ({"x": "long"}, {"x": "int"}, "patch", True),
    ],
)
def test_output_changes(old: object, new: object, bump: str, review: bool) -> None:
    report = compare([process(outputs=old)], [process(outputs=new)])
    assert report.minimum_bump == Bump(bump)
    assert report.review_required == review


def test_union_reordering() -> None:
    report = compare(
        [process(inputs={"x": ["null", "string", "int"]})],
        [process(inputs={"x": ["int", "string", "null"]})],
    )
    assert not report.findings


@pytest.mark.parametrize("direction,bump", [("inputs", "minor"), ("outputs", "major")])
def test_enum_variance(direction: str, bump: str) -> None:
    old = {"type": "enum", "name": "Mode", "symbols": ["one"]}
    new = {**old, "symbols": ["one", "two"]}
    report = compare(
        [process(**{direction: {"x": {"type": old}}})],
        [process(**{direction: {"x": {"type": new}}})],
    )
    assert report.minimum_bump == Bump(bump)


def test_named_schema_definition_change() -> None:
    def workflow(symbols: list[str]) -> dict[str, object]:
        return process(
            inputs={"x": "Mode"},
            requirements={
                "SchemaDefRequirement": {
                    "types": [{"name": "Mode", "type": "enum", "symbols": symbols}]
                }
            },
        )

    report = compare([workflow(["one", "two"])], [workflow(["one"])])
    assert report.minimum_bump == Bump.MAJOR
    assert any(f.rule == "input.type_incompatible" for f in report.findings)


@pytest.mark.parametrize(
    "old_fields,new_fields,bump",
    [
        ({"a": "string"}, {"a": "string", "b": "int"}, "major"),
        ({"a": "string"}, {"a": "string", "b": "int?"}, "minor"),
        ({"a": "string", "b": "int?"}, {"a": "string"}, "major"),
        ({"a": "string"}, {"a": "string?"}, "minor"),
    ],
)
def test_record_fields(old_fields: dict[str, str], new_fields: dict[str, str], bump: str) -> None:
    def workflow(fields: dict[str, str]) -> dict[str, object]:
        return process(
            inputs={"x": {"type": {"type": "record", "name": "Settings", "fields": fields}}}
        )

    assert compare([workflow(old_fields)], [workflow(new_fields)]).minimum_bump == Bump(bump)


def test_array_item_variance() -> None:
    report = compare(
        [process(inputs={"x": {"type": {"type": "array", "items": "long"}}})],
        [process(inputs={"x": {"type": {"type": "array", "items": "int"}}})],
    )
    assert report.minimum_bump == Bump.MAJOR
    assert any(f.path.endswith("/items") for f in report.findings)


def test_default_change_is_not_silently_patch() -> None:
    report = compare(
        [process(inputs={"x": {"type": "string", "default": "a"}})],
        [process(inputs={"x": {"type": "string", "default": "b"}})],
    )
    assert report.minimum_bump == Bump.NONE
    assert report.review_required
    assert report.suggested_version is None


def test_defaults_containing_identifier_keys_are_literal() -> None:
    def workflow(value: str) -> dict[str, object]:
        return process(inputs={"x": {"type": "Any", "default": {"id": value}}})

    report = compare(
        [workflow("file:///previous/workflow.cwl#literal")],
        [workflow("file:///current/workflow.cwl#literal")],
    )
    assert any(f.rule == "default.changed" for f in report.findings)


def test_doc_change_has_no_bump() -> None:
    report = compare([process(doc="Old")], [process(doc="New")])
    assert report.minimum_bump == Bump.NONE
    assert not report.review_required
    assert report.findings[0].category == FindingCategory.METADATA


def test_version_metadata_is_excluded() -> None:
    a, b = context(), context(version="2.0.0", source="file:///current/workflow.cwl")
    old = next(iter(a.document.values()))
    new = next(iter(b.document.values()))
    old.extension_fields["https://schema.org/softwareVersion"] = "1.2.3"
    new.extension_fields["https://schema.org/softwareVersion"] = "2.0.0"
    assert baseline(a, b).findings == []


def test_mandatory_requirement_added() -> None:
    report = compare(
        [process()], [process(requirements={"NetworkAccess": {"networkAccess": True}})]
    )
    assert report.minimum_bump == Bump.MAJOR
    assert report.findings[0].category == FindingCategory.ENVIRONMENT


def test_container_change_requires_review() -> None:
    def workflow(image: str) -> dict[str, object]:
        return process(requirements={"DockerRequirement": {"dockerPull": image}})

    report = compare([workflow("image:1")], [workflow("image:2")])
    assert report.review_required
    assert report.suggested_version is None


@pytest.mark.parametrize(
    "review_bump,expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")]
)
def test_review_policy(review_bump: Literal["patch", "minor", "major"], expected: str) -> None:
    old = process(requirements={"DockerRequirement": {"dockerPull": "image:1"}})
    new = process(requirements={"DockerRequirement": {"dockerPull": "image:2"}})
    report = compare([old], [new], review_bump=review_bump)
    assert report.suggested_version == expected
    assert report.review_bump == Bump(review_bump)
    assert not report.review_required
    assert any(f.review_required for f in report.findings)


def test_review_policy_never_downgrades_breaking_changes() -> None:
    report = compare(
        [process(inputs={"x": "string", "y": {"type": "string", "default": "a"}})],
        [process(inputs={"y": {"type": "string", "default": "b"}})],
        review_bump="patch",
    )
    assert report.suggested_version == "2.0.0"
    assert any(f.review_required for f in report.findings)
    assert not report.review_required


@pytest.mark.parametrize(
    "direction,old,new,bump",
    [
        ("inputs", [], [{"pattern": ".idx", "required": True}], "major"),
        ("inputs", [], [{"pattern": ".idx", "required": False}], "minor"),
        ("outputs", [{"pattern": ".idx", "required": True}], [], "major"),
        ("outputs", [], [{"pattern": ".idx", "required": True}], "minor"),
    ],
)
def test_secondary_files(direction: str, old: object, new: object, bump: str) -> None:
    a = process(**{direction: {"x": {"type": "File", "secondaryFiles": old}}})
    b = process(**{direction: {"x": {"type": "File", "secondaryFiles": new}}})
    assert compare([a], [b]).minimum_bump == Bump(bump)


@pytest.mark.parametrize(
    "direction,old,new,bump",
    [
        ("inputs", None, "https://example.org/tiff", "major"),
        ("inputs", "https://example.org/tiff", None, "minor"),
        ("outputs", "https://example.org/tiff", None, "major"),
        ("outputs", None, "https://example.org/tiff", "patch"),
    ],
)
def test_format_constraints(direction: str, old: str | None, new: str | None, bump: str) -> None:
    def workflow(fmt: str | None) -> dict[str, object]:
        p = {"type": "File"}
        if fmt:
            p["format"] = fmt
        return process(**{direction: {"x": p}})

    assert compare([workflow(old)], [workflow(new)]).minimum_bump == Bump(bump)


def test_different_format_iris_need_ontology_review() -> None:
    a = process(inputs={"x": {"type": "File", "format": "https://example.org/a"}})
    b = process(inputs={"x": {"type": "File", "format": "https://example.org/b"}})
    report = compare([a], [b])
    assert report.review_required


def test_unknown_extension_is_reported() -> None:
    a, b = context(), context()
    next(iter(b.document.values())).extension_fields["https://example.org/contract"] = "changed"
    report = baseline(a, b)
    assert report.review_required
    assert "contract" in report.findings[0].path


@pytest.mark.parametrize("version", ["1.2", "v1.2.3", "latest", ""])
def test_invalid_version(version: str) -> None:
    with pytest.raises(PluginFailureError, match="valid SemVer"):
        baseline(context(), context(version=version))


def test_prerelease_baseline_rejected() -> None:
    with pytest.raises(PluginFailureError, match="prerelease"):
        baseline(context(version="1.2.3-dev.1"), context())


def test_prerelease_current_is_not_release_ready() -> None:
    report = baseline(context(), context([process(), process("extra")], version="1.3.0-dev.1"))
    assert report.suggested_version == "1.3.0"
    assert not report.declared_version_sufficient


def test_bump_applied_once_not_per_change() -> None:
    report = compare(
        [process(inputs={"a": "string", "b": "string"})], [process(), process("extra")]
    )
    assert report.suggested_version == "2.0.0"


def test_no_mutation() -> None:
    a, b = context(), context([process(inputs={"x": "string?"})])
    before = copy.deepcopy(document(b))
    baseline(a, b)
    assert document(b) == before
    assert b.metadata.software_version == "1.2.3"


def test_any_excludes_null() -> None:
    assert assignable("null", "Any", {}, {}) is False
    assert assignable("string", "Any", {}, {}) is True
    assert assignable("Any", ["null", "Any"], {}, {}) is True


def test_unknown_named_type() -> None:
    assert assignable("missing", "string", {}, {}) is None


def test_recursive_named_record() -> None:
    a = {
        "Node": {
            "name": "Node",
            "type": "record",
            "fields": [{"name": "next", "type": ["null", "Node"]}],
        }
    }
    assert assignable("Node", "Node", a, a) is True


def test_named_input_enum_widening_produces_minor_suggestion() -> None:
    def workflow(symbols: list[str]) -> dict[str, object]:
        return process(
            inputs={"x": "Mode"},
            requirements={
                "SchemaDefRequirement": {
                    "types": [{"name": "Mode", "type": "enum", "symbols": symbols}]
                }
            },
        )

    report = compare([workflow(["one"])], [workflow(["one", "two"])])
    assert report.suggested_version == "1.3.0"
    assert not report.review_required


def test_record_inside_union_field_removal() -> None:
    def workflow(fields: dict[str, str]) -> dict[str, object]:
        return process(
            inputs={
                "x": {
                    "type": [
                        "null",
                        {"type": "record", "name": "Settings", "fields": fields},
                    ]
                }
            }
        )

    report = compare([workflow({"a": "string", "b": "string?"})], [workflow({"a": "string"})])
    assert report.minimum_bump == Bump.MAJOR


def test_record_metadata_inside_union_is_not_lost() -> None:
    def workflow(default: str) -> dict[str, object]:
        return process(
            inputs={
                "x": {
                    "type": [
                        "null",
                        {
                            "type": "record",
                            "name": "Settings",
                            "fields": {"a": {"type": "string", "label": default}},
                        },
                    ]
                }
            }
        )

    report = compare([workflow("a")], [workflow("b")])
    assert not report.review_required
    assert any(f.rule == "metadata.changed" for f in report.findings)


def test_enum_documentation_change_is_reported() -> None:
    def workflow(doc: str) -> dict[str, object]:
        return process(
            inputs={
                "x": {
                    "type": {
                        "type": "enum",
                        "symbols": ["one"],
                        "name": "Mode",
                        "label": doc,
                    }
                }
            }
        )

    report = compare([workflow("a")], [workflow("b")])
    assert report.findings
    assert not report.review_required
    assert report.minimum_bump == Bump.NONE


def test_steps_are_private_and_order_independent() -> None:
    def step(name: str) -> dict[str, object]:
        return {
            "id": name,
            "in": [],
            "out": [],
            "run": {
                "class": "CommandLineTool",
                "inputs": [],
                "outputs": [],
                "baseCommand": "echo",
            },
        }

    old = process()
    old["steps"] = [step("a"), step("b")]
    new = copy.deepcopy(old)
    new["steps"] = [step("b"), step("a")]
    assert compare([old], [new]).findings == []
    new["steps"] = [step("b")]
    report = compare([old], [new])
    assert report.review_required
    assert report.minimum_bump == Bump.NONE
    assert any(f.rule == "step.removed" for f in report.findings)


def test_step_wiring_and_embedded_run_are_reported() -> None:
    old = process(inputs={"x": "string", "y": "string"})
    old["steps"] = [
        {
            "id": "run",
            "in": {"arg": "x"},
            "out": [],
            "run": {
                "class": "CommandLineTool",
                "inputs": {"arg": "string"},
                "outputs": [],
                "baseCommand": "echo",
            },
        }
    ]
    new = copy.deepcopy(old)
    new["steps"] = [
        {
            "id": "run",
            "in": {"arg": "y"},
            "out": [],
            "run": {
                "class": "CommandLineTool",
                "inputs": {"arg": "string"},
                "outputs": [],
                "baseCommand": "printf",
            },
        }
    ]
    report = compare([old], [new])
    assert report.review_required
    assert any("baseCommand" in f.path for f in report.findings)
    assert any(f.path.endswith("/in") for f in report.findings)


def test_command_argument_order_matters() -> None:
    old = {
        "id": "tool",
        "class": "CommandLineTool",
        "inputs": [],
        "outputs": [],
        "baseCommand": "echo",
        "arguments": ["a", "b"],
    }
    new = {**old, "arguments": ["b", "a"]}
    report = compare([old], [new])
    assert report.review_required
    assert any(f.path.endswith("/arguments") for f in report.findings)


def test_parameter_ids_keep_scopes() -> None:
    a, b = (
        context([process("a", inputs={"x": "string"}), process("b", inputs={"x": "string"})]),
        context([process("a", inputs={"x": "string"}), process("b", inputs={"x": "int"})]),
    )
    report = baseline(a, b)
    assert all(f.path.startswith("/processes/b/") for f in report.findings)


def test_missing_vs_null_default_presence_flags() -> None:
    # cwl-utils generated serializers omit None defaults, so an explicit null
    # has the same effective contract as absence for a nullable parameter.
    old = process(inputs={"x": {"type": "string?"}})
    new = process(inputs={"x": {"type": "string?", "default": "value"}})
    report = compare([old], [new])
    finding = next(f for f in report.findings if f.rule == "default.changed")
    assert finding.before is None
    assert not finding.before_present
    assert finding.after_present


def test_boolean_default_differs_from_number() -> None:
    report = compare(
        [process(inputs={"x": {"type": "Any", "default": 1}})],
        [process(inputs={"x": {"type": "Any", "default": True}})],
    )
    assert report.review_required
    assert any(f.rule == "default.changed" for f in report.findings)


@pytest.mark.parametrize("module_name", ["cwl_v1_0", "cwl_v1_1", "cwl_v1_2"])
def test_version_specific_doms(module_name: str) -> None:
    import importlib

    module = importlib.import_module("cwl_utils.parser." + module_name)
    old = module.Workflow(id="main", inputs=[], outputs=[], steps=[])
    input_class = getattr(module, "WorkflowInputParameter", None) or module.InputParameter
    new = module.Workflow(
        id="main",
        inputs=[input_class(id="main/x", type_=["null", "string"])],
        outputs=[],
        steps=[],
    )
    a = context().model_copy(update={"document": {"main": old}})
    b = context().model_copy(update={"document": {"main": new}})
    assert baseline(a, b).suggested_version == "1.3.0"
