import json
import os
import time
import unittest

from unittest.mock import patch
from network_stub import NetworkStub
from statsig import StatsigOptions, statsig, StatsigUser
from statsig.evaluation_details import EvaluationDetails, EvaluationReason
from statsig.http_worker import HttpWorker

_network_stub = NetworkStub("http://test-sync-config-fallback", mock_statsig_api=True)
with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../testdata/download_config_specs.json')) as r:
    CONFIG_SPECS_RESPONSE = r.read()

class TestSyncConfigFallback(unittest.TestCase):
  @classmethod
  @patch('requests.request', side_effect=_network_stub.mock)
  def setUpClass(cls, mock_proxy):
    cls.dcs_hit = 0
    _network_stub.reset()
    def dcs_proxy_callback(url: str, **kwargs):
      cls.dcs_hit += 1
      return json.loads(CONFIG_SPECS_RESPONSE)

    _network_stub.stub_request_with_function(
        "download_config_specs/.*", 200, dcs_proxy_callback)

    cls.test_user = StatsigUser("123", email="testuser@statsig.com")
  
  def tearDown(self):
    self.dcs_hit = 0
    statsig.shutdown()
      
  @patch('requests.request', side_effect=_network_stub.mock)
  @patch.object(HttpWorker, 'get_dcs_fallback')
  def test_default_behavior(self, fallback_mock, request_mock):
    # default behavior is no fallback if is out of sync
    options = StatsigOptions(api=_network_stub.host, fallback_to_statsig_api=True, rulesets_sync_interval=1)
    statsig.initialize("secret-key", options)
    gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
    eval_detail: EvaluationDetails = gate.get_evaluation_details()
    self.assertEqual(eval_detail.reason, EvaluationReason.network)
    self.assertEqual(eval_detail.config_sync_time, 1631638014811)
    time.sleep(1.1)
    
    fallback_mock.assert_not_called()
    
  @patch('requests.request', side_effect=_network_stub.mock)
  @patch.object(HttpWorker, 'get_dcs_fallback')
  def test_fallback_when_out_of_sync(self, fallback_mock, request_mock):
    # default behavior is no fallback if is out of sync
    options = StatsigOptions(api_for_download_config_specs=_network_stub.host, fallback_to_statsig_api=True, rulesets_sync_interval=1, out_of_sync_threshold_in_s=0.5)
    statsig.initialize("secret-key", options)
    gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
    eval_detail: EvaluationDetails = gate.get_evaluation_details()
    self.assertEqual(eval_detail.reason, EvaluationReason.network)
    self.assertEqual(eval_detail.config_sync_time, 1631638014811)
    time.sleep(1.1)
    #ensure it falls back
    fallback_mock.assert_called_once()
    
  @patch('requests.request', side_effect=_network_stub.mock)
  @patch.object(HttpWorker, 'get_dcs_fallback')
  def test_behavior_when_not_out_of_sync(self, fallback_mock, request_mock):
    # default behavior is no fallback if is out of sync
    options = StatsigOptions(api_for_download_config_specs=_network_stub.host, fallback_to_statsig_api=True, rulesets_sync_interval=1, out_of_sync_threshold_in_s=4e10)
    statsig.initialize("secret-key", options)
    gate = statsig.get_feature_gate(self.test_user, "always_on_gate")
    eval_detail: EvaluationDetails = gate.get_evaluation_details()
    self.assertEqual(eval_detail.reason, EvaluationReason.network)
    self.assertEqual(eval_detail.config_sync_time, 1631638014811)
    time.sleep(1.1)
    #ensure no fallback
    fallback_mock.assert_not_called()
