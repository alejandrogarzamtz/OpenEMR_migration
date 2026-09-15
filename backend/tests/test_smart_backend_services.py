import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import app


ASSERTION_TYPE="urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
TOKEN_URL="http://localhost:8000/oauth2/default/token"


def encoded(value:int)->str:
    raw=value.to_bytes((value.bit_length()+7)//8,"big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def assertion(private_key,client_id:str,kid:str,jti:str|None=None)->str:
    now=datetime.now(timezone.utc)
    return jwt.encode({"iss":client_id,"sub":client_id,"aud":TOKEN_URL,"iat":now,"exp":now+timedelta(minutes=4),"jti":jti or str(uuid4())},private_key,algorithm="RS384",headers={"kid":kid})


def test_smart_backend_discovery_scopes_replay_introspection_and_revocation():
    private_key=rsa.generate_private_key(public_exponent=65537,key_size=2048);numbers=private_key.public_key().public_numbers();kid="backend-test-key"
    jwks={"keys":[{"kty":"RSA","kid":kid,"use":"sig","alg":"RS384","n":encoded(numbers.n),"e":encoded(numbers.e)}]}
    with TestClient(app) as client:
        discovery=client.get("/fhir/.well-known/smart-configuration")
        assert discovery.status_code==200 and discovery.json()["token_endpoint"]==TOKEN_URL
        assert "client-confidential-asymmetric" in discovery.json()["capabilities"]
        admin_token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];admin={"Authorization":f"Bearer {admin_token}"}
        registration=client.post("/api/v1/admin/smart-clients",headers=admin,json={"name":"Population reader","client_id":"population-reader","jwks":jwks,"allowed_scopes":["system/Patient.rs"]})
        assert registration.status_code==201,registration.text
        patient=client.post("/api/v1/patients",headers=admin,json={"first_name":"SMART","last_name":"Reader","date_of_birth":"1990-01-01","sex":"unknown"}).json()
        first_assertion=assertion(private_key,"population-reader",kid,"one-time-jti")
        form={"grant_type":"client_credentials","scope":"system/Patient.rs","client_assertion_type":ASSERTION_TYPE,"client_assertion":first_assertion}
        issued=client.post("/oauth2/default/token",data=form)
        assert issued.status_code==200,issued.text
        payload=issued.json();assert payload["token_type"]=="Bearer" and payload["expires_in"]<=300 and payload["scope"]=="system/Patient.rs"
        smart={"Authorization":f"Bearer {payload['access_token']}"}
        patients=client.get("/fhir/Patient?family=Reader",headers=smart);assert patients.status_code==200 and patients.json()["total"]==1
        denied=client.get(f"/fhir/Observation?patient={patient['uuid']}",headers=smart);assert denied.status_code==403 and denied.json()["detail"]["resourceType"]=="OperationOutcome"
        assert client.get("/api/v1/reports",headers=smart).status_code==403
        replay=client.post("/oauth2/default/token",data=form);assert replay.status_code==401 and replay.json()["error"]=="invalid_client"
        introspection_assertion=assertion(private_key,"population-reader",kid)
        inspected=client.post("/oauth2/default/introspect",data={"token":payload["access_token"],"client_assertion_type":ASSERTION_TYPE,"client_assertion":introspection_assertion})
        assert inspected.json()["active"] is True and inspected.json()["client_id"]=="population-reader"
        revoke_assertion=assertion(private_key,"population-reader",kid)
        revoked=client.post("/oauth2/default/revoke",data={"token":payload["access_token"],"client_assertion_type":ASSERTION_TYPE,"client_assertion":revoke_assertion});assert revoked.status_code==200
        assert client.get("/fhir/Patient?family=Reader",headers=smart).status_code==401
        final_assertion=assertion(private_key,"population-reader",kid)
        final=client.post("/oauth2/default/introspect",data={"token":payload["access_token"],"client_assertion_type":ASSERTION_TYPE,"client_assertion":final_assertion});assert final.json()=={"active":False}


def test_smart_registration_and_requested_scope_are_bounded():
    private_key=rsa.generate_private_key(public_exponent=65537,key_size=2048);numbers=private_key.public_key().public_numbers();kid="bounded-key";jwks={"keys":[{"kty":"RSA","kid":kid,"alg":"RS384","n":encoded(numbers.n),"e":encoded(numbers.e)}]}
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];admin={"Authorization":f"Bearer {token}"}
        invalid=client.post("/api/v1/admin/smart-clients",headers=admin,json={"name":"Writer","jwks":jwks,"allowed_scopes":["system/Patient.cud"]});assert invalid.status_code==422
        private_jwks={"keys":[{**jwks["keys"][0],"d":"private-material"}]};private=client.post("/api/v1/admin/smart-clients",headers=admin,json={"name":"Private key","jwks":private_jwks,"allowed_scopes":["system/Patient.r"]});assert private.status_code==422
        created=client.post("/api/v1/admin/smart-clients",headers=admin,json={"name":"Patient only","client_id":"patient-only-reader","jwks":jwks,"allowed_scopes":["system/Patient.r"]});assert created.status_code==201
        response=client.post("/oauth2/default/token",data={"grant_type":"client_credentials","scope":"system/Observation.r","client_assertion_type":ASSERTION_TYPE,"client_assertion":assertion(private_key,"patient-only-reader",kid)})
        assert response.status_code==400 and response.json()["error"]=="invalid_scope"
