import json
import time
from uuid import uuid4
import requests
from .utils import logger

REQUEST_TIMEOUT = 20


class _StatsigNetwork:

    _raise_on_error = False
    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(self, sdk_key, options, error_boundary):
        self.__sdk_key = sdk_key
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
            'STATSIG-RETRY': '0'
        }

        verified_payload = self._verify_json_payload(payload, endpoint)
        if verified_payload is None:
            return None

        try:
            response = requests.post(
                self.__api + endpoint, json=verified_payload, headers=headers, timeout=self.__timeout)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
            return None
        except Exception as err:
            if log_on_exception:
                self.__error_boundary.log_exception(err)
                self.__log.warning(
                    'Network exception caught when making request to %s failed', endpoint)
            if self._raise_on_error:
                raise err
            return None

    def retryable_request(self, endpoint, payload, log_on_exception = False, retry = 0):
        if self.__local_mode:
            return None

        headers = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            'STATSIG-SERVER-SESSION-ID': self.__session,
            'STATSIG-RETRY': str(retry)
        }

        verified_payload = self._verify_json_payload(payload, endpoint)
        if verified_payload is None:
            return None

        try:
            response = requests.post(
                self.__api + endpoint, json=verified_payload, headers=headers, timeout=self.__timeout)
            if response.status_code in self.__RETRY_CODES:
                return payload
            if response.status_code >= 300:
                self.__log.warning(
                    "Request to %s failed with code %d", endpoint, response.status_code)
            return None
        except Exception as err:
            if log_on_exception:
                template = "Network exception caught when making request to {0} - {1}. Arguments: {2!r}"
                message = template.format(self.__api + endpoint, type(err).__name__, err.args)
                self.__error_boundary.log_exception(err)
                self.__log.warning(message)
            if self._raise_on_error:
                raise err
            return payload

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
        except Exception as err:
            if log_on_exception:
                self.__error_boundary.log_exception(err)
                self.__log.warning(
                    'Network exception caught when making request to %s failed', url)
            if self._raise_on_error:
                raise err
            return None

    def _verify_json_payload(self, payload, endpoint):
        try:
            json.dumps(payload)
            return payload
        except TypeError as e:
            self.__log.error(
                "Dropping request to %s. Failed to json encode payload. Are you sure the input is json serializable? %s %s",
                endpoint,
                type(e).__name__,
                e.args,
            )
            if self._raise_on_error:
                raise e
            return None
