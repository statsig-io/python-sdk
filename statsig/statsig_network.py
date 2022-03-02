import time
import requests

REQUEST_TIMEOUT = 20


class _StatsigNetwork:

    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(self, sdkKey, options):
        self.__sdk_key = sdkKey
        api = options.api
        if not options.api.endswith("/"):
            api = options.api + "/"
        self.__api = api
        self.__timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode

    def post_request(self, endpoint, payload):
        if self.__local_mode:
            return None

        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        try:
            response = requests.post(
                self.__api + endpoint, json=payload, headers=headers, timeout=self.__timeout)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
                else:
                    return None
        except Exception as e:
            return None

    def retryable_request(self, endpoint, payload):
        if self.__local_mode:
            return None

        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        try:
            response = requests.post(
                self.__api + endpoint, json=payload, headers=headers, timeout=self.__timeout)
            if response.status_code in self.__RETRY_CODES:
                return payload
            else:
                return None
        except Exception as e:
            return None
