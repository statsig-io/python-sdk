import time
from typing import Union, Optional

from dataclasses import dataclass, field
from statsig.statsig_errors import StatsigValueError
from statsig.statsig_user import StatsigUser
from statsig.utils import to_raw_dict_or_none


@dataclass
class StatsigEvent:
    """An event to log to Statsig for analysis and experimentation
    To create metric dimensions in pulse, pass a value (str or float) with the event
    (e.g. pass the product category with a purchase event to generate a purchase metric across categories)
    Pass additional event information as metadata
    """
    user: StatsigUser
    event_name: str
    value: Union[str, int, None] = None
    metadata: Optional[dict] = None
    _secondary_exposures: Optional[list] = None
    _time: int = field(default_factory=lambda: round(time.time() * 1000))

    def __post_init__(self):
        if self.user is None or not isinstance(self.user, StatsigUser):
            raise StatsigValueError('StatsigEvent.user must be set')
        if self.event_name is None or self.event_name == "":
            raise StatsigValueError(
                'StatsigEvent.event_name must be a valid str')
        if self.value is not None and not isinstance(self.value, str) and not isinstance(
                self.value, float) and not isinstance(self.value, int):
            raise StatsigValueError(
                'StatsigEvent.value must be a str, float, or int')

    def to_dict(self):
        evt_nullable = {
            'user': None if self.user is None else self.user.to_dict(False),
            'eventName': self.event_name,
            'value': self.value,
            'metadata': to_raw_dict_or_none(self.metadata),
            'secondaryExposures': self._secondary_exposures,
            'time': self._time
        }
        return {k: v for k, v in evt_nullable.items() if v is not None}
