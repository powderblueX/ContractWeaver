"""Read a mounted Compose secret, then drop privileges before starting the API.

Local Compose file secrets retain host ownership. A root bootstrap copies only
the environment file into a private ephemeral file, so host mode 0600 works
without making credentials world-readable or running the HTTP server as root.
"""

import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if not sys.argv[1:]:
        raise SystemExit("A server command is required")
    source = Path(os.environ.get("LAW_ENV_FILE", "/run/secrets/backend_environment"))
    if not source.is_file() or source.stat().st_size > 1024 * 1024:
        raise SystemExit("Missing or oversized backend environment secret")
    descriptor, filename = tempfile.mkstemp(prefix="contractweaver-env-")
    with os.fdopen(descriptor, "wb") as target:
        target.write(source.read_bytes())
    os.chown(filename, 10001, 10001)
    os.environ["LAW_ENV_FILE"] = filename
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
