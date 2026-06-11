"""Work request model used by the ADAM training executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdamWorkRequest:
    """Normalized arguments received from workreqd."""

    work_request_id: str
    request_uid: str
    category_name: str
    category: str
    family: str
    target_name: str
    action_name: str
    target_rule_id: str
    payload: dict[str, Any]
