import traceback
import unittest

from unittest.mock import patch
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_errors import StatsigNameError, StatsigRuntimeError, StatsigValueError
from statsig.statsig_metadata import _StatsigMetadata
from statsig.statsig_options import StatsigOptions


def mocked_post(*args, **kwargs):
    TestStatsigErrorBoundary.requests.append({
        "url": args[0],
        "body": kwargs['json'],
        "headers": kwargs['headers']
    })


@patch('requests.post', side_effect=mocked_post)
class TestStatsigErrorBoundary(unittest.TestCase):    
    requests: list

    _boundary: _StatsigErrorBoundary

    def setUp(self):
        self._boundary = _StatsigErrorBoundary()
        self._boundary.set_api_key('secret-key')
        self._options = StatsigOptions(api="www.google.com", rulesets_sync_interval=10000)
        self._metadata = _StatsigMetadata.get()
        self._boundary.set_statsig_options_and_metadata(self._options, self._metadata)
        self._boundary._is_silent = True
        TestStatsigErrorBoundary.requests = []

    def test_recovers_from_errors(self, mock_post):
        called = False

        def task():
            raise RuntimeError()

        def recover():
            nonlocal called
            called = True

        self._boundary.capture("", task, recover)
        self._boundary.shutdown(True)
        self.assertTrue(called)

    def test_has_default_recovery_of_none(self, mock_post):
        def task():
            raise RuntimeError()

        res = self._boundary.swallow("", task)
        self._boundary.shutdown(True)
        self.assertIsNone(res)

    def test_logging_to_correct_endpoint(self, mock_post):
        self._capture_error()
        req = self._get_requests()[0]
        self.assertEqual(req['url'], "https://statsigapi.net/v1/sdk_exception")
        self.assertEqual(
            req['headers']['STATSIG-API-KEY'], "secret-key")
        metadata = _StatsigMetadata.get()
        self.assertEqual(
            req['headers']['STATSIG-SDK-TYPE'], metadata["sdkType"])
        self.assertEqual(
            req['headers']['STATSIG-SDK-VERSION'], metadata["sdkVersion"])

    def test_logging_exception_details(self, mock_post):
        err = self._capture_error()

        body = self._get_requests()[0]['body']
        self.assertEqual(body['exception'], "RuntimeError")
        self.assertEqual(body['info'], "".join(traceback.format_exception(
            type(err), err, err.__traceback__)))
        self.assertEqual(body['tag'], "_capture_error")
        self.assertIsInstance(body['extra'], dict)
        self.assertEqual(body['extra']['clientKey'], 'client-key')
        self.assertEqual(body['extra']['hash'], 'djb2')

    def test_logging_statsig_metadata(self, mock_post):
        self._capture_error()

        body = self._get_requests()[0]['body']
        self.assertEqual(body['statsigMetadata'], self._metadata)
    
    def test_logging_statsig_options(self, mock_post):
        self._capture_error()
        
        body = self._get_requests()[0]['body']
        self.assertEqual(body['statsigOptions'], self._options.logging_copy)
        
    def test_logging_errors_only_once(self, mock_post):
        self._capture_error()

        self.assertEqual(len(self._get_requests()), 1)
        body = self._get_requests()[0]['body']
        self.assertEqual(body['exception'], "RuntimeError")

        self._capture_error()
        self.assertEqual(len(self._get_requests()), 1)

    def test_does_not_catch_intended_error(self, mock_post):
        def test_value_error():
            def task():
                raise StatsigValueError()

            self._boundary.swallow("", task)

        def test_name_error():
            def task():
                raise StatsigNameError()

            self._boundary.swallow("", task)

        def test_runtime_error():
            def task():
                raise StatsigRuntimeError()

            self._boundary.swallow("", task)

        def test_interrupts():
            def task():
                raise KeyboardInterrupt()

            self._boundary.swallow("", task)

        def test_exits():
            def task():
                raise SystemExit()

            self._boundary.swallow("", task)

        self.assertRaises(StatsigValueError, test_value_error)
        self.assertRaises(StatsigNameError, test_name_error)
        self.assertRaises(StatsigRuntimeError, test_runtime_error)
        self.assertRaises(KeyboardInterrupt, test_interrupts)
        self.assertRaises(SystemExit, test_exits)

    def test_returns_successful_results(self, mock_post):
        def task():
            return "the_result"

        def recover():
            pass

        res = self._boundary.capture("", task, recover)
        self.assertEqual(res, "the_result")

    def test_returns_recovered_results(self, mock_post):
        def task():
            raise RuntimeError()

        def recover():
            return "recovered_result"

        res = self._boundary.capture("", task, recover)
        self.assertEqual(res, "recovered_result")

    def _capture_error(self) -> RuntimeError:
        err = RuntimeError()

        def task():
            raise err

        def recover():
            pass

        self._boundary.capture("_capture_error", task, recover, {'clientKey': 'client-key', 'hash': 'djb2'})
        return err

    def _get_requests(self):
        self._boundary.shutdown(True)
        return TestStatsigErrorBoundary.requests


if __name__ == '__main__':
    unittest.main()
