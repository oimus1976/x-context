import unittest

from x_context.x_api import HttpResponse, XApiError, lookup_post


class CapturingTransport:
    def __init__(self):
        self.request = None

    def __call__(self, request):
        self.request = request
        return HttpResponse(
            status=200,
            headers={},
            body=b'{"data":{"id":"123","text":"hello"}}',
        )


class FailingTransport:
    def __init__(self, secret):
        self.secret = secret

    def __call__(self, request):
        raise OSError(f"synthetic transport detail {self.secret}")


class FR002SecurityTests(unittest.TestCase):
    def test_FR_002_request_repr_does_not_expose_authorization(self):
        token = "fake-bearer-token-DO-NOT-LEAK"
        transport = CapturingTransport()

        lookup_post("123", bearer_token=token, transport=transport)

        self.assertIsNotNone(transport.request)
        self.assertNotIn(token, repr(transport.request))
        self.assertNotIn("Authorization", repr(transport.request))

    def test_FR_002_transport_exception_does_not_chain_secret(self):
        token = "fake-bearer-token-DO-NOT-LEAK"
        provider_detail_secret = "provider-transport-secret-DO-NOT-LEAK"

        with self.assertRaises(XApiError) as raised:
            lookup_post(
                "123",
                bearer_token=token,
                transport=FailingTransport(provider_detail_secret),
            )

        error = raised.exception
        self.assertEqual(error.category, "provider_error")
        self.assertNotIn(token, str(error))
        self.assertNotIn(provider_detail_secret, str(error))
        self.assertIsNone(error.__cause__)


if __name__ == "__main__":
    unittest.main()
