import json
import unittest
from unittest.mock import patch
from urllib.parse import quote

import requests

from statsig import globals
from statsig._secret_redactor import redact_exception, redact_text
from statsig.diagnostics import Diagnostics
from statsig.http_worker import HttpWorker
from statsig.request_result import RequestResult
from statsig.statsig_context import InitContext
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_metadata import _StatsigMetadata
from statsig.statsig_options import StatsigOptions


class TestSecretRedaction(unittest.TestCase):
    def setUp(self):
        self.key = 'secret-a+b/!'
        self.options = StatsigOptions(disable_diagnostics=True)
        self.boundary = _StatsigErrorBoundary()
        self.boundary.set_api_key(self.key)
        self.boundary.set_statsig_options_and_metadata(self.options, _StatsigMetadata.get())
        self.context = InitContext()
        self.worker = HttpWorker(self.key, self.options, _StatsigMetadata.get(),
                                 self.boundary, Diagnostics(), self.context)

    def tearDown(self):
        self.worker.shutdown()
        self.boundary.shutdown(True)

    def test_redacts_raw_encoded_repeated_and_unknown_dcs_key(self):
        encoded = quote(self.key, safe='')
        result = redact_text(f'{self.key} {encoded} {self.key} https://host/v1/download_config_specs/other.json?sinceTime=2', self.key)
        self.assertNotIn(self.key, result)
        self.assertNotIn(encoded, result)
        self.assertIn('/download_config_specs/[REDACTED].json?sinceTime=2', result)
        self.assertIn('https://host', result)

    def test_request_failure_is_safe_in_result_context_logger_and_diagnostics(self):
        url = 'https://example.test/v1/download_config_specs/' + self.key + '.json'
        request = requests.Request('GET', url).prepare()
        original = requests.ConnectionError('timeout for ' + url, request=request)
        original.__cause__ = ValueError(self.key)
        result = RequestResult(data=None, status_code=None, success=False, error=original)
        with patch.object(self.worker, '_run_request_with_strict_timeout', return_value=result) as run, \
             patch.object(globals.logger, 'warning') as warning, \
             patch.object(self.worker, '_handle_diagnostics_end') as marker:
            returned = self.worker._get_request(url, None, log_on_exception=False, tag='download_config_specs')
        self.assertIsInstance(returned.error, requests.ConnectionError)
        self.assertNotIn(self.key, str(returned.error))
        self.assertIsNone(returned.error.__cause__)
        self.assertIsNone(returned.error.request)
        self.assertNotIn(self.key, str(self.context.error))
        self.assertNotIn(self.key, str(warning.call_args))
        self.assertNotIn(self.key, str(marker.call_args))
        self.assertEqual(run.call_args.args[1], url)
        self.assertIn(self.key, str(original))
        self.assertIsNotNone(original.__cause__)

    def test_telemetry_and_callback_are_redacted_without_changing_headers(self):
        self.boundary.set_init_context(self.context)
        self.boundary._is_silent = True
        error = ValueError('failure ' + self.key)
        with patch.object(globals.logger, 'log_sdk_exception') as callback, \
             patch.object(self.boundary._session, 'post') as post:
            self.boundary.log_exception('tag ' + self.key, error, {'nested': [self.key]}, bypass_dedupe=True)
            self.boundary.shutdown(True)
        payload = json.dumps(post.call_args.kwargs['json'])
        self.assertNotIn(self.key, payload)
        self.assertNotIn(self.key, str(callback.call_args))
        self.assertNotIn(self.key, str(self.context.error))
        self.assertEqual(post.call_args.kwargs['headers']['STATSIG-API-KEY'], self.key)
        self.assertEqual(str(error), 'failure ' + self.key)

    def test_http_failures_preserve_status_without_key(self):
        url = 'https://example.test/v1/download_config_specs/' + self.key + '.json'
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                result = RequestResult(data=None, status_code=status, success=False,
                                       error=requests.HTTPError(f'{status} for {url}'))
                with patch.object(self.worker, '_run_request_with_strict_timeout', return_value=result), \
                     patch.object(globals.logger, 'warning') as warning:
                    returned = self.worker._get_request(url, None, tag='download_config_specs')
                self.assertEqual(returned.status_code, status)
                self.assertIsInstance(returned.error, requests.HTTPError)
                self.assertNotIn(self.key, str(returned.error))
                self.assertNotIn(self.key, str(warning.call_args))

    def test_intended_exceptions_are_returned_without_raw_cause(self):
        from statsig.statsig_errors import StatsigValueError
        def fail():
            try:
                raise ValueError('nested ' + self.key)
            except ValueError as cause:
                raise StatsigValueError('outer ' + self.key) from cause
        with self.assertRaises(StatsigValueError) as caught:
            self.boundary.capture('test', fail, lambda: None)
        self.assertNotIn(self.key, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_grpc_error_preserves_status_without_exposing_details(self):
        import grpc
        class RpcFailure(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.UNAVAILABLE
            def details(self):
                return 'details ' + self.args[0]
        original = RpcFailure(self.key)
        safe = redact_exception(original, self.key)
        self.assertIsInstance(safe, grpc.RpcError)
        self.assertEqual(safe.code(), grpc.StatusCode.UNAVAILABLE)
        self.assertNotIn(self.key, str(safe))
        self.assertNotIn(self.key, safe.details())
        self.assertIsNone(safe.__cause__)

    def test_bad_payload_raises_safe_exception(self):
        class Bad:
            pass
        self.worker._raise_on_error = True
        url = 'https://example.test/' + self.key
        with patch.object(globals.logger, 'error') as logger:
            with self.assertRaises(TypeError) as caught:
                self.worker._prepare_payload({'value': Bad()}, url)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(self.key, str(caught.exception))
        self.assertNotIn(self.key, str(logger.call_args))


if __name__ == '__main__':
    unittest.main()
