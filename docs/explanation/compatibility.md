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

# Compatibility and version policy

The analyzer asks whether the current Process can replace the previous release
for existing callers and downstream consumers. Inputs and outputs form its
public signature; workflow steps usually implement that signature. Identical
signatures do not establish identical behavior.

These are this plugin's baselining rules, not versioning requirements mandated
by CWL. The implementation has a **fixed static policy**. `review_bump` lets a
reviewer classify all unresolved changes for one comparison; there is no
per-rule policy configuration or waiver system.

## Compatibility direction

Replacement requires both relationships:

- AcceptedInputs(old) ⊆ AcceptedInputs(new): existing jobs remain valid.
- PossibleOutputs(new) ⊆ PossibleOutputs(old): existing consumers can still handle results.

Inputs are contravariant; outputs are covariant. Changing an input from `string`
to `string | null` widens accepted values and has a minor floor. The same change
to an output widens possible results and has a major floor. Narrowing an output
has a patch floor **and requires behavioral review**: a stronger type guarantee
can still change what the result means.

The type checker covers primitives, numeric promotions, nullability, unions,
enums, arrays, records, and available named schemas. Numeric promotion does not
promise lossless conversion. `Any` excludes null unless null is explicitly
included. Unresolved type compatibility requires review.

## Public surface and assumptions

Every Process in `context.document` is public, including helper tools exposed
in that mapping. `context.process_id` does not limit the comparison. Renames
appear as removal and addition. Public identifiers must remain stable.

Adding outputs assumes consumers tolerate additional output keys. Removing an
input is conservatively breaking because existing callers may still supply it.
Record fields use the parameter rules: field removal is conservatively major
in either direction, even where structural type assignability tolerates it.

## Static rules

A floor is the minimum established by static comparison. Review can increase it.
`none + review` means that classification is unresolved, not that the change is safe.

| Change | Minimum floor | Review |
| --- | --- | --- |
| Add a public Process | minor | No |
| Remove or rename a public Process | major | No |
| Add required input without a default | major | No |
| Add nullable input or input with a default | minor | No |
| Remove or rename input | major | No |
| Widen accepted input type; add input enum symbol | minor | No |
| Narrow accepted input type; remove input enum symbol | major | No |
| Add output | minor | No; assumes extra keys are tolerated |
| Remove or rename output | major | No |
| Widen possible output type; add output enum symbol | major | No |
| Narrow possible output type; remove output enum symbol | patch | Yes |
| Remove input omission capability | major | Separately review a changed default |
| Add, remove, or change an existing parameter default | none | Yes |
| Change `doc`, `label`, schema.org name/description | none | No |
| Change command, binding, expression, container, wiring, or steps | none | Yes |
| Change unknown extension fields | none | Yes |

Other changes in the same comparison may establish a higher floor or require
review. Metadata-only changes have no compatibility bump; this is not a
recommendation about an organization's release publication practices.

## Omission and defaults

Omission is checked independently from the value type. In this implementation,
an input is omittable when its serialized parameter has a `default` key or its
type admits null. Removing a default from a non-nullable input loses omission
capability and is major, with a separate default-change review finding. Removing
it from a nullable input preserves omission but still requires review.

Changing a default can change omitted/null-input behavior without altering the
type. The analyzer reports it rather than executing CWL default semantics.
Presence flags distinguish an absent value from explicit JSON null in the
supplied DOM; a serializer may already have discarded that distinction.

## Interface, environment, and behavior

| Dimension | Examples | Implemented treatment |
| --- | --- | --- |
| Interface | Parameter identity, types, omission, `format`, `secondaryFiles` | Directional rules, with review for unresolved constraints |
| Execution environment | Mandatory requirements, resource/network settings, CWL version | New mandatory requirement is major; existing changes need review |
| Behavior | Defaults, commands, expressions, images, wiring, output collection | Report changes for explicit classification |

Findings also have a `metadata` category for recognized documentation fields.
Categories are labels, not separate version calculations. New requirements and
CWL-version changes use `environment`; residual changes to existing requirements
and hints generally use `behavior`. A finding may use `interface` and still
require behavioral review, such as output narrowing.

### File constraints

For literal formats, widening accepted input formats has a minor floor and
narrowing output formats has a patch floor. The latter does not independently
request review in the current implementation. Adding an input format restriction
where none existed, or removing an output format guarantee, is major. Other
format-set changes may depend on ontology relationships and require review;
format expressions also require review. No ontology is fetched.

Requiring a new secondary input file, or changing it from optional to required,
is major. Removing or weakening a required secondary output guarantee is major.
Other literal secondary-file contract changes are minor. An optional secondary
output is not a required guarantee. Changes involving expressions in the pattern
or `required` value require review.

### Requirements and hints

Adding a mandatory requirement is major because it may exclude runners that
previously worked. `SchemaDefRequirement` is handled specially: referenced schemas
are compared through parameter types; unused declarations receive residual review.
Changing or removing an existing requirement generally requires review, as does
changing `cwlVersion`. Resource and network settings are not quantitatively
modeled.

Hints are advisory and do not use the mandatory-requirement addition rule.
Changed hints receive residual review. Changes to an existing container
requirement likewise need review; adding it as a new mandatory requirement
establishes a major floor.

### Steps and behavior

Steps are matched by ID; changing their order alone is ignored. Adding or
removing a step requests review without automatically setting a major floor.
Changes to `valueFrom`, `when`, `scatter`, `outputSource`, `glob`, commands,
containers, and embedded `run` objects are reported when present in the DOM.
Execution-significant lists, such as command arguments, retain order.

Static comparison cannot decide whether those changes are fixes, features, or
breaking behavior. A change in scientific meaning or units can require a major
release even when the public types remain unchanged.

## Version aggregation and review

The maximum static floor across all findings is applied **once** to the previous
release. The implementation applies major/minor/patch increments directly,
including for `0.x` versions; it has no special pre-1.0 policy. No changes retain
the previous version. The plugin never edits version metadata.

While review is unresolved, `suggested_version` is null and
`declared_version_sufficient` is false, even if the declared version is high.
After assessment, set `review_bump` to the highest required classification across
**all** review findings: `patch`, `minor`, or `major`. It cannot lower the static
floor. Per-finding review flags remain for audit; the report-level flag then
indicates that review is resolved. There is no `none` review classification.

Both contexts need valid SemVer metadata. The previous release must not be a
prerelease. Current prereleases are accepted, but `1.3.0-dev.1` is below a required
final `1.3.0`. `check=True` writes the complete report before raising a domain
failure for unresolved review or an insufficient declared version.

See [architecture and boundaries](architecture.md) for what the analyzer can
observe and [runtime usage](../how-to/use-cli.md) for review commands.
