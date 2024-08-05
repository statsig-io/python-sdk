import time
from concurrent.futures import ThreadPoolExecutor

import grpc

from statsig.grpc.generated.statsig_forward_proxy_pb2 import ConfigSpecResponse
from statsig.grpc.generated.statsig_forward_proxy_pb2_grpc import add_StatsigForwardProxyServicer_to_server, \
    StatsigForwardProxyServicer


def start_grpc_server():
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    mock_service = MockGRPCWebsocketServer()
    add_StatsigForwardProxyServicer_to_server(mock_service, server)
    port = server.add_insecure_port('[::]:0')
    server.start()
    return server, mock_service, port


class MockGRPCWebsocketServer(StatsigForwardProxyServicer):
    _stream = []
    _callback = None

    def reset(self):
        self._stream = []
        self._callback = None

    def set_callback(self, callback):
        self._callback = callback

    def stub_stream_with_event(self, spec, lcut):
        event = ConfigSpecResponse(spec=spec, lastUpdated=lcut)

        self._stream.append(event)

    def stub_stream_with_disconnection(self):
        self._stream.append("unavailable")

    def stub_stream_with_error(self):
        self._stream.append("error")

    def getConfigSpec(self, request, context):
        return self._stream[0]

    def StreamConfigSpec(self, request, context):
        if self._callback:
            self._callback(request)
        for event in self._stream:
            if event == "unavailable":
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details('unavailable')
            elif event == "error":
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('error')
            yield event
