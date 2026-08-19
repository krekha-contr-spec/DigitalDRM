"""
ad_auth_service.py
--------------------
Windows / Active Directory login for DigitalDRM, covering every plant,
implemented against Rane's internal "AD Login API" (SOP ISM_L01,
"AD Login API", v2.5). A user's company GEN ID + Windows/Domain
password are authenticated by that corporate API — this app never
talks to LDAP/AD directly and never sees or stores a domain password.

Flow (per the SOP)
--------------------
1. GET  {AD_BASE_URL}/getaccesskey        -> RSA public key (XML RSAKeyValue)
2. RSA-encrypt (PKCS#1 v1.5) the GenID and Password with that key
3. POST {AD_BASE_URL}/LoginWithEncryption -> user record (name, mailid,
   department, role, ...) if the domain credentials are valid

Investigation note (HTTP 200 + Messages: "InValid Credentials")
-------------------------------------------------------------------
The RSA encryption path itself was verified byte-for-byte correct via a
round-trip self-test (generate a keypair, build the exact SOP XML shape,
parse it with _rsa_public_key_from_xml, encrypt with _rsa_encrypt,
decrypt with the private key using PKCS#1 v1.5 — plaintext matches).
So a wrong GenID/Password is genuinely possible, but two other things in
the original implementation could ALSO produce this exact symptom and
were fixed here:

  1. The public key was cached for 30 minutes. If Rane's AD service
     rotates its RSA keypair more often than that (common for a shared
     "getaccesskey" endpoint), a request encrypted with a stale cached
     key decrypts to garbage server-side — which looks exactly like
     "invalid credentials" from this app's point of view, even though
     nothing about the login attempt itself was wrong. Fixed by fetching
     a fresh key on every login attempt (AD_PUBLIC_KEY_CACHE_SECONDS=0
     by default — configurable via env if Rane confirms the key is
     stable and caching is safe to re-enable).

  2. ApplicationName was hardcoded to "DigitalDRM". The SOP's own sample
     payloads use two DIFFERENT registered values ("XXXX" as a
     placeholder, "HCM_PS" in the real screenshot) — strongly suggesting
     ApplicationName must be a value Rane's IS team has pre-registered
     for this specific calling application, not an arbitrary string. If
     "DigitalDRM" was never registered, the AD API may reject even
     perfectly correct credentials this same way. Fixed by making this
     configurable via AD_APPLICATION_NAME (env var) instead of hardcoded,
     and logging the exact value sent on every attempt — confirm the
     correct registered name with Rane's IS team (ISM_L01 preparer/
     approver) and set it via that env var without a code change.

Every request/response is now logged in detail (never the raw password —
see log_ad_attempt_details below) specifically so the next occurrence of
this symptom can be diagnosed from server logs alone.

Plant / Department / Role mapping
------------------------------------
The AD API only proves WHO someone is (their corporate identity) — it
does not know anything about DigitalDRM's plants or departments. Once
AD confirms identity, resolve_plant_department_role() maps that person
to a Plant/Department/Role using the SAME Data Entry Users (role_access)
table the Admin Dashboard already manages — the person's AD email
(mailid) is matched against role_access.email for the target plant. A
person who authenticates successfully with AD but isn't provisioned in
role_access for that plant is still refused: valid domain credentials
alone are not enough to grant app access.

Error handling
---------------
AdAuthError    -> AD rejected the credentials (or returned no user).
AdServiceError -> the AD service itself couldn't be reached, or its
                  response was malformed (network/timeout/bad payload).
Callers MUST show the exact same generic message to the end user for
both, and for "no plant mapping" — the specific reason is only ever
recorded server-side via login_audit_service / this module's logger,
never surfaced to the person logging in.
"""

import base64
import logging
import os
import re
import threading
import time
import uuid
from typing import Optional

import requests
import defusedxml.ElementTree as DefusedET
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy.orm import Session

logger = logging.getLogger("digitaldrm.ad_auth")

AD_BASE_URL = os.getenv("AD_BASE_URL", "https://api.ranegroup.com/MasterApi/api")
PUBLIC_KEY_URL = f"{AD_BASE_URL}/getaccesskey"
LOGIN_URL = f"{AD_BASE_URL}/LoginWithEncryption"

REQUEST_TIMEOUT_SECONDS = 10

# Set to 0 (the default) after investigating an "AD returns HTTP 200 but
# rejects valid-looking credentials" issue that a stale cached key could
# explain — see the module docstring. Raise this back up (e.g. 1800 for
# 30 minutes) via the AD_PUBLIC_KEY_CACHE_SECONDS env var only once it's
# confirmed the key doesn't rotate faster than that.
_PUBLIC_KEY_CACHE_SECONDS = int(os.getenv("AD_PUBLIC_KEY_CACHE_SECONDS", "0"))

