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

# Run a baseline and enforce it in CI

The installed runtime exposes the plugin as `transpiler-mate baseline`. `SOURCE`
is the current document; `--previous` identifies the previous release. Both
locations must be accepted by the runtime resolver.

```bash
transpiler-mate baseline examples/current.cwl \
  --previous examples/previous.cwl \
  --output baseline.json
```

The output directory must already exist. This writes the report without failing
solely because the declared version is insufficient or review is unresolved.
Resolution errors, invalid version metadata, and write errors still fail.

Add `--check` for a CI gate:

```bash
transpiler-mate baseline examples/current.cwl \
  --previous examples/previous.cwl \
  --output baseline.json --check
```

If review is unresolved or the version is insufficient, the plugin writes the
report before raising `PluginFailureError`. Inspect the findings and assess the
observable behavior of every review item. Then classify all reviewed changes
with their highest necessary bump, for example:

```bash
transpiler-mate baseline examples/current.cwl \
  --previous examples/previous.cwl \
  --output baseline.json --review-bump patch --check
```

Use `patch` only after establishing that all review findings are compatible fixes;
choose `minor` for compatible features or `major` for breaking behavior.
Classification cannot reduce a statically proven floor. Update the current
release's version metadata when needed and rerun; the plugin does not edit it.

`--review-bump` maps to Python option `review_bump`. Run
`transpiler-mate baseline --help` for the host's resolver/authentication options.
See [API and report reference](../reference/api.md) for all plugin options and
[compatibility policy](../explanation/compatibility.md) for the decision rules.
