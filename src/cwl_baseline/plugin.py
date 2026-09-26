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

"""Runtime-neutral transpiler-mate plugin registration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from transpiler_mate.api import (
    PluginError,
    PluginExecutionError,
    PluginFailureError,
    TranspilerContext,
    transpiler_plugin,
)

from .compare import baseline


class BaselineOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous: str = Field(
        min_length=1,
        description="Previous release location accepted by the context resolver",
    )
    output: Path = Field(default=Path("baseline.json"), description="JSON report destination")
    check: bool = Field(
        default=False,
        description="Fail if review is unresolved or the declared version is insufficient",
    )
    review_bump: Literal["patch", "minor", "major"] | None = Field(
        default=None,
        description="Explicit classification of all changes requiring behavioral review",
    )


@transpiler_plugin(
    name="baseline",
    description="Compare CWL public contracts against a previous release and suggest SemVer",
    options_model=BaselineOptions,
)
def baseline_plugin(context: TranspilerContext, options: BaselineOptions) -> None:
    try:
        previous = context.resolver.resolve(options.previous)
    except PluginError:
        raise
    except Exception as error:
        raise PluginExecutionError("Could not resolve the previous CWL release") from error
    report = baseline(previous, context, review_bump=options.review_bump)
    try:
        options.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise PluginExecutionError(
            f"Could not write baseline report to {options.output}"
        ) from error
    # Write the complete report before an expected CI/domain failure.
    if options.check:
        if report.review_required:
            raise PluginFailureError(
                "Baseline requires behavioral review; inspect the report and classify reviewed changes with review_bump"
            )
        if not report.declared_version_sufficient:
            raise PluginFailureError(
                f"Declared version {report.current_version} is below required version {report.suggested_version}"
            )
