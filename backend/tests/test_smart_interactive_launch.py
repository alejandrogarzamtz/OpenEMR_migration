import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi.testclient import TestClient

from app.main import app
from test_communications import create_patient, create_portal


FHIR_BASE="http://localhost:8000/fhir";REDIRECT="https://app.example.org/callback";VERIFIER="correct-verifier-value-with-at-least-forty-three-chars"


def pkce()->str:return base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


def staff(client:TestClient)->dict:
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];return {"Authorization":f"Bearer {token}"}


def authorize_request(client:TestClient,scopes:str,launch:str|None=None,client_id:str="interactive-test-app"):
    params={"response_type":"code","client_id":client_id,"redirect_uri":REDIRECT,"scope":scopes,"state":"opaque-client-state","aud":FHIR_BASE,"code_challenge":pkce(),"code_challenge_method":"S256","nonce":"openid-nonce"}
    if launch:params["launch"]=launch
    response=client.get("/oauth2/default/authorize",params=params,follow_redirects=False);assert response.status_code==303,response.text
    request_token=parse_qs(urlparse(response.headers["location"]).query)["request"][0];return request_token


def test_interactive_standalone_pkce_oidc_and_patient_compartment():
    with TestClient(app) as client:
        headers=staff(client)
        practitioner=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"SMART","last_name":"Clinician","email":"admin@example.com"});assert practitioner.status_code==201,practitioner.text
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Interactive","last_name":"Launch","date_of_birth":"1990-01-01","sex":"unknown"}).json();other=client.post("/api/v1/patients",headers=headers,json={"first_name":"Outside","last_name":"Context","date_of_birth":"1991-01-01","sex":"unknown"}).json()
        registration=client.post("/api/v1/admin/smart-clients",headers=headers,json={"name":"Interactive test app","client_id":"interactive-test-app","client_kind":"interactive","redirect_uris":[REDIRECT],"launch_uri":"https://app.example.org/launch","launch_types":["standalone","ehr","patient"],"allowed_scopes":["openid","fhirUser","launch","launch/patient","patient/Patient.rs","patient/Observation.rs"]});assert registration.status_code==201,registration.text
        discovery=client.get("/fhir/.well-known/smart-configuration").json();assert discovery["authorization_endpoint"].endswith("/authorize") and discovery["code_challenge_methods_supported"]==["S256"] and "sso-openid-connect" in discovery["capabilities"]
        scopes="openid fhirUser launch/patient patient/Patient.rs patient/Observation.rs";request_token=authorize_request(client,scopes)
        details=client.get(f"/oauth2/default/authorize/requests/{request_token}").json();assert details["client_name"]=="Interactive test app" and details["patient_context_required"] is True
        context=client.get(f"/oauth2/default/authorize/requests/{request_token}/context",headers=headers);assert context.status_code==200 and any(item["uuid"]==patient["uuid"] for item in context.json()["patients"])
        approved=client.post(f"/oauth2/default/authorize/requests/{request_token}/approve",headers=headers,json={"patient_uuid":patient["uuid"]});assert approved.status_code==200,approved.text
        callback=parse_qs(urlparse(approved.json()["redirect_to"]).query);assert callback["state"]==["opaque-client-state"];code=callback["code"][0]
        issued=client.post("/oauth2/default/token",data={"grant_type":"authorization_code","client_id":"interactive-test-app","code":code,"redirect_uri":REDIRECT,"code_verifier":VERIFIER});assert issued.status_code==200,issued.text
        payload=issued.json();assert payload["patient"]==patient["uuid"] and payload["expires_in"]<=300 and "id_token" in payload
        jwk=client.get("/oauth2/default/jwks").json()["keys"][0];identity=jwt.decode(payload["id_token"],jwt.PyJWK.from_dict(jwk).key,algorithms=["RS256"],audience="interactive-test-app",issuer=FHIR_BASE);assert identity["nonce"]=="openid-nonce" and identity["patient"]==patient["uuid"] and identity["fhirUser"].endswith(practitioner.json()["uuid"])
        smart={"Authorization":f"Bearer {payload['access_token']}"};assert client.get("/fhir/Patient",params={"_id":patient["uuid"]},headers=smart).json()["total"]==1
        assert client.get(f"/fhir/Patient/{other['uuid']}",headers=smart).status_code==403
        replay=client.post("/oauth2/default/token",data={"grant_type":"authorization_code","client_id":"interactive-test-app","code":code,"redirect_uri":REDIRECT,"code_verifier":VERIFIER});assert replay.status_code==400 and replay.json()["error"]=="invalid_grant"


