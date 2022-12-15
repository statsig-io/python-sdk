import time
from uuid import uuid4
import requests
from .utils import logger

REQUEST_TIMEOUT = 20


class _StatsigNetwork:

    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(self, sdkKey, options, error_boundary):
        self.__sdk_key = sdkKey
        api = options.api
        if not options.api.endswith("/"):
            api = options.api + "/"
        self.__api = api
        self.__timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode
        self.__error_boundary = error_boundary
        self.__log = logger
        self.__session = str(uuid4())

    def post_request(self, endpoint, payload, log_on_exception = False):
        if self.__local_mode:
            self.__log.debug('Using local mode. Dropping network request')
            return None

        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            'STATSIG-SERVER-SESSION-ID': self.__session,
        }
        try:
            response = requests.post(
                self.__api + endpoint, json=payload, headers=headers, timeout=self.__timeout)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
                return None
            return None
        except Exception as e:
            if log_on_exception:
                self.__error_boundary.log_exception(e)
                self.__log.warning(
                    'Network exception caught when making request to %s failed', endpoint)
            return None

    def retryable_request(self, endpoint, payload, log_on_exception = False):
        if self.__local_mode:
            return None

        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            'STATSIG-SERVER-SESSION-ID': self.__session,
        }
        try:
            response = requests.post(
                self.__api + endpoint, json=payload, headers=headers, timeout=self.__timeout)
            if response.status_code in self.__RETRY_CODES:
                return payload
            if response.status_code >= 300:
                self.__log.warning(
                    "Request to %s failed with code %d", endpoint, response.status_code)
            return None
        except Exception as e:
            if log_on_exception:
                self.__error_boundary.log_exception(e)
                self.__log.warning(
                    "Network exception caught when making request to %s failed", endpoint)
            return None

    def get_request(self, url, headers, log_on_exception = False):
        if self.__local_mode:
            return None
        try:
            headers['STATSIG-SERVER-SESSION-ID'] = self.__session
            response = requests.get(
                url, headers=headers, timeout=self.__timeout)
            if response.ok:
                return response
            return None
        except Exception as e:
            if log_on_exception:
                self.__error_boundary.log_exception(e)
                self.__log.warning(
                    'Network exception caught when making request to %s failed', url)
            return None
