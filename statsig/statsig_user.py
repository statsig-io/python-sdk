from dataclasses import dataclass

from statsig import statsig_environment_tier

def _str_or_none(field):
    return str(field) if field is not None else None

@dataclass
class StatsigUser:
    """An object of properties relating to the current user
    user_id is required: learn more https://docs.statsig.com/messages/serverRequiredUserID
    Provide as many as possible to take advantage of advanced conditions in the statsig console
    A dictionary of additional fields can be provided under the custom field
    Set private_attributes for any user property you need for gate evaluation but prefer stripped from logs/metrics
    """
    user_id: str
    email: str = None
    ip: str = None
    user_agent: str = None
    country: str = None
    locale: str = None
    app_version: str = None
    custom: dict = None
    private_attributes: dict = None
    custom_ids: dict = None
    _statsig_environment: dict = None

    def __post_init__(self):
        if self.user_id is None or self.user_id == "":
            raise ValueError(
                'user_id is required: learn more https://docs.statsig.com/messages/serverRequiredUserID')

    def to_dict(self, forEvaluation=False):
        user_nullable = {
            'userID': _str_or_none(self.user_id),
            'email': _str_or_none(self.email),
            'ip': _str_or_none(self.ip),
            'userAgent': _str_or_none(self.user_agent),
            'country': _str_or_none(self.country),
            'locale': _str_or_none(self.locale),
            'appVersion': _str_or_none(self.app_version),
            'custom': self.custom,
            'statsigEnvironment': self._get_environment(),
            'customIDs': self.custom_ids,
        }

        if forEvaluation and self.private_attributes is not None:
            user_nullable["privateAttributes"] = self.private_attributes

        return {k: v for k, v in user_nullable.items() if v is not None}

    def _get_environment(self):
        if self._statsig_environment is None or self._statsig_environment['tier'] is None:
            return None

        tier = self._statsig_environment['tier']
        if isinstance(tier, str):
            return {'tier': tier}

        if isinstance(tier, statsig_environment_tier.StatsigEnvironmentTier):
            return {'tier': tier.value}

        return None

    