#!/bin/sh
SUPPRESS="Gtk-WARNING|Gtk-CRITICAL|GLib-GObject-WARNING"
exec python -m sqlitely.main "$@" 2>&1 | tr -d '\r' | grep -v -E "$SUPPRESS"
