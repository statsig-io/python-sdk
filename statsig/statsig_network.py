import json
import time
from uuid import uuid4
import requests
from .diagnostics import Diagnostics
from .statsig_options import StatsigOptions
from .statsig_error_boundary import _StatsigErrorBoundary

from . import globals

REQUEST_TIMEOUT = 20


class _StatsigNetwork:
    _raise_on_error = False
    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(self, sdk_key, options: StatsigOptions, statsig_metadata: dict, error_boundary: _StatsigErrorBoundary):
        self.__sdk_key = sdk_key
        api = options.api
        if not options.api.endswith("/"):
            api = options.api + "/"

        self.__api = api
        self.__req_timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode
        self.__error_boundary = error_boundary
        self.__session = str(uuid4())
        self.__statsig_metadata = statsig_metadata

    def post_request(self, endpoint, payload, log_on_exception=False, timeout=None):
        create_marker = self._get_diagnostics_from_url(endpoint)
        if create_marker is not None:
            create_marker().start()
        if self.__local_mode:
            globals.logger.debug('Using local mode. Dropping network request')
            return None

        headers = self._create_headers({
            'STATSIG-RETRY': '0'
        })

        verified_payload = self._verify_json_payload(payload, endpoint)
        if verified_payload is None:
            return None

        response = None
        try:
            if timeout is None:
                timeout = self.__req_timeout

            response = requests.post(
                self.__api + endpoint, json=verified_payload, headers=headers, timeout=timeout)

            if create_marker is not None:
                create_marker().end({
                    'statusCode': response.status_code,
                    "success": response.ok,
                    "sdkRegion": response.headers.get("x-statsig-region")
                })

            if response.status_code == 200:
                data = response.json()
                return data if data else {}
            return None
        except Exception as err:
            if create_marker is not None:
                create_marker().end({'statusCode': response.status_code if response is not None else False})
            if log_on_exception:
                self.__error_boundary.log_exception("post_request:" + endpoint, err, {"timeoutMs": timeout * 1000})
                globals.logger.warning(
                    'Network exception caught when making request to %s failed', endpoint)
            if self._raise_on_error:
                raise err
            return None

    def retryable_request(self, endpoint, payload, log_on_exception=False, retry=0):
        if self.__local_mode:
            return None

        headers = self._create_headers({
            'STATSIG-RETRY': str(retry)
        })

        verified_payload = self._verify_json_payload(payload, endpoint)
        if verified_payload is None:
            return None

        try:
            response = requests.post(
                self.__api + endpoint, json=verified_payload, headers=headers, timeout=self.__req_timeout)
            if response.status_code in self.__RETRY_CODES:
                return payload
            if response.status_code >= 300:
                globals.logger.warning(
                    "Request to %s failed with code %d", endpoint, response.status_code)
            return None
        except Exception as err:
            if log_on_exception:
                template = "Network exception caught when making request to {0} - {1}. Arguments: {2!r}"
                message = template.format(self.__api + endpoint, type(err).__name__, err.args)
                self.__error_boundary.log_exception("retryable_request", err)
                globals.logger.warning(message)
            if self._raise_on_error:
                raise err
            return payload

    def get_request(self, url, headers, log_on_exception=False):
        if self.__local_mode:
            return None

        response = None
        try:
            Diagnostics.mark().get_id_list().network_request().start({'url': url})
            headers = self._create_headers(headers)
            response = requests.get(
                url, headers=headers, timeout=self.__req_timeout)
            if response.ok:
                return response
            return None
        except Exception as err:
            if log_on_exception:
                self.__error_boundary.log_exception("get_request", err)
                globals.logger.warning(
                    'Network exception caught when making request to %s failed', url)
            if self._raise_on_error:
                raise err
            return None
        finally:
            Diagnostics.mark().get_id_list().network_request().end({
                'url': url,
                'success': (response.ok is True) if response else False,
                'statusCode': response.status_code if response else None
            })

    def _verify_json_payload(self, payload, endpoint):
        try:
            json.dumps(payload)
            return payload
        except TypeError as e:
            globals.logger.error(
                "Dropping request to %s. Failed to json encode payload. Are you sure the input is json serializable? "
                "%s %s",
                endpoint,
                type(e).__name__,
                e.args,
            )
            if self._raise_on_error:
                raise e
            return None

    def _get_diagnostics_from_url(self, url: str):
        if url.endswith('download_config_specs'):
            return lambda: Diagnostics.mark().download_config_specs().network_request()
        if url.endswith('get_id_lists'):
            return lambda: Diagnostics.mark().get_id_list_sources().network_request()
        return None

    def _create_headers(self, headers: dict):
        result = {
            'Content-type': 'application/json',
            'STATSIG-API-KEY': self.__sdk_key,
            'STATSIG-CLIENT-TIME': str(round(time.time() * 1000)),
            'STATSIG-SERVER-SESSION-ID': self.__session,
            'STATSIG-SDK-TYPE': self.__statsig_metadata['sdkType'],
            'STATSIG-SDK-VERSION': self.__statsig_metadata['sdkVersion'],
        }
        result.update(headers)
        return result
