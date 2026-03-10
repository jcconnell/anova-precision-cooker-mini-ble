# Anova Precision Cooker Mini — Home Assistant BLE Integration

A custom Home Assistant integration for the **Anova Precision Cooker Mini (Gen 3)** via Bluetooth Low Energy. Built on the [official Anova developer reference](https://developer.anovaculinary.com/docs/devices/mini/implementation-example) and the [official developer project](https://github.com/anova-culinary/developer-project-mini).

## Features

- Auto-discovery via BLE service UUID or manual MAC address entry
- Start and stop cooks with a configurable target temperature
- Real-time polling of current water temperature and cook state
- Configurable cook timer (hours + minutes)
- Timer mode selection: hold temperature indefinitely or stop when the timer expires
- Firmware version diagnostic sensor

## Entities

| Platform | Entity | Description |
|----------|--------|-------------|
| `climate` | Anova Precision Cooker Mini | Start/stop cook, set target temperature (°F) |
| `sensor` | Current Temperature | Live water temperature (°C) |
| `sensor` | Target Temperature | Active setpoint read from device (°C) |
| `sensor` | Cook State | Device mode: `idle`, `cooking`, `preheating`, etc. |
| `sensor` | Timer Remaining | Computed countdown in minutes |
| `sensor` | Firmware Version | Device firmware (diagnostic, hidden by default) |
| `number` | Cook Timer Hours | Hours component of cook timer (0–999) |
| `number` | Cook Timer Minutes | Minutes component of cook timer (0–59) |
| `select` | Timer Mode | `Hold Temperature` or `Stop When Done` |

## Requirements

- Home Assistant with the **Bluetooth** integration enabled (local adapter or ESPHome BLE proxy)
- Anova Precision Cooker Mini (Gen 3) — BLE service UUID `910772a8-a5e7-49a7-bc6d-701e9a783a5c`
- Python package: [`bleak`](https://github.com/hbldh/bleak) (included with Home Assistant)

## Installation

### HACS (recommended)

[HACS](https://hacs.xyz) must be installed in your Home Assistant instance.

1. Open HACS in Home Assistant.
2. Click **Custom Repositories** and add:
   - **URL**: `https://github.com/jcconnell/anova-precision-cooker-mini-ble`
   - **Category**: Integration
3. Search for **Anova Precision Cooker Mini** and install it.
4. Restart Home Assistant.

### Manual

1. Copy the `custom_components/anova_mini` directory into your Home Assistant `custom_components` folder:

   ```
   config/
   └── custom_components/
       └── anova_mini/
           ├── __init__.py
           ├── anova_ble.py
           ├── climate.py
           ├── config_flow.py
           ├── manifest.json
           ├── number.py
           ├── select.py
           ├── sensor.py
           └── strings.json
   ```

2. Restart Home Assistant.

3. Go to **Settings > Devices & Services > Add Integration** and search for **Anova Precision Cooker Mini**.

## Setup

The integration supports two discovery methods:

**Auto-discovery**: If Home Assistant detects the device via BLE advertisement, a discovery notification appears. Confirm to add it.

**Manual**: If the device is not yet in the BLE cache, enter the MAC address directly (e.g. `F8:64:65:16:C4:2E`). Make sure the cooker is powered on and within range of your BLE adapter or proxy.

## BLE Protocol

Communication follows the official Anova BLE protocol. Payloads are JSON objects encoded as Base64 over GATT characteristics.

| Characteristic | UUID | Purpose |
|----------------|------|---------|
| Set Temperature | `0f5639f7-...` | Write target setpoint |
| Current Temperature | `6ffdca46-...` | Read current water temp |
| Timer | `a2b179f8-...` | Read timer state |
| State | `54e53c60-...` | Read/write cook state and commands |
| Set Clock | `d8a89692-...` | Sync device clock (required on connect) |
| System Info | `153c9432-...` | Read firmware version and serial number |

The device clock must be set on every connection. All writes use `response=False` as specified in the official reference.

## References

- [Anova Developer Docs — Mini Implementation Example](https://developer.anovaculinary.com/docs/devices/mini/implementation-example)
- [Anova Culinary Developer Project (GitHub)](https://github.com/anova-culinary/developer-project-mini)
- [HACS — Home Assistant Community Store](https://hacs.xyz)
- [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html)

## License

MIT
