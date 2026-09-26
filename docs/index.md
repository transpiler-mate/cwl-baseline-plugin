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

# CWL Baseline Plugin

Compare two resolved CWL releases and obtain an explainable JSON report with a
minimum SemVer increment. The analyzer checks public inputs and outputs in
opposite compatibility directions, reports execution-environment changes, and
requests review for behavior that static comparison cannot classify.

```bash
python -m pip install cwl-baseline-plugin
transpiler-mate baseline current.cwl --previous released.cwl --output baseline.json
```

Install the plugin in the same environment as the separately installed runtime.
Both documents need version metadata accepted by that runtime.

- [First comparison](tutorials/first-steps.md): run the repository examples.
- [Installation](how-to/install.md): package and environment setup.
- [Runtime and CI usage](how-to/use-cli.md): reports, review, and version checks.
- [API and report reference](reference/api.md): options and JSON fields.
- [Compatibility policy](explanation/compatibility.md): rules, assumptions, and direction.
- [Architecture and boundaries](explanation/architecture.md): what the analyzer can observe.
