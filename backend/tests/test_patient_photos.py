from fastapi.testclient import TestClient

from app.main import app
from app.import_legacy import legacy_image
from test_communications import create_patient, staff_headers

PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"
JPEG = b"\xff\xd8\xff\xe0" + b"new-image"


def test_legacy_photo_detection_accepts_raw_and_base64_but_not_declared_type_only():
    import base64
    assert legacy_image(PNG) == (PNG,"image/png")
    assert legacy_image(base64.b64encode(JPEG).decode()) == (JPEG,"image/jpeg")
    assert legacy_image("not image data") is None


def test_patient_photos_are_private_versioned_validated_and_audited():
    with TestClient(app) as client:
        staff=staff_headers(client); patient=create_patient(client,staff,"PhotoOne"); other=create_patient(client,staff,"PhotoTwo")
        invalid=client.post(f"/api/v1/patients/{patient['uuid']}/photos",headers=staff,files={"file":("bad.png",b"not-an-image","image/png")})
        assert invalid.status_code==415
        first=client.post(f"/api/v1/patients/{patient['uuid']}/photos",headers=staff,files={"file":("first.txt",PNG,"text/plain")})
        assert first.status_code==201 and first.json()["mime_type"]=="image/png" and first.json()["is_primary"]
        second=client.post(f"/api/v1/patients/{patient['uuid']}/photos",headers=staff,files={"file":("second.jpg",JPEG,"image/jpeg")})
        assert second.status_code==201 and second.json()["is_primary"]
        rows=client.get(f"/api/v1/patients/{patient['uuid']}/photos",headers=staff).json()
        assert len(rows)==2 and sum(row["is_primary"] for row in rows)==1
        assert client.get(f"/api/v1/patients/{other['uuid']}/photos/{second.json()['uuid']}/content",headers=staff).status_code==404
        content=client.get(f"/api/v1/patients/{patient['uuid']}/photos/{second.json()['uuid']}/content",headers=staff)
        assert content.content==JPEG and content.headers["cache-control"]=="private, no-store" and content.headers["x-content-type-options"]=="nosniff"
        inactive=client.post(f"/api/v1/patients/{patient['uuid']}/photos/{second.json()['uuid']}/inactivate",headers=staff,json={"reason":"Updated portrait"})
        assert inactive.status_code==200 and not inactive.json()["active"]
        rows=client.get(f"/api/v1/patients/{patient['uuid']}/photos",headers=staff).json()
        assert next(row for row in rows if row["uuid"]==first.json()["uuid"])["is_primary"]
        assert client.post(f"/api/v1/patients/{patient['uuid']}/photos/{second.json()['uuid']}/primary",headers=staff).status_code==409
