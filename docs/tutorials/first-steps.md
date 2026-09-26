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

# Compare two releases

Start from a checkout of this repository with the plugin and runtime installed
in the same environment, following the [installation guide](../how-to/install.md).

The fixtures in `examples/` contain the same public `main` Process. The previous
release declares version `1.2.3`; the current release adds a nullable `prefix`
input and declares `1.3.0`. Existing callers can omit the new input.

From the repository root, run:

```bash
transpiler-mate baseline examples/current.cwl \
  --previous examples/previous.cwl \
  --output baseline.json --check
```

Open `baseline.json`. The expected result is:

| Field | Value | Meaning |
| --- | --- | --- |
| `minimum_bump` | `minor` | An optional public input was added |
| `minimum_version` | `1.3.0` | One minor increment from `1.2.3` |
| `suggested_version` | `1.3.0` | No unresolved review |
| `review_required` | `false` | This finding is statically classified |
| `declared_version_sufficient` | `true` | Current metadata satisfies the floor |

The `input.added` finding identifies the normalized input path and records its
new value. `examples/baseline.json` provides a sample report.

For changes involving defaults, commands, or wiring, a report may instead have
`review_required: true` and `suggested_version: null`. Continue with
[review and CI usage](../how-to/use-cli.md); a high version alone does not resolve
behavioral review.