def test_ehr_launch_is_one_time_and_binds_patient_context():
    with TestClient(app) as client:
        headers=staff(client);patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"EHR","last_name":"Context","date_of_birth":"1985-01-01","sex":"unknown"}).json()
        registration=client.post("/api/v1/admin/smart-clients",headers=headers,json={"name":"EHR launch app","client_id":"interactive-ehr-test","client_kind":"interactive","redirect_uris":[REDIRECT],"launch_uri":"https://app.example.org/launch","launch_types":["ehr"],"allowed_scopes":["launch","launch/patient","patient/Patient.rs"]});assert registration.status_code==201,registration.text
        launch=client.post("/api/v1/smart/launches",headers=headers,json={"client_id":"interactive-ehr-test","identity_kind":"staff","patient_uuid":patient["uuid"]});assert launch.status_code==200,launch.text
        assert "iss=" in launch.json()["launch_url"] and "launch=" in launch.json()["launch_url"]
        scopes="launch launch/patient patient/Patient.rs";request_token=authorize_request(client,scopes,launch.json()["launch"],"interactive-ehr-test")
        context=client.get(f"/oauth2/default/authorize/requests/{request_token}/context",headers=headers).json();assert context["fixed_patient"] is True and context["patients"]==[{"uuid":patient["uuid"],"name":"EHR Context"}]
        approved=client.post(f"/oauth2/default/authorize/requests/{request_token}/approve",headers=headers,json={});assert approved.status_code==200
        reused=client.get("/oauth2/default/authorize",params={"response_type":"code","client_id":"interactive-ehr-test","redirect_uri":REDIRECT,"scope":scopes,"state":"again","aud":FHIR_BASE,"code_challenge":pkce(),"code_challenge_method":"S256","launch":launch.json()["launch"]},follow_redirects=False);assert "error=invalid_request" in reused.headers["location"]


def test_patient_portal_launch_issues_patient_identity():
    with TestClient(app) as client:
        headers=staff(client);patient=create_patient(client,headers,"SmartPatient");portal=create_portal(client,headers,patient,"smart-patient-launch")
        registration=client.post("/api/v1/admin/smart-clients",headers=headers,json={"name":"Patient launch app","client_id":"interactive-patient-test","client_kind":"interactive","redirect_uris":[REDIRECT],"launch_uri":"https://app.example.org/patient-launch","launch_types":["patient"],"allowed_scopes":["openid","fhirUser","launch","launch/patient","patient/Patient.rs"]});assert registration.status_code==201,registration.text
        launch=client.post("/api/v1/smart/launches",headers=portal,json={"client_id":"interactive-patient-test","identity_kind":"portal","patient_uuid":patient["uuid"]});assert launch.status_code==200,launch.text
        scopes="openid fhirUser launch launch/patient patient/Patient.rs";request_token=authorize_request(client,scopes,launch.json()["launch"],"interactive-patient-test")
        context=client.get(f"/oauth2/default/authorize/requests/{request_token}/context",headers=portal);assert context.status_code==200 and context.json()["patients"]==[{"uuid":patient["uuid"],"name":"SmartPatient Portal"}]
        approved=client.post(f"/oauth2/default/authorize/requests/{request_token}/approve",headers=portal,json={});code=parse_qs(urlparse(approved.json()["redirect_to"]).query)["code"][0]
        issued=client.post("/oauth2/default/token",data={"grant_type":"authorization_code","client_id":"interactive-patient-test","code":code,"redirect_uri":REDIRECT,"code_verifier":VERIFIER});assert issued.status_code==200,issued.text
        body=issued.json();identity=jwt.decode(body["id_token"],jwt.PyJWK.from_dict(client.get("/oauth2/default/jwks").json()["keys"][0]).key,algorithms=["RS256"],audience="interactive-patient-test",issuer=FHIR_BASE);assert identity["sub"].startswith("portal:") and identity["fhirUser"].endswith(f"/Patient/{patient['uuid']}")
