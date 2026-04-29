"""Playwright end-to-end tests for the mapping web UI.

Run with: .venv/Scripts/python tests/playwright_ui_test.py
Starts its own server on BASE_PORT for isolation.
"""

import sys
import json
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from windows.ui_server import MappingUIServer

BASE_PORT = 7726
BASE_MAP_PATH = Path("config/windows_midi_map.json")
LOCAL_MAP_PATH = Path("config/windows_midi_map.local.json")
ACTIONS_YAML_PATH = Path("config/actions.yaml")

reload_event = threading.Event()
server = MappingUIServer(
    base_map_path=BASE_MAP_PATH,
    local_map_path=LOCAL_MAP_PATH,
    actions_yaml_path=ACTIONS_YAML_PATH,
    reload_event=reload_event,
    port=BASE_PORT,
)
server.run_in_thread()
time.sleep(1.5)

BASE_URL = f"http://127.0.0.1:{BASE_PORT}"

from playwright.sync_api import sync_playwright

results: list[str] = []
failures = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global failures
    status = "PASS" if condition else "FAIL"
    if not condition:
        failures += 1
    msg = f"[{status}] {name}"
    if detail:
        msg += f": {detail}"
    results.append(msg)
    print(msg)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    # ── 1. Page load ──────────────────────────────────────────────
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    title = page.title()
    check("Page title contains Steam Deck MIDI", "Steam Deck MIDI" in title, title)

    # ── 2. Header ─────────────────────────────────────────────────
    h1 = page.locator("header h1").text_content() or ""
    check("Header h1 visible", "Steam Deck MIDI" in h1)

    # ── 3. Save initially disabled ────────────────────────────────
    check("Save & Apply initially disabled", page.locator("#btnSave").is_disabled())

    # ── 4. Action chips loaded ────────────────────────────────────
    page.wait_for_selector(".chip", timeout=5000)
    chip_count = page.locator(".chip").count()
    check("Action chips > 50", chip_count > 50, str(chip_count))

    # ── 5. BTN_A chip exists ──────────────────────────────────────
    btn_a = page.locator('.chip[data-action="BTN_A"]')
    check("BTN_A chip present", btn_a.count() == 1)

    # ── 6. BTN_A badge says NOTE ──────────────────────────────────
    badge = btn_a.locator(".chip-badge").text_content() or ""
    check("BTN_A badge = NOTE", badge == "NOTE", badge)

    # ── 7. BTN_A description contains 'note' ─────────────────────
    desc = btn_a.locator(".chip-desc").text_content() or ""
    check("BTN_A desc mentions note", "note" in desc.lower(), desc)

    # ── 8. Click BTN_A opens editor ───────────────────────────────
    btn_a.click()
    page.wait_for_selector(".action-badge", timeout=3000)
    action_label = page.locator(".action-badge").first.text_content() or ""
    check("Editor shows BTN_A", action_label == "BTN_A", action_label)

    # ── 9. Type selector = note ───────────────────────────────────
    page.wait_for_selector("#typeSelect", timeout=3000)
    type_val = page.eval_on_selector("#typeSelect", "el => el.value")
    check("Type selector = note for BTN_A", type_val == "note", type_val)

    # ── 10. Note fields visible ───────────────────────────────────
    check("f_note visible", page.locator("#f_note").is_visible())
    check("f_vel visible",  page.locator("#f_vel").is_visible())

    # ── 11. Switch type to CC ─────────────────────────────────────
    page.select_option("#typeSelect", "cc")
    page.wait_for_selector("#f_cc", timeout=3000)
    check("CC fields visible after type switch", page.locator("#f_cc").is_visible())
    check("On-value field visible", page.locator("#f_on").is_visible())

    # ── 12. Fill CC and Apply fields ──────────────────────────────
    page.fill("#f_cc", "15")
    page.click("#btnApplyFields")
    page.wait_for_timeout(300)
    check("Unsaved badge visible after change", page.locator("#unsavedBadge").is_visible())
    check("Save button enabled after change", not page.locator("#btnSave").is_disabled())

    # ── 13. Chip badge updated to CC ─────────────────────────────
    updated_badge = btn_a.locator(".chip-badge").text_content() or ""
    check("BTN_A badge updated to CC", updated_badge == "CC", updated_badge)

    # ── 14. Chip desc updated ────────────────────────────────────
    updated_desc = btn_a.locator(".chip-desc").text_content() or ""
    check("BTN_A desc shows CC 15", "15" in updated_desc, updated_desc)

    # ── 15. JSON raw editor populated ────────────────────────────
    raw_val = page.locator("#jsonRaw").input_value()
    try:
        parsed = json.loads(raw_val)
        check("JSON raw populated with type=cc", parsed.get("type") == "cc", str(parsed))
        check("JSON raw cc=15", parsed.get("cc") == 15, str(parsed.get("cc")))
    except Exception as e:
        check("JSON raw valid JSON", False, str(e))

    # ── 16. Apply raw JSON ────────────────────────────────────────
    new_spec = {"type": "note", "channel": 0, "note": 55, "velocity": 100}
    page.fill("#jsonRaw", json.dumps(new_spec, indent=2))
    page.click("#btnApplyJson")
    page.wait_for_timeout(400)
    badge_after = btn_a.locator(".chip-badge").text_content() or ""
    check("Apply JSON updates badge to NOTE", badge_after == "NOTE", badge_after)
    desc_after = btn_a.locator(".chip-desc").text_content() or ""
    check("Apply JSON desc shows note 55", "55" in desc_after, desc_after)

    # ── 17. Invalid JSON shows error ─────────────────────────────
    page.fill("#jsonRaw", "{bad json{{")
    page.click("#btnApplyJson")
    page.wait_for_timeout(200)
    check("JSON error message shown", page.locator("#jsonErr").is_visible())
    has_error = page.eval_on_selector("#jsonRaw", "el => el.classList.contains('has-error')")
    check("JSON textarea gets error class", has_error)

    # ── 18. Clear mapping ─────────────────────────────────────────
    btn_a.click()
    page.wait_for_selector("#btnClear", timeout=3000)
    page.click("#btnClear")
    page.wait_for_timeout(300)
    cleared_badge = btn_a.locator(".chip-badge").text_content() or ""
    check("Clear mapping sets badge to —", cleared_badge == "—", cleared_badge)
    cleared_desc = btn_a.locator(".chip-desc").text_content() or ""
    check("Clear mapping sets desc to unmapped", "unmapped" in cleared_desc.lower(), cleared_desc)

    # ── 19. DPAD_UP is MACRO ─────────────────────────────────────
    dpad_up = page.locator('.chip[data-action="DPAD_UP"]')
    check("DPAD_UP present", dpad_up.count() == 1)
    dpad_badge = dpad_up.locator(".chip-badge").text_content() or ""
    check("DPAD_UP badge = MACRO", dpad_badge == "MACRO", dpad_badge)

    # ── 20. Click DPAD_UP shows macro_cc fields ───────────────────
    dpad_up.click()
    page.wait_for_selector("#typeSelect", timeout=3000)
    dpad_type = page.eval_on_selector("#typeSelect", "el => el.value")
    check("DPAD_UP type = macro_cc", dpad_type == "macro_cc", dpad_type)
    check("Gesture field visible", page.locator("#f_gesture").is_visible())

    # ── 21. Analog axis action present ───────────────────────────
    l_stick_x = page.locator('.chip[data-action="L_STICK_X_AXIS"]')
    check("L_STICK_X_AXIS chip present", l_stick_x.count() == 1)

    # ── 22. Gyro analog actions present ──────────────────────────
    for action in ["GYRO_PITCH", "GYRO_YAW", "GYRO_ROLL"]:
        check(f"{action} present", page.locator(f'.chip[data-action="{action}"]').count() == 1)

    # ── 23. Group labels in sidebar ───────────────────────────────
    group_count = page.locator(".group-label").count()
    check("Group labels > 5", group_count > 5, str(group_count))

    # ── 24. Search filter ─────────────────────────────────────────
    page.fill("#searchInput", "GYRO")
    page.wait_for_timeout(400)
    chip_names = page.eval_on_selector_all(".chip:visible", "els => els.map(e => e.dataset.action)")
    all_gyro = all("GYRO" in (n or "") for n in chip_names)
    check("Search filters to GYRO only", all_gyro and len(chip_names) > 0, str(chip_names))

    # ── 25. Clear search ─────────────────────────────────────────
    page.fill("#searchInput", "")
    page.wait_for_timeout(400)
    check("Clear search restores all chips", page.locator(".chip").count() > 50)

    # ── 26. Settings tab ─────────────────────────────────────────
    page.click('.tab[data-tab="settings"]')
    page.wait_for_selector("#tab-settings.active", timeout=3000)
    check("Settings tab activates", True)
    macro_fields = page.locator("#macroGrid .field").count()
    check("Macro settings fields > 3", macro_fields > 3, str(macro_fields))
    analog_fields = page.locator("#analogGrid .field").count()
    check("Analog settings fields > 1", analog_fields > 1, str(analog_fields))

    # ── 27. Switch back to mappings ───────────────────────────────
    page.click('.tab[data-tab="editor"]')
    page.wait_for_selector("#tab-editor.active", timeout=3000)
    check("Mappings tab restores", True)

    # ── 28. Macro library cards ───────────────────────────────────
    dpad_up.click()
    page.wait_for_selector(".macro-card", timeout=3000)
    macro_count = page.locator(".macro-card").count()
    check("Macro library cards >= 4", macro_count >= 4, str(macro_count))

    # ── 29. Macro card click applies template ─────────────────────
    page.locator(".macro-card").first.click()
    page.wait_for_timeout(300)
    raw_after = page.locator("#jsonRaw").input_value()
    check("Macro card click populates JSON", len(raw_after) > 5)

    # ── 30. Reset modal cancel ────────────────────────────────────
    page.click("#btnReset")
    page.wait_for_selector("#resetOverlay.open", timeout=3000)
    check("Reset modal opens", True)
    page.click("#btnResetCancel")
    page.wait_for_timeout(250)
    overlay_class = page.locator("#resetOverlay").get_attribute("class") or ""
    check("Reset modal closes on cancel", "open" not in overlay_class)

    # ── 31. Ctrl+S shortcut ───────────────────────────────────────
    page.keyboard.press("Control+s")
    page.wait_for_timeout(600)
    check("Page still functional after Ctrl+S", page.locator(".chip").count() > 0)

    # ── 32. Status bar ────────────────────────────────────────────
    check("Status bar text element visible", page.locator("#statusText").is_visible())
    count_text = page.locator("#mappingCount").text_content() or ""
    check("Mapping count in status bar", "mapped" in count_text, count_text)

    # ── 33. API /api/mappings ─────────────────────────────────────
    resp = page.request.get(f"{BASE_URL}/api/mappings")
    check("GET /api/mappings returns 200", resp.status == 200)
    api_data = resp.json()
    check("Response has 'mappings' key", "mappings" in api_data)
    n_map = len(api_data["mappings"])
    check("At least 50 mappings returned", n_map >= 50, str(n_map))
    check("Response has 'macro_settings' key", "macro_settings" in api_data)

    # ── 34. API /api/actions ──────────────────────────────────────
    resp2 = page.request.get(f"{BASE_URL}/api/actions")
    check("GET /api/actions returns 200", resp2.status == 200)
    acts_data = resp2.json()
    check("Response has 'actions' key", "actions" in acts_data)
    n_acts = len(acts_data["actions"])
    check("At least 50 actions returned", n_acts >= 50, str(n_acts))

    # ── 35. POST /api/conflicts – no conflict ─────────────────────
    cr = page.request.post(
        f"{BASE_URL}/api/conflicts",
        data=json.dumps({"mappings": {"BTN_A": {"type":"note","channel":0,"note":36}}}),
        headers={"Content-Type": "application/json"},
    )
    check("POST /api/conflicts 200", cr.status == 200)
    check("No conflicts for single mapping", cr.json().get("conflicts") == [])

    # ── 36. POST /api/conflicts – detects conflict ────────────────
    cr2 = page.request.post(
        f"{BASE_URL}/api/conflicts",
        data=json.dumps({"mappings": {
            "X1": {"type":"cc","channel":0,"cc":99},
            "X2": {"type":"cc","channel":0,"cc":99},
        }}),
        headers={"Content-Type": "application/json"},
    )
    check("POST /api/conflicts detects cc=99 conflict", len(cr2.json().get("conflicts", [])) > 0)

    # ── 37. Intentional conflicts NOT flagged ─────────────────────
    cr3 = page.request.post(
        f"{BASE_URL}/api/conflicts",
        data=json.dumps({"mappings": {
            "DPAD_UP":            {"type":"macro_cc","channel":0,"cc":22,"gesture":"click"},
            "DPAD_UP_LONG_PRESS": {"type":"macro_cc","channel":0,"cc":22,"gesture":"long_press"},
        }}),
        headers={"Content-Type": "application/json"},
    )
    check("Intentional DPAD_UP cc=22 pair not flagged", cr3.json().get("conflicts") == [])

    # ── 38. POST /api/save valid ──────────────────────────────────
    sv = page.request.post(
        f"{BASE_URL}/api/save",
        data=json.dumps({"mappings": {"BTN_A": {"type":"note","channel":0,"note":36,"velocity":127}}}),
        headers={"Content-Type": "application/json"},
    )
    check("POST /api/save 200", sv.status == 200)
    check("POST /api/save ok=True", sv.json().get("ok") is True)
    check("Reload event set after save", reload_event.is_set())
    reload_event.clear()

    # ── 39. POST /api/save invalid ────────────────────────────────
    sv2 = page.request.post(
        f"{BASE_URL}/api/save",
        data=json.dumps({"mappings": {"BTN_A": {"type":"note","channel":0,"note":999}}}),
        headers={"Content-Type": "application/json"},
    )
    check("POST /api/save 422 on invalid note", sv2.status == 422)
    check("422 response has 'error' key", "error" in sv2.json())

    # ── 40. POST /api/reset ───────────────────────────────────────
    rr = page.request.post(
        f"{BASE_URL}/api/reset",
        data="{}",
        headers={"Content-Type": "application/json"},
    )
    check("POST /api/reset 200", rr.status == 200)
    check("Reload event set after reset", reload_event.is_set())

    # ── 41. chip-desc contains meaningful data ────────────────────
    # START is a CC mapping on ch3 (channel index 2)
    start_chip = page.locator('.chip[data-action="START"]')
    start_desc = start_chip.locator(".chip-desc").text_content() or ""
    check("START chip desc has CC info", "CC" in start_desc, start_desc)

    # ── 42. Staged note macro action ─────────────────────────────
    snm = page.locator('.chip[data-action="L_PAD_LEFT_LONG_PRESS"]')
    if snm.count() == 1:
        snm_badge = snm.locator(".chip-badge").text_content() or ""
        check("L_PAD_LEFT_LONG_PRESS badge = STAGED", snm_badge == "STAGED", snm_badge)

    # ── 43. Relative CC action ────────────────────────────────────
    rpad = page.locator('.chip[data-action="R_PAD_LEFT"]')
    if rpad.count() == 1:
        rpad_badge = rpad.locator(".chip-badge").text_content() or ""
        check("R_PAD_LEFT badge = REL", rpad_badge == "REL", rpad_badge)

    # ── Take screenshot ───────────────────────────────────────────
    start_chip.click()
    page.wait_for_timeout(400)
    page.screenshot(path="tests/playwright_screenshot.png", full_page=True)
    check("Screenshot saved", Path("tests/playwright_screenshot.png").exists())

    # ── 44. Trigger analog actions have correct mapping ───────────
    resp_map = page.request.get(f"{BASE_URL}/api/mappings")
    map_data = resp_map.json()["mappings"]
    # R_PAD_LEFT is relative_cc in the default map
    r_pad_spec = map_data.get("R_PAD_LEFT", {})
    check("R_PAD_LEFT type = relative_cc", r_pad_spec.get("type") == "relative_cc", str(r_pad_spec))
    # BTN_A is note in default
    btn_a_spec = map_data.get("BTN_A", {})
    check("BTN_A default type = note", btn_a_spec.get("type") == "note", str(btn_a_spec))

    ctx.close()
    browser.close()

# Clean up local file left by save test
if LOCAL_MAP_PATH.exists():
    LOCAL_MAP_PATH.unlink()

print("\n" + "=" * 54)
pass_count = len(results) - failures
print(f"Results: {pass_count} PASS  |  {failures} FAIL  |  {len(results)} total")
print("=" * 54)
sys.exit(0 if failures == 0 else 1)
