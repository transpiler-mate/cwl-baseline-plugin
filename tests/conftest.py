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

from cwl_utils.parser import load_document_by_string
from pydantic import AnyUrl
from schema_salad.runtime import LoadingOptions
from transpiler_mate.api import SoftwareApplication, TranspilerContext

if TYPE_CHECKING:
    from collections.abc import Sequence


class Resolver:
    """Record source resolution and return a configured context or failure."""

    def __init__(self, context: TranspilerContext | Exception | None = None) -> None:
        self.context = context
        self.calls: list[str] = []

    def resolve(self, location: str) -> TranspilerContext:
        """Resolve a fixture location or raise the configured exception."""
        self.calls.append(location)
        if isinstance(self.context, Exception):
            raise self.context
        if self.context is None:
            raise AssertionError("Unexpected resolution")
        return self.context


def process(
    name: str = "main", /, *, inputs: object = None, outputs: object = None, **extra: object
) -> dict[str, object]:
    """Build a raw workflow fixture for parsing by cwl-utils."""
    return dict(
        id=name,
        **{"class": "Workflow"},
        inputs=inputs or {},
        outputs=outputs or {},
        steps=[],
        **extra,
    )


def context(
    processes: Sequence[object] | None = None,
    *,
    version: str = "1.2.3",
    source: str = "file:///previous/workflow.cwl",
    resolver: Resolver | None = None,
) -> TranspilerContext:
    """Parse workflow fixtures into a context with synthetic source locations."""
    if processes is None:
        processes = [process()]
    data = {"cwlVersion": "v1.2", "$graph": processes}
    # Fixture URIs are synthetic: validate CWL structure, without checking
    # existence of links at these non-existent locations.
    doms = load_document_by_string(
        json.dumps(data),
        source,
        load_all=True,
        loadingOptions=LoadingOptions(no_link_check=True),
    )
    # The plugin only reads software_version, but validate it through the
    # generated field rather than mocking the TranspilerContext itself.
    metadata = SoftwareApplication.model_construct(software_version=version)
    return TranspilerContext(
        source=AnyUrl(source),
        metadata=metadata,
        document={p.id: p for p in doms},
        resolver=resolver or Resolver(),
    )
