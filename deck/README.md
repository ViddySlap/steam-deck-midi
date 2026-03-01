# Deck

Steam Deck-side components live here:

- `learn`: capture X11-generated tokens and bind them to Action IDs
- `send`: watch input events and transmit action messages over UDP

Current modules:

- `learn_wizard.py`: interactive xinput-based binding capture wizard
- `xinput_send.py`: run `xinput test <device_id>`, map keycodes to Action IDs, and send UDP events
