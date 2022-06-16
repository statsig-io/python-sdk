import traceback
import unittest

from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError
from statsig.statsig_metadata import _StatsigMetadata

from tests.mockserver import MockServer


class TestStatsigErrorBoundary(unittest.TestCase):
    _boundary: _StatsigErrorBoundary
    _server: MockServer
    _requests: list

    @classmethod
    def setUpClass(cls):
        cls._server = MockServer(port=1236)
        cls._server.start()
        cls._requests = []

        def on_request():
            req = MockServer.get_request()
            cls._requests.append({
                "path": req.path,
                "body": req.json,
                "headers": req.headers
            })
            return req.json

        cls._server.add_callback_response(
            "/v1/sdk_exception", on_request)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown_server()

    def setUp(self):
        self.__class__._requests = []
        self._boundary = _StatsigErrorBoundary()
        self._boundary.set_api_key('secret-key')
        self._boundary.endpoint = self._server.url + "/v1/sdk_exception"

    def test_recovers_from_errors(self):
        called = False

        def task():
            raise RuntimeError()

        def recover():
            nonlocal called
            called = True

        self._boundary.capture(task, recover)
        self.assertTrue(called)

    def test_has_default_recovery_of_none(self):
        def task():
            raise RuntimeError()

        res = self._boundary.capture(task)
        self.assertIsNone(res)

    def test_logging_to_correct_endpoint(self):
        self._capture_error()

        req = self._get_requests()[0]
        self.assertEqual(req['path'], "/v1/sdk_exception")
        self.assertEqual(
            req['headers']['statsig-api-key'], "secret-key")
        metadata = _StatsigMetadata.get()
        self.assertEqual(
            req['headers']['statsig-sdk-type'], metadata["sdkType"])
        self.assertEqual(
            req['headers']['statsig-sdk-version'], metadata["sdkVersion"])

    def test_logging_exception_details(self):
        err = self._capture_error()

        body = self._get_requests()[0]['body']
        self.assertEqual(body['exception'], "RuntimeError")
        self.assertEqual(body['info'], "".join(traceback.format_exception(
            type(err), err, err.__traceback__)))

    def test_logging_statsig_metadata(self):
        self._capture_error()

        body = self._get_requests()[0]['body']
        self.assertEqual(body['statsigMetadata'], _StatsigMetadata.get())

    def test_logging_errors_only_once(self):
        self._capture_error()

        body = self._get_requests()[0]['body']
        self.assertEqual(body['exception'], "RuntimeError")

        self._capture_error()
        self.assertEqual(len(self._get_requests()), 1)

    def test_does_not_catch_intended_error(self):
        def test_value_error():
            def task():
                raise StatsigValueError()
            self._boundary.capture(task)

        def test_name_error():
            def task():
                raise StatsigNameError()
            self._boundary.capture(task)

        def test_runtime_error():
            def task():
                raise StatsigRuntimeError()
            self._boundary.capture(task)

        def test_interrupts():
            def task():
                raise KeyboardInterrupt()
            self._boundary.capture(task)

        def test_exits():
            def task():
                raise SystemExit()
            self._boundary.capture(task)

        self.assertRaises(StatsigValueError, test_value_error)
        self.assertRaises(StatsigNameError, test_name_error)
        self.assertRaises(StatsigRuntimeError, test_runtime_error)
        self.assertRaises(KeyboardInterrupt, test_interrupts)
        self.assertRaises(SystemExit, test_exits)

    def test_returns_successful_results(self):
        def task():
            return "the_result"

        def recover():
            pass

        res = self._boundary.capture(task, recover)
        self.assertEqual(res, "the_result")

    def test_returns_recovered_results(self):
        def task():
            raise RuntimeError()

        def recover():
            return "recovered_result"

        res = self._boundary.capture(task, recover)
        self.assertEqual(res, "recovered_result")

    def _capture_error(self) -> RuntimeError:
        err = RuntimeError()

        def task():
            raise err

        def recover():
            pass

        self._boundary.capture(task, recover)
        return err

    def _get_requests(self):
        return self.__class__._requests


if __name__ == '__main__':
    unittest.main()
