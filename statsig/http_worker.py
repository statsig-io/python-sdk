import gzip
import json
import time
from concurrent.futures.thread import ThreadPoolExecutor
from io import BytesIO
from typing import Callable, Tuple, Optional, Any

import requests

from . import globals
from .diagnostics import Diagnostics, Marker
from .evaluation_details import DataSource
from .interface_network import IStatsigNetworkWorker, NetworkProtocol, NetworkEndpoint
from .sdk_configs import _SDK_Configs
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_options import StatsigOptions, STATSIG_API, STATSIG_CDN

REQUEST_TIMEOUT = 20


class HttpWorker(IStatsigNetworkWorker):
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
        self._executor = ThreadPoolExecutor(max_workers=2)
        self.__sdk_key = sdk_key
        self.__configure_endpoints(options)
        self.__req_timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode
        self.__error_boundary = error_boundary
        self.__statsig_metadata = statsig_metadata
        self.__diagnostics = diagnostics
        self.__request_count = 0

    def is_pull_worker(self) -> bool:
        return True

    def get_dcs(self, on_complete: Callable, since_time=0, log_on_exception=False, init_timeout=None):
        response = self._get_request(
            url=f"{self.__api_for_download_config_specs}download_config_specs/{self.__sdk_key}.json?sinceTime={since_time}",
            headers=None, init_timeout=init_timeout, log_on_exception=log_on_exception,
            tag="download_config_specs")
        if response is not None and self._is_success_code(response.status_code):
            on_complete(DataSource.NETWORK, response.json() or {}, None)
            return
        on_complete(DataSource.NETWORK, None, None)

    def get_dcs_fallback(self, on_complete: Callable, since_time=0, log_on_exception=False, init_timeout=None):
        response = self._get_request(
            url=f"{STATSIG_CDN}download_config_specs/{self.__sdk_key}.json?sinceTime={since_time}",
            headers=None, init_timeout=init_timeout, log_on_exception=log_on_exception,
            tag="download_config_specs")
        if response is not None and self._is_success_code(response.status_code):
            on_complete(DataSource.STATSIG_NETWORK, response.json() or {}, None)
            return
        on_complete(DataSource.STATSIG_NETWORK, None, None)

    def get_id_lists(self, on_complete: Callable, log_on_exception=False, init_timeout=None):
        response = self._post_request(
            url=f"{self.__api_for_get_id_lists}get_id_lists",
            headers=None,
            payload={"statsigMetadata": self.__statsig_metadata},
            log_on_exception=log_on_exception,
            init_timeout=init_timeout,
            tag="get_id_lists",
        )
        if response is not None and self._is_success_code(response.status_code):
            return on_complete(response.json() or {}, None)
        return on_complete(None, None)

    def get_id_lists_fallback(self, on_complete: Callable, log_on_exception=False, init_timeout=None):
        response = self._post_request(
            url=f"{STATSIG_API}get_id_lists",
            headers=None,
            payload={"statsigMetadata": self.__statsig_metadata},
            log_on_exception=log_on_exception,
            init_timeout=init_timeout,
            tag="get_id_lists",
        )
        if response is not None and self._is_success_code(response.status_code):
            return on_complete(response.json() or {}, None)
        return on_complete(None, None)

    def get_id_list(self, on_complete, url, headers, log_on_exception=False):
        resp = self._get_request(url, headers, log_on_exception, tag="get_id_list")
        on_complete(resp)

    def log_events(self, payload, headers=None, log_on_exception=False, retry=0):
        disable_compression = _SDK_Configs.on("stop_log_event_compression")
        additional_headers = {
            'STATSIG-RETRY': str(retry),
        }
        if headers is not None:
            additional_headers.update(headers)
        response = self._request(
            method='POST',
            url=f"{self.__api_for_log_event}log_event",
            headers=additional_headers,
            payload=payload, log_on_exception=log_on_exception, init_timeout=None, zipped=not disable_compression,
            tag="log_event")
        if response is None or response.status_code in self.__RETRY_CODES:
            return payload
        return None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    def _run_task_for_initialize(self, task, timeout) -> Tuple[Optional[Any], Optional[Exception]]:
        future = self._executor.submit(task)
        try:
            result = future.result(timeout=timeout)
            return result, None
        except Exception as e:
            return None, e

    def _post_request(
            self, url, headers, payload, log_on_exception=False, init_timeout=None, zipped=None,
            tag=None):
        return self._request('POST', url, headers, payload, log_on_exception, init_timeout, zipped, tag)

    def _get_request(
            self, url, headers, log_on_exception=False, init_timeout=None, zipped=None, tag=None):
        return self._request('GET', url, headers, None, log_on_exception, init_timeout, zipped, tag)

    def _request(
            self,
            method,
            url,
            headers=None,
            payload=None,
            log_on_exception=False,
            init_timeout=None,
            zipped=False,
            tag=None,
    ):
        if self.__local_mode:
            globals.logger.debug("Using local mode. Dropping network request")
            return None

        create_marker = self._get_diagnostics_from_url_or_tag(url, tag)
        marker_id = str(self.__request_count) if (tag == "log_event") else None
        self.__request_count += 1
        if create_marker is not None:
            self.__diagnostics.add_marker(
                create_marker().start({"markerID": marker_id})
            )

        base_headers = {
            "Content-type": "application/json",
            "STATSIG-API-KEY": self.__sdk_key,
            "STATSIG-CLIENT-TIME": str(round(time.time() * 1000)),
            "STATSIG-SERVER-SESSION-ID": self.__statsig_metadata["sessionID"],
            "STATSIG-SDK-TYPE": self.__statsig_metadata["sdkType"],
            "STATSIG-SDK-VERSION": self.__statsig_metadata["sdkVersion"],
            "STATSIG-RETRY": "0",
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

        payload_size = len(payload) if payload is not None else None
        try:
            timeout = init_timeout
            if timeout is None:
                timeout = self.__req_timeout

            def request_task():
                return requests.request(method, url, data=payload, headers=headers, timeout=timeout)

            response = None
            if init_timeout is not None:
                response, err = self._run_task_for_initialize(request_task, timeout)
                if response is None:
                    err = err or Exception("Request timed out")
                    raise err
            else:
                response = request_task()

            if create_marker is not None:
                self.__diagnostics.add_marker(
                    create_marker().end(
                        {
                            "statusCode": response.status_code,
                            "success": response.ok,
                            "sdkRegion": response.headers.get("x-statsig-region"),
                            "payloadSize": payload_size,
                            "markerID": marker_id,
                            "networkProtocol": NetworkProtocol.HTTP,
                        }
                    )
                )

            if response.status_code < 200 or response.status_code >= 300:
                globals.logger.warning(
                    f"Request to {url} failed with code {response.status_code}"
                )
            return response
        except Exception as err:
            globals.logger.warning(f"Request to {url} failed with error {err}")
            if create_marker is not None:
                self.__diagnostics.add_marker(
                    create_marker().end(
                        {
                            "statusCode": (
                                response.status_code if response is not None else None
                            ),
                            "success": False,
                            "error": Diagnostics.format_error(err),
                            "payloadSize": payload_size,
                            "markerID": marker_id,
                            "networkProtocol": NetworkProtocol.HTTP,
                        }
                    )
                )
            if log_on_exception:
                self.__error_boundary.log_exception(
                    "request:" + tag,
                    err,
                    {"timeoutMs": timeout * 1000, "httpMethod": method},
                    log_mode="none",
                )
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
                f"Dropping request to {url}. Failed to json encode payload. Are you sure the input is json serializable? "
                f"{type(e).__name__} {e.args}"
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

    def __get_proxy_address(self, options: StatsigOptions, endpoint: NetworkEndpoint) -> Optional[str]:
        proxy_config = options.proxy_configs.get(endpoint)
        return proxy_config.proxy_address + "/v1" if proxy_config and proxy_config.proxy_address else None

    def __configure_endpoints(self, options: StatsigOptions) -> None:
        api_for_download_config_specs = (self.__get_proxy_address(options, NetworkEndpoint.DOWNLOAD_CONFIG_SPECS)
                                         or options.api_for_download_config_specs
                                         or options.api or STATSIG_CDN)
        if not api_for_download_config_specs.endswith("/"):
            api_for_download_config_specs += "/"

        api_for_get_id_lists = (self.__get_proxy_address(options, NetworkEndpoint.GET_ID_LISTS)
                                or options.api_for_get_id_lists
                                or options.api or STATSIG_API)
        if not api_for_get_id_lists.endswith("/"):
            api_for_get_id_lists += "/"

        api_for_log_event = (self.__get_proxy_address(options, NetworkEndpoint.LOG_EVENT)
                             or options.api_for_log_event
                             or options.api or STATSIG_API)
        if not api_for_log_event.endswith("/"):
            api_for_log_event += "/"

        self.__api_for_download_config_specs = api_for_download_config_specs
        self.__api_for_get_id_lists = api_for_get_id_lists
        self.__api_for_log_event = api_for_log_event
