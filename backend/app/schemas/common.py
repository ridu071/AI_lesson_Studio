"""Building blocks used by every data contract."""

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ContractModel(BaseModel):
    """Base class for all data contracts.

    - extra="forbid": an unknown or misspelled field is an error, not silently dropped.
    - frozen=True: a contract cannot be changed after it is created. This is how
      we keep a lesson version "immutable" while QC is evaluating it.
    - str_strip_whitespace: "  text  " is stored as "text".
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

# Typed IDs. A pattern check catches mix-ups such as putting a section ID
# where a source ID belongs.
LessonId = Annotated[str, StringConstraints(pattern=r"^LES-\d+$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^REQ-\d+$")]
ObjectiveId = Annotated[str, StringConstraints(pattern=r"^LO-\d+$")]
SectionId = Annotated[str, StringConstraints(pattern=r"^SEC-\d+$")]
ClaimId = Annotated[str, StringConstraints(pattern=r"^CL-\d+$")]
ActivityId = Annotated[str, StringConstraints(pattern=r"^ACT-\d+$")]
QuestionId = Annotated[str, StringConstraints(pattern=r"^Q-\d+$")]
VideoId = Annotated[str, StringConstraints(pattern=r"^VID-\d+$")]
SourceId = Annotated[str, StringConstraints(pattern=r"^SRC-\d+$")]
PassageId = Annotated[str, StringConstraints(pattern=r"^EV-\d+$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def find_duplicates(values: Iterable[str]) -> list[str]:
    """Return each value that appears more than once, in first-seen order."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
