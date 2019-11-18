# -*- coding: utf-8 -*-
"""
SQLitely main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    18.11.2019
------------------------------------------------------------------------------
"""
import argparse
import functools
import glob
import logging
import os
import sys
import threading
import traceback

import wx

from . lib import util
from . import conf
from . import guibase
from . import gui

logger = logging.getLogger(__package__)


ARGUMENTS = {
    "description": "%s - SQLite database tool." % conf.Title,
    "arguments": [
        {"args": ["-v", "--version"], "action": "version",
         "version": "%s %s, %s." % (conf.Title, conf.Version, conf.VersionDate)},
        {"args": ["FILE"], "nargs": "*",
         "help": "SQLite database to open on startup, if any"},
    ],
}


def except_hook(etype, evalue, etrace):
    """Handler for all unhandled exceptions."""
    text = "".join(traceback.format_exception(etype, evalue, etrace)).strip()
    log = "An unexpected error has occurred:\n\n%s"
    logger.error(log, text)
    if not conf.PopupUnexpectedErrors: return
    msg = "An unexpected error has occurred:\n\n%s\n\n" \
          "See log for full details." % util.format_exc(evalue)
    wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)


def install_thread_excepthook():
    """
    Workaround for sys.excepthook not catching threading exceptions.

    @from   https://bugs.python.org/issue1230540
    """
    init_old = threading.Thread.__init__
    def init(self, *args, **kwargs):
        init_old(self, *args, **kwargs)
        run_old = self.run
        def run_with_except_hook(*a, **b):
            try: run_old(*a, **b)
            except Exception: sys.excepthook(*sys.exc_info())
        self.run = run_with_except_hook
    threading.Thread.__init__ = init


def run_gui(filenames):
    """Main GUI program entrance."""
    global logger

    # Set up logging to GUI log window
    logger.addHandler(guibase.GUILogHandler())
    logger.setLevel(logging.DEBUG)

    install_thread_excepthook()
    sys.excepthook = except_hook

    # Create application main window
    app = wx.App(redirect=True) # stdout and stderr redirected to wx popup
    window = gui.MainWindow()
    app.SetTopWindow(window) # stdout/stderr popup closes with MainWindow

    # Override stdout/stderr.write to swallow Gtk warnings
    swallow = lambda w, s: None if ("Gtk" in s and "eprecat" in s) else w(s)
    try:
        sys.stdout.write = functools.partial(swallow, sys.stdout.write)
        sys.stderr.write = functools.partial(swallow, sys.stderr.write)
    except Exception: raise

    # Some debugging support
    window.run_console("import datetime, os, re, time, sys, wx")
    window.run_console("# All %s modules:" % conf.Title)
    window.run_console("import components, conf, database, grammar, guibase, "
                       "gui, images, importexport, main, searchparser, "
                       "support, templates, workers")
    window.run_console("from lib import controls, util, wx_accel")

    window.run_console("self = wx.GetApp().TopWindow # Application main window")
    for f in filter(os.path.isfile, filenames):
        wx.CallAfter(wx.PostEvent, window, gui.OpenDatabaseEvent(-1, file=f))
    app.MainLoop()


def run():
    """Parses command-line arguments and runs GUI."""
    conf.load()
    argparser = argparse.ArgumentParser(description=ARGUMENTS["description"])
    for arg in ARGUMENTS["arguments"]:
        argparser.add_argument(*arg.pop("args"), **arg)

    argv = sys.argv[1:]
    if "nt" == os.name: # Fix Unicode arguments, otherwise converted to ?
        argv = util.win32_unicode_argv()[1:]
    arguments, _ = argparser.parse_known_args(argv)

    if arguments.FILE: # Expand wildcards to actual filenames
        arguments.FILE = sum([glob.glob(f) if "*" in f else [f]
                              for f in arguments.FILE], [])
        arguments.FILE = sorted(set(util.to_unicode(f) for f in arguments.FILE))
        arguments.FILE = map(util.longpath, arguments.FILE)

    run_gui(arguments.FILE)


if "__main__" == __name__:
    run()
