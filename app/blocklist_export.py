"""
Writes the current blocked IP list to a file for consumption by fail2ban or iptables.

Configure via:
  BLOCKLIST_FILE    — full path to write (e.g. /etc/honeypot-blocklist.txt)
  BLOCKLIST_FORMAT  — "plain" (one IP per line, default) or "fail2ban"
"""

import logging

from config import Config

logger = logging.getLogger(__name__)


def update_blocklist_file(blocked_ips: list[str]) -> None:
    """Overwrite the blocklist file with the current set of blocked IPs."""
    if not Config.BLOCKLIST_FILE:
        return
    try:
        sorted_ips = sorted(blocked_ips)
        if Config.BLOCKLIST_FORMAT == "fail2ban":
            # fail2ban jail.local [honeypot] section — set ignoreip to whitelist,
            # but more commonly used as: fail2ban-client set honeypot addignoreip ...
            # Here we write a plain list that a fail2ban action can read.
            content = "\n".join(sorted_ips) + "\n" if sorted_ips else "# no blocked IPs\n"
        else:
            content = "\n".join(sorted_ips) + "\n" if sorted_ips else "# no blocked IPs\n"

        with open(Config.BLOCKLIST_FILE, "w") as fh:
            fh.write(content)
        logger.debug("Blocklist file updated: %s (%d IPs)", Config.BLOCKLIST_FILE, len(blocked_ips))
    except OSError as exc:
        logger.warning("Failed to write blocklist %s: %s", Config.BLOCKLIST_FILE, exc)
