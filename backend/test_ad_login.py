"""
test_ad_login.py
------------------
Standalone diagnostic script to test the AD Login API DIRECTLY against
Rane's live server, from wherever this backend actually runs (so it has
real network access to api.ranegroup.com, unlike a dev sandbox). It
calls the EXACT SAME ad_login() used in production — this is not a
reimplementation, so if it works here, the app's login will work too.

Usage
------
    cd backend
    python test_ad_login.py                     # tries the SOP's own sample credentials
    python test_ad_login.py <gen_id>             # prompts for password securely
    python test_ad_login.py <gen_id> <password>  # both on the command line (fine for local testing)

What this tells you
----------------------
1. If GEN ID 15660 / password "Pwd@15660" (the exact sample values used
   throughout SOP ISM_L01, e.g. page 9's "To Create Encryption" example
   and the cover page's "Victor A (GENID: 15660)") is ALSO rejected,
   the problem is almost certainly NOT specific to any one person's
   credentials — it's most likely ApplicationName not being registered
   with Rane's IS team for "DigitalDRM" (see AD_APPLICATION_NAME in
   .env), or some other account-independent server-side restriction.
   Worth asking Rane's IS team directly whether ISM_L01's own sample
   GEN ID is even a real, currently-valid test account before reading
   too much into this.

2. If the SOP's sample credentials succeed but a real person's GEN ID
   still fails, the problem is specific to that account: wrong/expired
   password, disabled account, or (less likely now, but still possible)
   a GEN ID format this script's real-world usage hasn't seen yet.

3. Either way, run this with -v to see the exact same detailed logging
   the app writes in production, including which GenID variant(s) were
   tried and the raw AD response for each.
"""

import argparse
import getpass
import logging
import sys


def main():
    parser = argparse.ArgumentParser(description="Test AD Login API directly against the live server.")
    parser.add_argument("gen_id", nargs="?", default="15660", help="GEN ID to test (default: SOP sample GENID 15660)")
    parser.add_argument("password", nargs="?", default=None, help="Password (omit to be prompted; default sample uses Pwd@15660)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed request/response logging (recommended)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    gen_id = args.gen_id
    if args.password is not None:
        password = args.password
    elif gen_id == "15660":
        # SOP's own documented sample password for GENID 15660.
        password = "Pwd@15660"
        print(f"(no password given — using the SOP's sample password for GENID {gen_id})")
    else:
        password = getpass.getpass(f"Password for GEN ID {gen_id}: ")

    print(f"\nTesting AD login for GEN ID: {gen_id}")
    print("-" * 60)

    from app.services.ad_auth_service import (
        AD_APPLICATION_NAME, AD_BASE_URL, AD_DEVICE_TYPE, ad_login,
        AdAuthError, AdServiceError,
    )

    print(f"AD_BASE_URL         = {AD_BASE_URL}")
    print(f"AD_APPLICATION_NAME = {AD_APPLICATION_NAME}  <-- confirm this is registered with Rane IS if login fails")
    print(f"AD_DEVICE_TYPE       = {AD_DEVICE_TYPE}")
    print("-" * 60)

    try:
        profile = ad_login(gen_id, password, ip_address="127.0.0.1")
    except AdAuthError as exc:
        print(f"\n❌ REJECTED by AD: {exc}")
        print("\nNext steps:")
        print("  - If this is GEN ID 15660 (the SOP's own sample), the issue is likely")
        print("    account-independent — check AD_APPLICATION_NAME with Rane's IS team.")
        print("  - If this is a real person's GEN ID, double-check the password is their")
        print("    CURRENT Windows/domain password (not expired/recently changed).")
        print("  - Re-run with -v to see the full request/response detail.")
        sys.exit(1)
    except AdServiceError as exc:
        print(f"\n❌ Could not complete the request: {exc}")
        print("\nThis is a connectivity/service problem, not a credentials problem —")
        print("check that this machine can reach api.ranegroup.com over HTTPS.")
        sys.exit(1)

    print("\n✅ SUCCESS — AD accepted these credentials.")
    print(f"   name       : {profile.get('name')}")
    print(f"   mailid     : {profile.get('mailid')}")
    print(f"   department : {profile.get('department')}")
    print(f"   genid      : {profile.get('genid')}")

    mailid = (profile.get("mailid") or "").strip()
    if mailid:
        from app.database import SessionLocal
        from app.services.ad_auth_service import resolve_plant_department_role

        db = SessionLocal()
        try:
            mapping = resolve_plant_department_role(db, mailid)
        finally:
            db.close()

        print("-" * 60)
        if mapping:
            print(f"✅ This email IS provisioned in Data Entry Users for Plant {mapping['plant_id']}:")
            print(f"   department : {mapping['department']}")
            print(f"   person     : {mapping['person_name']}")
            print("   -> This person would be logged in successfully by the app.")
        else:
            print(f"⚠️  AD accepted the credentials, but {mailid} has no active Data Entry User")
            print("   for Plant 5 — the app would still show the generic login error.")
            print("   Add this person in Admin Dashboard > Data Entry Users to fix that.")


if __name__ == "__main__":
    main()