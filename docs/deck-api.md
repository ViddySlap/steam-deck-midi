# Deck control API

The Deck uses system Python and the standard library only. No install or venv
change is needed. From the checkout root, start either:

```sh
python3 -m deck.launch_send
python3 -m deck.control_api
```

Use one process at a time. Both serve `http://127.0.0.1:7724` by default. The
first starts the API before showing its menu; the second stays up without a
menu and starts with the sender stopped. The existing sender desktop launcher
uses the first command. Keep a standalone service running in an SSH session or
under your existing process supervisor. Ctrl+C exits it and closes capture and
HTTP sockets. In the menu, `t` stops, `x` restarts, and `q` closes the launcher.
`POST /api/shutdown` performs that quit action over HTTP, replying `{"ok":true}`
after stopping capture, then closing the API and launcher.

```sh
python3 -m deck.deckctl status
python3 -m deck.deckctl targets
python3 -m deck.deckctl activate windows,macbook
python3 -m deck.deckctl start
python3 -m deck.deckctl stop
python3 -m deck.deckctl restart
```

Names here are Deck receiver target preset names, not bridge section names.
An empty activation (`activate ''`) clears the set and stops sending. Old
settings with no `active_targets` still support the menu's single selection
without rewriting the old file. API clients explicitly activate names before
starting. A menu single selection remains restartable for that process only.
Every event still goes to every selected target through S4's one UDP socket.

`deckctl --url http://HOST:7724 --token TOKEN status` addresses another listener.
`DECK_API_TOKEN` can supply the token instead of putting it in command arguments.
The CLI prints JSON and exits 0 on HTTP success, 1 on refusal/connection error,
and 2 on invalid CLI arguments.

To reach the API from another machine on the travel router, first persist a
random shared `api_token` with local `PUT /api/settings`, then run
`python3 -m deck.control_api --api-bind 0.0.0.0` and send `X-Deck-Token: TOKEN`
to `http://DECK_ROUTER_IP:7724` on every request.

The default loopback bind needs no token. An off-loopback bind refuses startup
without one, including when widened by `--api-bind`. Only literal IPv4 binds
and `localhost` are accepted. The token comes from machine-local
`config/deck_runtime_settings.local.json`; never put it in a shared preset.
Token rotation takes effect immediately. A running LAN listener cannot have its
token removed. HTTP is unencrypted; use the trusted travel LAN or SSH forwarding
(`ssh -L 7724:127.0.0.1:7724 deck@DECK_IP`) with the default loopback bind.

## Requests and responses

The complete route inventory is in [api.md](api.md#deck-sender). Send JSON
objects, with `Content-Type: application/json`, for writes. Empty POST bodies
are accepted for bodyless actions. Errors return 4xx with `{"error":"..."}`.
Responses use `application/json` and `Cache-Control: no-store`. Bodies are
limited to 1 MiB; chunked request bodies are refused.

- `GET /api/status` returns `running`, `active_targets` (selected preset objects),
  `running_targets` (the running worker's destinations), `seq`, `heartbeat_age`
  in seconds or null before a heartbeat, `profile_name`, `profile_hash`,
  `bindings_path`, `device_id`, `last_error`, and `exit_code`.
- `seq` is the last event sequence attempted through transport, initially 0.
  Heartbeat age measures the last heartbeat attempt, not bridge receipt or
  feedback. Both reset at sender start. Missing profile hashes remain null;
  none are invented. `profile_name` falls back to the loaded bindings document.
- Start is asynchronous and idempotent. Poll status for hardware startup errors;
  a 200 start response acknowledges the worker request. Stop sets its Event and
  waits up to 3 seconds. If still stopping, it returns an error and restart
  refuses to launch a second worker. Native polling checks stop every 1/60 second;
  slow OS operations such as DNS or HID opening can extend that time.
- `GET /api/targets` returns `presets` and ordered `active_targets` name lists.
  `POST /api/targets` takes `{"presets":[{"name":"Mac","host":"mac.local",
  "port":45123}]}` and replaces the list, retaining active names still present.
  Add takes `{name,host,port?}`; omitted port uses `default_port`. Delete takes
  `{name}`, rename takes `{old,new}`, and active takes `{"names":["Mac"]}`.
  Duplicate/unknown/ambiguous names, invalid ports, and invalid hosts are refused.
- Successful target changes are persisted atomically and applied to a running
  sender through stop/start. Removing all selected targets stops it. Rename
  follows the selected name. Menu edits use the same controller and refuse stale
  snapshots if an API edit arrived while a prompt was open.
- `GET /api/bindings` returns the loaded JSON snapshot, including metadata.
  `POST /api/bindings/reload` validates disk content first, keeps the last good
  snapshot on error, and restarts a running sender using the new snapshot.
- `GET /api/settings` returns persisted settings, with the token omitted and
  `api_token_configured` added. `PUT` accepts `device_id`, `bindings_path`,
  `actions_path`, `default_port`, `profile_name`, `profile_hash`, `api_bind`,
  `api_port`, and `api_token`. Target edits use their dedicated routes. Bind/port
  changes apply on process relaunch; command-line bind/port overrides do not
  rewrite the file. Sender identity/bindings changes restart a running worker;
  API-only settings do not. A changed bindings path must validate before save.
  A disk write failure leaves the prior in-memory settings and worker intact.
  If a worker exceeds its stop deadline after persistence, settings are saved
  and the error requires polling status and retrying start once it exits.

## Learn wizard over HTTP

An SSH agent can perform full learning or re-learn one action using the same
XI2 capture and atomic bindings format as the TTY wizard. A person still presses
the physical control; HTTP replaces the wizard's keyboard/menu actions.

1. Stop the sender. `GET /api/actions` lists action IDs; `GET /api/bindings`
   shows current mappings. A missing bindings file does not prevent API startup.
2. `POST /api/learn/start` with `{}` starts full learning from scratch; use
   `{"action":"BTN_A"}` to re-learn just that action, preserving siblings.
3. `GET /api/learn` reports `active`, current `action`, latest `candidate`, draft
   `bindings` (action to token), `saved`, and `error`. Press a Deck control and
   poll for its captured token. `POST /api/learn/confirm` confirms it. A missing
   candidate or token already assigned to another action is refused.
4. `POST /api/learn/skip` leaves the current full-learn action unmapped, or
   cancels a single-action re-learn. `POST /api/learn/cancel` exits without saving.
5. Confirming/skipping the last full-learn action, or confirming a single action,
   atomically writes the file and reloads the controller's bindings snapshot.
   No partial draft is written. `saved:true` and the file/GET bindings prove save.

Learning refuses to start while the sender is running, and active learning
refuses sender starts and settings writes. These avoid two capture owners and
changing the destination file halfway through a draft. The separate legacy
`deck.launch_learn` TTY wizard remains available; run only one capture tool at a
time. After saving, use `/api/sender/start` to resume sending.
