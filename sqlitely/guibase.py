# -*- coding: utf-8 -*-
"""
GUI frame template:
- auto-accelerated control shortcuts, "&OK" will turn Alt-O into shortcut
- Python console window, initially hidden,
  with auto-saved command history kept in conf.ConsoleHistoryCommands
- wx widget inspector window, initially hidden
- option for log panel, handles logging messages via wx events

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    06.09.2019
"""
import datetime
import os

import wx
import wx.lib.inspection
import wx.lib.newevent
import wx.py

from . lib.controls import ColourManager
from . lib import util, wx_accel
from . import conf


"""Custom application event for adding to log."""
LogEvent,    EVT_LOG    = wx.lib.newevent.NewEvent()
"""Custom application event for setting main window status."""
StatusEvent, EVT_STATUS = wx.lib.newevent.NewEvent()


deferred_logs   = []   # Log messages cached before main window is available
deferred_status = []   # Last status cached before main window is available,
                       # as [(msg, flash)]
window          = None # Application main window instance


def log(text, *args):
    """
    Logs a timestamped message to main window.

    @param   args  string format arguments, if any, to substitute in text
    """
    global deferred_logs, window
    now = datetime.datetime.now()
    try:
        finaltext = text % args if args else text
    except UnicodeError:
        args = tuple(map(util.to_unicode, args))
        finaltext = text % args if args else text
    if "\n" in finaltext: # Indent all linebreaks
        finaltext = finaltext.replace("\n", "\n\t\t")
    msg = "%s.%03d\t%s" % (now.strftime("%H:%M:%S"), now.microsecond / 1000,
                           finaltext)
    if not window: return deferred_logs.append(msg)

    process_deferreds()
    wx.PostEvent(window, LogEvent(text=msg))


def status(text, *args, **kwargs):
    """
    Sets main window status text, optionally logs the message.

    @param   args   string format arguments, if any, to substitute in text
    @param   flash  whether to clear the status after timeout,
                    by default after conf.StatusFlashLength if not given seconds
    @param   log    whether to log the message to main window
    """
    global deferred_status, window
    try:
        msg = text % args if args else text
    except UnicodeError:
        args = tuple(map(util.to_unicode, args))
        msg = text % args if args else text
    do_log, flash = (kwargs.get(x) for x in ("log", "flash"))
    if do_log: log(msg)
    if not window:
        deferred_status[:] = [(msg, flash)]
        return

    process_deferreds()
    wx.PostEvent(window, StatusEvent(text=msg, timeout=flash))


def process_deferreds():
    """
    Forwards log messages and status, cached before main window was available.
    """
    global deferred_logs, deferred_status, window
    if not window: return

    if deferred_logs:
        for msg in deferred_logs:
            wx.PostEvent(window, LogEvent(text=msg))
        del deferred_logs[:]
    if deferred_status:
        msg, flash = deferred_status[0]
        wx.PostEvent(window, StatusEvent(text=msg, timeout=flash))
        del deferred_status[:]



