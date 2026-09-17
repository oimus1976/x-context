import io
import json
import unittest

from x_context.cli import main


class FailIfCalledAcquirer:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("OAuth acquisition must not be called for parser rejection")


class OAuthBootstrapCliSecurityTests(unittest.TestCase):
    def test_AUTH_login_rejects_credential_cli_argument_without_echoing_secret(self):
        secret = "SENTINEL-CLI-CREDENTIAL-DO-NOT-LEAK"
        out, err = io.StringIO(), io.StringIO()
        acquirer = FailIfCalledAcquirer()

        code = main(
            ["auth", "login", "--token", secret],
            environ={
                "X_CONTEXT_OAUTH_CLIENT_ID": "fake-client-id",
                "X_CONTEXT_OAUTH_REDIRECT_URI": "http://127.0.0.1:8765/callback",
            },
            oauth_acquirer=acquirer,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["error_category"], "invalid_input")
        self.assertEqual(acquirer.calls, [])
        self.assertNotIn(secret, out.getvalue() + err.getvalue())

    def test_AUTH_login_rejects_extra_secret_argument_without_echoing_it(self):
        secret = "SENTINEL-EXTRA-ARGUMENT-DO-NOT-LEAK"
        out, err = io.StringIO(), io.StringIO()
        acquirer = FailIfCalledAcquirer()

        code = main(
            ["auth", "login", secret],
            environ={},
            oauth_acquirer=acquirer,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["error_category"], "invalid_input")
        self.assertEqual(acquirer.calls, [])
        self.assertNotIn(secret, out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
