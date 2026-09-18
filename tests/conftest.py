from __future__ import annotations

import json

from cwl_utils.parser import load_document_by_string
from cwl_utils.parser.cwl_v1_2 import LoadingOptions
from transpiler_mate.api import SoftwareApplication, TranspilerContext


class Resolver:
    def __init__(self, context=None):
        self.context = context
        self.calls = []

    def resolve(self, location):
        self.calls.append(location)
        if isinstance(self.context, Exception):
            raise self.context
        if self.context is None:
            raise AssertionError("Unexpected resolution")
        return self.context


def process(name="main", *, inputs=None, outputs=None, **extra):
    return dict(
        id=name,
        **{"class": "Workflow"},
        inputs=inputs or {},
        outputs=outputs or {},
        steps=[],
        **extra,
    )


def context(
    processes=None,
    *,
    version="1.2.3",
    source="file:///previous/workflow.cwl",
    resolver=None,
):
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
        source=source,
        metadata=metadata,
        document={p.id: p for p in doms},
        resolver=resolver or Resolver(),
    )