class TemplateFrameMixIn(wx_accel.AutoAcceleratorMixIn):
    """Application main window."""

    def __init__(self):
        wx_accel.AutoAcceleratorMixIn.__init__(self)

        self.Bind(EVT_LOG,      self.on_log_message)
        self.Bind(EVT_STATUS,   self.on_set_status)
        self.Bind(wx.EVT_CLOSE, self.on_exit)

        self.console_commands = set() # Commands from run_console()
        self.frame_console = wx.py.shell.ShellFrame(parent=self,
            title=u"%s Console" % conf.Title, size=conf.ConsoleSize)
        self.frame_console.Bind(wx.EVT_CLOSE, self.on_toggle_console)
        self.frame_console_shown = False # Init flag
        console = self.console = self.frame_console.shell
        if not isinstance(conf.ConsoleHistoryCommands, list):
            conf.ConsoleHistoryCommands = []
        for cmd in conf.ConsoleHistoryCommands:
            console.addHistory(cmd)
        console.Bind(wx.EVT_KEY_DOWN, self.on_keydown_console)
        self.widget_inspector = wx.lib.inspection.InspectionTool()

        self.CreateStatusBar()


    def create_log_panel(self, parent):
        """Creates and returns the log output panel."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)

        button_clear = wx.Button(parent=panel, label="C&lear log",
                                 size=(100, -1))
        button_clear.Bind(wx.EVT_BUTTON, lambda event: self.log.Clear())
        edit_log = self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE)
        edit_log.SetEditable(False)
        # Read-only controls tend to be made grey by default
        ColourManager.Manage(edit_log, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)
        ColourManager.Manage(edit_log, "BackgroundColour", wx.SYS_COLOUR_WINDOW)

        sizer.Add(button_clear, border=5, flag=wx.ALIGN_RIGHT | wx.TOP |
                  wx.RIGHT)
        sizer.Add(edit_log, border=5, proportion=1, flag=wx.GROW | wx.ALL)
        return panel


    def create_menu(self):
        """Creates the program menu."""
        menu = wx.MenuBar()
        menu_file = wx.Menu()
        menu.Insert(0, menu_file, "&File")
        menu_recent = self.menu_recent = wx.Menu()
        menu_file.AppendMenu(id=wx.NewId(), text="&Recent files",
            submenu=menu_recent, help="Recently opened files.")
        menu_file.AppendSeparator()
        menu_console = self.menu_console = menu_file.Append(
            id=wx.NewId(), kind=wx.ITEM_CHECK, text="Show &console\tCtrl-E",
            help="Show/hide a Python shell environment window")
        menu_inspect = self.menu_inspect = menu_file.Append(
            id=wx.NewId(), kind=wx.ITEM_CHECK, text="Show &widget inspector",
            help="Show/hide the widget inspector")

        self.file_history = wx.FileHistory(conf.MaxRecentFiles)
        self.file_history.UseMenu(menu_recent)
        for f in conf.RecentFiles[::-1]: # Backwards - FileHistory is a stack
            os.path.exists(f) and self.file_history.AddFileToHistory(f)
        wx.EVT_MENU_RANGE(self, wx.ID_FILE1, wx.ID_FILE9, self.on_recent_file)
        menu_file.AppendSeparator()
        m_exit = menu_file.Append(-1, "E&xit\tAlt-X", "Exit")

        self.Bind(wx.EVT_MENU, self.on_toggle_console, menu_console)
        self.Bind(wx.EVT_MENU, self.on_open_widget_inspector, menu_inspect)
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)
        self.SetMenuBar(menu)


    def on_exit(self, *_):
        """Handler on application exit, saves configuration."""
        do_exit = True
        if do_exit:
            conf.save()
            self.Destroy()


    def on_keydown_console(self, event):
        """Handler for keydown in console, saves entered command in history."""
        event.Skip()
        if (wx.WXK_RETURN == event.KeyCode and not event.ShiftDown()
        and self.console.history):
            # Defer saving until command is inserted into console history
            wx.CallAfter(self.save_last_command)


    def run_console(self, command):
        """
        Runs the command in the Python console. Will not be saved to console
        commands history.
        """
        self.console.run(command)
        self.console_commands.add(command)


    def save_last_command(self):
        """
        Saves the last console command in conf, minus the commands given via
        run_console().
        """
        h = [x for x in self.console.history if x not in self.console_commands]
        history = h[:conf.MaxConsoleHistory][::-1]
        if history != conf.ConsoleHistoryCommands:
            conf.ConsoleHistoryCommands[:] = history
            conf.save()


    def on_set_status(self, event):
        """Event handler for setting main window status bar text."""
        self.SetStatusText(event.text)
        if not event.timeout: return
            
        timeout = event.timeout
        if isinstance(timeout, bool): timeout = conf.StatusFlashLength
        clear = lambda sb: sb and sb.StatusText == event.text and window.SetStatusText("")
        wx.CallLater(timeout * 1000, clear, window.StatusBar)


    def on_log_message(self, event):
        """Event handler for adding a message to the log control."""
        if hasattr(self, "log") and getattr(conf, "LogEnabled", False):
            text = event.text
            try:
                self.log.AppendText(text + "\n")
            except Exception:
                try:
                    self.log.AppendText(text.decode("utf-8", "replace") + "\n")
                except Exception as e:
                    print("Exception %s: %s in on_log_message" %
                          (e.__class__.__name__, e))


    def on_toggle_console(self, *_):
        """Toggles the console shown/hidden."""
        show = not self.frame_console.IsShown()
        if show:
            if not self.frame_console_shown:
                # First showing of console, set height to a fraction of main
                # form, and position it immediately under the main form, or
                # covering its bottom if no room.
                self.frame_console_shown = True
                size = wx.Size(self.Size.width, max(200, self.Size.height / 3))
                self.frame_console.Size = size
                display = wx.GetDisplaySize()
                y = 0
                min_bottom_space = 130 # Leave space for autocomplete dropdown
                if size.height > display.height - self.Size.height \
                - self.Position.y - min_bottom_space:
                    y = display.height - self.Size.height - self.Position.y \
                        - size.height - min_bottom_space
                self.frame_console.Position = (
                    self.Position.x, self.Position.y + self.Size.height + y
                )
            # Scroll to the last line
            self.console.ScrollToLine(self.console.LineCount + 3 - (
                self.console.Size.height / self.console.GetTextExtent(" ")[1]
            ))
        self.frame_console.Show(show)
        if hasattr(self, "menu_console"):
            self.menu_console.Check(show)


    def on_open_widget_inspector(self, *_):
        """Toggles the widget inspection tool shown/hidden."""
        visible = not (self.widget_inspector.initialized
                       and self.widget_inspector._frame)
        if visible:
            self.widget_inspector.Init()
            self.widget_inspector.Show(selectObj=self, refreshTree=True)
            self.widget_inspector._frame.Bind(wx.EVT_CLOSE, lambda e: e.Skip())
        else:
            self.widget_inspector._frame.Close()
        if hasattr(self, "menu_inspect"):
            self.menu_inspect.Check(visible)


    def on_recent_file(self, event):
        """Handler for clicking an entry in Recent Files menu."""
        filename = self.file_history.GetHistoryFile(event.GetId() - wx.ID_FILE1)
        self.open_file(filename)
