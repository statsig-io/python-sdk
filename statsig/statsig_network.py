import time
import requests

class _StatsigNetwork:

    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(self, sdkKey, api):
        self.__sdk_key = sdkKey
        if not api.endswith("/"):
            api = api + "/"
        self.__api = api
    
    def post_request(self, endpoint, payload):
        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        try:
            response = requests.post(self.__api + endpoint, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
                else:
                    return None
        except Exception as e:
            return None
            
    def retryable_request(self, endpoint, payload):
        headers = {
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        try:
            response = requests.post(self.__api + endpoint, json=payload, headers=headers)
            if response.status_code in self.__RETRY_CODES:
                return payload
            else:
                return None
        except Exception as e:
            return None