# Copyright 2026 Transpiler-Mate
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

"""Serializable findings and version policy, independent of any CLI."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BumpName = Literal["none", "patch", "minor", "major"]
FindingCategory = Literal["interface", "environment", "behavior", "metadata"]


class Bump(IntEnum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3

    @property
    def label(self) -> BumpName:
        labels: dict[Bump, BumpName] = {
            Bump.NONE: "none",
            Bump.PATCH: "patch",
            Bump.MINOR: "minor",
            Bump.MAJOR: "major",
        }
        return labels[self]


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    path: str
    category: FindingCategory
    minimum_bump: BumpName
    review_required: bool = False
    message: str
    before: Any = None
    after: Any = None
    # Presence flags distinguish an absent field from an explicit JSON null.
    before_present: bool = True
    after_present: bool = True


class BaselineReport(BaseModel):
    schema_version: str = "1.0"
    previous_version: str
    current_version: str
    minimum_bump: BumpName
    minimum_version: str
    suggested_version: str | None
    review_required: bool
    review_bump: Literal["patch", "minor", "major"] | None = None
    declared_version_sufficient: bool
    findings: list[Finding] = Field(default_factory=list)
