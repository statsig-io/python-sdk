from dataclasses import dataclass
from typing import Optional

@dataclass
class ExposureAggregationData:
    gate: Optional[str] = None
    rule_id: Optional[str] = None
    value: Optional[bool] = None
    count: int = 0

    def to_dict(self):
        return {
            "gate": self.gate,
            "rule_id": self.rule_id,
            "value": self.value,
            "count": self.count,
        }
