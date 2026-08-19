"""
ad_auth.py
----------
Windows / Active Directory authentication for Plant Users, integrated
against Rane's internal "AD Login API" (see AD_Login_API.pdf, ISM_L01):

    1. GET  {AD_LOGIN_BASE_URL}/getaccesskey        -> RSA public key (XML)
    2. RSA-encrypt GenID + Password with that key (PKCS#1 v1.5, matching
       the .NET `RSACryptoServiceProvider.Encrypt(bytes, fOAEP=false)`
       reference implementation in the PDF).
    3. POST {AD_LOGIN_BASE_URL}/LoginWithEncryption  -> AD authenticates
       the GenID/Windows-password pair and returns the employee's profile
       (name, department, grade, company, location, manager, etc).

This module ONLY talks to the AD Login API and turns its response into a
plain Python dict, or raises `ADAuthError` / `ADServiceUnavailable`. It
never decides application role/plant/dashboard access — that mapping is
looked up locally afterwards (see auth_routes.ad_login) so existing
role-based access control, audit logging, and authorization are
untouched.

No AD credentials or tokens are ever logged. Only high-level outcomes
(success / failure / unavailable) are logged, keyed by a masked GenID —
never by password.
"""

import base64
import logging
import os
import re
import time

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.number import bytes_to_long

logger = logging.getLogger("digitaldrm.ad_auth")

# ── Configuration (see backend/.env.example) ────────────────────────────────
AD_LOGIN_BASE_URL = os.getenv(
    "AD_LOGIN_BASE_URL", "https://api.ranegroup.com/MasterApi/api"
).rstrip("/")
AD_PUBLIC_KEY_URL = os.getenv("AD_PUBLIC_KEY_URL", f"{AD_LOGIN_BASE_URL}/getaccesskey")
AD_LOGIN_URL = os.getenv("AD_LOGIN_URL", f"{AD_LOGIN_BASE_URL}/LoginWithEncryption")
AD_APPLICATION_NAME = os.getenv("AD_APPLICATION_NAME", "Digitalization_DigitalDRM2.o")
AD_LOGIN_ENABLED = os.getenv("AD_LOGIN_ENABLED", "true").lower() in ("1", "true", "yes")
AD_REQUEST_TIMEOUT = float(os.getenv("AD_REQUEST_TIMEOUT_SECONDS", "10"))

# The public key rarely (if ever) changes — cache it for a while so a
# normal login only needs one round trip to the AD API.
_PUBLIC_KEY_CACHE_SECONDS = int(os.getenv("AD_PUBLIC_KEY_CACHE_SECONDS", "3600"))
_public_key_cache: dict = {"xml": None, "fetched_at": 0.0}


class ADAuthError(Exception):
    """Raised for a definitive authentication failure (bad GenID/password
    or account issue reported by AD). Safe, generic message only —
    callers must not append any extra internal detail to this message."""


class ADServiceUnavailable(Exception):
    """Raised when the AD Login API itself could not be reached / errored
    (network, timeout, malformed response, RSA failure, etc). This is
    distinct from a bad-credential failure so the UI can tell the user
    the service is down rather than implying their password is wrong."""


def _mask_genid(genid: str) -> str:
    """For log lines only — never log a password, and don't log the full
    GenID string either, out of caution."""
    if not genid:
        return "<empty>"
    if len(genid) <= 2:
        return "*" * len(genid)
    return genid[:2] + "*" * (len(genid) - 2)


