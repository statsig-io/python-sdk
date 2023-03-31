import unittest

from uuid import uuid4
from statsig.statsig_error_boundary import _StatsigErrorBoundary
from statsig.statsig_event import StatsigEvent
from statsig.statsig_network import _StatsigNetwork
from statsig.statsig_user import StatsigUser
from statsig.utils import logger
from statsig import StatsigOptions

class TestNetwork(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # This test logspews expected errors, but the test itself should pass
        logger.disabled = False
        cls.net = _StatsigNetwork("secret-test", StatsigOptions(disable_diagnostics=True), _StatsigErrorBoundary())
        cls.net._raise_on_error = True

    @classmethod
    def tearDownClass(cls):
        logger.disabled = True

    def test_invalid_user(self):
        user = StatsigUser(user_id= "123", custom={'field': uuid4()})
        event = StatsigEvent(user, "test_event")
        # request fails due to json serialization of user
        self.assertRaises(
            TypeError,
            self.net.retryable_request,
            "log_event",
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
            self.net.retryable_request,
            "log_event2",
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
            self.net.post_request,
            "log_event3",
            {
                'events':[
                    event.to_dict()
                ],
            },
            True,
        )
