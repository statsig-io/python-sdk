import gzip
import json
import os
import tempfile
import time
from concurrent.futures.thread import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from typing import Callable, Tuple, Optional, Any, Dict, List

import ijson
import requests

from .stream_decompressor import StreamDecompressor

from . import globals
from .diagnostics import Diagnostics, Marker
from .evaluation_details import DataSource
from .interface_network import IStatsigNetworkWorker, NetworkProtocol, NetworkEndpoint
from .request_result import RequestResult
from .sdk_configs import _SDK_Configs
from .statsig_context import InitContext
from .statsig_error_boundary import _StatsigErrorBoundary
from .statsig_options import ProxyConfig, StatsigOptions, STATSIG_API, STATSIG_CDN, AuthenticationMode
from .grpc_websocket_worker import load_credential_from_file

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
        diagnostics: Diagnostics,
        context: InitContext,
    ):
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._context = context
        self.__sdk_key = sdk_key
        self.__configure_endpoints(options)
        self.__req_timeout = options.timeout or REQUEST_TIMEOUT
        self.__local_mode = options.local_mode
        self.__error_boundary = error_boundary
        self.__statsig_metadata = statsig_metadata
        self.__diagnostics = diagnostics
        self.__request_count = 0
        self.__temp_cert_files: List[str] = []
        self.__statsig_request_session = requests.Session()
        self.__request_session = requests.Session()

    def is_pull_worker(self) -> bool:
        return True

    def get_dcs(
        self,
        on_complete: Callable,
        since_time=0,
        log_on_exception=False,
        init_timeout=None,
    ):
        url = f"{self.__api_for_download_config_specs}download_config_specs/{self.__sdk_key}.json"
        if since_time != 0:
            url += f"?sinceTime={since_time}"
        response = self._get_request(
            url=url,
            headers=None,
            init_timeout=init_timeout,
            log_on_exception=log_on_exception,
            tag="download_config_specs",
        )
        self._context.source_api = self.__api_for_download_config_specs
        if response is not None and self._is_success_code(response.status_code):
            on_complete(DataSource.NETWORK, response.data, None)
            return
        on_complete(DataSource.NETWORK, None, None)

    def get_dcs_fallback(
        self,
        on_complete: Callable,
        since_time=0,
        log_on_exception=False,
        init_timeout=None,
    ):
        url = f"{STATSIG_CDN}download_config_specs/{self.__sdk_key}.json"
        if since_time != 0:
            url += f"?sinceTime={since_time}"
        response = self._get_request(
            url=url,
            headers=None,
            init_timeout=init_timeout,
            log_on_exception=log_on_exception,
            tag="download_config_specs",
            useStatsigClient = True,
        )
        self._context.source_api = STATSIG_CDN
        if response is not None and self._is_success_code(response.status_code):
            on_complete(DataSource.STATSIG_NETWORK, response.data, None)
            return
        on_complete(DataSource.STATSIG_NETWORK, None, None)

    def get_id_lists(
        self, on_complete: Callable, log_on_exception=False, init_timeout=None
    ):
        response = None
        if self.__is_cdn_url(self.__api_for_get_id_lists):
            response = self.get_id_lists_fallback(
                on_complete, log_on_exception, init_timeout
            )
        else:
            response = self._post_request(
                url=f"{self.__api_for_get_id_lists}get_id_lists",
                headers=None,
                payload={"statsigMetadata": self.__statsig_metadata},
                log_on_exception=log_on_exception,
                init_timeout=init_timeout,
                tag="get_id_lists",
            )
        if response is not None and self._is_success_code(response.status_code):
            return on_complete(response.data, None)
        return on_complete(None, None)

    def get_id_lists_fallback(
        self, on_complete: Callable, log_on_exception=False, init_timeout=None
    ):
        response = self._get_request(
            url=f"{STATSIG_CDN}get_id_lists/{self.__sdk_key}.json",
            headers=None,
            log_on_exception=log_on_exception,
            init_timeout=init_timeout,
            tag="get_id_lists",
            useStatsigClient = True,
        )
        if response is not None and self._is_success_code(response.status_code):
            return on_complete(response.data, None)
        return on_complete(None, None)

    def get_id_list(self, on_complete, url, headers, log_on_exception=False):
        resp = self._get_request(
            url, headers, log_on_exception, tag="get_id_list", get_text_value_only=True
        )
        if resp is not None and self._is_success_code(resp.status_code):
            return on_complete(resp)
        return on_complete(None)

    def log_events(
        self, payload, headers=None, log_on_exception=False, retry=0
    ) -> RequestResult:
        disable_compression = _SDK_Configs.on("stop_log_event_compression")
        additional_headers = {
            "STATSIG-RETRY": str(retry),
        }
        if headers is not None:
            additional_headers.update(headers)
        response = self._request(
            method="POST",
            url=f"{self.__api_for_log_event}log_event",
            headers=additional_headers,
            payload=payload,
            log_on_exception=log_on_exception,
            init_timeout=None,
            zipped=not disable_compression,
            tag="log_event",
        )
        if response.status_code in self.__RETRY_CODES:
            response.retryable = True
        return response

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
        for temp_file in self.__temp_cert_files:
            try:
                os.unlink(temp_file)
            except Exception:
                pass
        self.__temp_cert_files.clear()

    def authenticate_request_session(self, http_proxy_config: ProxyConfig):
        try:
            if http_proxy_config.authentication_mode == AuthenticationMode.TLS:
                ca_cert = load_credential_from_file(http_proxy_config.tls_ca_cert_path, "TLS CA certificate")
                if ca_cert:
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as ca_file:
                        ca_file.write(ca_cert)
                        self.__request_session.verify = ca_file.name
                        self.__temp_cert_files.append(ca_file.name)
                    globals.logger.log_process("HTTP Worker", "Connecting using an TLS secure channel for HTTP")
            elif http_proxy_config.authentication_mode == AuthenticationMode.MTLS:
                client_cert = load_credential_from_file(http_proxy_config.tls_client_cert_path, "TLS client certificate")
                client_key = load_credential_from_file(http_proxy_config.tls_client_key_path, "TLS client key")
                ca_cert = load_credential_from_file(http_proxy_config.tls_ca_cert_path, "TLS CA certificate")
                if client_cert and client_key and ca_cert:
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as cert_file:
                        cert_file.write(client_cert)
                        cert_path = cert_file.name
                        self.__temp_cert_files.append(cert_path)
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.key') as key_file:
                        key_file.write(client_key)
                        key_path = key_file.name
                        self.__temp_cert_files.append(key_path)
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as ca_file:
                        ca_file.write(ca_cert)
                        ca_path = ca_file.name
                        self.__temp_cert_files.append(ca_path)
                    self.__request_session.cert = (cert_path, key_path)
                    self.__request_session.verify = ca_path
                    globals.logger.log_process("HTTP Worker", "Connecting using an mTLS secure channel for HTTP")
        except Exception as e:
            self.__error_boundary.log_exception("http_worker:init_session", e)

    def _run_task_for_initialize(
        self, task, timeout
    ) -> Tuple[Optional[Any], Optional[Exception]]:
        future = self._executor.submit(task)
        try:
            result = future.result(timeout=timeout)
            return result, None
        except Exception as e:
            return None, e

    def _post_request(
        self,
        url,
        headers,
        payload,
        log_on_exception=False,
        init_timeout=None,
        zipped=None,
        tag=None,
        useStatsigClient=False,
    ):
        return self._request(
            "POST", url, headers, payload, log_on_exception, init_timeout, zipped, tag, useStatsigClient
        )

    def _get_request(
        self,
        url,
        headers,
        log_on_exception=False,
        init_timeout=None,
        zipped=None,
        tag=None,
        get_text_value_only=False,
        useStatsigClient=False,
    ):
        return self._request(
            "GET",
            url,
            headers,
            None,
            log_on_exception,
            init_timeout,
            zipped,
            tag,
            get_text_value_only,
            useStatsigClient
        )

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
        get_text_value_only=False,
        useStatsigClient = False,
    ) -> RequestResult:
        if self.__local_mode:
            globals.logger.debug("Using local mode. Dropping network request")
            return RequestResult(data=None, status_code=None, success=False, error=None)

        create_marker = self._get_diagnostics_from_url_or_tag(url, tag)
        marker_id = str(self.__request_count) if (tag == "log_event") else None
        self.__request_count += 1
        if create_marker is not None:
            self.__diagnostics.add_marker(
                create_marker().start({"markerID": marker_id})
            )

        headers = self._prepare_headers(headers, zipped)

        if payload is not None:
            payload = self._prepare_payload(payload, url, zipped)
            if payload is None:
                return RequestResult(
                    data=None,
                    status_code=None,
                    success=False,
                    error=Exception("Invalid payload or failed to encode payload"),
                )

        timeout = init_timeout if init_timeout is not None else self.__req_timeout
        payload_size = len(payload) if payload else None
        result = self._run_request_with_strict_timeout(
            method,
            url,
            headers,
            payload,
            timeout,
            init_timeout is not None,
            get_text_value_only,
            useStatsigClient
        )

        if create_marker is not None:
            self._handle_diagnostics_end(create_marker, result, payload_size, marker_id)

        if result.error is not None:
            self._handle_response_error(
                url, result.error, log_on_exception, tag, timeout, method
            )

        return result

    def _run_request_with_strict_timeout(
        self,
        method,
        url,
        headers,
        payload,
        timeout,
        for_initialize=False,
        get_text_value_only=False,
        useStatsigClient=False
    ) -> RequestResult:
        def request_task():
            try:
                request_session = self.__statsig_request_session if useStatsigClient else self.__request_session
                with request_session.request(
                    method,
                    url,
                    data=payload,
                    headers=headers,
                    timeout=timeout,
                    stream=True,
                ) as response:
                    try:
                        response.raise_for_status()
                    except requests.exceptions.HTTPError as e:
                        return RequestResult(
                            data=None,
                            status_code=response.status_code,
                            success=False,
                            headers=response.headers,
                            error=e,
                        )

                    result = RequestResult(
                        data=None,
                        status_code=response.status_code,
                        success=True,
                        headers=response.headers,
                    )
                    if get_text_value_only:
                        result.text = response.text
                    else:
                        result.data = self._stream_response_into_result_dict(response)
                    return result
            except Exception as e:
                return RequestResult(
                    data=None, status_code=None, success=False, error=e
                )

        if for_initialize:
            future = self._executor.submit(request_task)
            try:
                return future.result(timeout=timeout)
            except Exception as e:
                return RequestResult(
                    data=None, status_code=None, success=False, error=e
                )
        return request_task()

    def _stream_response_into_result_dict(self, response):
        decompressor = StreamDecompressor(
            response.raw, response.headers.get("Content-Encoding")
        )

        json_result = {}

        for k, v in ijson.kvitems(decompressor, ""):
            json_result[k] = self._convert_decimals_to_floats(v)

        return json_result

    def _convert_decimals_to_floats(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: self._convert_decimals_to_floats(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_decimals_to_floats(v) for v in obj]
        return obj

    def _is_success_code(self, status_code: Optional[int]) -> bool:
        if status_code is None:
            return False
        return 200 <= status_code < 300

    def _prepare_headers(
        self, headers: Optional[Dict[str, Any]], zipped: bool
    ) -> Dict[str, Any]:
        base_headers = {
            "Content-type": "application/json",
            "STATSIG-API-KEY": self.__sdk_key,
            "STATSIG-CLIENT-TIME": str(round(time.time() * 1000)),
            "STATSIG-SERVER-SESSION-ID": self.__statsig_metadata["sessionID"],
            "STATSIG-SDK-TYPE": self.__statsig_metadata["sdkType"],
            "STATSIG-SDK-VERSION": self.__statsig_metadata["sdkVersion"],
            "STATSIG-RETRY": "0",
            "Accept-Encoding": "gzip, deflate, br",
        }

        if zipped:
            base_headers.update({"Content-Encoding": "gzip"})

        if headers is not None:
            base_headers.update(headers)

        return base_headers

    def _zip_payload(self, payload: str) -> bytes:
        btsio = BytesIO()
        with gzip.GzipFile(fileobj=btsio, mode="w") as gz:
            gz.write(payload.encode("utf-8"))
        return btsio.getvalue()

    def _prepare_payload(self, payload, url, zipped=False):
        try:
            payload = json.dumps(payload)
            if zipped:
                payload = self._zip_payload(payload)
        except Exception as e:
            error_message = (
                f"Dropping request to {url}. Failed to JSON encode payload. "
                f"Are you sure the input is JSON serializable? {type(e).__name__}: {e.args}"
            )
            globals.logger.error(error_message)
            if self._raise_on_error:
                raise e
            return None

        return payload

    def _verify_json_payload(self, payload, url):
        try:
            return json.dumps(payload)
        except TypeError as e:
            globals.logger.error(
                f"Dropping request to {url}. Failed to json encode payload. Are you sure the input is json serializable? "
                f"{type(e).__name__} {e.args}"
            )
            if self._raise_on_error:
                raise e
            return None

    def _handle_response_error(
        self,
        url: str,
        error: Exception,
        log_on_exception: bool,
        tag: str,
        timeout: int,
        method: str,
    ):
        globals.logger.warning(f"Request to {url} failed with error {error}")
        self._context.error = error
        if log_on_exception and not isinstance(error, requests.HTTPError):
            self.__error_boundary.log_exception(
                "request:" + tag,
                error,
                {"timeoutMs": timeout * 1000, "httpMethod": method},
                log_mode="none",
            )

    def _handle_diagnostics_end(
        self,
        create_marker: Callable,
        result: RequestResult,
        payload_size: Optional[int],
        marker_id: Optional[str],
    ):
        marker_data = {
            "statusCode": result.status_code,
            "success": result.success,
            "payloadSize": payload_size,
            "markerID": marker_id,
            "networkProtocol": NetworkProtocol.HTTP,
        }

        if result.headers:
            marker_data["sdkRegion"] = result.headers.get("x-statsig-region")

        if not result.success:
            marker_data["error"] = Diagnostics.format_error(result.error)

        self.__diagnostics.add_marker(create_marker().end(marker_data))

    def _get_diagnostics_from_url_or_tag(
        self, url: str, tag: str
    ) -> Optional[Callable]:
        if "download_config_specs" in url or tag == "download_config_specs":
            return lambda: Marker(url=url).download_config_specs().network_request()
        if "get_id_lists" in url or tag == "get_id_lists":
            return lambda: Marker(url=url).get_id_list_sources().network_request()
        if "idliststorage" in url or tag == "get_id_list":
            return lambda: Marker(url=url).get_id_list().network_request()
        if "log_event" in url or tag == "log_event":
            return lambda: Marker().log_event().network_request()
        return None

    def __get_proxy_address(
        self, options: StatsigOptions, endpoint: NetworkEndpoint
    ) -> Optional[str]:
        proxy_config = options.proxy_configs.get(endpoint)
        return (
            proxy_config.proxy_address + "/v1"
            if proxy_config and proxy_config.proxy_address
            else None
        )

    def __configure_endpoints(self, options: StatsigOptions) -> None:
        api_for_download_config_specs = (
            self.__get_proxy_address(options, NetworkEndpoint.DOWNLOAD_CONFIG_SPECS)
            or options.api_for_download_config_specs
            or options.api
            or STATSIG_CDN
        )
        if not api_for_download_config_specs.endswith("/"):
            api_for_download_config_specs += "/"

        api_for_get_id_lists = (
            self.__get_proxy_address(options, NetworkEndpoint.GET_ID_LISTS)
            or options.api_for_get_id_lists
            or options.api
            or STATSIG_CDN
        )
        if not api_for_get_id_lists.endswith("/"):
            api_for_get_id_lists += "/"

        api_for_log_event = (
            self.__get_proxy_address(options, NetworkEndpoint.LOG_EVENT)
            or options.api_for_log_event
            or options.api
            or STATSIG_API
        )
        if not api_for_log_event.endswith("/"):
            api_for_log_event += "/"

        self.__api_for_download_config_specs = api_for_download_config_specs
        self.__api_for_get_id_lists = api_for_get_id_lists
        self.__api_for_log_event = api_for_log_event

    def __is_cdn_url(self, url: str) -> bool:
        return url.startswith(STATSIG_CDN)
