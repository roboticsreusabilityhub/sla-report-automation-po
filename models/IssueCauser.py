from __future__ import annotations

import json
from collections import Counter
from typing import Optional, List, Dict, Literal

from pydantic import BaseModel, Field, validator

# Optional: json_repair support
try:
    from json_repair import repair_json  # pip install json-repair
except Exception:
    repair_json = None  # fallback if not installed


# -----------------------------
# Pydantic models for responses
# -----------------------------
CauserCategory = Literal["Kunde", "Organisation", "nicht nachvollziehbar"]


class ChunkIssueCauserResponse(BaseModel):
    """
    Holds the extraction result for a single chunk.
    Mirrors the model's JSON schema in your prompt.
    """
    chunk_index: int

    causerCategory: Optional[CauserCategory] = None
    causerEntity: Optional[str] = None
    causerResultFoundInCurrentChunk: Optional[bool] = None

    customerSideFault: Optional[bool] = None
    organizationSideFault: Optional[bool] = None
    noErrorIdentified: Optional[bool] = None

    confidence_score: Optional[float] = None
    evidenceLogs: Optional[str] = None   # EN (translated) with anonymized tokens as-is
    exactLogs: List[str] = None      # DE verbatim quotes

    # For traceability / debugging:
    raw: Optional[str] = None            # raw model output (minified JSON string)
    parsed: Optional[dict] = None        # parsed JSON object (if valid)

    @validator("confidence_score")
    def _confidence_in_range(cls, v):
        if v is None:
            return v
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence_score must be in [0.0, 1.0]")
        return v



    def is_consistent(self) -> bool:
        """
        Check the boolean consistency constraints:
        Exactly one of customerSideFault / organizationSideFault / noErrorIdentified must be True.
        And causerCategory must align with that boolean.
        """
        flags = [
            bool(self.customerSideFault),
            bool(self.organizationSideFault),
            bool(self.noErrorIdentified),
        ]
        if sum(flags) != 1:
            return False

        mapping_ok = (
            (self.causerCategory == "Kunde" and self.customerSideFault) or
            (self.causerCategory == "Organisation" and self.organizationSideFault) or
            (self.causerCategory == "nicht nachvollziehbar" and self.noErrorIdentified)
        )
        return bool(self.causerCategory) and mapping_ok


class IssueCauser(BaseModel):
    """
    Final aggregated response across all chunks.
    """
    finalCauserCategory: CauserCategory
    finalCauserEntity: Optional[str] = None
    evidence:Optional[str] = None
    exactLogs:List[str]
    voteTally: Dict[CauserCategory, int] = Field(default_factory=dict)
    perChunk: List[ChunkIssueCauserResponse] = Field(default_factory=list)

    @validator("finalCauserEntity", always=True)
    def _entity_null_if_undetermined(cls, v, values):
        cat: CauserCategory = values.get("finalCauserCategory")
        if cat == "nicht nachvollziehbar":
            return None
        return v