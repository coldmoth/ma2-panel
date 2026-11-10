# ma2-panel

A web-based lighting control interface for grandMA2 onPC. Control scenes, fixtures and your venue layout from a computer or tablet.

**[Download for Windows](https://github.com/coldmoth/ma2-panel/releases/latest/download/ma2-panel-win.zip)**

[Documentation](docs/README.md) · [Releases](https://github.com/coldmoth/ma2-panel/releases) · [Source code](https://github.com/coldmoth/ma2-panel)

The full ZIP includes Python and dependencies. Choose **ma2-panel-win.zip** for a new computer; you do not need an older installation.

**Updating v3.2.0–v3.2.4?** Use the [external USB updater](https://github.com/coldmoth/ma2-panel/releases/latest/download/ma2-panel-update-usb.zip), not the old in-app updater. Stop the app, extract the USB kit outside the installation, run `update-usb.bat` and select the existing `program` folder. Settings, passwords, shows and backups are preserved. See [update instructions](docs/update-usb.txt).

## Getting started

1. Download the Windows package above.
2. Extract the entire `ma2-panel` folder to a writable location.
3. Open the outer **`start.bat`**, next to the `program` folder. Keep its window open.
4. Follow the setup wizard. Prepare a dedicated user and enable Telnet Remote in grandMA2, then enter those connection details in the wizard.
5. Open the control panel at [http://127.0.0.1:8080](http://127.0.0.1:8080).

Python and dependencies are included; no terminal or separate Python installation is needed. The interface is currently in Russian. Start with the [installation guide](docs/SETUP.md) and a supervised test of one fixture.

For v3.2.5, the compatible in-app updater accepts the regular update ZIP. Versions v3.2.0–v3.2.4 require the external USB updater; see [update compatibility](docs/repository-structure.md).

Version 3.3.0 adds manual scenes with a shared fade, reversible global blackout and a concert interface with a permanent venue plan. See the [Russian release notes](docs/RELEASE-3.3.md) for changes and the remaining real-light acceptance checks.

## Features

- Manual scenes, shared fade and global blackout.
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
