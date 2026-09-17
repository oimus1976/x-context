import os
import tempfile
import unittest
from pathlib import Path

from x_context.credential_lifecycle import CredentialRecord, DPAPIFileCredentialStore


@unittest.skipUnless(os.name == "nt", "real DPAPI integration is Windows-only")
class WindowsDPAPICredentialLifecycleTests(unittest.TestCase):
    def test_CRED_real_windows_dpapi_round_trip_and_plaintext_absent(self):
        access = "SYNTHETIC-DPAPI-ACCESS-SENTINEL"
        refresh = "SYNTHETIC-DPAPI-REFRESH-SENTINEL"
        original = CredentialRecord(
            access_token=access,
            refresh_token=refresh,
            token_type="bearer",
            expires_at=4_102_444_800,
            scopes=("tweet.read", "users.read", "bookmark.read", "like.read", "offline.access"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential-v1.dpapi"
            store = DPAPIFileCredentialStore(path=path)

            store.replace(original)
            durable = path.read_bytes()
            self.assertTrue(durable)
            self.assertNotIn(access.encode("utf-8"), durable)
            self.assertNotIn(refresh.encode("utf-8"), durable)

            loaded = store.load()
            self.assertEqual(loaded, original)

            store.delete()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
