# Deck sender fan-out

On the Deck, launch the sender menu and create a named target preset for each
bridge, for example PC at `192.168.1.20` and Mac at `viddymac.local` (the default
port is 45123). Choose `m. Select multiple targets`, toggle both preset numbers,
press `s` to save, then `s. Start active targets` on the main menu. The `[active]`
markers show the saved selection; it persists as `"active_targets": ["PC", "Mac"]`
in `config/deck_runtime_settings.local.json`. Targets send in selection order;
each receives identical action, axis, and heartbeat packets from one UDP socket.
Renaming a preset updates its active name and deleting it removes that selection.
Use the multiple-target menu again to change the set, or choose one preset number
on the main menu to clear the set and start only that target. Old settings with
no `active_targets` default to `[]` and retain the original one-at-a-time menu.
For a direct launch, use `python3 -m deck.xinput_send --device-id 5 --bindings
config/deck_bindings.json --targets 192.168.1.20:45123,viddymac.local:45123`
as one shell command; `--target` remains an alias. Hostnames are resolved when
sending and cached for 60 seconds, including failed lookups. After expiry the
next packet retries DNS, allowing DHCP changes to recover. A send or DNS error
is logged at most once per target per 30 seconds and other targets still receive
the packet. Each bridge uses its own preset section; no target is primary.
