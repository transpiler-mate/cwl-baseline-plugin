<!--
Copyright 2026 Terradue

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

# API and report reference

## Public Python API

```python
from cwl_baseline import BaselineOptions, baseline, baseline_plugin

# previous and current are TranspilerContext objects supplied by the host.
report = baseline(previous, current, review_bump=None)

# Resolve previous through current.resolver and write a report.
baseline_plugin.execute(
    current,
    BaselineOptions(previous="release.cwl", output="baseline.json", check=True),
)
```

`baseline(previous, current, *, review_bump=None)` returns `BaselineReport`.
`baseline_plugin.execute(context, options)` returns `None` and writes JSON.
Both compare all Processes in the contexts, using each context's
`metadata.software_version`.

## Plugin options

| Option | Type / default | Meaning |
| --- | --- | --- |
| `previous` | Nonempty string, required | Passed unchanged to `context.resolver.resolve()` |
| `output` | Path, `baseline.json` | Destination; parent directory must exist |
| `check` | Boolean, `false` | Fail on unresolved review or insufficient version |
| `review_bump` | `patch`, `minor`, `major`, or `None` | Global classification of review findings |

Unknown options are rejected. The runtime CLI uses `--review-bump` for
`review_bump` and `--check` / `--no-check` for `check`.

## Report fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Report format version, currently `1.0` |
| `previous_version`, `current_version` | Compared SemVer metadata |
| `minimum_bump` | Maximum static floor: `none`, `patch`, `minor`, or `major` |
| `minimum_version` | Previous version incremented once by that floor |
| `suggested_version` | Version after review classification, or null while unresolved |
| `review_required` | Whether any review remains unresolved |
| `review_bump` | Supplied global classification, or null |
| `declared_version_sufficient` | Review is resolved and current version meets the suggestion |
| `findings` | Detailed changes contributing to the decision |

Each finding contains `rule`, `path`, `category`, `minimum_bump`,
`review_required`, `message`, `before`, `after`, `before_present`, and
`after_present`. Categories are `interface`, `environment`, `behavior`, and
`metadata`. Paths use JSON-Pointer-style escaping in the normalized model.
Presence flags distinguish missing values from null. Original finding review
flags remain true after global classification for audit.

The suggestion is a minimum release, not an instruction to downgrade an already
higher version. See [policy](../explanation/compatibility.md) for aggregation,
prereleases, and the meaning of unresolved review.

## Errors

- `PluginFailureError`: domain failures, including invalid version metadata,
  ambiguous/duplicate identities, unresolved review or insufficient version under `check`.
- `PluginExecutionError`: unexpected resolver errors or report write failures.
- Resolver `PluginError` exceptions propagate unchanged.
- Invalid options raise Pydantic validation errors.

Check failures occur after the report is written. Failures during resolution or
comparison may prevent a report from being produced.

## Implementation reference

::: cwl_baseline.compare.baseline

::: cwl_baseline.plugin.BaselineOptions

::: cwl_baseline.models.BaselineReport

::: cwl_baseline.models.Finding
