"""OIDC signing material for SMART interactive launches."""
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..config import settings


@lru_cache
def signing_key():
    if settings.smart_oidc_private_key_path:
        raw=Path(settings.smart_oidc_private_key_path).read_bytes()
        key=serialization.load_pem_private_key(raw,password=None)
        if not isinstance(key,rsa.RSAPrivateKey) or key.key_size<2048:
            raise RuntimeError("SMART OIDC requires an RSA private key of at least 2048 bits")
        return key
    if settings.deployment_environment=="production":
        raise RuntimeError("SMART_OIDC_PRIVATE_KEY_PATH is required in production")
    return rsa.generate_private_key(public_exponent=65537,key_size=3072)


def public_jwk()->dict:
    value=jwt.algorithms.RSAAlgorithm.to_jwk(signing_key().public_key(),as_dict=True)
    return {**value,"kid":settings.smart_oidc_key_id,"use":"sig","alg":"RS256"}


def encode_id_token(claims:dict)->str:
    return jwt.encode(claims,signing_key(),algorithm="RS256",headers={"kid":settings.smart_oidc_key_id,"typ":"JWT"})
