# Deck Sender

This first Deck-side sender uses `xinput test <device_id>` as the input source.

It watches lines like:

```text
key press   14
key release 14
```

Then it:

- maps the numeric keycode token to an Action ID using `config/deck_bindings.json`
- converts `press` to `down` and `release` to `up`
- sends the JSON event to the Windows receiver over UDP

## Binding Format

Example `config/deck_bindings.json`:

```json
{
  "profile_name": "default",
  "bindings": {
    "14": "BTN_A",
    "15": "BTN_B"
  }
}
```

## Running

Example:

```bash
python3 -m deck.xinput_send \
  --device-id 5 \
  --bindings config/deck_bindings.json \
  --target 10.10.10.15:45123
```

## Notes

- Unmapped keycodes are ignored and printed to stdout.
- Sequence numbers start at `1` each time the sender starts.
- This is intended for SteamOS Desktop Mode / X11.
