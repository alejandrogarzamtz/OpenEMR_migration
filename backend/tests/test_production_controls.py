from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def production_values(tmp_path:Path)->dict:
    key=tmp_path/"oidc.pem";key.write_text("placeholder");key.chmod(0o600)
    return {"deployment_environment":"production","database_url":"postgresql+psycopg://user:password@db/openrm","jwt_secret":"a"*64,"mfa_encryption_key":Fernet.generate_key().decode(),"secure_cookies":True,"public_web_url":"https://ehr.example.org","api_public_url":"https://api.example.org","cors_origins":"https://ehr.example.org","allowed_hosts":"ehr.example.org,api.example.org","smart_oidc_private_key_path":str(key),"bootstrap_admin_email":None,"bootstrap_admin_password":None}


def test_production_configuration_is_fail_closed(tmp_path):
    values=production_values(tmp_path);configured=Settings(_env_file=None,**values)
    assert configured.allowed_host_list==["ehr.example.org","api.example.org"]
    with pytest.raises(ValueError,match="SECURE_COOKIES"):Settings(_env_file=None,**{**values,"secure_cookies":False})
    with pytest.raises(ValueError,match="bootstrap administrator"):Settings(_env_file=None,**{**values,"bootstrap_admin_email":"admin@example.org","bootstrap_admin_password":"secret"})
    with pytest.raises(ValueError,match="explicit HTTPS"):Settings(_env_file=None,**{**values,"cors_origins":"*"})


def test_health_and_security_headers():
    with TestClient(app) as client:
        response=client.get("/health/ready")
        assert response.status_code==200 and response.json()["checks"]=={"database":True,"schema":True,"signing_key":True}
        assert response.headers["x-content-type-options"]=="nosniff" and response.headers["x-frame-options"]=="DENY"
        assert response.headers["cache-control"]=="no-store" and "strict-transport-security" not in response.headers
        oversized=client.post("/api/v1/auth/token",headers={"Content-Length":str(26*1024*1024)},content=b"{}")
        assert oversized.status_code==413
