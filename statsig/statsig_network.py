import json
import time
from io import BytesIO
import gzip
import requests
from .diagnostics import Diagnostics, Marker
from .sdk_flags import _SDKFlags
from .statsig_options import StatsigOptions
from .statsig_error_boundary import _StatsigErrorBoundary

from . import globals

REQUEST_TIMEOUT = 20
STATSIG_API = "https://statsigapi.net/v1/"
STATSIG_CDN = "https://api.statsigcdn.com/v1/"


class _StatsigNetwork:
    _raise_on_error = False
    __RETRY_CODES = [408, 500, 502, 503, 504, 522, 524, 599]

    def __init__(
        self,
        sdk_key,
        options: StatsigOptions,
        statsig_metadata: dict,
        error_boundary: _StatsigErrorBoundary,
        diagnostics: Diagnostics
    ):
        self.__sdk_key = sdk_key
        api_for_download_config_specs = options.api_for_download_config_specs or options.api or STATSIG_CDN
        if not api_for_download_config_specs.endswith("/"):
            api_for_download_config_specs = api_for_download_config_specs + "/"

        api_for_get_id_lists = options.api_for_get_id_lists or options.api or STATSIG_API
        if not api_for_get_id_lists.endswith("/"):
            api_for_get_id_lists = api_for_get_id_lists + "/"

        api_for_log_event = options.api_for_log_event or options.api or STATSIG_API
        if not api_for_log_event.endswith("/"):
            api_for_log_event = api_for_log_event + "/"

        self.__api_for_download_config_specs = api_for_download_config_specs
        self.__api_for_get_id_lists = api_for_get_id_lists
        self.__api_for_log_event = api_for_log_event
        self.__req_timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode
        self.__error_boundary = error_boundary
        self.__statsig_metadata = statsig_metadata
        self.__diagnostics = diagnostics
        self.__request_count = 0

    def download_config_specs(self, since_time=0, log_on_exception=False, timeout=None):
        response = self._get_request(
            url=f"{self.__api_for_download_config_specs}download_config_specs/{self.__sdk_key}.json?sinceTime={since_time}",
            headers=None, log_on_exception=log_on_exception, timeout=timeout,
            tag="download_config_specs")
        if response is not None and self._is_success_code(response.status_code):
            return response.json() or {}
        return None

    def get_id_lists(self, log_on_exception=False, timeout=None):
        response = self._post_request(
            url=f"{self.__api_for_get_id_lists}get_id_lists",
            headers=None,
            payload={"statsigMetadata": self.__statsig_metadata},
            log_on_exception=log_on_exception,
            timeout=timeout,
            tag="get_id_lists"
        )
        if response is not None and self._is_success_code(response.status_code):
            return response.json() or {}
        return None

    def get_id_list(self, url, headers, log_on_exception=False):
        return self._get_request(url, headers, log_on_exception, tag="get_id_list")

    def retryable_log_event(self, payload, headers=None, log_on_exception=False, retry=0):
        disable_compression = _SDKFlags.on("stop_log_event_compression")
        additional_headers = {
            'STATSIG-RETRY': str(retry),
        }
        if headers is not None:
            additional_headers.update(headers)
        response = self._request(
            method='POST', url=f"{self.__api_for_log_event}log_event", headers=additional_headers,
            payload=payload, log_on_exception=log_on_exception, timeout=None,
            zipped=not disable_compression, tag="log_event")
        if response is None or response.status_code in self.__RETRY_CODES:
            return payload
        return None

    def _post_request(
            self, url, headers, payload, log_on_exception=False, timeout=None, zipped=None,
            tag=None):
        return self._request('POST', url, headers, payload, log_on_exception, timeout, zipped, tag)

    def _get_request(
            self, url, headers, log_on_exception=False, timeout=None, zipped=None, tag=None):
        return self._request('GET', url, headers, None, log_on_exception, timeout, zipped, tag)

    def _request(self, method, url, headers=None, payload=None, log_on_exception=False,
                 timeout=None, zipped=False, tag=None):
        if self.__local_mode:
            globals.logger.debug("Using local mode. Dropping network request")
            return None

        create_marker = self._get_diagnostics_from_url_or_tag(url, tag)
        marker_id = str(self.__request_count) if (tag == 'log_event') else None
        self.__request_count += 1
        if create_marker is not None:
            self.__diagnostics.add_marker(create_marker().start({'markerID': marker_id}))

        base_headers = {
            "Content-type": "application/json",
            "STATSIG-API-KEY": self.__sdk_key,
            "STATSIG-CLIENT-TIME": str(round(time.time() * 1000)),
            "STATSIG-SERVER-SESSION-ID": self.__statsig_metadata["sessionID"],
            "STATSIG-SDK-TYPE": self.__statsig_metadata["sdkType"],
            "STATSIG-SDK-VERSION": self.__statsig_metadata["sdkVersion"],
            'STATSIG-RETRY': '0',
        }
        if zipped:
            base_headers.update({"Content-Encoding": "gzip"})
        if headers is not None:
            base_headers.update(headers)
        headers = base_headers

        if payload is not None:
            payload = self._verify_json_payload(payload, url)
            if payload is None:
                return None
            if zipped:
                payload = self._zip_payload(payload)

        response = None
        payload_size = len(payload) if payload is not None else None
        try:
            if timeout is None:
                timeout = self.__req_timeout

            response = requests.request(
                method,
                url,
                data=payload,
                headers=headers,
                timeout=timeout,
            )

            if create_marker is not None:
                self.__diagnostics.add_marker(create_marker().end(
                    {
                        "statusCode": response.status_code,
                        "success": response.ok,
                        "sdkRegion": response.headers.get("x-statsig-region"),
                        "payloadSize": payload_size,
                        "markerID": marker_id
                    }
                ))

            if response.status_code < 200 or response.status_code >= 300:
                clean_url = url.replace(self.__sdk_key, "********")
                globals.logger.warning(
                    "Request to %s failed with code %d", clean_url, response.status_code)
                globals.logger.warning(response.text)
            return response
        except Exception as err:
            if create_marker is not None:
                self.__diagnostics.add_marker(create_marker().end(
                    {
                        "statusCode": response.status_code
                        if response is not None
                        else None,
                        "success": False,
                        "error": Diagnostics.format_error(err),
                        "payloadSize": payload_size,
                        "markerID": marker_id
                    }
                ))
            if log_on_exception:
                self.__error_boundary.log_exception(
                    "request:" + tag, err, {"timeoutMs": timeout * 1000, "httpMethod": method})
            return None

    def _is_success_code(self, status_code: int) -> bool:
        return 200 <= status_code < 300

    def _zip_payload(self, payload: str) -> bytes:
        btsio = BytesIO()
        with gzip.GzipFile(fileobj=btsio, mode="w") as gz:
            gz.write(payload.encode("utf-8"))
        return btsio.getvalue()

    def _verify_json_payload(self, payload, url):
        try:
            if payload is None:
                return None
            return json.dumps(payload)
        except TypeError as e:
            globals.logger.error(
                "Dropping request to %s. Failed to json encode payload. Are you sure the input is json serializable? "
                "%s %s",
                url,
                type(e).__name__,
                e.args,
            )
            if self._raise_on_error:
                raise e
            return None

    def _get_diagnostics_from_url_or_tag(self, url: str, tag: str):
        if 'download_config_specs' in url or tag == "download_config_specs":
            return lambda: Marker(url=url).download_config_specs().network_request()
        if 'get_id_lists' in url or tag == "get_id_lists":
            return lambda: Marker(url=url).get_id_list_sources().network_request()
        if 'idliststorage' in url or tag == "get_id_list":
            return lambda: Marker(url=url).get_id_list().network_request()
        if 'log_event' in url or tag == "log_event":
            return lambda: Marker().log_event().network_request()
        return None
