from dataclasses import dataclass


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
            'userID': self.user_id,
            'email': self.email,
            'ip': self.ip,
            'userAgent': self.user_agent,
            'country': self.country,
            'locale': self.locale,
            'appVersion': self.app_version,
            'custom': self.custom,
            'statsigEnvironment': self._statsig_environment,
            'customIDs': self.custom_ids,
        }

        if forEvaluation and self.private_attributes is not None:
            user_nullable["privateAttributes"] = self.private_attributes

        return {k: v for k, v in user_nullable.items() if v is not None}
