import unittest

from uuid import uuid4
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_event import StatsigEvent
from statsig.statsig_metadata import _StatsigMetadata
from statsig.statsig_network import _StatsigNetwork
from statsig.statsig_user import StatsigUser
from statsig.diagnostics import Diagnostics
from statsig import globals
from statsig import StatsigOptions

class TestNetwork(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # This test logspews expected errors, but the test itself should pass
        globals.logger._disabled = False
        metadata = _StatsigMetadata.get()
        cls.net = _StatsigNetwork("secret-test", StatsigOptions(disable_diagnostics=True), metadata, _StatsigErrorBoundary(), Diagnostics())
        cls.net._raise_on_error = True

    @classmethod
    def tearDownClass(cls):
        globals.logger._disabled = True

    def test_invalid_user(self):
        user = StatsigUser(user_id= "123", custom={'field': uuid4()})
        event = StatsigEvent(user, "test_event")
        # request fails due to json serialization of user
        self.assertRaises(
            TypeError,
            self.net.retryable_log_event,
            {
                'events':[
                    event.to_dict()
                ],
            },
            True,
        )
    
    def test_invalid_metadata(self):
        user = StatsigUser(user_id= "123", )
        event = StatsigEvent(user, "test_event", None, {'field': uuid4()})
        # request fails due to json serialization of event
        self.assertRaises(
            TypeError,
            self.net.retryable_log_event,
            {
                'events':[
                    event.to_dict()
                ],
            },
            True,
        )
    
    def test_invalid_post(self):
        user = StatsigUser(user_id= "123", )
        event = StatsigEvent(user, "test_event", None, {'field': uuid4()})
        # request fails due to json serialization of event
        self.assertRaises(
            TypeError,
            self.net._post_request,
            "http://statsigapi.net/v1/log_event3",
            None,
            {
                'events':[
                    event.to_dict()
                ],
            },
            True,
        )
