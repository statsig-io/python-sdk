from dataclasses import dataclass
from typing import Optional

from statsig import statsig_environment_tier
from statsig.statsig_errors import StatsigValueError
from statsig.utils import str_or_none, to_raw_dict_or_none


@dataclass
class StatsigUser:
    """An object of properties relating to the current user
    user_id or at least a custom ID is required: learn more https://docs.statsig.com/messages/serverRequiredUserID
    Provide as many as possible to take advantage of advanced conditions in the statsig console
    A dictionary of additional fields can be provided under the custom field
    Set private_attributes for any user property you need for gate evaluation but prefer stripped from logs/metrics
    """
    user_id: Optional[str] = None
    email: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    country: Optional[str] = None
    locale: Optional[str] = None
    app_version: Optional[str] = None
    custom: Optional[dict] = None
    private_attributes: Optional[dict] = None
    custom_ids: Optional[dict] = None
    _statsig_environment: Optional[dict] = None

    def __post_init__(self):
        # ensure there is a user id or at least a custom ID, empty dict
        # evaluates to false in python so we can use "not" operator to check
        if not self.user_id and not self.custom_ids:
            raise StatsigValueError(
                'user_id or at least a custom ID is required: learn more https://docs.statsig.com/messages/serverRequiredUserID')

    def to_dict(self, forEvaluation=False):
        user_nullable = {
            'userID': str_or_none(self.user_id),
            'email': str_or_none(self.email),
            'ip': str_or_none(self.ip),
            'userAgent': str_or_none(self.user_agent),
            'country': str_or_none(self.country),
            'locale': str_or_none(self.locale),
            'appVersion': str_or_none(self.app_version),
            'custom': to_raw_dict_or_none(self.custom),
            'statsigEnvironment': self._get_environment(),
            'customIDs': to_raw_dict_or_none(self.custom_ids),
        }

        if forEvaluation and self.private_attributes is not None:
            user_nullable["privateAttributes"] = to_raw_dict_or_none(self.private_attributes)

        return {k: v for k, v in user_nullable.items() if v is not None}

    def _get_environment(self):
        if self._statsig_environment is None or not isinstance(
                self._statsig_environment, dict) or self._statsig_environment['tier'] is None:
            return None

        tier = self._statsig_environment['tier']
        if isinstance(tier, str):
            return {'tier': tier}

        if isinstance(tier, statsig_environment_tier.StatsigEnvironmentTier):
            return {'tier': tier.value}

        return None
