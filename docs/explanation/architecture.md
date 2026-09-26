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

# Architecture and boundaries

The runtime resolves the current CWL into a `TranspilerContext`, including its
Processes, metadata, and resolver. `baseline_plugin` resolves only `previous`
through that resolver, compares both contexts, and writes a JSON report.
The library function `baseline(previous, current, review_bump=None)` returns the
report directly without writing a file (`review_bump` is keyword-only).

| Module | Responsibility |
| --- | --- |
| `normalize` | Serialize supplied DOMs; normalize identities; index parameters and schemas |
| `types` | Directional type assignability, including an unknown result |
| `compare` | Compatibility findings, residual change reporting, version aggregation |
| `models` | Report, finding, and bump types |
| `plugin` | Options, previous-release resolution, report writing, and check failures |

Normalization uses `save(relative_uris=False)`. It strips the owning document's
location from CWL identity/reference fields while retaining scopes and external
URIs. Defaults, command arguments, expressions, and extension values remain
literal. Named schema references resolve within a Process when unambiguous.
Generated IDs for anonymous inline tools are normalized; public Process IDs
need stable identifiers.

The runtime owns parsing, imports, graph validation, and metadata extraction.
The plugin does not execute CWL, evaluate JavaScript, inspect image contents,
fetch ontologies, or recursively fetch external `run` URLs. Pin dependencies
and supply their resolved snapshots when reproducible comparisons are needed.
Changes behind an unchanged external reference absent from the supplied DOMs
cannot be detected. Missing or inherited schema definitions can leave type
compatibility unresolved.

Comparison concerns the serialized DOM, not source text. Comments, spelling,
and distinctions discarded by the parser cannot be recovered. Finding paths
refer to the normalized comparison model, not file line numbers. Neither input
context nor its metadata is mutated.

The [compatibility policy](compatibility.md) separates static guarantees from
behavior that needs a reviewer. A report is not proof of scientific or behavioral
equivalence.
