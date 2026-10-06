#!/bin/sh
# Entry point for Steam launch options on Linux/Proton:
#   "/absolute/path/to/loader/run-linux.sh" %command%
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Accept whichever virtualenv name the user happened to create.
for venv in venv-linux venv .venv; do
    python="$here/$venv/bin/python"
    if [ -x "$python" ]; then
        exec "$python" "$here/main.py" "$@"
    fi
done

echo "run-linux.sh: no Python virtualenv found next to this script ($here)." >&2
echo "Create one first, then set the Steam launch option again:" >&2
echo "  cd \"$here\" && python3 -m venv venv-linux && venv-linux/bin/pip install -r requirements-linux.txt" >&2
exit 1
