import time
import requests

class _StatsigNetwork:
    def __init__(self, sdkKey, api):
        self.__sdk_key = sdkKey
        self.__api = api
    
    def post_request(self, endpoint, payload):
        headers = {
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