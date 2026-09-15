# OpenRM Python extension SDK

This dependency-free SDK implements the OpenRM extension credential, event
publication, and webhook verification contracts.

```bash
python -m pip install ./sdk/python
```

```python
from openrm_extension import ExtensionClient, verify_webhook

client = ExtensionClient("https://openrm.example.org", credential)
client.publish(
    "extension.lab-bridge.result-ready",
    {"external_id": "42"},
    resource_type="DiagnosticReport",
    resource_id="external-42",
)

# In the receiving framework, pass the unmodified request bytes and headers.
event = verify_webhook(raw_body, request_headers, webhook_secret, seen=already_seen)
```

Persist every `OpenRM-Webhook-Id` before applying side effects and provide a
`seen` callback so retries cannot repeat them. Keep extension credentials and
webhook secrets in a secret manager; OpenRM displays both only when issued.