def _fetch_public_key() -> str:
    now = time.time()
    if (
        _public_key_cache["xml"]
        and now - _public_key_cache["fetched_at"] < _PUBLIC_KEY_CACHE_SECONDS
    ):
        return _public_key_cache["xml"]

    try:
        resp = requests.get(AD_PUBLIC_KEY_URL, timeout=AD_REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.error("[AD_AUTH] Failed to fetch AD public key: %s", exc)
        raise ADServiceUnavailable("Could not reach the authentication service.") from exc

    try:
        if payload.get("IsError"):
            raise ValueError(payload.get("Messages") or "IsError=true")
        items = payload["Item"]
        public_key_xml = items[0]["PUBLICKEY"]
        if not public_key_xml:
            raise ValueError("empty PUBLICKEY")
    except Exception as exc:
        logger.error("[AD_AUTH] Unexpected getaccesskey response shape: %s", exc)
        raise ADServiceUnavailable("Authentication service returned an unexpected response.") from exc

    _public_key_cache["xml"] = public_key_xml
    _public_key_cache["fetched_at"] = now
    return public_key_xml


_MODULUS_RE = re.compile(r"<Modulus>(.*?)</Modulus>")
_EXPONENT_RE = re.compile(r"<Exponent>(.*?)</Exponent>")


def _build_rsa_key(public_key_xml: str) -> RSA.RsaKey:
    """Parses the <RSAKeyValue> XML from getaccesskey and builds an RSA
    public key object — equivalent to `rsa1.FromXmlString(publickeyval)`
    in the .NET reference code."""
    mod_match = _MODULUS_RE.search(public_key_xml)
    exp_match = _EXPONENT_RE.search(public_key_xml)
    if not mod_match or not exp_match:
        raise ADServiceUnavailable("Authentication service returned an invalid key.")

    modulus_bytes = base64.b64decode(mod_match.group(1))
    exponent_bytes = base64.b64decode(exp_match.group(1))

    n = bytes_to_long(modulus_bytes)
    e = bytes_to_long(exponent_bytes)
    return RSA.construct((n, e))


def _rsa_encrypt(rsa_key: RSA.RsaKey, plaintext: str) -> str:
    """PKCS#1 v1.5 RSA encryption, Base64-encoded — matches
    `rsa1.Encrypt(textBytes, false)` in the .NET reference code and the
    OPENSSL_PKCS1_PADDING PHP reference in the PDF."""
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")

'''import re

def normalize_genid(genid: str) -> str:
    genid = (genid or "").strip()

    if not genid:
        return genid

    # 1-6 digits only -> prepend 'c'
    if re.fullmatch(r"\d{1,6}", genid):
        return f"c{genid}"

    # c/C followed by 1-6 digits
    if re.fullmatch(r"[cC]\d{1,6}", genid):
        return genid.lower()

    raise ADAuthError(
        "GEN ID must be up to 6 digits (e.g. 103191) or c followed by up to 6 digits (e.g. c103191)."
    )''''
def authenticate(
    genid: str,
    password: str,
    *,
    mobile_no: str = "",
    ip_address: str = "",
    mac_id: str = "",
    geo: str = "",
    unique_device_id: str = "",
    device_type: str = "Web",
) -> dict:
    """
    Authenticates `genid`/`password` against Active Directory via the AD
    Login API and returns the AD profile dict (genid, name, role,
    mailid, companyname, locationname, department, grade, ManagerId,
    reporting_name, Tokenid, ...) on success.

    Raises:
        ADAuthError            - AD rejected the credentials (bad GenID
                                  or password, locked/disabled account).
        ADServiceUnavailable   - The AD Login API could not be reached
                                  or returned something we can't parse.
    """
    if not AD_LOGIN_ENABLED:
        raise ADServiceUnavailable("AD authentication is not enabled on this server.")

    

    if not genid or not password:
        raise ADAuthError("GEN ID and password are required.")

    public_key_xml = _fetch_public_key()

    try:
        rsa_key = _build_rsa_key(public_key_xml)
        enc_genid = _rsa_encrypt(rsa_key, genid)
        enc_password = _rsa_encrypt(rsa_key, password)
    except ADServiceUnavailable:
        raise
    except Exception as exc:
        logger.error("[AD_AUTH] RSA encryption failed for %s: %s", _mask_genid(genid), exc)
        raise ADServiceUnavailable("Could not prepare secure login request.") from exc

    body = {
        "GenID": enc_genid,
        "Password": enc_password,
        "MobileNo": mobile_no or "",
        "IPAddress": ip_address or "",
        "MACID": mac_id or "",
        "Geo": geo or "",
        "UniqueDeviceId": unique_device_id or "",
        "DeviceType": device_type or "Web",
        "ApplicationName":"Digitalization_DigitalDRM2.o",
    }

    try:
        resp = requests.post(
            AD_LOGIN_URL,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=AD_REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        logger.error("[AD_AUTH] Network error calling AD Login API for %s: %s", _mask_genid(genid), exc)
        raise ADServiceUnavailable("Could not reach the authentication service.") from exc

    if resp.status_code >= 500:
        logger.error("[AD_AUTH] AD Login API returned %s for %s", resp.status_code, _mask_genid(genid))
        raise ADServiceUnavailable("Authentication service error.")

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.error("[AD_AUTH] Non-JSON response from AD Login API for %s: %s", _mask_genid(genid), exc)
        raise ADServiceUnavailable("Authentication service returned an unexpected response.") from exc

    is_error = payload.get("IsError")
    items = payload.get("Item") or []

    if is_error or not items:
        messages = payload.get("Messages")
        logger.info("[AD_AUTH] Login rejected by AD for %s (Messages=%s)", _mask_genid(genid), messages)
        raise ADAuthError("Invalid GEN ID or password.")

    profile = dict(items[0])
    logger.info("[AD_AUTH] Login accepted by AD for %s", _mask_genid(genid))
    return profile