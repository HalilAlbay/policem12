import unittest
from push_service import valid_endpoint

class EndpointTests(unittest.TestCase):
    def test_valid_https(self):
        self.assertTrue(valid_endpoint('https://fcm.googleapis.com/fcm/send/123456789'))
    def test_unknown_host_rejected(self):
        self.assertFalse(valid_endpoint('https://push.example.org/sub/123456789'))
    def test_http_rejected(self):
        self.assertFalse(valid_endpoint('http://localhost:8000/sub'))
    def test_credentials_rejected(self):
        self.assertFalse(valid_endpoint('https://user:password@push.example.org/sub'))
    def test_custom_port_rejected(self):
        self.assertFalse(valid_endpoint('https://push.example.org:8443/sub'))

if __name__ == '__main__':
    unittest.main()
