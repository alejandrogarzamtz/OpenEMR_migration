import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
from openrm_extension import ExtensionError, verify_webhook


class WebhookVerifierTest(unittest.TestCase):
    def test_verifies_signature_timestamp_and_payload(self):
        body=json.dumps({"id":"event-1","type":"api.mutation","data":{"safe":True}},separators=(",", ":")).encode();delivery="delivery-1";timestamp=1700000000;secret="secret"
        digest=hmac.new(secret.encode(),f"{delivery}.{timestamp}.".encode()+body,hashlib.sha256).hexdigest()
        document=verify_webhook(body,{"openrm-webhook-id":delivery,"openrm-webhook-timestamp":str(timestamp),"openrm-webhook-signature":f"v1={digest}"},secret,now=timestamp)
        self.assertEqual(document["type"],"api.mutation")

    def test_rejects_tampering_expiry_and_replay(self):
        body=b'{"id":"event-2"}';headers={"OpenRM-Webhook-Id":"delivery-2","OpenRM-Webhook-Timestamp":"1700000000","OpenRM-Webhook-Signature":"v1=bad"}
        with self.assertRaises(ExtensionError):verify_webhook(body,headers,"secret",now=1700000000)
        digest=hmac.new(b"secret",b"delivery-2.1700000000."+body,hashlib.sha256).hexdigest();headers["OpenRM-Webhook-Signature"]=f"v1={digest}"
        with self.assertRaises(ExtensionError):verify_webhook(body,headers,"secret",now=1700000400)
        with self.assertRaises(ExtensionError):verify_webhook(body,headers,"secret",now=1700000000,seen=lambda _:True)


if __name__ == "__main__": unittest.main()
