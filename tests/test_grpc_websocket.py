import json
import os
import unittest
from unittest.mock import patch

import time

from statsig import StatsigServer, _Evaluator, StatsigUser
from statsig.interface_network import NetworkProtocol, NetworkEndpoint
from statsig.statsig_options import ProxyConfig, StatsigOptions
from tests.grpc_websocket_stub import start_grpc_server
from tests.gzip_helpers import GzipHelpers
from tests.network_stub import NetworkStub

with open(
        os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "../testdata/download_config_specs.json",
        )
) as r:
    CONFIG_SPECS_RESPONSE = r.read()

_api_override = "http://evaluation-details-test"
_network_stub = NetworkStub(_api_override)


@patch('requests.Session.request', side_effect=_network_stub.mock)
class TestGRPCWebsocketInitialize(unittest.TestCase):
    _server: StatsigServer
    _evaluator: _Evaluator
    _user = StatsigUser(user_id="a-user")

    @patch('requests.Session.request', side_effect=_network_stub.mock)
    def setUp(self, mock_request):
        mock_server, grpc_stub, port = start_grpc_server()
        self.grpc_stub = grpc_stub
        self.mock_server = mock_server
        proxy_address = f'localhost:{port}'
        proxy_config = ProxyConfig(proxy_address=proxy_address, protocol=NetworkProtocol.GRPC_WEBSOCKET)
        self._options = StatsigOptions(proxy_configs={
            NetworkEndpoint.DOWNLOAD_CONFIG_SPECS: proxy_config
        }, api=_api_override)
        self._events = []
        self._server = StatsigServer()

        self.statsig_user = StatsigUser(
            "regular_user_id", email="testuser@statsig.com", private_attributes={"test": 123})
        self.random_user = StatsigUser("random")

        grpc_stub.reset()
        _network_stub.reset()

        def on_log(url: str, **kwargs):
            self._events += GzipHelpers.decode_body(kwargs, False)["events"]

        _network_stub.stub_request_with_function("log_event", 202, on_log)

        _network_stub.stub_request_with_value(
            "download_config_specs/.*", 200, json.loads(CONFIG_SPECS_RESPONSE)
        )

        self.get_id_list_response = {}

        _network_stub.stub_request_with_value("get_id_lists", 200, {})

    def test_grpc_websocket_initialized(self, mock_request):
        self.grpc_stub.stub_stream_with_event(CONFIG_SPECS_RESPONSE, json.loads(CONFIG_SPECS_RESPONSE)['time'])
        self._server.initialize("secret-key", self._options)
        self._server.shutdown()

        self.assertEqual(len(self._events), 1)
        metadata = self._events[0]["metadata"]
        markers = metadata["markers"]
        self.assertEqual(len(markers), 10)

    def test_retry_on_disconnection_with_lcut(self, mock_request):
        connect_count = 0
        lcut = 0

        def on_connect(request):
            nonlocal connect_count
            nonlocal lcut
            lcut = request.sinceTime
            connect_count += 1

        self.grpc_stub.set_callback(on_connect)
        self.grpc_stub.stub_stream_with_event(CONFIG_SPECS_RESPONSE, json.loads(CONFIG_SPECS_RESPONSE)['time'])
        self.grpc_stub.stub_stream_with_disconnection()
        self.grpc_stub.stub_stream_with_event(CONFIG_SPECS_RESPONSE, json.loads(CONFIG_SPECS_RESPONSE)['time'])
        self._server.initialize("secret-key", self._options)
        time.sleep(11)
        self._server.shutdown()
        self.assertEqual(connect_count, 2)
        self.assertEqual(lcut, json.loads(CONFIG_SPECS_RESPONSE)['time'])
