"""One-line stdlib client for Deck sender control over SSH or the LAN."""
import argparse
import http.client
import json
import os
import sys
from urllib.parse import urlsplit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:7724")
    parser.add_argument("--token", default=os.environ.get("DECK_API_TOKEN"))
    parser.add_argument("command", choices=["status", "targets", "activate", "start", "stop", "restart"])
    parser.add_argument("names", nargs="?", help="comma-separated names for activate")
    args = parser.parse_args(argv)
    if (args.command == "activate") != (args.names is not None):
        parser.error("activate requires names; other commands take no names")
    address = urlsplit(args.url)
    if address.scheme != "http" or not address.hostname:
        parser.error("--url must be an http://host:port URL")
    method, path, body = "GET", "/api/" + args.command, None
    if args.command == "activate":
        method, path = "POST", "/api/targets/active"
        body = json.dumps({"names": [name.strip() for name in args.names.split(",") if name.strip()]})
    elif args.command in {"start", "stop", "restart"}:
        method, path = "POST", "/api/sender/" + args.command
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-Deck-Token"] = args.token
    conn = None
    try:
        conn = http.client.HTTPConnection(address.hostname, address.port or 80, timeout=5)
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        payload = json.loads(response.read())
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0 if 200 <= response.status < 300 else 1
    except (OSError, ValueError, http.client.HTTPException) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
