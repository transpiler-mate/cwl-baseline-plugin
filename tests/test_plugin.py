from __future__ import annotations

import json

import pytest
from conftest import Resolver, context, process
from pydantic import ValidationError
from transpiler_mate.api import (
    PluginExecutionError,
    PluginFailureError,
    TranspilerPlugin,
)

from cwl_baseline import BaselineOptions, baseline_plugin


def test_registration():
    assert isinstance(baseline_plugin, TranspilerPlugin)
    assert baseline_plugin.name == "baseline"
    assert baseline_plugin.options_model is BaselineOptions


def test_resolves_only_previous_and_writes_report(tmp_path):
    resolver = Resolver(context())
    current = context([process(), process("extra")], resolver=resolver)
    output = tmp_path / "report.json"
    result = baseline_plugin.execute(
        current,
        BaselineOptions(previous="oci://registry/released:1.2.3", output=output),
    )
    assert result is None
    assert resolver.calls == ["oci://registry/released:1.2.3"]
    report = json.loads(output.read_text())
    assert report["suggested_version"] == "1.3.0"
    assert not report["declared_version_sufficient"]


def test_check_writes_before_failure(tmp_path):
    resolver = Resolver(context([process(), process("removed")]))
    output = tmp_path / "report.json"
    with pytest.raises(PluginFailureError, match="below required"):
        baseline_plugin.execute(
            context(resolver=resolver),
            BaselineOptions(previous="release.cwl", output=output, check=True),
        )
    assert json.loads(output.read_text())["minimum_bump"] == "major"


def test_check_passes_sufficient_version(tmp_path):
    resolver = Resolver(context())
    baseline_plugin.execute(
        context([process(), process("extra")], version="1.3.0", resolver=resolver),
        BaselineOptions(
            previous="release.cwl", output=tmp_path / "report.json", check=True
        ),
    )


def test_check_rejects_unresolved_review_even_with_large_version(tmp_path):
    resolver = Resolver(
        context([process(inputs={"x": {"type": "string", "default": "a"}})])
    )
    current = context(
        [process(inputs={"x": {"type": "string", "default": "b"}})],
        version="99.0.0",
        resolver=resolver,
    )
    with pytest.raises(PluginFailureError, match="behavioral review"):
        baseline_plugin.execute(
            current,
            BaselineOptions(
                previous="release.cwl", output=tmp_path / "report.json", check=True
            ),
        )


def test_classified_review_passes(tmp_path):
    resolver = Resolver(
        context([process(inputs={"x": {"type": "string", "default": "a"}})])
    )
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


def test_resolver_preserves_plugin_error(tmp_path):
    error = PluginFailureError("unsupported source")
    with pytest.raises(PluginFailureError) as caught:
        baseline_plugin.execute(
            context(resolver=Resolver(error)),
            BaselineOptions(previous="release.cwl", output=tmp_path / "report.json"),
        )
    assert caught.value is error


def test_resolver_wraps_technical_error(tmp_path):
    error = OSError("unavailable")
    with pytest.raises(PluginExecutionError) as caught:
        baseline_plugin.execute(
            context(resolver=Resolver(error)),
            BaselineOptions(previous="release.cwl", output=tmp_path / "report.json"),
        )
    assert caught.value.__cause__ is error


def test_write_error_is_technical(tmp_path):
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
def test_options_validation(options):
    with pytest.raises(ValidationError):
        BaselineOptions.model_validate(options)
