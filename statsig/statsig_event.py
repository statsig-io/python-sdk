from dataclasses import dataclass
import typing

from statsig.statsig_user import StatsigUser


@dataclass
class StatsigEvent:
    """An event to log to Statsig for analysis and experimentation
    To create metric dimensions in pulse, pass a value (str or float) with the event
    (e.g. pass the product category with a purchase event to generate a purchase metric across categories)
    Pass additional event information as metadata
    """
    user: StatsigUser
    event_name: str
    value: 'typing.Any' = None
    metadata: dict = None
    _secondary_exposures: list = None

    def __post_init__(self):
        if self.user is None or not isinstance(self.user, StatsigUser):
            raise ValueError('StatsigEvent.user must be set')
        if self.event_name is None or self.event_name == "":
            raise ValueError('StatsigEvent.event_name must be a valid str')
        if self.value is not None and not isinstance(self.value, str) and not isinstance(self.value, float) and not isinstance(self.value, int):
            raise ValueError('StatsigEvent.value must be a str, float, or int')

    def to_dict(self):
        evt_nullable = {
            'user': None if self.user is None else self.user.to_dict(False),
            'eventName': self.event_name,
            'value': self.value,
            'metadata': self.metadata,
            'secondaryExposures': self._secondary_exposures,
        }
        return {k: v for k, v in evt_nullable.items() if v is not None}
