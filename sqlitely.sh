#!/bin/sh
SUPPRESS="Gtk-WARNING|Gtk-CRITICAL|GLib-GObject-WARNING"
exec python -m sqlitemate "$@" 2>&1 | tr -d '\r' | grep -v -E "$SUPPRESS"
