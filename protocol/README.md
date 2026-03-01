# Protocol

Shared message contracts and validation logic belong here.

The v1 message shape from `AGENTS.md` includes:

- `action`
- `state`
- `seq`
- optional `profile_name`
- optional `profile_hash`

Test sender:

```bash
python3 -m protocol.send_test --action BTN_A --state tap --target 127.0.0.1:45123
```
