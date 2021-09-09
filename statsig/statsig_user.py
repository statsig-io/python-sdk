import json

class StatsigUser:
    def __init__(self, user_id):
        self.user_id = user_id
        self.email = None
        self.ip = None
        self.user_agent = None
        self.country = None
        self.locale = None
        self.app_version = None
        self.custom = None
        self.private_attributes = None
        self.statsig_metadata = None

    def to_json_string(self):
        user = self.to_dict()

        return json.dumps(user)

    def to_dict(self):
        user_nullable = {
            'userID': self.user_id,
            'email': self.email,
            'ip': self.ip,
            'userAgent': self.user_agent,
            'country': self.country,
            'locale': self.locale,
            'appVerison': self.app_version,
            'custom': self.custom,
            'privateAttributes': self.private_attributes,
            'statsigMetadata': self.statsig_metadata,
        }
        user = {}
        for key in user_nullable:
            if not user_nullable[key] is None:
                user[key] = user_nullable[key]
        return user
