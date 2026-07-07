[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# Home Assistant NAD C338  support

This is a fork from `martonperei/ha-nadtcp`. This version is tested and working with a C338. 

## Installing
1. Add this [custom repository to HACS](https://hacs.xyz/docs/faq/custom_repositories/).
2. Download the component using HACS.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** and search for
   **NAD C338 integration**.

## Configuration

The integration is configured from the UI. When adding it you provide:

- **Host** — the IP address or hostname of the amplifier.
- **Name** — the name of the device in Home Assistant.

The volume range and reconnect behaviour can be tuned afterwards via the
integration's **Configure** button (options):

- **Minimum / maximum volume (dB)** — maps the amplifier's dB range to Home
  Assistant's `0..1` volume slider.
- **Volume step (dB)** — how much a single volume up/down step changes the level.
- **Reconnect interval (seconds)** — how long to wait before retrying a dropped
  connection.

### Legacy YAML configuration (deprecated)

Existing YAML configurations are automatically imported into the UI on startup
and can then be removed. New setups should use the UI.

```yaml
media_player:
  - platform: nadtcp2
    name: nad-amp
    max_volume: -20
    min_volume: -70
    volume_step: 2
    host: 192.168.1.112
```