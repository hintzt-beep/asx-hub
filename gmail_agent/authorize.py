"""One-off login on your own PC:  python authorize.py client_secret.json

Standalone on purpose: download just this file, no need for the whole repo.
Opens Google's sign-in page in your browser. You sign in with Google (this code never
sees your password). It then prints a refresh token to paste into the
GMAIL_REFRESH_TOKEN GitHub secret. Keep client_secret.json out of the repo (.gitignore covers it).
"""
from __future__ import annotations

import json
import sys

# Must match config.SCOPES (a test checks this). Modify = read + labels + Spam/Trash, never permanent delete.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "client_secret.json"
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install first:  pip install google-auth-oauthlib")
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            client = json.load(f).get("installed", {})
    except (OSError, ValueError):
        print(f"Could not read {path}. Download it from Google Cloud (OAuth client, Desktop app).")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(path, scopes=SCOPES)
    # prompt=consent makes Google return a refresh token even if you authorised before.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("Google did not return a refresh token. Remove the app's access in your Google Account and try again.")
        return 1

    print("\nDone. Add these three GitHub secrets (Settings > Secrets and variables > Actions):\n")
    print(f"  GMAIL_CLIENT_ID      = {client.get('client_id', '(see client_secret.json)')}")
    print(f"  GMAIL_CLIENT_SECRET  = {client.get('client_secret', '(see client_secret.json)')}")
    print(f"  GMAIL_REFRESH_TOKEN  = {creds.refresh_token}")
    print("\nTreat the refresh token like a password: don't share it or save it in the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