# Per the SOP, ApplicationName must be a value Rane's IS team has
# pre-registered for this calling application — see the investigation
# note above. Override via env var once the correct value is confirmed.
AD_APPLICATION_NAME = os.getenv("AD_APPLICATION_NAME", "Digitalization_DigitalDRM2.o")
AD_DEVICE_TYPE = os.getenv("AD_DEVICE_TYPE", "Web")  # SOP enum: Android | Apple | Web

# This AD integration covers every plant. A person's Plant/Department/
# Role is resolved dynamically from whichever plant(s)/department(s)
# they're actually provisioned for (see resolve_plant_department_role
# below) — there is no fixed default plant anymore.


class AdAuthError(Exception):
    """AD rejected the GenID/Password, or returned no matching user."""


class AdServiceError(Exception):
    """The AD login service could not be reached, timed out, or returned
    something this app couldn't parse."""


_cache_lock = threading.Lock()
_cached_public_key = None
_cached_at = 0.0


def _fetch_public_key_xml() -> str:
    try:
        started = time.monotonic()
        resp = requests.get(PUBLIC_KEY_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        logger.info(
            "[AD getaccesskey] url=%s status=%s elapsed_ms=%s",
            PUBLIC_KEY_URL, resp.status_code, elapsed_ms,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("[AD getaccesskey] request failed: %s", exc, exc_info=True)
        raise AdServiceError(f"Could not reach AD key service: {exc}")

    if data.get("IsError"):
        logger.error("[AD getaccesskey] IsError=true Messages=%r", data.get("Messages"))
        raise AdServiceError(f"AD key service returned an error: {data.get('Messages')}")

    items = data.get("Item") or []
    if not items or not items[0].get("PUBLICKEY"):
        logger.error("[AD getaccesskey] response had no Item[0].PUBLICKEY: %r", data)
        raise AdServiceError("AD key service returned no public key.")

    return items[0]["PUBLICKEY"]


def _rsa_public_key_from_xml(xml_str: str):
    """Parses the .NET RSAKeyValue XML format (<Modulus>/<Exponent>,
    both base64) into a cryptography RSAPublicKey — the same key shape
    LoginWithEncryption expects to have been used for encryption.
    Uses defusedxml since this XML comes from an external HTTP response."""
    root = DefusedET.fromstring(xml_str)
    modulus_el = root.find("Modulus")
    exponent_el = root.find("Exponent")
    if modulus_el is None or exponent_el is None or not modulus_el.text or not exponent_el.text:
        raise AdServiceError("AD public key XML is missing Modulus/Exponent.")

    n = int.from_bytes(base64.b64decode(modulus_el.text), "big")
    e = int.from_bytes(base64.b64decode(exponent_el.text), "big")
    logger.info(
        "[AD getaccesskey] parsed public key: modulus_bits=%s exponent=%s",
        n.bit_length(), e,
    )
    return rsa.RSAPublicNumbers(e, n).public_key()


def _get_public_key(force_refresh: bool = False):
    global _cached_public_key, _cached_at

    with _cache_lock:
        if (
            not force_refresh
            and _PUBLIC_KEY_CACHE_SECONDS > 0
            and _cached_public_key is not None
            and (time.time() - _cached_at) < _PUBLIC_KEY_CACHE_SECONDS
        ):
            logger.info(
                "[AD getaccesskey] using cached public key (age=%.0fs, ttl=%ss)",
                time.time() - _cached_at, _PUBLIC_KEY_CACHE_SECONDS,
            )
            return _cached_public_key

        xml_str = _fetch_public_key_xml()
        key = _rsa_public_key_from_xml(xml_str)
        _cached_public_key = key
        _cached_at = time.time()
        return key


def _rsa_encrypt(public_key, plaintext: str) -> str:
    """PKCS#1 v1.5 encryption + base64 — matches the SOP's .NET
    `rsa1.Encrypt(textBytes, false)` (fOAEP=false) and PHP
    OPENSSL_PKCS1_PADDING reference implementations exactly. Verified
    with a round-trip self-test against a locally generated keypair —
    see the module docstring."""
    ciphertext = public_key.encrypt(plaintext.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(ciphertext).decode("ascii")


# Every sample GenID in the SOP (ISM_L01) is purely numeric — "15660",
# "03186", "16334", "15826". A Windows/domain username often looks like
# "C102641" (a letter prefix + digits) instead, which is a DIFFERENT
# value from the numeric "GenID" this API expects. If someone naturally
# types their Windows username here, a real attempt failed exactly this
# way (IsError=true, Messages="InValid Credentials", both requests
# otherwise well-formed) with gen_id="c103191". This pattern catches
# that shape so ad_login() can automatically retry with the digits only.
_LETTER_PREFIXED_GEN_ID_RE = re.compile(r"^[A-Za-z](\d{3,})$")


def ad_login(gen_id: str, password: str, ip_address: Optional[str] = None) -> dict:
    """
    Authenticates gen_id/password against Rane's AD Login API. Returns
    the user record (dict with genid, name, mailid, department, role,
    ...) on success. Raises AdAuthError or AdServiceError on failure —
    see module docstring for how callers must handle these.

    Every attempt is logged in detail (request shape, response status,
    the parsed IsError/Messages/Item-count) so a failure can be
    diagnosed from server logs alone — the password itself and the RSA-
    encrypted ciphertexts are NEVER logged, only which fields were sent
    and their non-secret values (MobileNo, IPAddress, DeviceType, etc).

    If gen_id looks like a letter-prefixed Windows username (e.g.
    "c103191") and the first attempt is rejected, automatically retries
    ONCE with just the digits ("103191") before giving up — see
    _LETTER_PREFIXED_GEN_ID_RE above. This never happens more than once
    per login, and only when the shape actually matches, so it can't
    turn into a password-guessing loop against a real account.
    """
    attempt_id = uuid.uuid4().hex[:8]  # ties every log line for this login together
    logger.info("[AD login %s] attempt starting | gen_id=%s", attempt_id, gen_id)

    try:
        return _ad_login_attempt(gen_id, password, ip_address, attempt_id)
    except AdAuthError as first_error:
        match = _LETTER_PREFIXED_GEN_ID_RE.match(gen_id)
        if not match:
            raise

        digits_only = match.group(1)
        logger.warning(
            "[AD login %s] gen_id=%s was rejected; it looks like a letter-prefixed Windows username "
            "rather than the SOP's numeric GenID format — retrying once with the digits only (%s)",
            attempt_id, gen_id, digits_only,
        )
        try:
            result = _ad_login_attempt(digits_only, password, ip_address, attempt_id)
            logger.info(
                "[AD login %s] retry with numeric-only GenID (%s) SUCCEEDED where '%s' failed — "
                "this confirms the numeric GenID (without the letter prefix) is what this API expects.",
                attempt_id, digits_only, gen_id,
            )
            return result
        except AdAuthError:
            # Neither variant worked — surface the ORIGINAL error/message,
            # since that's what the person actually typed.
            raise first_error


def _ad_login_attempt(gen_id: str, password: str, ip_address: Optional[str], attempt_id: str) -> dict:
    """One single GenID/Password round-trip against LoginWithEncryption.
    Raises AdAuthError (rejected) or AdServiceError (unreachable/malformed).
    Factored out so ad_login() can retry with a normalized GenID without
    duplicating the request-building/logging logic."""
    try:
        public_key = _get_public_key()
    except AdServiceError:
        # The cached key might be stale (rotated server-side) — try one
        # forced refresh before giving up entirely. With caching disabled
        # by default (see _PUBLIC_KEY_CACHE_SECONDS) this only matters if
        # an admin has re-enabled caching via env var.
        logger.warning("[AD login %s] public key fetch failed once, forcing refresh and retrying", attempt_id)
        public_key = _get_public_key(force_refresh=True)

    encrypted_gen_id = _rsa_encrypt(public_key, gen_id)
    encrypted_password = _rsa_encrypt(public_key, password)

    # Per SOP: MobileNo/MACID/Geo/UniqueDeviceId are required Text
    # parameters. A browser-based "Web" login can't reliably supply real
    # device/location values (no MAC access, no silent geolocation), so
    # well-formed placeholders are sent rather than empty strings — in
    # case the AD API's own validation rejects blank fields the same way
    # it reports bad credentials (same "InValid Credentials" symptom).
    device_id = f"web-{uuid.uuid4().hex}"
    payload = {
        "GenID": encrypted_gen_id,
        "Password": encrypted_password,
        "MobileNo": "0000000000",
        "IPAddress": ip_address or "0.0.0.0",
        "MACID": "00:00:00:00:00:00",
        "Geo": "0,0",
        "UniqueDeviceId": device_id,
        "DeviceType": AD_DEVICE_TYPE,
        "ApplicationName": AD_APPLICATION_NAME,
    }

    logger.info(
        "[AD login %s] POST %s | gen_id_variant=%s ApplicationName=%s DeviceType=%s IPAddress=%s "
        "UniqueDeviceId=%s (GenID/Password sent RSA-encrypted, not logged)",
        attempt_id, LOGIN_URL, gen_id, AD_APPLICATION_NAME, AD_DEVICE_TYPE,
        payload["IPAddress"], device_id,
    )

    try:
        started = time.monotonic()
        resp = requests.post(
            LOGIN_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        logger.info(
            "[AD login %s] response status=%s elapsed_ms=%s", attempt_id, resp.status_code, elapsed_ms,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("[AD login %s] request failed: %s", attempt_id, exc, exc_info=True)
        raise AdServiceError(f"Could not reach AD login service: {exc}")

    is_error = data.get("IsError")
    messages = data.get("Messages")
    items = data.get("Item") or []
    logger.info(
        "[AD login %s] parsed response | IsError=%s Messages=%r item_count=%s",
        attempt_id, is_error, messages, len(items),
    )

    if is_error:
        logger.warning(
            "[AD login %s] REJECTED (IsError=true) | gen_id_variant=%s | Messages=%r",
            attempt_id, gen_id, messages,
        )
        raise AdAuthError(str(messages or "AD login rejected the credentials."))

    if not items:
        logger.warning(
            "[AD login %s] REJECTED (IsError=false but Item is empty — AD's own signal for invalid "
            "credentials in this API) | gen_id=%s | Messages=%r | "
            "If this GenID/password pair is believed correct, check: (1) AD_APPLICATION_NAME=%r is the "
            "value actually registered for this app with Rane's IS team (SOP ISM_L01), (2) the public key "
            "wasn't stale (caching is %s), (3) GenID is the numeric company ID, not an email/username.",
            attempt_id, gen_id, messages, AD_APPLICATION_NAME,
            "disabled" if _PUBLIC_KEY_CACHE_SECONDS == 0 else f"enabled, ttl={_PUBLIC_KEY_CACHE_SECONDS}s",
        )
        raise AdAuthError(str(messages or "AD login returned no user record."))

    logger.info("[AD login %s] SUCCESS | gen_id=%s | mailid=%s", attempt_id, gen_id, items[0].get("mailid"))
    return items[0]


def resolve_plant_department_role(db: Session, email: str) -> Optional[dict]:
    """
    Maps an AD-authenticated person to a Plant/Department/Role. Checked
    in this order, across ALL plants (no hardcoded plant) — the first
    match wins:

      1. President   (email_recipients, recipient_type="president",
                       plant_id IS NULL — a President is global) ->
                       role="president", plant_id=None, full access to
                       every plant's Overall Summary and every plant's
                       department drill-down.
      2. Plant Head   (email_recipients, recipient_type="plant_head",
                       matched to ONE specific plant_id) ->
                       role="plant", that plant_id only, full access to
                       every department within that plant.
      3. Staff Incharge (role_access — the Data Entry Users table the
                       Admin Dashboard manages, matched to ONE specific
                       plant_id + department) -> role="staff", that
                       plant_id + department only, restricted to that
                       one department's data entry/detail view.

    Returns None if this person isn't provisioned anywhere — AD proving
    their identity is not, by itself, authorization to use this app.
    """
    from app.models.models import RoleAccess, EmailRecipient

    if not email:
        logger.warning("[AD mapping] AD profile had no mailid — cannot map to a Plant/Department.")
        return None

    email = email.strip()

    # 1. President — global, no plant_id.
    president = (
        db.query(EmailRecipient)
        .filter(
            EmailRecipient.recipient_type == "president",
            EmailRecipient.email.ilike(email),
            EmailRecipient.is_active == True,  # noqa: E712
        )
        .first()
    )
    if president:
        logger.info("[AD mapping] email=%s -> President (all plants)", email)
        return {"role": "president", "plant_id": None, "department": None, "person_name": president.name}

    # 2. Plant Head — one specific plant, every department in it.
    plant_head = (
        db.query(EmailRecipient)
        .filter(
            EmailRecipient.recipient_type == "plant_head",
            EmailRecipient.email.ilike(email),
            EmailRecipient.is_active == True,  # noqa: E712
            EmailRecipient.plant_id.isnot(None),
        )
        .first()
    )
    if plant_head:
        logger.info("[AD mapping] email=%s -> Plant Head | plant_id=%s", email, plant_head.plant_id)
        return {"role": "plant", "plant_id": plant_head.plant_id, "department": None, "person_name": plant_head.name}

    # 3. Staff Incharge — one specific plant + department only.
    staff = (
        db.query(RoleAccess)
        .filter(
            RoleAccess.email.ilike(email),
            RoleAccess.is_active == True,  # noqa: E712
        )
        .first()
    )
    if staff:
        logger.info(
            "[AD mapping] email=%s -> Staff Incharge | plant_id=%s department=%s",
            email, staff.plant_id, staff.role,
        )
        return {"role": "staff", "plant_id": staff.plant_id, "department": staff.role, "person_name": staff.person_name}

    logger.warning(
        "[AD mapping] AD authenticated email=%s but no President / Plant Head / Staff Incharge "
        "record exists for that email — add one in Admin Dashboard (Email Services for President/"
        "Plant Head, Data Entry Users for Staff Incharge).",
        email,
    )
    return None