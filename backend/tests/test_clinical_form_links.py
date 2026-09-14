from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_clinical_form_links_are_patient_scoped_audited_unique_and_locked():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Linked","last_name":"Note","date_of_birth":"1980-01-02","sex":"unknown"}).json()
        other=client.post("/api/v1/patients",headers=headers,json={"first_name":"Other","last_name":"Patient","date_of_birth":"1981-02-03","sex":"unknown"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-14T12:00:00Z"}).json()
        form=client.post(f"/api/v1/patients/{patient['uuid']}/clinical-forms",headers=headers,json={"encounter_uuid":encounter["uuid"],"form_type":"soap","title":"Linked evidence","content":{"assessment":"Evidence reviewed"}}).json()
        document=client.post(f"/api/v1/patients/{patient['uuid']}/documents",headers=headers,files={"file":("scan.txt",b"scan","text/plain")}).json()
        other_document=client.post(f"/api/v1/patients/{other['uuid']}/documents",headers=headers,files={"file":("other.txt",b"other","text/plain")}).json()
        order=client.post(f"/api/v1/patients/{patient['uuid']}/lab-orders",headers=headers,json={"ordered_at":"2026-09-14T12:00:00Z","code":"718-7","name":"Hemoglobin"}).json()
        result=client.post(f"/api/v1/lab-orders/{order['uuid']}/results",headers=headers,json={"observed_at":"2026-09-14T13:00:00Z","code":"718-7","name":"Hemoglobin","value":"13.4","unit":"g/dL"}).json()
        base=f"/api/v1/patients/{patient['uuid']}/clinical-forms/{form['uuid']}"
        assert client.post(f"{base}/documents/{other_document['uuid']}",headers=headers).status_code==404
        linked=client.post(f"{base}/documents/{document['uuid']}",headers=headers)
        assert linked.status_code==201 and linked.json()["documents"][0]["label"]=="scan.txt"
        assert client.post(f"{base}/documents/{document['uuid']}",headers=headers).status_code==409
        linked=client.post(f"{base}/results/{result['uuid']}",headers=headers)
        assert linked.status_code==201 and "13.4 g/dL" in linked.json()["results"][0]["label"]
        assert client.get(f"{base}/links",headers=headers).json()==linked.json()
        assert client.delete(f"{base}/documents/{document['uuid']}",headers=headers).status_code==204
        assert client.post(f"{base}/documents/{document['uuid']}",headers=headers).status_code==201
        signed=client.post(f"{base}/sign",headers=headers,json={"password":"change-me-now","lock":True,"attestation":"I attest that this clinical record is accurate and complete."})
        assert signed.status_code==201
        signatures=client.get(f"{base}/signatures",headers=headers)
        assert signatures.status_code==200 and signatures.json()[0]["integrity_valid"] is True
        assert client.delete(f"{base}/results/{result['uuid']}",headers=headers).status_code==423
        with SessionLocal() as db:
            actions=set(db.scalars(select(AuditEvent.action).where(AuditEvent.resource_id==form["uuid"])))
            assert actions >= {"link","unlink","read","sign"}
