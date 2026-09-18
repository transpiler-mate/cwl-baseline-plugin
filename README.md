<!--
Copyright 2026 Transpiler-Mate

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# CWL Baseline Transpiler Mate Plugin

[![PyPI - Version](https://img.shields.io/pypi/v/cwl-baseline-plugin.svg)](https://pypi.org/project/cwl-baseline-plugin)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cwl-baseline-plugin.svg)](https://pypi.org/project/cwl-baseline-plugin)

A standalone plugin implementing the public `transpiler-mate-api` contract.
It compares every Process in two resolved CWL documents and produces an
explainable JSON baseline report with a minimum SemVer increment.

## Install

```bash
python -m pip install ./transpiler-mate-baseline
```

For development, install your checkout of the API first if it has not yet been
published, then install this project:

```bash
python -m pip install -e ../transpiler-mate-api
python -m pip install -e '.[test]'
pytest
```

Requires Python >=3.10, `transpiler-mate-api>=1,<2`, and `semver>=3.0.4,<4`.
The API supplies cwl-utils and Pydantic. The effective Python requirement also
depends on the selected versions of those dependencies.

## Integrate with a transpiler-mate runtime

Exported plugin object: `transpiler_mate_baseline.plugin`.
Plugin name: `baseline`. Options model: `BaselineOptions`.

The API deliberately specifies no CLI syntax or discovery entry-point group.
Register the exported object using your runtime's plugin discovery/adapter.
This package does not invent an entry-point group or reload the current CWL.

The host CLI resolves its input CWL into `context` and invokes:

```python
from pathlib import Path
from transpiler_mate.api import TranspilerContext
from transpiler_mate_baseline import BaselineOptions, plugin


def execute_baseline(context: TranspilerContext) -> None:
    plugin.execute(
        context,
        BaselineOptions(
            previous="path-or-URI-to-previous-release.cwl",
            output=Path("baseline.json"),
            check=True,
        ),
    )
```

Equivalent options payload for a runtime accepting JSON:

```json
{
  "previous": "path-or-URI-to-previous-release.cwl",
  "output": "baseline.json",
  "check": true
}
```

| Option | Default | Meaning |
| --- | --- | --- |
| `previous` | required | Passed unchanged to `context.resolver.resolve()` |
| `output` | `baseline.json` | JSON destination; its parent directory must exist |
| `check` | `false` | Fail for unresolved review or insufficient declared version |
| `review_bump` | `null` | Explicitly classify review findings as `patch`, `minor`, or `major` |

`previous_context = context.resolver.resolve(options.previous)` supplies the
baseline. `context.document` supplies **all** current Processes, irrespective
of `context.process_id`. Both versions are read from
`context.metadata.software_version` on their respective contexts.

The highest applicable bump is applied **once to the previous release** using
`semver.Version.bump_major()`, `.bump_minor()`, or `.bump_patch()`. SemVer calls
the third component *patch*; this corresponds to *micro* in the request.
Neither CWL document nor either metadata object is mutated.

## Compatibility policy

Every Process exposed in `context.document` is treated as public. A Process
addition is minor; a removal or rename is major. This policy is intentionally
conservative for documents containing helper tools in their public mapping.

| Change | Minimum bump |
| --- | --- |
| Add Process | minor |
| Remove/rename Process | major |
| Add input that cannot be omitted | major |
| Add nullable/defaulted input | minor |
| Remove/rename input or output | major |
| Add output | minor |
| Widen accepted input values | minor |
| Narrow accepted input values | major |
| Widen possible output values | major |
| Narrow possible output values | patch, with behavioral review |
| Remove input omission capability | major |
| Change default | review; independently detect loss of omission capability |
| Add mandatory execution requirement | major |
| Change language version/existing execution requirement | review |
| Change command, binding, expression, wiring, container, or step | review |
| Change `doc`, `label`, schema.org name/description | none |
| Change unknown extensions | review |

Type comparison is directional: old inputs must be assignable to new inputs;
new outputs must be assignable to old outputs. It covers primitives, CWL
numeric promotions, nullability, unions, enums, arrays, records, and named
schemas. Numeric promotion follows CWL type assignability; it does not claim
lossless numeric conversion. `Any` excludes null unless explicitly unioned
with null. Removed record fields are conservatively major for either direction.

File constraints include `format` and `secondaryFiles`. Literal format subset
relations can prove compatibility, but relationships between different format
IRIs may require ontology knowledge and are left for review. Secondary-file
expressions are also left for review. Existing optional secondary-file outputs
are not treated as required guarantees.

Workflow steps are internal implementation details. They are matched by ID;
adding/removing one requires behavioral review rather than automatically
changing the public version. All residual changed DOM fields are reported,
including embedded `run` objects and unknown extension fields. Lists with
execution-significant order (arguments, source lists, etc.) retain their order.

## Interpreting the report

```json
{
  "schema_version": "1.0",
  "previous_version": "1.2.3",
  "current_version": "1.2.3",
  "minimum_bump": "major",
  "minimum_version": "2.0.0",
  "suggested_version": "2.0.0",
  "review_required": false,
  "review_bump": null,
  "declared_version_sufficient": false,
  "findings": []
}
```

The abbreviated example omits findings. Real findings contain a stable rule
identifier, JSON-Pointer-style comparison path, category, minimum bump,
before/after values, presence flags, explanation, and review flag. Paths refer
to the normalized comparison model, not source-file line numbers.

- `minimum_bump` and `minimum_version` express the statically established floor.
- `suggested_version` is `null` while review remains unresolved. Otherwise it
  is the minimum proposed release, not an instruction to downgrade a higher
  already-declared version.
- A report without changes retains the previous release version.
- `declared_version_sufficient` is false while review is unresolved, even if the
  current version is numerically high enough.
- The full report is written before `check=True` raises `PluginFailureError`.
- Missing/invalid SemVer metadata and prerelease baselines are domain errors.
  Current development prereleases are accepted as input, but `1.3.0-dev.1`
  does not satisfy a required final `1.3.0` release. Build metadata is handled
  by the semver library.

After reviewing behavioral changes, classify them explicitly:

```python
options = BaselineOptions(
    previous="release.cwl",
    output="baseline.json",
    review_bump="patch",  # All review findings have been assessed as compatible fixes.
    check=True,
)
plugin.execute(context, options)
```

`review_bump` applies to **all** review findings in this invocation. It cannot
reduce a proven major/minor requirement. Original per-finding review flags are
retained for auditing, while the report-level flag indicates unresolved review.
A global classification is not a per-rule waiver mechanism.

For library use without writing files:

```python
from transpiler_mate_baseline import baseline

previous = context.resolver.resolve("release.cwl")
report = baseline(previous, context)
print(report.model_dump_json(indent=2))
```

## Normalization and boundaries

The plugin serializes the existing cwl-utils DOMs using
`save(relative_uris=False)`. It strips only the owning document's location from
CWL identity/reference fields, retaining scopes and external URIs. It does not
rewrite literal defaults, command arguments, expressions, or extension values.
Unambiguous short named-type references are recognized within a Process;
ambiguous/unresolved references produce review when their compatibility cannot
be established. Reachable named schemas are compared through their parameters;
changes to otherwise unused declarations are reported for review.

The runtime owns CWL parsing, import resolution, graph validation, and metadata
extraction. This plugin does not execute CWL, evaluate JavaScript, inspect image
contents, fetch format ontologies, or recursively fetch additional `run` URLs.
For reproducible baselines, the resolver must provide pinned dependency snapshots
in `document`. Changes behind an unchanged external reference that is absent
from the supplied DOMs cannot be detected. Inherited or externally defined
schemas not present in a Process's available declarations may require review.

Generated serializers may discard source spelling, comments, and explicit null
defaults. The comparison concerns the effective supplied DOM representation;
it cannot recover syntax that the parser discarded. Anonymous/generated **public Process** IDs
should be replaced with stable public IDs before baselining. Generated IDs of
anonymous inline tools are ignored; their enclosing step/run path identifies
them.

Static type compatibility does not prove scientific or behavioral equivalence.
A reviewed major release can still be necessary when output meanings or units
change without changing CWL types.

## Tests and examples

`tests/` exercises parsed CWL DOMs, plugin resolution and error semantics,
variance, schema references, record/array changes, file constraints, source
relocation, ordered arguments, steps, and version aggregation. Test fixtures
use synthetic source URIs and disable link-existence checking only in their
fixture loader; production loading remains entirely with the host resolver.

`examples/previous.cwl`, `examples/current.cwl`, and
`examples/baseline.json` illustrate adding an optional input. See
`VALIDATION.md` for the exact environment and checks used for this delivery.

Upstream API: https://github.com/transpiler-mate/transpiler-mate-api
SemVer library: https://pypi.org/project/semver/

## Documentation

Project documentation is published at: https://Transpiler-Mate.github.io/cwl-baseline-plugin/

## Contribute

Submit a [Github issue](https://github.com/Transpiler-Mate/cwl-baseline-plugin/issues) if you have comments or suggestions.

### Local quality checks

Install [Hatch](https://hatch.pypa.io/) and [Taskfiles](https://taskfile.dev/docs/guide) then install the Git hook:

```console
task quality:pre-commit:install
```

Every commit runs Ruff (including the configured McCabe complexity limit),
Ruff formatting, strict mypy checks, and the pytest suite.

Run the complete hook explicitly with:

```console
task quality:pre-commit:run
```

## License

[![Apache License, Version 2.0](https://img.shields.io/badge/license-Apache%20License%202.0-blue)](https://www.apache.org/licenses/LICENSE-2.0)
