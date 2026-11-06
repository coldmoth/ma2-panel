# ma2-panel

A web-based lighting control interface for grandMA2 onPC. Control scenes, fixtures and your venue layout from a computer or tablet.

**[Download for Windows](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/ma2-panel-win.zip)**

[Documentation](docs/README.md) · [Releases](https://github.com/coldmoth/ma2-panel/releases) · [Source code](https://github.com/coldmoth/ma2-panel)

**3.2.0 is a pre-release for supervised testing. Validation with real grandMA2 hardware is not yet complete.**

## Getting started

1. Download the Windows package above.
2. Extract the entire `ma2-panel` folder to a writable location.
3. Open the outer **`start.bat`**, next to the `program` folder. Keep its window open.
4. Follow the setup wizard. Prepare a dedicated user and enable Telnet Remote in grandMA2, then enter those connection details in the wizard.
5. Open the control panel at [http://127.0.0.1:8080](http://127.0.0.1:8080).

Python and dependencies are included; no terminal or separate Python installation is needed. The interface is currently in Russian. Start with the [installation guide](docs/SETUP.md) and a supervised test of one fixture.

## Features

- Scenes and executors.
- Fixture control: dimmer, color and Pan/Tilt.
- Interactive venue layout with search, zoom and fixture selection.
- Groups and presets.
- Local show plans and permission-controlled MA2 show management.
- Settings and diagnostics.
- Tablet-friendly interface and a simple scene view.

Available controls depend on the fixture type and configured permissions.

## Requirements

- Windows 10/11 x64.
- grandMA2 onPC 3.9 with Telnet Remote configured.
- A modern browser, such as Chrome or Edge.
- A trusted local network for tablet access.

## Documentation

- [Installation](docs/SETUP.md)
- [User guide](docs/USAGE.md)
- [First connection](docs/FIRST-CONNECTION.md)
- [Tablet connection](docs/TABLET.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

[GNU GPL v3](LICENSE), **GPL-3.0-only**.

An independent project, not an official MA Lighting product. grandMA2 and MA Lighting are trademarks of their respective owners.
