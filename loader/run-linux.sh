#!/bin/sh
# Entry point for Steam launch options on Linux/Proton:
#   "/absolute/path/to/loader/run-linux.sh" %command%
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$here/venv-linux/bin/python" "$here/main.py" "$@"
