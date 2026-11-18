"""Connect HubSpot: sign in and click Allow. No API key to copy.

`python3 -m accounthub connect` opens HubSpot's sign-in page in your browser. After you click
Allow, HubSpot sends a one-time code to redavio.com, which swaps it for an access token
(that step needs the app's secret, so it can't live in this open-source repo) and passes the
token straight back to this computer. Redavio doesn't store it. The token is saved to
~/.account-hub/hubspot.json and refreshed through the same route when it expires.

Prefer not to use the Redavio route? Set HUBSPOT_TOKEN to a token from a HubSpot private app
(Settings > Integrations > Private apps) with the read scopes listed in hubspot.py.
"""
import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

CONNECT_URL = os.environ.get("ACCOUNT_HUB_CONNECT_URL", "https://www.redavio.com/api/account-hub/hubspot")
STORE = os.path.expanduser("~/.account-hub/hubspot.json")
PORT = 8765


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _save(tok):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 1800)) - 60
    with open(STORE, "w") as f:
        json.dump(tok, f)
    os.chmod(STORE, 0o600)


def connect():
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "access_token" in q:
                got.update({k: v[0] for k, v in q.items()})
                msg = "HubSpot is connected. You can close this tab and go back to the terminal."
            else:
                msg = "Something went wrong: " + (q.get("error", ["no token came back"])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<p style='font:16px system-ui;margin:40px'>{msg}</p>".encode())

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    url = f"{CONNECT_URL}/connect?port={PORT}"
    print(f"Opening HubSpot sign-in: {url}")
    webbrowser.open(url)
    for _ in range(600):
        if got:
            break
        time.sleep(0.5)
    server.server_close()
    if not got:
        raise SystemExit("No answer from HubSpot within 5 minutes. Run connect again.")
    _save(got)
    print("Connected. Now run: python3 -m accounthub run --hubspot")


def token():
    if os.environ.get("HUBSPOT_TOKEN"):
        return os.environ["HUBSPOT_TOKEN"]
    if not os.path.exists(STORE):
        raise SystemExit("Not connected. Run: python3 -m accounthub connect  (or set HUBSPOT_TOKEN)")
    tok = json.load(open(STORE))
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    req = urllib.request.Request(f"{CONNECT_URL}/refresh", method="POST",
                                 data=json.dumps({"refresh_token": tok["refresh_token"]}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
        new = json.loads(r.read())
    new.setdefault("refresh_token", tok["refresh_token"])
    _save(new)
    return new["access_token"]
