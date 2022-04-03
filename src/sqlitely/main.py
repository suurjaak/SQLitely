# -*- coding: utf-8 -*-
"""
SQLitely main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    26.03.2022
------------------------------------------------------------------------------
"""
import argparse
import functools
import glob
import locale
import logging
import multiprocessing.connection
import os
import sys
import threading
import traceback
import warnings

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


class MainApp(wx.App):

    def InitLocale(self):
        self.ResetLocale()
        if "win32" == sys.platform:  # Avoid dialog buttons in native language
            mylocale = wx.Locale(wx.LANGUAGE_ENGLISH_US, wx.LOCALE_LOAD_DEFAULT)
            mylocale.AddCatalog("wxstd")
            self._initial_locale = mylocale  # Override wx.App._initial_locale
            # Workaround for MSW giving locale as "en-US"; standard format is "en_US".
            # Py3 provides "en[-_]US" in wx.Locale names and accepts "en" in locale.setlocale();
            # Py2 provides "English_United States.1252" in wx.Locale.SysName and accepts only that.
            name = mylocale.SysName if sys.version_info < (3, ) else mylocale.Name.split("_", 1)[0]
            locale.setlocale(locale.LC_ALL, name)


def except_hook(etype, evalue, etrace):
    """Handler for all unhandled exceptions."""
    mqueue = getattr(except_hook, "queue", [])
    setattr(except_hook, "queue", mqueue)

    text = "".join(traceback.format_exception(etype, evalue, etrace)).strip()
    log = "An unexpected error has occurred:\n\n%s"
    logger.error(log, text)
    if not conf.PopupUnexpectedErrors: return
    conf.UnexpectedErrorCount += 1
    msg = "An unexpected error has occurred:\n\n%s\n\n" \
          "See log for full details." % util.format_exc(evalue)
    mqueue.append(msg)

    def after():
        if not mqueue: return
        msg = mqueue[0]
        dlg = wx.RichMessageDialog(None, msg, conf.Title, wx.OK | wx.ICON_ERROR)
        if conf.UnexpectedErrorCount > 2:
            dlg.ShowCheckBox("&Do not pop up further errors")
        dlg.ShowModal()
        if dlg.IsCheckBoxChecked():
            conf.PopupUnexpectedErrors = False
            del mqueue[:]
            conf.save()
        if mqueue: mqueue.pop(0)
        if mqueue and conf.PopupUnexpectedErrors: wx.CallAfter(after)

    if len(mqueue) < 2: wx.CallAfter(after)


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


def ipc_send(authkey, port, data, limit=10000):
    """
    Sends data to another program instance via multiprocessing,
    climbing port number higher until success or reaching step limit.

    @return  True if operation successful, False otherwise
    """
    result = False
    while not result and limit:
        kwargs = {"address": ("localhost", port), "authkey": authkey}
        try:   multiprocessing.connection.Client(**kwargs).send(data)
        except Exception: port, limit = port + 1, limit - 1
        else:  result = True
    return result


def run_gui(filenames):
    """Main GUI program entrance."""
    global logger
    filenames = list(filter(os.path.isfile, filenames))

    # Set up logging to GUI log window
    logger.addHandler(guibase.GUILogHandler())
    logger.setLevel(logging.DEBUG)

    singlechecker = wx.SingleInstanceChecker(conf.IPCName)
    if not conf.AllowMultipleInstances and singlechecker.IsAnotherRunning():
        data = list(map(os.path.realpath, filenames))
        if ipc_send(conf.IPCName, conf.IPCPort, data): return
        else: logger.error("Failed to communicate with allowed instance.")

    install_thread_excepthook()
    sys.excepthook = except_hook

    # Create application main window
    app = MainApp(redirect=True) # stdout and stderr redirected to wx popup
    window = gui.MainWindow()
    app.SetTopWindow(window) # stdout/stderr popup closes with MainWindow

    if "posix" == os.name:
        # Override stdout/stderr.write to swallow Gtk deprecation warnings
        swallow = lambda w, s: None if ("Gtk" in s and "eprecat" in s) else w(s)
        try:
            sys.stdout.write = functools.partial(swallow, sys.stdout.write)
            sys.stderr.write = functools.partial(swallow, sys.stderr.write)
        except Exception: pass

    # Some debugging support
    window.run_console("import datetime, os, re, time, sys, wx")
    window.run_console("# All %s modules:" % conf.Title)
    window.run_console("from sqlitely import components, conf, database, "
                       "grammar, guibase, gui, images, importexport, main, "
                       "searchparser, support, templates, workers")
    window.run_console("from sqlitely.lib import controls, util, wx_accel")

    window.run_console("self = wx.GetApp().TopWindow # Application main window")
    for f in filenames:
        wx.CallAfter(wx.PostEvent, window, gui.OpenDatabaseEvent(-1, file=f))
    app.MainLoop()
    del singlechecker


def run():
    """Parses command-line arguments and runs GUI."""
    warnings.simplefilter("ignore", UnicodeWarning)
    conf.load()
    argparser = argparse.ArgumentParser(description=ARGUMENTS["description"])
    for arg in ARGUMENTS["arguments"]:
        argparser.add_argument(*arg.pop("args"), **arg)

    argv = sys.argv[1:]
    if "nt" == os.name and sys.version_info < (3, ): # Fix Unicode arguments, otherwise converted to ?
        argv = util.win32_unicode_argv()[1:]
    arguments, _ = argparser.parse_known_args(argv)

    if arguments.FILE: # Expand wildcards to actual filenames
        arguments.FILE = sum([glob.glob(f) if "*" in f else [f]
                              for f in arguments.FILE], [])
        arguments.FILE = sorted(set(util.to_unicode(f) for f in arguments.FILE))
        arguments.FILE = list(map(util.longpath, arguments.FILE))

    run_gui(arguments.FILE)


if "__main__" == __name__:
    run()
