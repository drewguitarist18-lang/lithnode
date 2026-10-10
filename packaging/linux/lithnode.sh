#!/bin/sh
# Starts Lithnode's window inside the Flatpak (zypak lets Electron's own sandbox work there).
exec zypak-wrapper /app/lithnode/Lithnode "$@"
