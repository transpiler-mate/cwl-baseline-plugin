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

# Install

Install the plugin into the same Python environment as the `transpiler-mate`
runtime:

```bash
python -m pip install cwl-baseline-plugin
transpiler-mate baseline --help
```

The package requires Python >=3.10 and declares `transpiler-mate-api==1.0.0`,
`semver>=3.0.4,<4`, and `loguru==0.7.3`. The API supplies Pydantic and CWL DOM
support. The runtime CLI is a separate installation; the plugin provides no
standalone `cwl_baseline` executable.

For a local checkout:

```bash
python -m pip install -e .
```

The installed entry point is `baseline = "cwl_baseline.plugin:baseline_plugin"`
in group `transpiler_mate.plugins`. Reinstall after changing package dependencies
or entry-point metadata.

For development, use the configured Hatch environments:

```bash
hatch run test:test
hatch run dev:typecheck
hatch run dev:check
```
