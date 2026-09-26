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

import json
from typing import TYPE_CHECKING

import pytest
from conftest import Resolver, context, process
from pydantic import ValidationError
from transpiler_mate.api import (
    PluginExecutionError,
    PluginFailureError,
    TranspilerPlugin,
)

from cwl_baseline import BaselineOptions, baseline_plugin

if TYPE_CHECKING:
    from pathlib import Path


def test_registration() -> None:
    assert isinstance(baseline_plugin, TranspilerPlugin)
    assert baseline_plugin.name == "baseline"
    assert baseline_plugin.options_model is BaselineOptions


def test_resolves_only_previous_and_writes_report(tmp_path: Path) -> None:
    resolver = Resolver(context())
    current = context([process(), process("extra")], resolver=resolver)
    output = tmp_path / "report.json"
    baseline_plugin.execute(
        current,
        BaselineOptions(previous="oci://registry/released:1.2.3", output=output),
    )
    assert resolver.calls == ["oci://registry/released:1.2.3"]
    report = json.loads(output.read_text())
    assert report["suggested_version"] == "1.3.0"
    assert not report["declared_version_sufficient"]


def test_check_writes_before_failure(tmp_path: Path) -> None:
    resolver = Resolver(context([process(), process("removed")]))
    output = tmp_path / "report.json"
    with pytest.raises(PluginFailureError, match="below required"):
        baseline_plugin.execute(
            context(resolver=resolver),
            BaselineOptions(previous="release.cwl", output=output, check=True),
        )
    assert json.loads(output.read_text())["minimum_bump"] == "major"


def test_check_passes_sufficient_version(tmp_path: Path) -> None:
    resolver = Resolver(context())
    baseline_plugin.execute(
        context([process(), process("extra")], version="1.3.0", resolver=resolver),
        BaselineOptions(previous="release.cwl", output=tmp_path / "report.json", check=True),
    )


def test_check_rejects_unresolved_review_even_with_large_version(tmp_path: Path) -> None:
    resolver = Resolver(context([process(inputs={"x": {"type": "string", "default": "a"}})]))
    current = context(
        [process(inputs={"x": {"type": "string", "default": "b"}})],
        version="99.0.0",
        resolver=resolver,
    )
    with pytest.raises(PluginFailureError, match="behavioral review"):
        baseline_plugin.execute(
            current,
            BaselineOptions(previous="release.cwl", output=tmp_path / "report.json", check=True),
        )


def test_classified_review_passes(tmp_path: Path) -> None:
    resolver = Resolver(context([process(inputs={"x": {"type": "string", "default": "a"}})]))
    current = context(
        [process(inputs={"x": {"type": "string", "default": "b"}})],
        version="1.2.4",
        resolver=resolver,
    )
    baseline_plugin.execute(
        current,
        BaselineOptions(
            previous="release.cwl",
            output=tmp_path / "report.json",
            check=True,
            review_bump="patch",
        ),
    )


def test_resolver_preserves_plugin_error(tmp_path: Path) -> None:
    error = PluginFailureError("unsupported source")
    with pytest.raises(PluginFailureError) as caught:
        baseline_plugin.execute(
            context(resolver=Resolver(error)),
            BaselineOptions(previous="release.cwl", output=tmp_path / "report.json"),
        )
    assert caught.value is error


def test_resolver_wraps_technical_error(tmp_path: Path) -> None:
    error = OSError("unavailable")
    with pytest.raises(PluginExecutionError) as caught:
        baseline_plugin.execute(
            context(resolver=Resolver(error)),
            BaselineOptions(previous="release.cwl", output=tmp_path / "report.json"),
        )
    assert caught.value.__cause__ is error


def test_write_error_is_technical(tmp_path: Path) -> None:
    with pytest.raises(PluginExecutionError, match="write baseline"):
        baseline_plugin.execute(
            context(resolver=Resolver(context())),
            BaselineOptions(previous="release.cwl", output=tmp_path),
        )


@pytest.mark.parametrize(
    "options",
    [
        {"previous": ""},
        {"previous": "x", "review_bump": "micro"},
        {"previous": "x", "typo": True},
    ],
)
def test_options_validation(options: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BaselineOptions.model_validate(options)
