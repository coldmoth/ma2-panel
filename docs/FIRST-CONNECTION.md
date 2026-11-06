# First connection to grandMA2

[Install the Windows package](SETUP.md) first. Version 3.2.0 is a **pre-release**; use a copy of the show and work with the MA2 operator. Real hardware validation is not complete.

## 1. Prepare grandMA2 onPC

These steps take place **in grandMA2**, before entering anything in the panel wizard.

1. Open grandMA2 onPC and save the current show.
2. Using an administrator account, open **Setup → User & Profiles Setup**.
3. Create a dedicated **User Profile**, then a **User** assigned to that profile. An existing dedicated account can be reused. Give it the permissions needed for the intended operations.
4. Keep the onPC operator on a different User Profile. Sharing a profile can share fixture selection and the Programmer.
5. Under **Setup → Console → Global Settings → Telnet**, select **Login Enabled**. Confirm the Telnet port; the usual value is **30000**.

Check the account and Telnet settings again after changing the MA2 show. Consult the official MA2 documentation for [users and profiles](https://help.malighting.com/grandMA2/en/help/key_single_multi_systems_create.html) and [Telnet Remote](https://help.malighting.com/grandMA2/en/help/key_remote_control_telnet.html) if your version differs.

## 2. Enter the connection settings in the panel

Open the [setup wizard](http://localhost:8080/setup.html) on the computer running ma2-panel. The interface is currently in Russian; connection fields appear in this order:

1. **MA2 address:** `127.0.0.1` when onPC runs on the same computer, or the IPv4 address of the onPC computer on your trusted local network. Replace the initial `ma2-unconfigured.invalid` placeholder.
2. **Telnet port:** usually `30000`. This is different from the panel's browser port, `8080`.
3. **MA2 user:** the exact name of the dedicated user prepared in grandMA2.
4. **MA2 password:** that user's password.

Save the settings, then use the restart button below the form to restart the bridge. The Windows launcher handles this restart. Settings can be reopened later from the panel.

**The MA2 account belongs to grandMA2. The wizard only stores the connection details used by the panel.** Saving the form neither creates an account nor proves that login succeeded. There is no separate panel web account.

The password is stored in `program/secret.env`, alongside `program/settings.json`, rather than in the JSON settings. An existing `MA2_PASSWORD` environment variable takes precedence over the file.

## 3. Confirm login before sending commands

Check the current connection status below the form and the [diagnostics page](http://127.0.0.1:8080/diag.html). Confirm successful MA2 login, the intended user and profile. A TCP connection alone is insufficient; mock mode is a simulation.

New installations use **test** mode with no allowed fixtures or scenes. Controls may therefore be blocked until the operator grants the appropriate permissions in [Settings](http://127.0.0.1:8080/settings.html). Keep test mode and initially allow only one safe Fixture ID. Do not switch to full mode to bypass a refusal.

The venue plan starts empty. Read or import the intended fixtures and groups with the operator and the required permissions. If reading fixtures from onPC, set `ma2.export_dir` to its actual export directory; the default local `importexport` folder may not be the onPC export folder.

Follow the [first-session checklist](ONPC-HALL-TEST-3.2.md) for the first physical test. Confirm the result in the command log, onPC and on the fixture. An accepted command does not prove that the light changed.

## Next steps

[Connect a tablet](TABLET.md) · [User guide](USAGE.md) · [Troubleshooting](TROUBLESHOOTING.md)
