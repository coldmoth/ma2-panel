# Connect a tablet

Complete the [first connection](FIRST-CONNECTION.md) on the Windows computer first. Tablet access uses a **trusted local network**; internet access is not required after installation.

## Enable local network access

1. Connect the Windows computer and tablet to the same lighting router. Avoid guest Wi-Fi that isolates devices from each other.
2. On the Windows computer, open the [setup wizard](http://localhost:8080/setup.html).
3. Enable the local network access checkbox below the connection fields, save and restart the bridge.
4. In Windows, use the **Private** network profile for the trusted lighting network.
5. If Windows Firewall blocks access, right-click **`program/firewall-open.bat`** and choose **Run as administrator**. It opens the configured panel ports for private networks. Administrator access is not required for ordinary panel startup.
6. Scan the QR code shown in the wizard, or enter its displayed address in the tablet browser. With several addresses, use the one for the lighting router's network.

## Choose a view

- **Full panel:** the Windows computer's address with port **8080**.
- **Simple scene view:** the same address with port **8090**.

These are the default ports; use the current addresses shown by the wizard if you changed them. `localhost` and `127.0.0.1` refer to the device opening the page, so they will not reach the Windows computer from a tablet.

The web interface has no user authentication. Keep it on a trusted network and do not expose or forward its ports to the internet. Connection settings are managed locally on the Windows computer.

After changing the installation path or ports, run `program/firewall-open.bat` again. To remove its firewall rules, run `program/firewall-close.bat` as administrator.

Layout checks in desktop browsers do not confirm operation on physical Android tablets or iPads. Verify touch controls on the intended device before a performance.

[Connection troubleshooting](TROUBLESHOOTING.md#the-tablet-cannot-open-the-panel) · [All documentation](README.md)
