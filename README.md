# csc-openconnect
Connect to Cisco Secure Client using openconnect

Opens the VPN login page in a browser for SSO, then runs `sudo openconnect`
with the resulting session cookies. Reconnects automatically if the
connection drops.

## Install

```
./install.sh              # installs `csc-openconnect` into ~/.local/bin
./install.sh --uninstall
```

Re-run `./install.sh` after pulling changes to update the installed copy.

## Manual setup

```
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

`openconnect` must also be installed.

## Usage

```
csc-openconnect vpn.mycompany.com     # log in via browser, then connect in the background
csc-openconnect --disconnect          # disconnect
```

If openconnect can't verify the server's certificate, check and remember it
once (you'll be shown the fingerprint and asked to confirm). It's saved in
`~/.config/csc-openconnect/servercerts.json` and used automatically after that:

```
csc-openconnect --trust vpn.mycompany.com
```

Other options: `--servercert pin-sha256:...` to give a fingerprint directly, and
`--foreground` to stay connected in the terminal (Ctrl-C to disconnect).
