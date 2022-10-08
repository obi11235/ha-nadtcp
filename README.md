[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# Home Assistant NAD C338  support

This is a fork from `martonperei/ha-nadtcp`. This version is tested and working with a C338. 

## Installing
1. Add this [custom repository to HACS](https://hacs.xyz/docs/faq/custom_repositories/).
2. Download the component using HACS.
3. Add the configuration to your YAML.
4. Restart your home assistant

## Configuration
```yaml
media_player:
  - platform: nadtcp2
    name: nad-amp
    max_volume: -20
    min_volume: -70
    volume_step: 2
    host: 192.168.1.112
```