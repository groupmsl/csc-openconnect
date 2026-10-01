#!/usr/bin/env python3
"""Connect to a Cisco Secure Client VPN using openconnect.

Opens the VPN's login page in a browser so you can complete SSO, grabs the
session cookies once login succeeds, then runs openconnect with them. By
default openconnect keeps running in the background once connected; use
--disconnect to stop it.
"""
import argparse
import base64
import hashlib
import json
import os
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from playwright.sync_api import Error as PlaywrightError, sync_playwright

PID_FILE = Path("/run/csc-openconnect.pid")
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) \
	/ "csc-openconnect" / "servercerts.json"
DISCONNECT_TIMEOUT_SECONDS = 15


def browser_login(url):
	"""Show the login page; return (username, cookie_header) once logged in."""
	with sync_playwright() as p:
		browser = p.chromium.launch(headless=False)
		context = browser.new_context()
		page = context.new_page()
		page.set_viewport_size({"width": 800, "height": 600})
		page.goto(url)

		while True:
			try:
				cookies = {c["name"]: c["value"] for c in context.cookies()}
				if "webvpn" in cookies:
					break
				page.wait_for_timeout(1000)
			except PlaywrightError:
				sys.exit("Browser closed before login completed")

		browser.close()

	username = unquote(cookies.get("remembered-username", ""))
	cookie = f"webvpn={cookies['webvpn']}"
	if "webvpnc" in cookies:
		cookie += f"; webvpnc={cookies['webvpnc']}"
	return username, cookie


def load_saved_certs():
	try:
		return json.loads(CONFIG_FILE.read_text())
	except (FileNotFoundError, ValueError):
		return {}


def fetch_server_cert(host, port):
	"""Return (certificate, openconnect-style pin) for what the server presents."""
	# get_server_certificate doesn't verify the chain, which is the point here.
	pem = ssl.get_server_certificate((host, port))
	cert = x509.load_pem_x509_certificate(pem.encode())
	spki = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
	pin = "pin-sha256:" + base64.b64encode(hashlib.sha256(spki).digest()).decode()
	return cert, pin


def trust_server(url):
	"""Ask the user to confirm the server's certificate, and remember it."""
	parsed = urlparse(url)
	host, port = parsed.hostname, parsed.port or 443
	try:
		cert, pin = fetch_server_cert(host, port)
	except (OSError, ssl.SSLError) as e:
		sys.exit(f"Could not fetch certificate from {host}:{port}: {e}")

	print(f"Server:  {host}:{port}")
	print(f"Subject: {cert.subject.rfc4514_string()}")
	print(f"Issuer:  {cert.issuer.rfc4514_string()}")
	print(f"Pin:     {pin}")
	if input("Trust this certificate for future connections? [y/N] ").strip().lower() != "y":
		sys.exit("Not trusted.")

	certs = load_saved_certs()
	certs[host] = pin
	CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
	CONFIG_FILE.write_text(json.dumps(certs, indent=2) + "\n")
	print(f"Saved to {CONFIG_FILE}")
	return pin


def running_pid():
	"""Return the pid of a running openconnect started by us, or None."""
	try:
		pid = int(PID_FILE.read_text().strip())
		os.kill(pid, 0)
	except (FileNotFoundError, ValueError, ProcessLookupError):
		return None
	except PermissionError:
		pass  # exists, but owned by root: it's alive
	return pid


def disconnect():
	pid = running_pid()
	if pid is None:
		print("Not connected.")
		return
	# openconnect runs as root; SIGTERM makes it disconnect cleanly.
	subprocess.run(["sudo", "kill", "-TERM", str(pid)], check=True)
	deadline = time.monotonic() + DISCONNECT_TIMEOUT_SECONDS
	while time.monotonic() < deadline:
		if running_pid() is None:
			print("Disconnected.")
			return
		time.sleep(0.5)
	sys.exit(f"openconnect (pid {pid}) did not exit within {DISCONNECT_TIMEOUT_SECONDS}s")


def connect(url, username, cookie, servercert, foreground):
	# Arguments are passed as a list (no shell), so they must not be quoted.
	# The cookie can't go via stdin: openconnect reads its interactive
	# prompts from stdin too.
	cmd = [
		"sudo", "openconnect", url,
		"--protocol=anyconnect",
		f"--cookie={cookie}",
		f"--pid-file={PID_FILE}",
	]
	if username:
		cmd.append(f"--user={username}")
	if servercert:
		cmd.append(f"--servercert={servercert}")
	if not foreground:
		cmd.append("--background")

	try:
		result = subprocess.run(cmd)
	except KeyboardInterrupt:
		print("\nDisconnected.")
		return
	if result.returncode != 0:
		sys.exit(f"openconnect failed (exit code {result.returncode})")
	if not foreground:
		print("Connected. Run again with --disconnect to disconnect.")


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("url", nargs="?", help="VPN server, e.g. vpn.mycompany.com")
	parser.add_argument("--disconnect", action="store_true",
						help="disconnect from the VPN")
	parser.add_argument("--trust", action="store_true",
						help="check the server's certificate once and remember it, "
							 "for servers whose certificate openconnect can't verify")
	parser.add_argument("--servercert", metavar="pin-sha256:...",
						help="trust the server certificate with this fingerprint "
							 "(overrides any remembered one)")
	parser.add_argument("--foreground", action="store_true",
						help="stay connected in this terminal instead of the background")
	args = parser.parse_args()

	if args.disconnect:
		disconnect()
		return
	if not args.url:
		parser.error("url is required")

	url = args.url if args.url.startswith("http") else "https://" + args.url

	if running_pid() is not None:
		sys.exit("Already connected. Run again with --disconnect first.")

	servercert = args.servercert
	if args.trust:
		servercert = trust_server(url)
	elif not servercert:
		servercert = load_saved_certs().get(urlparse(url).hostname)

	username, cookie = browser_login(url)
	connect(url, username, cookie, servercert, args.foreground)


if __name__ == "__main__":
	main()
