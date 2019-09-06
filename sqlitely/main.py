# -*- coding: utf-8 -*-
"""
SQLitely main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    06.09.2019
------------------------------------------------------------------------------
"""
import argparse
import glob
import logging
import os
import sys

import wx

from . lib import util
from . import conf
from . import guibase
from . import gui


ARGUMENTS = {
    "description": "%s - SQLite database tool." % conf.Title,
    "arguments": [
        {"args": ["-v", "--version"], "action": "version",
         "version": "%s %s, %s." % (conf.Title, conf.Version, conf.VersionDate)},
        {"args": ["FILE"], "nargs": "*",
         "help": "SQLite database to open on startup, if any"},
    ],
}


def run_gui(filenames):
    """Main GUI program entrance."""

    # Set up logging to GUI log window
    logger = logging.getLogger(__package__)
    logger.addHandler(guibase.GUILogHandler())
    logger.setLevel(logging.DEBUG)

    # Create application main window
    app = wx.App(redirect=0) # stdout and stderr redirected to wx popup
    window = gui.MainWindow()
    app.SetTopWindow(window) # stdout/stderr popup closes with MainWindow

    # Some debugging support
    window.run_console("import datetime, os, re, time, sys, wx")
    window.run_console("# All %s modules:" % conf.Title)
    window.run_console("import conf, database, export, guibase, gui, images, "
                       "main, searchparser, support, templates, workers")
    window.run_console("from lib import controls, util, wx_accel")

    window.run_console("self = wx.GetApp().GetTopWindow() # Application main window instance")
    for f in filter(os.path.isfile, filenames):
        wx.CallAfter(wx.PostEvent, window, gui.OpenDatabaseEvent(file=f))
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
