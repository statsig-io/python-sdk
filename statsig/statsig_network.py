import time
import requests

class StatsigNetwork:
    def __init__(self, sdkKey, api):
        print('StatsigNetwork')
        self.sdk_key = sdkKey
        self.api = api
    
    def post_request(self, endpoint, payload):
        headers = {
            'STATSIG-API-KEY': self.sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
        }
        try:
            response = requests.post(self.api + endpoint, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
                else:
                    return None
        except Exception as e:
            return None