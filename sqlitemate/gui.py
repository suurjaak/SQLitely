# -*- coding: utf-8 -*-
"""
SQLiteMate UI application main window class and project-specific UI classes.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    02.09.2019
------------------------------------------------------------------------------
"""
import ast
import base64
import collections
import datetime
import functools
import hashlib
import inspect
import os
import re
import shutil
import sys
import textwrap
import traceback
import urllib
import webbrowser

import wx
import wx.gizmos
import wx.grid
import wx.html
import wx.lib
import wx.lib.agw.fmresources
import wx.lib.agw.genericmessagedialog
import wx.lib.agw.labelbook
import wx.lib.agw.flatmenu
import wx.lib.agw.flatnotebook
import wx.lib.agw.ultimatelistctrl
import wx.lib.newevent
import wx.lib.scrolledpanel
import wx.stc

from . lib import controls
from . lib.controls import ColourManager
from . lib import util
from . lib.vendor import step

from . import conf
from . import database
from . import export
from . import guibase
from . import images
from . import support
from . import templates
from . import workers


"""Custom application events for worker results."""
WorkerEvent, EVT_WORKER = wx.lib.newevent.NewEvent()
DetectionWorkerEvent, EVT_DETECTION_WORKER = wx.lib.newevent.NewEvent()
OpenDatabaseEvent, EVT_OPEN_DATABASE = wx.lib.newevent.NewEvent()


class MainWindow(guibase.TemplateFrameMixIn, wx.Frame):
    """SQLiteMate main window."""

    TRAY_ICON = (images.Icon16x16_32bit if "linux2" != sys.platform
                 else images.Icon24x24_32bit)

    def __init__(self):
        wx.Frame.__init__(self, parent=None, title=conf.Title, size=conf.WindowSize)
        guibase.TemplateFrameMixIn.__init__(self)
        guibase.window = self

        ColourManager.Init(self, conf, {
            "FgColour":                wx.SYS_COLOUR_BTNTEXT,
            "BgColour":                wx.SYS_COLOUR_WINDOW,
            "DisabledColour":          wx.SYS_COLOUR_GRAYTEXT,
            "MainBgColour":            wx.SYS_COLOUR_WINDOW,
            "WidgetColour":            wx.SYS_COLOUR_BTNFACE,
        }, {
            "DBListForegroundColour":  wx.SYS_COLOUR_BTNTEXT,
            "DBListBackgroundColour":  wx.SYS_COLOUR_WINDOW,
            "GridRowInsertedColour":   wx.SYS_COLOUR_HIGHLIGHTTEXT,
            "GridRowChangedColour":    wx.SYS_COLOUR_GRAYTEXT,
            "GridCellChangedColour":   wx.RED,
            "LinkColour":              wx.SYS_COLOUR_HOTLIGHT,
            "TitleColour":             wx.SYS_COLOUR_HOTLIGHT,
            "MainBgColour":            wx.SYS_COLOUR_BTNFACE,
            "HelpCodeColour":          wx.SYS_COLOUR_HIGHLIGHT,
            "HelpBorderColour":        wx.SYS_COLOUR_ACTIVEBORDER,
        })
        self.dbs_selected = []  # Current selected files in main list
        self.db_datas = {}  # added DBs {filename: {size, last_modified,
                            #            tables, error},}
        self.dbs = {}       # Open databases {filename: Database, }
        self.db_pages = {}  # {DatabasePage: Database, }
        self.page_db_latest = None  # Last opened database page
        # List of Notebook pages user has visited, used for choosing page to
        # show when closing one.
        self.pages_visited = []

        icons = images.get_appicons()
        self.SetIcons(icons)

        panel = self.panel_main = wx.Panel(self)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        self.frame_console.SetIcons(icons)

        notebook = self.notebook = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=panel, style=wx.NB_TOP,
            agwStyle=wx.lib.agw.flatnotebook.FNB_NODRAG |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_FF2)
        ColourManager.Manage(notebook, "ActiveTabColour",        wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "ActiveTabTextColour",    wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(notebook, "NonActiveTabTextColour", wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(notebook, "TabAreaColour",          wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(notebook, "GradientColourBorder",   wx.SYS_COLOUR_BTNSHADOW)
        ColourManager.Manage(notebook, "GradientColourTo",       wx.SYS_COLOUR_ACTIVECAPTION)
        ColourManager.Manage(notebook, "ForegroundColour",       wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(notebook, "BackgroundColour",       wx.SYS_COLOUR_WINDOW)

        self.create_page_main(notebook)
        self.page_log = self.create_log_panel(notebook)
        notebook.AddPage(self.page_log, "Log")
        notebook.RemovePage(self.notebook.GetPageCount() - 1) # Hide log window
        # Kludge for being able to close log window repeatedly, as DatabasePage
        # get automatically deleted on closing.
        self.page_log.is_hidden = True

        sizer.Add(notebook, proportion=1, flag=wx.GROW | wx.RIGHT | wx.BOTTOM)
        self.create_menu()

        self.dialog_selectfolder = wx.DirDialog(
            parent=self,
            message="Choose a directory where to search for databases",
            defaultPath=os.getcwd(),
            style=wx.DD_DIR_MUST_EXIST | wx.RESIZE_BORDER)
        self.dialog_savefile = wx.FileDialog(
            parent=self, defaultDir=os.getcwd(), defaultFile="",
            style=wx.FD_SAVE | wx.RESIZE_BORDER)
        self.dialog_search = controls.EntryDialog(
            parent=self, title="Find in %s" % conf.Title, label="Search:",
            emptyvalue="Find in last database..",
            tooltip="Find in last database..")
        self.dialog_search.Bind(wx.EVT_COMMAND_ENTER, self.on_tray_search)
        if conf.SearchHistory and conf.SearchHistory[-1:] != [""]:
            self.dialog_search.Value = conf.SearchHistory[-1]
        self.dialog_search.SetChoices(list(filter(None, conf.SearchHistory)))
        self.dialog_search.SetIcons(icons)

        # Memory file system for showing images in wx.HtmlWindow
        self.memoryfs = {"files": {}, "handler": wx.MemoryFSHandler()}
        wx.FileSystem_AddHandler(self.memoryfs["handler"])
        self.load_fs_images()

        self.worker_detection = \
            workers.DetectDatabaseThread(self.on_detect_databases_callback)
        self.Bind(EVT_DETECTION_WORKER, self.on_detect_databases_result)
        self.Bind(EVT_OPEN_DATABASE, self.on_open_database_event)

        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)
        self.Bind(wx.EVT_CLOSE, self.on_exit)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOVE, self.on_move)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_page)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                      self.on_close_page)

        # Register Ctrl-F4 and Ctrl-W close and Ctrl-1..9 tab handlers
        def on_close_hotkey(event):
            notebook and notebook.DeletePage(notebook.GetSelection())
        def on_tab_hotkey(number, event):
            if notebook and notebook.GetSelection() != number \
            and number < notebook.GetPageCount():
                notebook.SetSelection(number)
                self.on_change_page(None)

        id_close = wx.NewId()
        accelerators = [(wx.ACCEL_CTRL, k, id_close) for k in (ord('W'), wx.WXK_F4)]
        for i in range(9):
            id_tab = wx.NewId()
            accelerators += [(wx.ACCEL_CTRL, ord(str(i + 1)), id_tab)]
            notebook.Bind(wx.EVT_MENU, functools.partial(on_tab_hotkey, i), id=id_tab)

        notebook.Bind(wx.EVT_MENU, on_close_hotkey, id=id_close)
        notebook.SetAcceleratorTable(wx.AcceleratorTable(accelerators))


        class FileDrop(wx.FileDropTarget):
            """A simple file drag-and-drop handler for application window."""
            def __init__(self, window):
                wx.FileDropTarget.__init__(self)
                self.window = window

            def OnDropFiles(self, x, y, filenames):
                # CallAfter to allow UI to clear up the dragged icons
                wx.CallAfter(self.ProcessFiles, filenames)

            def ProcessFiles(self, filenames):
                for filename in filenames:
                    self.window.update_database_list(filename)
                for filename in filenames:
                    self.window.load_database_page(filename)

        self.DropTarget = FileDrop(self)
        self.notebook.DropTarget = FileDrop(self)

        self.MinSize = conf.MinWindowSize
        if conf.WindowPosition and conf.WindowSize:
            if [-1, -1] != conf.WindowSize:
                self.Size = conf.WindowSize
                if not conf.WindowIconized:
                    self.Position = conf.WindowPosition
            else:
                self.Maximize()
        else:
            self.Center(wx.HORIZONTAL)
            self.Position.top = 50
        self.list_db.SetFocus()

        self.trayicon = wx.TaskBarIcon()
        if conf.TrayIconEnabled:
            self.trayicon.SetIcon(self.TRAY_ICON.Icon, conf.Title)
        self.trayicon.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.on_toggle_iconize)
        self.trayicon.Bind(wx.EVT_TASKBAR_LEFT_DOWN, self.on_open_tray_search)
        self.trayicon.Bind(wx.EVT_TASKBAR_RIGHT_DOWN, self.on_open_tray_menu)

        if conf.WindowIconized:
            conf.WindowIconized = False
            wx.CallAfter(self.on_toggle_iconize)
        else:
            self.Show(True)
        wx.CallLater(20000, self.update_check)
        wx.CallLater(0, self.populate_database_list)
        guibase.log("Started application.")


    def create_page_main(self, notebook):
        """Creates the main page with database list and buttons."""
        page = self.page_main = wx.Panel(notebook)
        ColourManager.Manage(page, "BackgroundColour", "MainBgColour")
        notebook.AddPage(page, "Databases")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer_list = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)

        label_count = self.label_count = wx.StaticText(page)
        edit_filter = self.edit_filter = controls.SearchCtrl(page, "Filter list")
        list_db = self.list_db = controls.SortableUltimateListCtrl(parent=page,
            agwStyle=wx.LC_REPORT | wx.BORDER_NONE)
        list_db.MinSize = 400, -1 # Maximize-restore would resize width to 100

        columns = [("name", "Name"), ("last_modified", "Modified"), ("size", "Size")]
        frmt_dt = lambda r, c: r[c].strftime("%Y-%m-%d %H:%M:%S") if r.get(c) else ""
        frmt_sz = lambda r, c: util.format_bytes(r[c]) if r.get(c) is not None else ""
        formatters = {"last_modified": frmt_dt, "size": frmt_sz}
        list_db.SetColumns(columns)
        list_db.SetColumnFormatters(formatters)
        list_db.SetColumnAlignment(2, wx.lib.agw.ultimatelistctrl.ULC_FORMAT_RIGHT)

        list_db.AssignImages([images.ButtonHome.Bitmap, images.ButtonListDatabase.Bitmap])
        ColourManager.Manage(list_db, "ForegroundColour", "DBListForegroundColour")
        ColourManager.Manage(list_db, "BackgroundColour", "DBListBackgroundColour")
        topdata = collections.defaultdict(lambda: None, name="Home")
        list_db.SetTopRow(topdata, [0])
        list_db.Select(0)

        panel_right = wx.lib.scrolledpanel.ScrolledPanel(page)
        panel_right.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        panel_main   = self.panel_db_main   = wx.Panel(panel_right)
        panel_detail = self.panel_db_detail = wx.Panel(panel_right)
        panel_main.MinSize   = 400, -1
        panel_detail.MinSize = 400, -1
        panel_main.Sizer   = wx.BoxSizer(wx.VERTICAL)
        panel_detail.Sizer = wx.BoxSizer(wx.VERTICAL)

        # Create main page label and buttons
        label_main = wx.StaticText(panel_main,
                                   label="Welcome to %s" % conf.Title)
        ColourManager.Manage(label_main, "ForegroundColour", "TitleColour")
        label_main.Font = wx.Font(14, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        BUTTONS_MAIN = [
            ("new", "&New database", images.ButtonNew,
             "Create a new SQLite database."),
            ("opena", "&Open a database..", images.ButtonOpenA,
             "Choose a database from your computer to open."),
            ("folder", "&Import from folder.", images.ButtonFolder,
             "Select a folder where to look for databases."),
            ("detect", "Detect databases", images.ButtonDetect,
             "Auto-detect databases from user folders."),
            ("missing", "Remove missing", images.ButtonRemoveMissing,
             "Remove non-existing files from the database list."),
            ("clear", "C&lear list", images.ButtonClear,
             "Clear the current database list."), ]
        for name, label, img, note in BUTTONS_MAIN:
            button = controls.NoteButton(panel_main, label, note, img.Bitmap)
            setattr(self, "button_" + name, button)
        self.button_missing.Hide(); self.button_clear.Hide()

        # Create detail page labels, values and buttons
        label_db = self.label_db = wx.TextCtrl(parent=panel_detail, value="",
            style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH)
        label_db.Font = wx.Font(12, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        ColourManager.Manage(label_db, "BackgroundColour", "WidgetColour")
        label_db.SetEditable(False)

        sizer_labels = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        LABELS = [("path", "Location"), ("size", "Size"),
                  ("modified", "Last modified"), ("tables", "Tables")]
        for field, title in LABELS:
            lbltext = wx.StaticText(parent=panel_detail, label="%s:" % title)
            valtext = wx.TextCtrl(parent=panel_detail, value="",
                                  size=(300, -1), style=wx.NO_BORDER)
            ColourManager.Manage(valtext, "BackgroundColour", "WidgetColour")
            ColourManager.Manage(valtext, "ForegroundColour", wx.SYS_COLOUR_WINDOWTEXT)
            valtext.SetEditable(False)
            ColourManager.Manage(lbltext, "ForegroundColour", "DisabledColour")
            sizer_labels.Add(lbltext, border=5, flag=wx.LEFT)
            sizer_labels.Add(valtext, proportion=1, flag=wx.GROW)
            setattr(self, "label_" + field, valtext)

        BUTTONS_DETAIL = [
            ("open", "&Open", images.ButtonOpen,
             "Open the database."),
            ("saveas", "Save &as..", images.ButtonSaveAs,
             "Save a copy of the database under another name."),
            ("remove", "Remove", images.ButtonRemove,
             "Remove this database from the list."), ]
        for name, label, img, note in BUTTONS_DETAIL:
            button = controls.NoteButton(panel_detail, label, note, img.Bitmap)
            setattr(self, "button_" + name, button)

        children = list(panel_main.Children) + list(panel_detail.Children)
        for c in [panel_main, panel_detail] + children:
            ColourManager.Manage(c, "BackgroundColour", "MainBgColour")
        panel_right.SetupScrolling(scroll_x=False)
        panel_detail.Hide()

        list_db.Bind(wx.EVT_LIST_ITEM_SELECTED,    self.on_select_list_db)
        list_db.Bind(wx.EVT_LIST_ITEM_DESELECTED,  self.on_deselect_list_db)
        list_db.Bind(wx.EVT_LIST_ITEM_ACTIVATED,   self.on_open_from_list_db)
        list_db.Bind(wx.EVT_CHAR_HOOK,             self.on_list_db_key)
        list_db.Bind(wx.EVT_LIST_COL_CLICK,        self.on_sort_list_db)
        list_db.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.on_rclick_list_db)
        list_db.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_END_DRAG, self.on_drag_list_db)

        edit_filter.Bind(wx.EVT_TEXT_ENTER,       self.on_filter_list_db)
        self.button_new.Bind(wx.EVT_BUTTON,       self.on_new_database)
        self.button_opena.Bind(wx.EVT_BUTTON,     self.on_open_database)
        self.button_detect.Bind(wx.EVT_BUTTON,    self.on_detect_databases)
        self.button_folder.Bind(wx.EVT_BUTTON,    self.on_add_from_folder)
        self.button_missing.Bind(wx.EVT_BUTTON,   self.on_remove_missing)
        self.button_clear.Bind(wx.EVT_BUTTON,     self.on_clear_databases)
        self.button_open.Bind(wx.EVT_BUTTON,      self.on_open_current_database)
        self.button_saveas.Bind(wx.EVT_BUTTON,    self.on_save_database_as)
        self.button_remove.Bind(wx.EVT_BUTTON,    self.on_remove_database)

        panel_main.Sizer.Add(label_main, border=10, flag=wx.ALL)
        panel_main.Sizer.Add((0, 10))
        panel_main.Sizer.Add(self.button_new,    flag=wx.GROW)
        panel_main.Sizer.Add(self.button_opena,  flag=wx.GROW)
        panel_main.Sizer.Add(self.button_folder, flag=wx.GROW)
        panel_main.Sizer.Add(self.button_detect, flag=wx.GROW)
        panel_main.Sizer.AddStretchSpacer()
        panel_main.Sizer.Add(self.button_missing, flag=wx.GROW)
        panel_main.Sizer.Add(self.button_clear,   flag=wx.GROW)
        panel_detail.Sizer.Add(label_db,     border=10, flag=wx.ALL | wx.GROW)
        panel_detail.Sizer.Add(sizer_labels, border=10, flag=wx.ALL | wx.GROW)
        panel_detail.Sizer.AddStretchSpacer()
        panel_detail.Sizer.Add(self.button_open,   flag=wx.GROW)
        panel_detail.Sizer.Add(self.button_saveas, flag=wx.GROW)
        panel_detail.Sizer.Add(self.button_remove, flag=wx.GROW)
        panel_right.Sizer.Add(panel_main,   proportion=1, flag=wx.GROW)
        panel_right.Sizer.Add(panel_detail, proportion=1, flag=wx.GROW)
        sizer_header.Add(label_count, flag=wx.ALIGN_BOTTOM)
        sizer_header.AddStretchSpacer()
        sizer_header.Add(edit_filter)
        sizer_list.Add(sizer_header, border=5, flag=wx.BOTTOM | wx.GROW)
        sizer_list.Add(list_db, proportion=1, flag=wx.GROW)
        sizer.Add(sizer_list,  border=10, proportion=6, flag=wx.ALL | wx.GROW)
        sizer.Add(panel_right, border=10, proportion=4, flag=wx.ALL | wx.GROW)


    def create_menu(self):
        """Creates the program menu."""
        menu = wx.MenuBar()
        self.SetMenuBar(menu)

        menu_file = wx.Menu()
        menu.Append(menu_file, "&File")

        menu_new_database = self.menu_new_database = menu_file.Append(
            id=wx.ID_ANY, text="&New database\tCtrl-N",
            help="Create a new SQLite database."
        )
        menu_open_database = self.menu_open_database = menu_file.Append(
            id=wx.ID_ANY, text="&Open database...\tCtrl-O",
            help="Choose a database file to open."
        )
        menu_recent = self.menu_recent = wx.Menu()
        menu_file.AppendMenu(id=wx.ID_ANY, text="&Recent databases",
            submenu=menu_recent, help="Recently opened databases.")
        menu_file.AppendSeparator()
        menu_options = self.menu_options = \
            menu_file.Append(id=wx.ID_ANY, text="&Advanced options",
                help="Edit advanced program options")
        menu_iconize = self.menu_iconize = \
            menu_file.Append(id=wx.ID_ANY, text="Minimize to &tray",
                help="Minimize %s window to notification area" % conf.Title)
        menu_exit = self.menu_exit = \
            menu_file.Append(id=wx.ID_ANY, text="E&xit\tAlt-X", help="Exit")

        menu_help = wx.Menu()
        menu.Append(menu_help, "&Help")

        menu_update = self.menu_update = menu_help.Append(id=wx.ID_ANY,
            text="Check for &updates",
            help="Check whether a new version of %s is available" % conf.Title)
        menu_homepage = self.menu_homepage = menu_help.Append(id=wx.ID_ANY,
            text="Go to &homepage",
            help="Open the %s homepage, %s" % (conf.Title, conf.HomeUrl))
        menu_help.AppendSeparator()
        menu_log = self.menu_log = menu_help.Append(id=wx.ID_ANY,
            kind=wx.ITEM_CHECK, text="Show &log window",
            help="Show/hide the log messages window")
        menu_console = self.menu_console = menu_help.Append(id=wx.ID_ANY,
            kind=wx.ITEM_CHECK, text="Show Python &console\tCtrl-E",
            help="Show/hide a Python shell environment window")
        menu_help.AppendSeparator()
        menu_tray = self.menu_tray = menu_help.Append(id=wx.ID_ANY,
            kind=wx.ITEM_CHECK, text="Display &icon in notification area",
            help="Show/hide %s icon in system tray" % conf.Title)
        menu_autoupdate_check = self.menu_autoupdate_check = menu_help.Append(
            id=wx.ID_ANY, kind=wx.ITEM_CHECK,
            text="Automatic up&date check",
            help="Automatically check for program updates periodically")
        menu_help.AppendSeparator()
        menu_about = self.menu_about = menu_help.Append(
            id=wx.ID_ANY, text="&About %s" % conf.Title,
            help="Show program information and copyright")

        self.history_file = wx.FileHistory(conf.MaxRecentFiles)
        self.history_file.UseMenu(menu_recent)
        # Reverse list, as FileHistory works like a stack
        [self.history_file.AddFileToHistory(f) for f in conf.RecentFiles[::-1]]
        wx.EVT_MENU_RANGE(self, wx.ID_FILE1, wx.ID_FILE1 + conf.MaxRecentFiles,
                          self.on_recent_file)
        menu_tray.Check(conf.TrayIconEnabled)
        menu_autoupdate_check.Check(conf.UpdateCheckAutomatic)

        self.Bind(wx.EVT_MENU, self.on_new_database, menu_new_database)
        self.Bind(wx.EVT_MENU, self.on_open_database, menu_open_database)
        self.Bind(wx.EVT_MENU, self.on_open_options, menu_options)
        self.Bind(wx.EVT_MENU, self.on_exit, menu_exit)
        self.Bind(wx.EVT_MENU, self.on_toggle_iconize, menu_iconize)
        self.Bind(wx.EVT_MENU, self.on_check_update, menu_update)
        self.Bind(wx.EVT_MENU, self.on_menu_homepage, menu_homepage)
        self.Bind(wx.EVT_MENU, self.on_showhide_log, menu_log)
        self.Bind(wx.EVT_MENU, self.on_showhide_console, menu_console)
        self.Bind(wx.EVT_MENU, self.on_toggle_trayicon, menu_tray)
        self.Bind(wx.EVT_MENU, self.on_toggle_autoupdate_check,
                  menu_autoupdate_check)
        self.Bind(wx.EVT_MENU, self.on_about, menu_about)


    def update_check(self):
        """
        Checks for an updated SQLiteMate version if sufficient time
        from last check has passed, and opens a dialog for upgrading
        if new version available. Schedules a new check on due date.
        """
        if not conf.UpdateCheckAutomatic:
            return
        interval = datetime.timedelta(days=conf.UpdateCheckInterval)
        due_date = datetime.datetime.now() - interval
        if not (conf.WindowIconized or support.update_window) \
        and conf.LastUpdateCheck < due_date.strftime("%Y%m%d"):
            callback = lambda resp: self.on_check_update_callback(resp, False)
            support.check_newest_version(callback)
        elif not support.update_window:
            try:
                dt = datetime.datetime.strptime(conf.LastUpdateCheck, "%Y%m%d")
                interval = (dt + interval) - datetime.datetime.now()
            except (TypeError, ValueError):
                pass
        # Schedule a check for due date, should the program run that long.
        millis = min(sys.maxint, util.timedelta_seconds(interval) * 1000)
        wx.CallLater(millis, self.update_check)


    def on_tray_search(self, event):
        """Handler for searching from tray dialog, launches search."""
        if self.dialog_search.Value.strip():
            self.dialog_search.Hide()
            if self.IsIconized() and not self.Shown:
                self.on_toggle_iconize()
            else:
                self.Iconize(False), self.Show(), self.Raise()
            page = self.page_db_latest
            if not page:
                if self.dbs_selected: # Load database focused in dblist
                    page = self.load_database_page(self.dbs_selected[-1])
                elif self.dbs: # Load an open database
                    page = self.load_database_page(list(self.dbs)[0])
                elif conf.RecentFiles:
                    page = self.load_database_page(conf.RecentFiles[0])
            if page:
                page.edit_searchall.Value = self.dialog_search.Value
                page.on_searchall(None)
                for i in range(self.notebook.GetPageCount()):
                    if self.notebook.GetPage(i) == page:
                        if self.notebook.GetSelection() != i:
                            self.notebook.SetSelection(i)
                            self.update_notebook_header()
                        break # break for i in range(self.notebook.GetPage..
            else:
                wx.MessageBox("No database to search from.", conf.Title)


    def on_toggle_iconize(self, event=None):
        """Handler for toggling main window to tray and back."""
        self.dialog_search.Hide()
        conf.WindowIconized = not conf.WindowIconized
        if conf.WindowIconized:
            self.Iconize(), self.Hide()
            conf.WindowPosition = self.Position[:]
            if not conf.TrayIconEnabled:
                conf.TrayIconEnabled = True
                self.trayicon.SetIcon(self.TRAY_ICON.Icon, conf.Title)
        else:
            self.Iconize(False), self.Show(), self.Raise()


    def on_toggle_trayicon(self, event=None):
        """
        Handler for toggling tray icon, removes or adds it to the tray area.

        @param   event  if not given or false, tray icon is toggled on
        """
        conf.TrayIconEnabled = event.IsChecked() if event else True
        self.menu_tray.Check(conf.TrayIconEnabled)
        if conf.TrayIconEnabled:
            self.trayicon.SetIcon(self.TRAY_ICON.Icon, conf.Title)
        else:
            self.trayicon.RemoveIcon()
        if conf.WindowIconized:
            self.on_toggle_iconize()


    def on_open_tray_search(self, event):
        """Opens the search entry dialog."""
        self.dialog_search.Show(not self.dialog_search.Shown)


    def on_open_tray_menu(self, event):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()
        item_search = wx.MenuItem(menu, -1, "&Search for..")
        font = item_search.Font
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        font.SetFaceName(self.Font.FaceName)
        font.SetPointSize(self.Font.PointSize)
        item_search.Font = font
        label = ["Minimize to", "Restore from"][conf.WindowIconized] + " &tray"
        item_toggle = wx.MenuItem(menu, -1, label)
        item_icon = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                text="Show &icon in notification area")
        item_console = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                   text="Show Python &console")
        item_exit = wx.MenuItem(menu, -1, "E&xit %s" % conf.Title)

        menu.AppendItem(item_search)
        menu.AppendItem(item_toggle)
        menu.AppendSeparator()
        menu.AppendItem(item_icon)
        menu.AppendItem(item_console)
        menu.AppendSeparator()
        menu.AppendItem(item_exit)
        item_icon.Check(True)
        item_console.Check(self.frame_console.Shown)

        menu.Bind(wx.EVT_MENU, self.on_open_tray_search, id=item_search.GetId())
        menu.Bind(wx.EVT_MENU, self.on_toggle_iconize, id=item_toggle.GetId())
        menu.Bind(wx.EVT_MENU, self.on_toggle_trayicon, id=item_icon.GetId())
        menu.Bind(wx.EVT_MENU, self.on_showhide_console, id=item_console.GetId())
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item_exit.GetId())
        self.trayicon.PopupMenu(menu)


    def on_change_page(self, event):
        """
        Handler for changing a page in the main Notebook, remembers the visit.
        """
        p = self.notebook.GetPage(self.notebook.GetSelection())
        if not self.pages_visited or self.pages_visited[-1] != p:
            self.pages_visited.append(p)
        self.Title = conf.Title
        if hasattr(p, "title"):
            subtitle = p.title
            if isinstance(p, DatabasePage): # Use parent/file.db or C:/file.db
                path, file = os.path.split(p.db.filename)
                subtitle = os.path.join(os.path.split(path)[-1] or path, file)
            self.Title += " - " + subtitle
        self.update_notebook_header()
        if event: event.Skip() # Pass event along to next handler


    def on_size(self, event):
        """Handler for window size event, tweaks controls and saves size."""
        conf.WindowSize = [-1, -1] if self.IsMaximized() else self.Size[:]
        conf.save()
        event.Skip()
        # Right panel scroll
        wx.CallAfter(lambda: self and (self.list_db.RefreshRows(),
                                       self.panel_db_main.Parent.Layout()))


    def on_move(self, event):
        """Handler for window move event, saves position."""
        conf.WindowPosition = event.Position[:]
        conf.save()
        event.Skip()


    def on_sys_colour_change(self, event):
        """Handler for system colour change, updates filesystem images."""
        event.Skip()
        wx.CallAfter(self.load_fs_images) # Postpone to allow conf update


    def load_fs_images(self):
        """Loads content to MemoryFS."""
        abouticon = "%s.png" % conf.Title.lower() # Program icon shown in About window
        raw = base64.b64decode(images.Icon48x48_32bit.data)
        if abouticon in self.memoryfs["files"]:
            self.memoryfs["handler"].RemoveFile(abouticon)
        self.memoryfs["handler"].AddFile(abouticon, raw, wx.BITMAP_TYPE_PNG)
        self.memoryfs["files"][abouticon] = 1

        # Screenshots look better with colouring if system has off-white colour
        tint_colour = wx.NamedColour(conf.BgColour)
        tint_factor = [((4 * x) % 256) / 255. for x in tint_colour]
        # Images shown on the default search content page
        for name in ["Search", "Tables", "SQL", "Pragma", "Info"]:
            embedded = getattr(images, "Help" + name, None)
            if not embedded: continue # for name
            img = embedded.Image.AdjustChannels(*tint_factor)
            raw = util.img_wx_to_raw(img)
            filename = "Help%s.png" % name
            if filename in self.memoryfs["files"]:
                self.memoryfs["handler"].RemoveFile(filename)
            self.memoryfs["handler"].AddFile(filename, raw, wx.BITMAP_TYPE_PNG)
            self.memoryfs["files"][filename] = 1


    def update_notebook_header(self):
        """
        Removes or adds X to notebook tab style, depending on whether current
        page can be closed.
        """
        if not self:
            return
        p = self.notebook.GetPage(self.notebook.GetSelection())
        style = self.notebook.GetAGWWindowStyleFlag()
        if isinstance(p, DatabasePage):
            if p.ready_to_close \
            and not (style & wx.lib.agw.flatnotebook.FNB_X_ON_TAB):
                style |= wx.lib.agw.flatnotebook.FNB_X_ON_TAB
            elif not p.ready_to_close \
            and (style & wx.lib.agw.flatnotebook.FNB_X_ON_TAB):
                style ^= wx.lib.agw.flatnotebook.FNB_X_ON_TAB
        elif self.page_log == p:
            style |= wx.lib.agw.flatnotebook.FNB_X_ON_TAB
        elif style & wx.lib.agw.flatnotebook.FNB_X_ON_TAB: # Hide close box
            style ^= wx.lib.agw.flatnotebook.FNB_X_ON_TAB  # on main page
        if style != self.notebook.GetAGWWindowStyleFlag():
            self.notebook.SetAGWWindowStyleFlag(style)


    def on_toggle_autoupdate_check(self, event):
        """Handler for toggling automatic update checking, changes conf."""
        conf.UpdateCheckAutomatic = event.IsChecked()
        conf.save()


    def on_list_db_key(self, event):
        """
        Handler for pressing a key in dblist, loads selected database on Enter,
        removes from list on Delete, refreshes columns on F5,
        focuses filter on Ctrl-F.
        """
        if event.KeyCode in [wx.WXK_F5]:
            items, selected_files, selected_home = [], [], False
            selected = self.list_db.GetFirstSelected()
            while selected >= 0:
                if selected:
                    selected_files.append(self.list_db.GetItemText(selected))
                else: selected_home = True
                selected = self.list_db.GetNextSelected(selected)

            for filename in conf.DBFiles:
                data = collections.defaultdict(lambda: None, name=filename)
                if os.path.exists(filename):
                    if filename in self.dbs:
                        self.dbs[filename].update_fileinfo()
                        data["size"] = self.dbs[filename].filesize
                        data["last_modified"] = self.dbs[filename].last_modified
                    else:
                        data["size"] = os.path.getsize(filename)
                        data["last_modified"] = datetime.datetime.fromtimestamp(
                                                os.path.getmtime(filename))
                self.db_datas[filename].update(data)
                items.append(data)
            self.list_db.Populate(items, [1])
            if selected_home: self.list_db.Select(0)
            if selected_files:
                for i in range(1, self.list_db.GetItemCount()):
                    if self.list_db.GetItemText(i) in selected_files:
                        self.list_db.Select(i)
                self.update_database_detail()
        elif event.KeyCode in [ord('F')] and event.ControlDown():
            self.edit_filter.SetFocus()
        elif self.list_db.GetFirstSelected() >= 0 and self.dbs_selected \
        and not event.AltDown() \
        and event.KeyCode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            for f in self.dbs_selected: self.load_database_page(f)
        elif event.KeyCode in [wx.WXK_DELETE] and self.dbs_selected:
            self.on_remove_database(None)
        event.Skip()


    def on_sort_list_db(self, event):
        """Handler for sorting dblist, saves sort state."""
        event.Skip()
        def save_sort_state():
            conf.DBSort = self.list_db.GetSortState()
            conf.save()
        wx.CallAfter(save_sort_state) # Allow list to update sort state


    def on_rclick_list_db(self, event):
        """Handler for right-clicking dblist, opens popup menu."""
        files, selecteds = [], []
        selected = self.list_db.GetFirstSelected()
        while selected >= 0:
            if selected:
                selecteds.append(selected)
                files.append(self.list_db.GetItemText(selected))
            selected = self.list_db.GetNextSelected(selected)
        if event.GetIndex() >= 0 and event.GetIndex() not in selecteds:
            if not event.GetIndex(): return # Home row
            files, selecteds = [event.GetText()], [event.GetIndex()]
        if not files: return

        def clipboard_copy(*a, **kw):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject("\n".join(files))
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
        def open_folder(*a, **kw):
            for f in files: util.start_file(os.path.split(f)[0])

        name = os.path.split(files[0])[-1] if len(files) == 1 \
               else util.plural("file", files)

        menu = wx.Menu()
        item_name    = wx.MenuItem(menu, -1, name)
        item_copy    = wx.MenuItem(menu, -1, "&Copy file path")
        item_folder  = wx.MenuItem(menu, -1, "Open file &directory")

        item_open    = wx.MenuItem(menu, -1, "&Open")
        item_save    = wx.MenuItem(menu, -1, "&Save as")
        item_remove  = wx.MenuItem(menu, -1, "&Remove from list")
        item_missing = wx.MenuItem(menu, -1, "Remove &missing from list")

        menu.Bind(wx.EVT_MENU, clipboard_copy,                id=item_copy.GetId())
        menu.Bind(wx.EVT_MENU, open_folder,                   id=item_folder.GetId())
        menu.Bind(wx.EVT_MENU, self.on_open_current_database, id=item_open.GetId())
        menu.Bind(wx.EVT_MENU, self.on_save_database_as,      id=item_save.GetId())
        menu.Bind(wx.EVT_MENU, self.on_remove_database,       id=item_remove.GetId())
        menu.Bind(wx.EVT_MENU, lambda e: self.on_remove_missing(event, selecteds),
                 id=item_missing.GetId())

        menu.AppendItem(item_name)
        menu.AppendSeparator()
        menu.AppendItem(item_copy)
        menu.AppendItem(item_folder)
        menu.AppendSeparator()
        menu.AppendItem(item_open)
        menu.AppendItem(item_save)
        menu.AppendItem(item_remove)
        menu.AppendItem(item_missing)

        wx.CallAfter(self.list_db.PopupMenu, menu)


    def on_drag_list_db(self, event):
        """Handler for dragging items around in dblist, saves file order."""
        event.Skip()
        def save_list_order():
            del conf.DBFiles[:]
            for i in range(self.list_db.GetItemCountFull()):
                conf.DBFiles.append(self.list_db.GetItemTextFull(i))
            conf.save()
        wx.CallAfter(save_list_order) # Allow list to update items


    def on_filter_list_db(self, event):
        """Handler for filtering dblist, applies search filter."""
        self.list_db.SetFilter(event.String.strip())
        event.Skip()
        self.update_database_count()


    def on_menu_homepage(self, event):
        """Handler for opening SQLiteMate webpage from menu,"""
        webbrowser.open(conf.HomeUrl)


    def on_about(self, event):
        """
        Handler for clicking "About SQLiteMate" menu, opens a small info frame.
        """
        maketext = lambda: step.Template(templates.ABOUT_HTML).expand()
        AboutDialog(self, "About %s" % conf.Title, maketext).ShowModal()


    def on_check_update(self, event):
        """
        Handler for checking for updates, starts a background process for
        checking for and downloading the newest version.
        """
        if not support.update_window:
            guibase.status("Checking for new version of %s.", conf.Title)
            wx.CallAfter(support.check_newest_version,
                         self.on_check_update_callback)
        elif hasattr(support.update_window, "Raise"):
            support.update_window.Raise()


    def on_check_update_callback(self, check_result, full_response=True):
        """
        Callback function for processing update check result, offers new
        version for download if available.

        @param   full_response  if False, show message only if update available
        """
        if not self:
            return
        support.update_window = True
        guibase.status("")
        if check_result:
            version, url, changes = check_result
            MAX = 1000
            changes = changes[:MAX] + ".." if len(changes) > MAX else changes
            guibase.status_flash("New %s version %s available.",
                              conf.Title, version)
            if wx.OK == wx.MessageBox(
                "Newer version (%s) available. You are currently on "
                "version %s.%s\nDownload and install %s %s?" %
                (version, conf.Version, "\n\n%s\n" % changes,
                 conf.Title, version),
                "Update information", wx.OK | wx.CANCEL | wx.ICON_INFORMATION
            ):
                wx.CallAfter(support.download_and_install, url)
        elif full_response and check_result is not None:
            wx.MessageBox("You are using the latest version of %s, %s.\n\n " %
                (conf.Title, conf.Version), "Update information",
                wx.OK | wx.ICON_INFORMATION)
        elif full_response:
            wx.MessageBox("Could not contact download server.",
                          "Update information", wx.OK | wx.ICON_WARNING)
        if check_result is not None:
            conf.LastUpdateCheck = datetime.date.today().strftime("%Y%m%d")
            conf.save()
        support.update_window = None


    def on_detect_databases(self, event):
        """
        Handler for clicking to auto-detect databases, starts the
        detection in a background thread.
        """
        if self.button_detect.FindFocus() == self.button_detect:
            self.list_db.SetFocus()
        guibase.logstatus("Searching local computer for databases..")
        self.button_detect.Enabled = False
        self.worker_detection.work(True)


    def on_detect_databases_callback(self, result):
        """Callback for DetectDatabaseThread, posts the data to self."""
        if self: # Check if instance is still valid (i.e. not destroyed by wx)
            wx.PostEvent(self, DetectionWorkerEvent(result=result))


    def on_detect_databases_result(self, event):
        """
        Handler for getting results from database detection thread, adds the
        results to the database list.
        """
        result = event.result
        if "filenames" in result:
            for f in result["filenames"]:
                if self.update_database_list(f):
                    guibase.log("Detected database %s.", f)
        if "count" in result:
            name = ("" if result["count"] else "additional ") + "database"
            guibase.logstatus_flash("Detected %s.",
                                  util.plural(name, result["count"]))
        if result.get("done", False):
            self.button_detect.Enabled = True
            wx.Bell()


    def populate_database_list(self):
        """
        Inserts all databases into the list, updates UI buttons.
        """
        items, selected_files = [], []
        for filename in conf.DBFiles:
            filename = util.to_unicode(filename)
            data = collections.defaultdict(lambda: None, name=filename)
            if os.path.exists(filename):
                data["size"] = os.path.getsize(filename)
                data["last_modified"] = datetime.datetime.fromtimestamp(
                                        os.path.getmtime(filename))
            self.db_datas[filename] = data
            items.append(data)
            if filename in conf.LastSelectedFiles: selected_files += [filename]

        self.list_db.Populate(items, [1])
        if conf.DBSort and conf.DBSort[0] >= 0:
            self.list_db.SortListItems(*conf.DBSort)

        if selected_files:
            idx = -1
            self.list_db.Select(0, on=False) # Deselect home row
            for i in range(1, self.list_db.GetItemCount()):
                if self.list_db.GetItemText(i) in selected_files:
                    if idx < 0: idx = i
                    self.list_db.Select(i)
                    self.list_db.SetFocus()

            if idx >= self.list_db.GetCountPerPage():
                lh = self.list_db.GetUserLineHeight()
                dy = (idx - self.list_db.GetCountPerPage() / 2) * lh
                self.list_db.ScrollList(0, dy)
                self.list_db.Update()

        self.button_missing.Show(bool(items))
        self.button_clear.Show(bool(items))
        self.update_database_count()
        self.panel_db_main.Layout()


    def update_database_list(self, filename=""):
        """
        Inserts the database into the list, if not there already, and updates
        UI buttons.

        @param   filename  possibly new filename, if any
        @return            True if was file was new or changed, False otherwise
        """
        result = False
        # Insert into database lists, if not already there
        if filename:
            filename = util.to_unicode(filename)
            if filename not in conf.DBFiles:
                conf.DBFiles.append(filename)
                conf.save()
            data = collections.defaultdict(lambda: None, name=filename)
            if os.path.exists(filename):
                if filename in self.dbs:
                    self.dbs[filename].update_fileinfo()
                    data["size"] = self.dbs[filename].filesize
                    data["last_modified"] = self.dbs[filename].last_modified
                else:
                    data["size"] = os.path.getsize(filename)
                    data["last_modified"] = datetime.datetime.fromtimestamp(
                                            os.path.getmtime(filename))
            data_old = self.db_datas.get(filename)
            if not data_old or data_old["size"] != data["size"] \
            or data_old["last_modified"] != data["last_modified"]:
                self.db_datas.setdefault(filename, {}).update(data)
                if not data_old: self.list_db.AppendRow(data, [1])
                result = True

        self.button_missing.Show(self.list_db.GetItemCount() > 1)
        self.button_clear.Show(self.list_db.GetItemCount() > 1)
        self.update_database_count()
        return result


    def update_database_count(self):
        """Updates database count label."""
        count, total = self.list_db.GetItemCount() - 1, len(self.db_datas)
        text = ""
        if total: text = util.plural("file", count)
        if count != total: text += " visible (%s in total)" % total
        self.label_count.Label = text


    def update_database_detail(self):
        """Updates database detail panel with current database information."""
        self.label_db.Value = self.label_path.Value = ""
        self.label_size.Value = self.label_modified.Value = ""
        self.label_tables.Value = ""
        self.label_tables.ForegroundColour = self.ForegroundColour
        self.label_size.ForegroundColour = self.ForegroundColour
        if not self.panel_db_detail.Shown:
            self.panel_db_main.Hide()
            self.panel_db_detail.Show()
            self.panel_db_detail.Parent.Layout()

        size = None
        for filename in self.dbs_selected:
            sz = os.path.getsize(filename) if os.path.exists(filename) else None
            if sz: size = (size or 0) + sz

            if len(self.dbs_selected) > 1:
                self.label_db.Value = "<%s files>" % len(self.dbs_selected)
            else:
                path, tail = os.path.split(filename)
                self.label_db.Value = tail
                self.label_path.Value = path

                if os.path.exists(filename):
                    dt = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
                    self.label_modified.Value = dt.strftime("%Y-%m-%d %H:%M:%S")
                    data = self.db_datas[filename]
                    if data["size"] == sz and data["last_modified"] == dt \
                    and data.get("tables") is not None:
                        # File does not seem changed: use cached values
                        self.label_tables.Value = data["tables"]
                    else:
                        wx.CallLater(10, self.update_database_stats, filename)
                else:
                    self.label_size.Value = "File does not exist."
                    self.label_size.ForegroundColour = conf.LabelErrorColour

        if size is not None: self.label_size.Value = util.format_bytes(size)



    def on_clear_databases(self, event):
        """Handler for clicking to clear the database list."""
        if (self.list_db.GetItemCount() > 1) and wx.OK == wx.MessageBox(
            "Are you sure you want to clear the list of all databases?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            self.list_db.Populate([])
            del conf.DBFiles[:]
            del conf.LastSelectedFiles[:]
            del conf.RecentFiles[:]
            conf.LastSearchResults.clear()
            while self.history_file.Count:
                self.history_file.RemoveFileFromHistory(0)
            del self.dbs_selected[:]
            self.db_datas.clear()
            conf.save()
            self.update_database_list()


    def on_save_database_as(self, event):
        """Handler for clicking to save a copy of a database in the list."""
        filenames = filter(os.path.exists, self.dbs_selected)
        if not filenames:
            m = "None of the selected files" if len(self.dbs_selected) > 1 \
                else "The file \"%s\" does not" % self.dbs_selected[0]
            return wx.MessageBox("%s exist on this computer." % m, conf.Title,
                                 wx.OK | wx.ICON_INFORMATION)

        dialog = wx.DirDialog(parent=self,
            message="Choose directory where to save databases",
            defaultPath=os.getcwd(),
            style=wx.DD_DIR_MUST_EXIST | wx.RESIZE_BORDER
        ) if len(filenames) > 1 else wx.FileDialog(parent=self,
            message="Save a copy..",
            defaultDir=os.path.split(filenames[0])[0],
            defaultFile=os.path.basename(filenames[0]),
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        path = dialog.GetPath()
        wx.YieldIfNeeded() # Allow UI to refresh

        for filename in filenames:
            _, basename = os.path.split(filename)
            newpath = os.path.join(path, basename) if len(filenames) > 1 else path
            try: shutil.copyfile(filename, newpath)
            except Exception as e:
                guibase.log("%r when trying to copy %s to %s.",
                         e, basename, newpath)
                wx.MessageBox("Failed to copy \"%s\" to \"%s\"." %
                              (basename, newpath), conf.Title,
                              wx.OK | wx.ICON_WARNING)
            else:
                guibase.logstatus_flash("Saved a copy of %s as %s.",
                                        filename, newpath)
                self.update_database_list(newpath)


    def on_remove_database(self, event):
        """Handler for clicking to remove an item from the database list."""
        if not self.dbs_selected: return

        m = "%s files" % len(self.dbs_selected)
        if len(self.dbs_selected) == 1: m = self.dbs_selected[0]
        if wx.OK == wx.MessageBox(
            "Remove %s from database list?" % m,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            for filename in self.dbs_selected:
                for lst in conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles:
                    if filename in lst: lst.remove(filename)
                for dct in conf.LastSearchResults, self.db_datas:
                    dct.pop(filename, None)
            for i in range(self.list_db.GetItemCount())[::-1]:
                if self.list_db.GetItemText(i) in self.dbs_selected:
                    self.list_db.DeleteItem(i)
            # Remove from recent file history
            historyfiles = [(i, self.history_file.GetHistoryFile(i))
                            for i in range(self.history_file.Count)]
            for i in [i for i, f in historyfiles if f in self.dbs_selected][::-1]:
                self.history_file.RemoveFileFromHistory(i)
            del self.dbs_selected[:]
            self.list_db.Select(0)
            self.update_database_list()
            conf.save()


    def on_remove_missing(self, event, selecteds=None):
        """Handler to remove nonexistent files from the database list."""
        selecteds = selecteds or range(1, self.list_db.GetItemCount())
        filter_func = lambda i: not os.path.exists(self.list_db.GetItemText(i))
        selecteds = list(filter(filter_func, selecteds))
        filenames = list(map(self.list_db.GetItemText, selecteds))
        for i in range(len(selecteds)):
            # - i, as item count is getting smaller one by one
            selected = selecteds[i] - i
            filename = self.list_db.GetItemText(selected)
            for lst in (conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles,
                        self.dbs_selected):
                if filename in lst: lst.remove(filename)
            for dct in conf.LastSearchResults, self.db_datas:
                dct.pop(filename, None)
            self.list_db.DeleteItem(selected)
        self.update_database_list()
        if self.dbs_selected: self.update_database_detail()
        else: self.list_db.Select(0)

        if not selecteds: return
        # Remove from recent file history
        historyfiles = [(i, self.history_file.GetHistoryFile(i))
                        for i in range(self.history_file.Count)]
        for i, f in historyfiles[::-1]: # Work upwards to have unchanged index
            if f in filenames: self.history_file.RemoveFileFromHistory(i)
        conf.save()


    def on_showhide_log(self, event):
        """Handler for clicking to show/hide the log window."""
        if self.notebook.GetPageIndex(self.page_log) < 0:
            self.notebook.AddPage(self.page_log, "Log")
            self.page_log.is_hidden = False
            self.page_log.Show()
            self.notebook.SetSelection(self.notebook.GetPageCount() - 1)
            self.on_change_page(None)
            self.menu_log.Check(True)
        elif self.notebook.GetPageIndex(self.page_log) != self.notebook.GetSelection():
            self.notebook.SetSelection(self.notebook.GetPageCount() - 1)
            self.on_change_page(None)
            self.menu_log.Check(True)
        else:
            self.page_log.is_hidden = True
            self.notebook.RemovePage(self.notebook.GetPageIndex(self.page_log))
            self.menu_log.Check(False)


    def on_open_options(self, event):
        """
        Handler for opening advanced options, creates the property dialog
        and saves values.
        """
        dialog = controls.PropertyDialog(self, title="Advanced options")
        def get_field_doc(name, tree=ast.parse(inspect.getsource(conf))):
            """Returns the docstring immediately before name assignment."""
            for i, node in enumerate(tree.body):
                if i and ast.Assign == type(node) and node.targets[0].id == name:
                    prev = tree.body[i - 1]
                    if ast.Expr == type(prev) and ast.Str == type(prev.value):
                        return prev.value.s.strip()
            return ""

        def typelist(mytype):
            def convert(v):
                v = ast.literal_eval(v) if isinstance(v, basestring) else v
                if not isinstance(v, (list, tuple)): v = tuple([v])
                if not v: raise ValueError("Empty collection")
                return tuple(map(mytype, v))
            convert.__name__ = "tuple(%s)" % mytype.__name__
            return convert

        for name in sorted(conf.OptionalFileDirectives):
            value, help = getattr(conf, name, None), get_field_doc(name)
            default = conf.OptionalFileDirectiveDefaults.get(name)
            if value is None and default is None:
                continue # continue for name

            kind = type(value)
            if isinstance(value, (tuple, list)):
                kind = typelist(type(value[0]))
                default = kind(default)
            dialog.AddProperty(name, value, help, default, kind)
        dialog.Realize()

        if wx.ID_OK == dialog.ShowModal():
            for k, v in dialog.GetProperties():
                # Keep numbers in sane regions
                if type(v) in [int, long]: v = max(1, min(sys.maxint, v))
                setattr(conf, k, v)
            conf.save()
            self.MinSize = conf.MinWindowSize


    def on_open_database(self, event):
        """
        Handler for open database menu or button, displays a file dialog and
        loads the chosen database.
        """
        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.FileDialog(
            parent=self, message="Open", defaultFile="", wildcard=wildcard,
            style=wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE | wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK == dialog.ShowModal():
            for filename in dialog.GetPaths():
                self.update_database_list(filename)
                self.load_database_page(filename)


    def on_new_database(self, event):
        """
        Handler for new database menu or button, displays a save file dialog,
        creates and loads the chosen database.
        """
        self.dialog_savefile.Filename = "database"
        self.dialog_savefile.Message = "Save new database as"
        exts = ";".join("*" + x for x in conf.DBExtensions)
        self.dialog_savefile.Wildcard = "SQLite database (%s)|%s" % (exts, exts)
        self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
        if wx.ID_OK != self.dialog_savefile.ShowModal():
            return

        filename = self.dialog_savefile.GetPath()
        try:
            with open(filename, "w"): pass
        except Exception:
            guibase.log("Error creating %s.\n\n%s", filename,
                     traceback.format_exc())
            wx.MessageBox(
                "Could not create %s.\n\n"
                "Some other process may be using the file."
                % filename, conf.Title, wx.OK | wx.ICON_WARNING)
        else:
            self.update_database_list(filename)
            self.load_database_page(filename)


    def on_open_database_event(self, event):
        """
        Handler for OpenDatabaseEvent, updates db list and loads the event
        database.
        """
        filename = os.path.realpath(event.file)
        self.update_database_list(filename)
        self.load_database_page(filename)


    def on_recent_file(self, event):
        """Handler for clicking an entry in Recent Files menu."""
        filename = self.history_file.GetHistoryFile(event.Id - wx.ID_FILE1)
        self.update_database_list(filename)
        self.load_database_page(filename)


    def on_add_from_folder(self, event):
        """
        Handler for clicking to select folder where to search for databases,
        updates database list.
        """
        if self.dialog_selectfolder.ShowModal() == wx.ID_OK:
            if self.button_folder.FindFocus() == self.button_folder:
                self.list_db.SetFocus()
            self.button_folder.Enabled = False
            folder = self.dialog_selectfolder.GetPath()
            guibase.logstatus("Detecting databases under %s.", folder)
            wx.YieldIfNeeded()
            count = 0
            for filename in database.find_databases(folder):
                if filename not in self.db_datas:
                    guibase.log("Detected database %s.", filename)
                    self.update_database_list(filename)
                    count += 1
            self.button_folder.Enabled = True
            self.list_db.RefreshRows()
            guibase.logstatus_flash("Detected %s under %s.",
                util.plural("new database", count), folder)


    def on_open_current_database(self, event):
        """Handler for clicking to open selected files from database list."""
        for f in self.dbs_selected: self.load_database_page(f)


    def on_open_from_list_db(self, event):
        """Handler for clicking to open selected files from database list."""
        if event.GetIndex() > 0:
            self.load_database_page(event.GetText())


    def update_database_stats(self, filename):
        """Opens the database and updates main page UI with database info."""
        db = None
        try:
            db = self.dbs.get(filename) or database.Database(filename)
        except Exception as e:
            self.label_tables.Value = util.format_exc(e)
            self.label_tables.ForegroundColour = conf.LabelErrorColour
            guibase.log("Error opening %s.\n\n%s", filename,
                     traceback.format_exc())
            return
        try:
            tables = db.get_tables()
            self.label_tables.Value = str(len(tables))
            if tables:
                s = ""
                for t in tables:
                    s += (", " if s else "") + database.Database.quote(t["name"])
                    if len(s) > 40:
                        s += ", .."
                        break # for t
                self.label_tables.Value += " (%s)" % s

            data = self.db_datas.get(filename, {})
            data["tables"] = self.label_tables.Value
        except Exception as e:
            self.label_tables.Value = util.format_exc(e)
            self.label_tables.ForegroundColour = conf.LabelErrorColour
            guibase.log("Error loading data from %s.\n\n%s", filename,
                     traceback.format_exc())
        if db and not db.has_consumers():
            db.close()
            if filename in self.dbs:
                del self.dbs[filename]


    def on_select_list_db(self, event):
        """Handler for selecting an item in main list, updates info panel."""
        if event.GetIndex() > 0 \
        and event.GetText() not in self.dbs_selected:
            self.dbs_selected.append(event.GetText())
            conf.LastSelectedFiles[:] = self.dbs_selected[:]
            self.update_database_detail()
        elif event.GetIndex() == 0 and not self.dbs_selected \
        and not self.panel_db_main.Shown:
            self.panel_db_main.Show()
            self.panel_db_detail.Hide()
            self.panel_db_main.Parent.Layout()


    def on_deselect_list_db(self, event):
        """Handler for deselecting an item in main list, updates info panel."""
        if not self.dbs_selected or not event.GetIndex(): return

        filename = event.GetText()
        self.dbs_selected = [x for x in self.dbs_selected if x != filename]
        conf.LastSelectedFiles[:] = self.dbs_selected[:]

        if self.dbs_selected:
            self.update_database_detail()
        else:
            self.panel_db_main.Show()
            self.panel_db_detail.Hide()
            self.panel_db_main.Parent.Layout()


    def on_exit(self, event):
        """
        Handler on application exit, asks about unsaved changes, if any.
        """
        do_exit = True
        unsaved_pages = {} # {DatabasePage: filename, }
        for page, db in self.db_pages.items():
            if page and page.get_unsaved_grids():
                unsaved_pages[page] = db.filename
        if unsaved_pages:
            response = wx.MessageBox(
                "There are unsaved changes in data grids\n(%s).\n\n"
                "Save changes before closing?" %
                "\n".join(textwrap.wrap(", ".join(unsaved_pages.values()))),
                conf.Title, wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION
            )
            do_exit = (wx.CANCEL != response)
            if wx.YES == response:
                do_exit = all(p.save_unsaved_grids() for p in unsaved_pages)
        if do_exit:
            for page in self.db_pages:
                if not page: continue # continue for page, if dead object
                active_idx = page.notebook.Selection
                if active_idx:
                    conf.LastActivePage[page.db.filename] = active_idx
                elif page.db.filename in conf.LastActivePage:
                    del conf.LastActivePage[page.db.filename]
                page.save_page_conf()
                for worker in page.workers_search.values(): worker.stop()
            self.worker_detection.stop()

            # Save last selected files in db lists, to reselect them on rerun
            conf.LastSelectedFiles[:] = self.dbs_selected[:]
            if not conf.WindowIconized: conf.WindowPosition = self.Position[:]
            conf.WindowSize = [-1, -1] if self.IsMaximized() else self.Size[:]
            conf.save()
            self.trayicon.Destroy()
            sys.exit()


    def on_close_page(self, event):
        """
        Handler for closing a page, asks the user about saving unsaved data,
        if any, removes page from main notebook and updates accelerators.
        """
        if event.EventObject == self.notebook:
            page = self.notebook.GetPage(event.GetSelection())
        else:
            page = event.EventObject
            page.Show(False)
        if self.page_log == page:
            if not self.page_log.is_hidden:
                event.Veto() # Veto delete event
                self.on_showhide_log(None) # Fire remove event
            self.pages_visited = [x for x in self.pages_visited if x != page]
            self.page_log.Show(False)
            return
        elif (not isinstance(page, DatabasePage) or not page.ready_to_close):
            return event.Veto()

        # Remove page from MainWindow data structures
        do_close = True
        unsaved = page.get_unsaved_grids()
        if unsaved:
            response = wx.MessageBox(
                "Some tables in %s have unsaved data (%s).\n\n"
                "Save changes before closing?" % (
                    page.db, ", ".join(sorted(x.table for x in unsaved))
                ), conf.Title,
                wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION
            )
            if wx.YES == response:
                do_close = page.save_unsaved_grids()
            elif wx.CANCEL == response:
                do_close = False
        if not do_close:
            return event.Veto()

        if page.notebook.Selection:
            conf.LastActivePage[page.db.filename] = page.notebook.Selection
        elif page.db.filename in conf.LastActivePage:
            del conf.LastActivePage[page.db.filename]

        for worker in page.workers_search.values(): worker.stop()
        page.save_page_conf()

        if page in self.db_pages:
            del self.db_pages[page]
        guibase.log("Closed database tab for %s." % page.db)
        conf.save()

        # Close databases, if not used in any other page
        page.db.unregister_consumer(page)
        if not page.db.has_consumers():
            if page.db.filename in self.dbs:
                del self.dbs[page.db.filename]
            page.db.close()
            guibase.log("Closed database %s." % page.db)
        # Remove any dangling references
        if self.page_db_latest == page:
            self.page_db_latest = next((i for i in self.pages_visited[::-1]
                                        if isinstance(i, DatabasePage)), None)
        self.SendSizeEvent() # Multiline wx.Notebooks need redrawing
        self.UpdateAccelerators() # Remove page accelerators

        # Remove page from visited pages order
        self.pages_visited = [x for x in self.pages_visited if x != page]
        index_new = 0
        if self.pages_visited:
            for i in range(self.notebook.GetPageCount()):
                if self.notebook.GetPage(i) == self.pages_visited[-1]:
                    index_new = i
                    break
        self.notebook.SetSelection(index_new)


    def on_clear_searchall(self, event):
        """
        Handler for clicking to clear search history in a database page,
        confirms action and clears history globally.
        """
        choice = wx.MessageBox("Clear search history?", conf.Title,
                               wx.OK | wx.CANCEL | wx.ICON_WARNING)
        if wx.OK == choice:
            conf.SearchHistory = []
            for page in self.db_pages:
                page.edit_searchall.SetChoices(conf.SearchHistory)
                page.edit_searchall.ShowDropDown(False)
                page.edit_searchall.Value = ""
            self.dialog_search.SetChoices(conf.SearchHistory)
            conf.save()


    def get_unique_tab_title(self, title):
        """
        Returns a title that is unique for the current notebook - if the
        specified title already exists, appends a counter to the end,
        e.g. "Database comparison (1)". Title is shortened from the left
        if longer than allowed.
        """
        if len(title) > conf.MaxTabTitleLength:
            title = "..%s" % title[-conf.MaxTabTitleLength:]
        unique = title_base = title
        all_titles = [self.notebook.GetPageText(i)
                      for i in range(self.notebook.GetPageCount())]
        i = 1 # Start counter from 1
        while unique in all_titles:
            unique = "%s (%d)" % (title_base, i)
            i += 1
        return unique


    def load_database(self, filename):
        """
        Tries to load the specified database, if not already open, and returns
        it.
        """
        db = self.dbs.get(filename)
        if not db:
            db = None
            if os.path.exists(filename):
                try:
                    db = database.Database(filename)
                except Exception:
                    is_accessible = False
                    try:
                        with open(filename, "rb"):
                            is_accessible = True
                    except Exception:
                        pass
                    if not is_accessible:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Some other process may be using the file."
                            % filename, conf.Title, wx.OK | wx.ICON_WARNING)
                    else:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Not a valid SQLITE database?" % filename,
                            conf.Title, wx.OK | wx.ICON_WARNING)
                if db:
                    guibase.log("Opened %s (%s).", db, util.format_bytes(
                             db.filesize))
                    guibase.status_flash("Reading database file %s.", db)
                    self.dbs[filename] = db
                    # Add filename to Recent Files menu and conf, if needed
                    if filename in conf.RecentFiles: # Remove earlier position
                        idx = conf.RecentFiles.index(filename)
                        try: self.history_file.RemoveFileFromHistory(idx)
                        except Exception: pass
                    self.history_file.AddFileToHistory(filename)
                    util.add_unique(conf.RecentFiles, filename, -1,
                                    conf.MaxRecentFiles)
                    conf.save()
            else:
                wx.MessageBox("Nonexistent file: %s." % filename,
                              conf.Title, wx.OK | wx.ICON_WARNING)
        return db


    def load_database_page(self, filename):
        """
        Tries to load the specified database, if not already open, create a
        subpage for it, if not already created, and focuses the subpage.

        @return  database page instance
        """
        db = None
        page = None
        if filename in self.dbs:
            db = self.dbs[filename]
        if db and db in self.db_pages.values():
            page = next((x for x in self.db_pages if x and x.db == db), None)
        if not page:
            if not db:
                db = self.load_database(filename)
            if db:
                guibase.status_flash("Opening database file %s." % db)
                tab_title = self.get_unique_tab_title(db.filename)
                page = DatabasePage(self.notebook, tab_title, db, self.memoryfs)
                self.db_pages[page] = db
                self.UpdateAccelerators()
                conf.save()
                self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS,
                          self.on_clear_searchall, page.edit_searchall)
        if page:
            self.list_db.Select(0, on=False) # Deselect home row
            for i in range(1, self.list_db.GetItemCount()):
                if self.list_db.GetItemText(i) == filename:
                    self.list_db.Select(i)
                    break # break for i
            for i in range(self.notebook.GetPageCount()):
                if self.notebook.GetPage(i) == page:
                    self.notebook.SetSelection(i)
                    self.update_notebook_header()
                    break # break for i in range(self.notebook..)
        return page



class DatabasePage(wx.Panel):
    """
    A wx.Notebook page for managing a single database file, has its own
    Notebook with a number of pages for searching, browsing, SQL, information.
    """

    def __init__(self, parent_notebook, title, db, memoryfs):
        wx.Panel.__init__(self, parent=parent_notebook)
        self.parent_notebook = parent_notebook
        self.title = title

        self.pageorder = {} # {page: notebook index, }
        self.ready_to_close = False
        self.db = db
        self.db.register_consumer(self)
        self.db_grids = {} # {"tablename": SqliteGridBase, }
        self.pragma         = db.get_pragma_values() # {pragma_name: value}
        self.pragma_changes = {} # {pragma_name: value}
        self.pragma_ctrls   = {} # {pragma_name: wx component}
        self.pragma_edit = False # Whether in PRAGMA edit mode
        self.memoryfs = memoryfs
        parent_notebook.InsertPage(1, self, title)
        busy = controls.BusyPanel(self, "Loading \"%s\"." % db.filename)
        self.counter = lambda x={"c": 0}: x.update(c=1+x["c"]) or x["c"]
        ColourManager.Manage(self, "BackgroundColour", "WidgetColour")
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)

        # Create search structures and threads
        self.Bind(EVT_WORKER, self.on_searchall_result)
        self.workers_search = {} # {search ID: workers.SearchThread, }
        self.search_data_contact = {"id": None} # Current contacts search data

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        label_title = self.label_title = wx.StaticText(parent=self, label="")
        sizer_header.Add(label_title, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_header.AddStretchSpacer()


        self.label_search = wx.StaticText(self, -1, "&Search in messages:")
        sizer_header.Add(self.label_search, border=5,
                         flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        edit_search = self.edit_searchall = controls.TextCtrlAutoComplete(
            self, description=conf.SearchDescription,
            size=(300, -1), style=wx.TE_PROCESS_ENTER)
        self.Bind(wx.EVT_TEXT_ENTER, self.on_searchall, edit_search)
        tb = self.tb_search = wx.ToolBar(parent=self,
                                         style=wx.TB_FLAT | wx.TB_NODIVIDER)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR,
                                       (16, 16))
        tb.SetToolBitmapSize(bmp.Size)
        tb.AddLabelTool(wx.ID_FIND, "", bitmap=bmp, shortHelp="Start search")
        tb.Realize()
        self.Bind(wx.EVT_TOOL, self.on_searchall, id=wx.ID_FIND)
        sizer_header.Add(edit_search, border=5,
                     flag=wx.RIGHT | wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_header.Add(tb, flag=wx.ALIGN_RIGHT | wx.GROW)
        sizer.Add(sizer_header,
                  border=5, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.GROW)
        sizer.Layout() # To avoid searchbox moving around during page creation

        bookstyle = wx.lib.agw.fmresources.INB_LEFT
        if (wx.version().startswith("2.8") and sys.version_info.major == 2
        and sys.version_info < (2, 7, 3)):
            # wx 2.8 + Python below 2.7.3: labelbook can partly cover tab area
            bookstyle |= wx.lib.agw.fmresources.INB_FIT_LABELTEXT
        notebook = self.notebook = wx.lib.agw.labelbook.FlatImageBook(
            parent=self, agwStyle=bookstyle, style=wx.BORDER_STATIC)

        il = wx.ImageList(32, 32)
        idx1 = il.Add(images.PageSearch.Bitmap)
        idx2 = il.Add(images.PageTables.Bitmap)
        idx3 = il.Add(images.PageSQL.Bitmap)
        idx4 = il.Add(images.PagePragma.Bitmap)
        idx5 = il.Add(images.PageInfo.Bitmap)
        notebook.AssignImageList(il)

        self.create_page_search(notebook)
        self.create_page_tables(notebook)
        self.create_page_sql(notebook)
        self.create_page_pragma(notebook)
        self.create_page_info(notebook)

        notebook.SetPageImage(0, idx1)
        notebook.SetPageImage(1, idx2)
        notebook.SetPageImage(2, idx3)
        notebook.SetPageImage(3, idx4)
        notebook.SetPageImage(4, idx5)

        sizer.Add(notebook, proportion=1, border=5, flag=wx.GROW | wx.ALL)

        self.dialog_savefile = wx.FileDialog(
            parent=self,
            defaultDir=os.getcwd(),
            defaultFile="",
            style=wx.FD_SAVE | wx.RESIZE_BORDER)

        self.TopLevelParent.page_db_latest = self
        self.TopLevelParent.run_console(
            "page = self.page_db_latest # Database tab")
        self.TopLevelParent.run_console("db = page.db # SQLite database wrapper")

        self.Layout()
        # Hack to get info-page multiline TextCtrls to layout without quirks.
        self.notebook.SetSelection(self.pageorder[self.page_info])
        self.notebook.SetSelection(self.pageorder[self.page_search])
        # Restore last active page
        if db.filename in conf.LastActivePage \
        and conf.LastActivePage[db.filename] != self.notebook.Selection:
            self.notebook.SetSelection(conf.LastActivePage[db.filename])

        try:
            self.load_data()
        finally:
            busy.Close()
        self.edit_searchall.SetFocus()
        wx.CallAfter(self.edit_searchall.SelectAll)
        if "linux2" == sys.platform and wx.version().startswith("2.8"):
            wx.CallAfter(self.split_panels)


    def create_page_search(self, notebook):
        """Creates a page for searching the database."""
        page = self.page_search = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Search")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_top = wx.BoxSizer(wx.HORIZONTAL)

        label_html = self.label_html = \
            wx.html.HtmlWindow(page, style=wx.html.HW_SCROLLBAR_NEVER)
        label_html.SetFonts(normal_face=self.Font.FaceName,
                            fixed_face=self.Font.FaceName, sizes=[8] * 7)
        label_html.SetPage(step.Template(templates.SEARCH_HELP_SHORT).expand())
        label_html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNFACE)
        label_html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)

        tb = self.tb_search_settings = \
            wx.ToolBar(parent=page, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        tb.SetToolBitmapSize((24, 24))
        tb.AddRadioTool(wx.ID_INDEX, bitmap=images.ToolbarTitle.Bitmap,
            shortHelp="Search in table and column names and types")
        tb.AddRadioTool(wx.ID_STATIC, bitmap=images.ToolbarTables.Bitmap,
            shortHelp="Search in all columns of all database tables")
        tb.AddSeparator()
        tb.AddCheckTool(wx.ID_NEW, bitmap=images.ToolbarTabs.Bitmap,
            shortHelp="New tab for each search  (Alt-N)", longHelp="")
        tb.AddSimpleTool(wx.ID_STOP, bitmap=images.ToolbarStopped.Bitmap,
            shortHelpString="Stop current search, if any")
        tb.Realize()
        tb.ToggleTool(wx.ID_INDEX, conf.SearchInNames)
        tb.ToggleTool(wx.ID_STATIC, conf.SearchInTables)
        tb.ToggleTool(wx.ID_NEW, conf.SearchUseNewTab)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_INDEX)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_STATIC)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_NEW)
        self.Bind(wx.EVT_TOOL, self.on_searchall_stop, id=wx.ID_STOP)

        self.label_search.Label = "&Search in database:"
        if conf.SearchInNames:
            self.label_search.Label = "&Search in table and column names and types:"

        html = self.html_searchall = controls.TabbedHtmlWindow(parent=page)
        default = step.Template(templates.SEARCH_WELCOME_HTML).expand()
        html.SetDefaultPage(default)
        html.SetDeleteCallback(self.on_delete_tab_callback)
        label_html.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                        self.on_click_html_link)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                  self.on_click_html_link)
        html._html.Bind(wx.EVT_RIGHT_UP, self.on_rightclick_searchall)
        html.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_searchall_tab)
        html.Bind(controls.EVT_TAB_LEFT_DCLICK, self.on_dclick_searchall_tab)
        ColourManager.Manage(html, "TabAreaColour", "WidgetColour")
        html.Font.PixelSize = (0, 8)

        sizer_top.Add(label_html, proportion=1, flag=wx.GROW)
        sizer_top.Add(tb, border=5, flag=wx.TOP | wx.RIGHT |
                      wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        sizer.Add(sizer_top, border=5, flag=wx.TOP | wx.RIGHT | wx.GROW)
        sizer.Add(html, border=5, proportion=1,
                  flag=wx.GROW | wx.LEFT | wx.RIGHT | wx.BOTTOM)
        wx.CallAfter(label_html.Show)


    def create_page_tables(self, notebook):
        """Creates a page for listing and browsing tables."""
        page = self.page_tables = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Data")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = self.splitter_tables = wx.SplitterWindow(
            parent=page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(100)

        panel1 = wx.Panel(parent=splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_topleft = wx.BoxSizer(wx.HORIZONTAL)
        sizer_topleft.Add(wx.StaticText(parent=panel1, label="&Tables:"),
                          flag=wx.ALIGN_CENTER_VERTICAL)
        button_refresh = self.button_refresh_tables = \
            wx.Button(panel1, label="Refresh")
        sizer_topleft.AddStretchSpacer()
        sizer_topleft.Add(button_refresh)
        tree = self.tree_tables = wx.gizmos.TreeListCtrl(
            parent=panel1,
            style=wx.TR_DEFAULT_STYLE
            #| wx.TR_HAS_BUTTONS
            #| wx.TR_TWIST_BUTTONS
            #| wx.TR_ROW_LINES
            #| wx.TR_COLUMN_LINES
            #| wx.TR_NO_LINES
            | wx.TR_FULL_ROW_HIGHLIGHT
        )
        ColourManager.Manage(tree, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(tree, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)

        tree.AddColumn("Table")
        tree.AddColumn("Info")
        tree.AddRoot("Loading data..")
        tree.SetMainColumn(0)
        tree.SetColumnAlignment(1, wx.ALIGN_RIGHT)
        self.Bind(wx.EVT_BUTTON, self.on_refresh_tables, button_refresh)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_change_tree_tables, tree)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_rclick_tree_tables, tree)

        sizer1.Add(sizer_topleft, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer1.Add(tree, proportion=1,
                   border=5, flag=wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM)

        panel2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_tb = wx.BoxSizer(wx.HORIZONTAL)
        tb = self.tb_grid = wx.ToolBar(
            parent=panel2, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp_tb = images.ToolbarInsert.Bitmap
        tb.SetToolBitmapSize(bmp_tb.Size)
        tb.AddLabelTool(id=wx.ID_ADD, label="Insert new row.",
                        bitmap=bmp_tb, shortHelp="Add new row.")
        tb.AddLabelTool(id=wx.ID_DELETE, label="Delete current row.",
            bitmap=images.ToolbarDelete.Bitmap, shortHelp="Delete row.")
        tb.AddSeparator()
        tb.AddLabelTool(id=wx.ID_SAVE, label="Commit",
                        bitmap=images.ToolbarCommit.Bitmap,
                        shortHelp="Commit changes to database.")
        tb.AddLabelTool(id=wx.ID_UNDO, label="Rollback",
            bitmap=images.ToolbarRollback.Bitmap,
            shortHelp="Rollback changes and restore original values.")
        tb.EnableTool(wx.ID_ADD, False)
        tb.EnableTool(wx.ID_DELETE, False)
        tb.EnableTool(wx.ID_UNDO, False)
        tb.EnableTool(wx.ID_SAVE, False)
        self.Bind(wx.EVT_TOOL, handler=self.on_insert_row, id=wx.ID_ADD)
        self.Bind(wx.EVT_TOOL, handler=self.on_delete_row, id=wx.ID_DELETE)
        self.Bind(wx.EVT_TOOL, handler=self.on_commit_table, id=wx.ID_SAVE)
        self.Bind(wx.EVT_TOOL, handler=self.on_rollback_table, id=wx.ID_UNDO)
        tb.Realize() # should be called after adding tools
        label_table = self.label_table = wx.StaticText(parent=panel2, label="")
        button_reset = self.button_reset_grid_table = \
            wx.Button(parent=panel2, label="&Reset filter/sort")
        button_reset.SetToolTipString("Resets all applied sorting "
                                      "and filtering.")
        button_reset.Bind(wx.EVT_BUTTON, self.on_button_reset_grid)
        button_reset.Enabled = False
        button_export = self.button_export_table = \
            wx.Button(parent=panel2, label="&Export to file")
        button_export.MinSize = (100, -1)
        button_export.SetToolTipString("Export rows to a file.")
        button_export.Bind(wx.EVT_BUTTON, self.on_button_export_grid)
        button_export.Enabled = False
        button_close = self.button_close_grid_table = \
            wx.Button(parent=panel2, label="&Close table")
        button_close.Bind(wx.EVT_BUTTON, self.on_button_close_grid)
        button_close.Enabled = False
        sizer_tb.Add(label_table, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_tb.AddStretchSpacer()
        sizer_tb.Add(button_reset, border=5, flag=wx.BOTTOM | wx.RIGHT |
                     wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_tb.Add(button_export, border=5, flag=wx.BOTTOM | wx.RIGHT |
                     wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_tb.Add(button_close, border=5, flag=wx.BOTTOM | wx.RIGHT |
                     wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_tb.Add(tb, flag=wx.ALIGN_RIGHT)
        grid = self.grid_table = wx.grid.Grid(parent=panel2)
        grid.SetToolTipString("Double click on column header to sort, "
                              "right click to filter.")
        ColourManager.Manage(grid, "DefaultCellBackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(grid, "DefaultCellTextColour",       wx.SYS_COLOUR_WINDOWTEXT)
        ColourManager.Manage(grid, "LabelBackgroundColour",       wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(grid, "LabelTextColour",             wx.SYS_COLOUR_WINDOWTEXT)

        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK, self.on_sort_grid_column)
        grid.GridWindow.Bind(wx.EVT_MOTION, self.on_mouse_over_grid)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK,
                  self.on_filter_grid_column)
        grid.Bind(wx.grid.EVT_GRID_CELL_CHANGE, self.on_change_table)
        grid.GridWindow.Bind(wx.EVT_CHAR_HOOK, functools.partial(self.on_grid_key, grid))

        label_help = self.label_help_table = wx.StaticText(panel2,
            label="Double-click on column header to sort, right click to filter.")
        ColourManager.Manage(label_help, "ForegroundColour", "DisabledColour")
        sizer2.Add(sizer_tb, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer2.Add(grid, border=5, proportion=2,
                   flag=wx.GROW | wx.LEFT | wx.RIGHT)
        sizer2.Add(label_help, border=5, flag=wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 270)
        label_help.Hide()


    def create_page_sql(self, notebook):
        """Creates a page for executing arbitrary SQL."""
        page = self.page_sql = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "SQL")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)
        splitter = self.splitter_sql = \
            wx.SplitterWindow(parent=page, style=wx.BORDER_NONE)
        splitter.SetMinimumPaneSize(100)

        panel1 = self.panel_sql1 = wx.Panel(parent=splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_top = wx.BoxSizer(wx.HORIZONTAL)
        label_stc = wx.StaticText(parent=panel1, label="SQ&L:")
        tb = self.tb_sql = wx.ToolBar(parent=panel1,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, (16, 16))
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR, (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_OPEN, "", bitmap=bmp1, shortHelp="Load SQL file")
        tb.AddLabelTool(wx.ID_SAVE, "", bitmap=bmp2, shortHelp="Save SQL file")
        tb.Realize()
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_open_sql(self.stc_sql, e), id=wx.ID_OPEN)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_save_sql(self.stc_sql, e), id=wx.ID_SAVE)

        stc = self.stc_sql = controls.SQLiteTextCtrl(parent=panel1,
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        stc.Bind(wx.EVT_KEY_DOWN, self.on_keydown_sql)
        stc.SetText(conf.SQLWindowTexts.get(self.db.filename, ""))
        stc.EmptyUndoBuffer() # So that undo does not clear the STC
        sizer_top.Add(label_stc, border=5, flag=wx.ALL)
        sizer_top.AddStretchSpacer()
        sizer_top.Add(tb, flag=wx.ALIGN_RIGHT)
        sizer1.Add(sizer_top, border=5, flag=wx.RIGHT | wx.GROW)
        sizer1.Add(stc, border=5, proportion=1, flag=wx.GROW | wx.LEFT)

        panel2 = self.panel_sql2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)
        label_help = wx.StaticText(panel2, label=
            "Alt-Enter/Ctrl-Enter runs the query contained in currently selected "
            "text or on the current line. Ctrl-Space shows autocompletion list.")
        ColourManager.Manage(label_help, "ForegroundColour", "DisabledColour")
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_sql = self.button_sql = wx.Button(panel2, label="Execute S&QL")
        button_script = self.button_script = wx.Button(panel2,
                                                       label="Execute scrip&t")
        button_sql.SetToolTipString("Execute a single statement "
                                    "from the SQL window")
        button_script.SetToolTipString("Execute multiple SQL statements, "
                                       "separated by semicolons")
        self.Bind(wx.EVT_BUTTON, self.on_button_sql, button_sql)
        self.Bind(wx.EVT_BUTTON, self.on_button_script, button_script)
        button_reset = self.button_reset_grid_sql = \
            wx.Button(parent=panel2, label="&Reset filter/sort")
        button_reset.SetToolTipString("Resets all applied sorting "
                                      "and filtering.")
        button_reset.Bind(wx.EVT_BUTTON, self.on_button_reset_grid)
        button_reset.Enabled = False
        button_export = self.button_export_sql = \
            wx.Button(parent=panel2, label="&Export to file")
        button_export.SetToolTipString("Export result to a file.")
        button_export.Bind(wx.EVT_BUTTON, self.on_button_export_grid)
        button_export.Enabled = False
        button_close = self.button_close_grid_sql = \
            wx.Button(parent=panel2, label="&Close query")
        button_close.Bind(wx.EVT_BUTTON, self.on_button_close_grid)
        button_close.Enabled = False
        sizer_buttons.Add(button_sql, flag=wx.ALIGN_LEFT)
        sizer_buttons.Add(button_script, border=5, flag=wx.LEFT | wx.ALIGN_LEFT)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_reset, border=5,
                          flag=wx.ALIGN_RIGHT | wx.RIGHT)
        sizer_buttons.Add(button_export, border=5, flag=wx.RIGHT | wx.ALIGN_RIGHT)
        sizer_buttons.Add(button_close, flag=wx.ALIGN_RIGHT)
        grid = self.grid_sql = wx.grid.Grid(parent=panel2)
        ColourManager.Manage(grid, "DefaultCellBackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(grid, "DefaultCellTextColour",       wx.SYS_COLOUR_WINDOWTEXT)
        ColourManager.Manage(grid, "LabelBackgroundColour",       wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(grid, "LabelTextColour",             wx.SYS_COLOUR_WINDOWTEXT)

        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK,
                  self.on_sort_grid_column)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK,
                  self.on_filter_grid_column)
        grid.Bind(wx.EVT_SCROLLWIN, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_SCROLL_CHANGED, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_KEY_DOWN, self.on_scroll_grid_sql)
        grid.GridWindow.Bind(wx.EVT_MOTION, self.on_mouse_over_grid)
        grid.GridWindow.Bind(wx.EVT_CHAR_HOOK, functools.partial(self.on_grid_key, grid))

        label_help_sql = self.label_help_sql = wx.StaticText(panel2,
            label="Double-click on column header to sort, right click to filter.")
        ColourManager.Manage(label_help_sql, "ForegroundColour", "DisabledColour")

        sizer2.Add(label_help, border=5, flag=wx.GROW | wx.LEFT | wx.BOTTOM)
        sizer2.Add(sizer_buttons, border=5, flag=wx.GROW | wx.ALL)
        sizer2.Add(grid, border=5, proportion=2,
                   flag=wx.GROW | wx.LEFT | wx.RIGHT)
        sizer2.Add(label_help_sql, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        sash_pos = self.Size[1] / 3
        splitter.SplitHorizontally(panel1, panel2, sashPosition=sash_pos)
        label_help_sql.Hide()


    def create_page_pragma(self, notebook):
        """Creates a page for database PRAGMA settings."""
        page = self.page_pragma = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Pragma")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)

        panel_pragma = self.panel_pragma = wx.lib.scrolledpanel.ScrolledPanel(page)
        panel_sql = wx.Panel(page)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_pragma = panel_pragma.Sizer = wx.FlexGridSizer(cols=4, vgap=4, hgap=10)
        sizer_sql = panel_sql.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer_footer = wx.BoxSizer(wx.HORIZONTAL)

        label_header = wx.StaticText(parent=page, label="Database PRAGMA settings")
        label_header.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                    wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)

        def on_help(ctrl, text, event):
            """Handler for clicking help bitmap, shows text popup."""
            wx.TipWindow(ctrl, text, maxLength=300)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_QUESTION, wx.ART_TOOLBAR, (16, 16))
        cursor_pointer = wx.StockCursor(wx.CURSOR_HAND)
        lastopts = {}
        for name, opts in sorted(database.Database.PRAGMA.items(),
                                 key=lambda x: (bool(x[1].get("deprecated")), x[1]["label"])):
            value = self.pragma.get(name)
            description = "%s:\n\n%s%s" % (name,
                "DEPRECATED.\n\n" if opts.get("deprecated") else "", opts["description"]
            )
            ctrl_name, label_name = "pragma_%s" % name, "pragma_%s_label" % name

            label = wx.StaticText(parent=panel_pragma, label=opts["label"], name=label_name)
            if "table" == opts["type"]:
                ctrl = wx.TextCtrl(panel_pragma, name=ctrl_name, style=wx.TE_MULTILINE,
                                   value="\n".join(str(x) for x in value or ()))
                ctrl.SetEditable(False)
                ctrl.SetInitialSize((200, -1)) # Size to fit vertical content
            elif bool == opts["type"]:
                style = 0
                if opts.get("read") == False:
                    style = wx.CHK_3STATE | wx.CHK_ALLOW_3RD_STATE_FOR_USER
                ctrl = wx.CheckBox(panel_pragma, name=ctrl_name, style=style)
                if value is not None: ctrl.Value = value
                elif ctrl.Is3State(): ctrl.Set3StateValue(wx.CHK_UNDETERMINED)
                ctrl.Bind(wx.EVT_CHECKBOX, self.on_pragma_change)
            elif opts.get("values"):
                items = sorted(opts["values"].items(), key=lambda x: x[1])
                choices = [str(v) for k, v in items]
                ctrl = wx.Choice(panel_pragma, name=ctrl_name, choices=choices)
                ctrl.Selection = [k for k, v in items].index(value)
                ctrl.Bind(wx.EVT_CHOICE, self.on_pragma_change)
            elif int == opts["type"]:
                ctrl = wx.SpinCtrl(panel_pragma, name=ctrl_name)
                ctrl.SetRange(opts.get("min", -sys.maxint), opts.get("max", sys.maxint))
                ctrl.Value = value
                ctrl.Bind(wx.EVT_SPINCTRL, self.on_pragma_change)
            else:
                ctrl = wx.TextCtrl(panel_pragma, name=ctrl_name, size=(200, -1))
                ctrl.Value = "" if value is None else value
                ctrl.Bind(wx.EVT_TEXT, self.on_pragma_change)
            label_text = wx.StaticText(parent=panel_pragma, label=opts["short"])
            help_bmp = wx.StaticBitmap(panel_pragma, bitmap=bmp)

            if opts.get("deprecated"):
                ColourManager.Manage(label, "ForegroundColour", "DisabledColour")
                ColourManager.Manage(label_text, "ForegroundColour", "DisabledColour")
            label.SetToolTipString(description)
            ctrl.SetToolTipString(description)
            label_text.SetToolTipString(description)
            help_bmp.SetCursor(cursor_pointer)
            help_bmp.Bind(wx.EVT_LEFT_UP, functools.partial(on_help, help_bmp, description))

            if "table" != opts["type"]: ctrl.Disable()
            self.pragma_ctrls[name] = ctrl

            if opts.get("deprecated") \
            and bool(lastopts.get("deprecated")) != bool(opts.get("deprecated")):
                label_deprecated = wx.StaticText(panel_pragma, label="DEPRECATED:")
                ColourManager.Manage(label_deprecated, "ForegroundColour", "DisabledColour")
                sizer_pragma.Add(label_deprecated, border=25, flag=wx.TOP)
                for i in range(3): sizer_pragma.AddSpacer(20)

            sizer_pragma.Add(label, border=5, flag=wx.LEFT)
            sizer_pragma.Add(ctrl)
            sizer_pragma.Add(label_text)
            sizer_pragma.Add(help_bmp)
            lastopts = opts

        check_sql = self.check_pragma_sql = \
            wx.CheckBox(parent=page, label="See change S&QL")
        check_sql.SetToolTipString("See SQL statements for PRAGMA changes")
        check_sql.Value = True
        check_sql.Hide()

        stc = self.stc_pragma = controls.SQLiteTextCtrl(
            parent=panel_sql, style=wx.BORDER_STATIC)
        stc.SetReadOnly(True)
        tb = self.tb_pragma = wx.ToolBar(parent=panel_sql,
                                         style=wx.VERTICAL | wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = wx.ArtProvider.GetBitmap(wx.ART_COPY, wx.ART_TOOLBAR,
                                        (16, 16))
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR,
                                        (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_COPY, "", bitmap=bmp1, shortHelp="Copy pragma SQL to clipboard")
        tb.AddLabelTool(wx.ID_SAVE, "", bitmap=bmp2, shortHelp="Save pragma SQL to file")
        tb.Realize()
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_copy_sql(self.stc_pragma, e), id=wx.ID_COPY)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_save_sql(self.stc_pragma, e), id=wx.ID_SAVE)
        panel_sql.Hide()

        button_edit = self.button_pragma_edit = \
            wx.Button(parent=page, label="&Edit")
        button_refresh = self.button_pragma_refresh = \
            wx.Button(parent=page, label="&Refresh")
        button_save = self.button_pragma_save = \
            wx.Button(parent=page, label="&Save")
        button_cancel = self.button_pragma_cancel = \
            wx.Button(parent=page, label="&Cancel")

        button_edit.SetToolTipString("Edit PRAGMA values")
        button_refresh.SetToolTipString("Reload PRAGMA values from database")
        button_save.SetToolTipString("Save changed PRAGMAs")
        button_cancel.SetToolTipString("Cancel PRAGMA changes")
        button_save.Enabled = button_cancel.Enabled = False

        self.Bind(wx.EVT_BUTTON,   self.on_pragma_save,    button_save)
        self.Bind(wx.EVT_BUTTON,   self.on_pragma_edit,    button_edit)
        self.Bind(wx.EVT_BUTTON,   self.on_pragma_refresh, button_refresh)
        self.Bind(wx.EVT_BUTTON,   self.on_pragma_cancel,  button_cancel)
        self.Bind(wx.EVT_CHECKBOX, self.on_pragma_sql,     check_sql)

        sizer_header.AddStretchSpacer()
        sizer_header.Add(label_header, border=5, flag=wx.ALL)
        sizer_header.AddStretchSpacer()

        sizer_sql.Add(stc, proportion=1, flag=wx.GROW)
        sizer_sql.Add(tb)

        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_edit)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_refresh)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_save)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_cancel)
        sizer_footer.AddStretchSpacer()

        #sizer_panel.AddGrowableCol(2, 1)

        sizer.Add(sizer_header, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel_pragma, proportion=1, border=20, flag=wx.LEFT | wx.GROW)
        sizer.Add(check_sql, border=10, flag=wx.LEFT | wx.TOP)
        sizer.Add(panel_sql, border=10, flag=wx.LEFT | wx.TOP | wx.GROW)
        sizer.Add(sizer_footer, border=10, flag=wx.BOTTOM | wx.TOP | wx.GROW)
        panel_pragma.SetupScrolling(scroll_x=False)


    def create_page_info(self, notebook):
        """Creates a page for seeing general database information."""
        page = self.page_info = wx.lib.scrolledpanel.ScrolledPanel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Information")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        panel1, panel2 = wx.Panel(parent=page), wx.Panel(parent=page)
        panel1c, panel2c = wx.Panel(parent=panel1), wx.Panel(parent=panel2)
        ColourManager.Manage(panel1c, "BackgroundColour", "BgColour")
        ColourManager.Manage(panel2c, "BackgroundColour", "BgColour")
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_file = panel1c.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_info = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        label_file = wx.StaticText(parent=panel1, label="Database information")
        label_file.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                  wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)

        names = ["edit_info_path", "edit_info_size", "edit_info_modified",
                 "edit_info_sha1", "edit_info_md5", ]
        labels = ["Full path", "File size", "Last modified",
                  "SHA-1 checksum", "MD5 checksum",  ]
        for name, label in zip(names, labels):
            if not name and not label:
                sizer_info.AddSpacer(20), sizer_info.AddSpacer(20)
                continue # continue for i, (name, label) in enumerate(..
            labeltext = wx.StaticText(parent=panel1c, label="%s:" % label)
            labeltext.ForegroundColour = wx.Colour(102, 102, 102)
            valuetext = wx.TextCtrl(parent=panel1c, value="Analyzing..",
                style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH)
            valuetext.MinSize = (-1, 35)
            ColourManager.Manage(valuetext, "BackgroundColour", "BgColour")
            valuetext.SetEditable(False)
            sizer_info.Add(labeltext, border=5, flag=wx.LEFT | wx.TOP)
            sizer_info.Add(valuetext, border=5, proportion=1, flag=wx.TOP | wx.GROW)
            setattr(self, name, valuetext)
        self.edit_info_path.Value = self.db.filename

        button_vacuum = self.button_vacuum = \
            wx.Button(parent=panel1c, label="Vacuum")
        button_check = self.button_check_integrity = \
            wx.Button(parent=panel1c, label="Check for corruption")
        button_refresh = self.button_refresh_fileinfo = \
            wx.Button(parent=panel1c, label="Refresh")
        button_vacuum.Enabled = button_check.Enabled = button_refresh.Enabled = False
        button_vacuum.SetToolTipString("Rebuild the database file, repacking "
                                       "it into a minimal amount of disk space.")
        button_check.SetToolTipString("Check database integrity for "
                                      "corruption and recovery.")

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons.Add(button_vacuum)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_check)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_refresh, border=15,
                       flag=wx.ALIGN_RIGHT | wx.RIGHT)
        self.Bind(wx.EVT_BUTTON, self.on_vacuum, button_vacuum)
        self.Bind(wx.EVT_BUTTON, self.on_check_integrity, button_check)
        self.Bind(wx.EVT_BUTTON, lambda e: self.update_info_page(),
                  button_refresh)

        sizer_info.AddGrowableCol(1, 1)
        sizer_file.Add(sizer_info, proportion=1, border=10, flag=wx.LEFT | wx.GROW)
        sizer_file.Add(sizer_buttons, border=10, flag=wx.LEFT | wx.BOTTOM | wx.GROW)
        sizer1.Add(label_file, border=5, flag=wx.ALL)
        sizer1.Add(panel1c, border=6, proportion=1, flag=wx.TOP | wx.GROW)

        sizer_schematop = wx.BoxSizer(wx.HORIZONTAL)
        label_schema = wx.StaticText(parent=panel2, label="Database schema")
        label_schema.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                  wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)

        tb = self.tb_sql = wx.ToolBar(parent=panel2,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = images.ToolbarRefresh.Bitmap
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_COPY, wx.ART_TOOLBAR,
                                        (16, 16))
        bmp3 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR,
                                        (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_REFRESH, "", bitmap=bmp1, shortHelp="Refresh schema SQL")
        tb.AddLabelTool(wx.ID_COPY,    "", bitmap=bmp2, shortHelp="Copy schema SQL to clipboard")
        tb.AddLabelTool(wx.ID_SAVE,    "", bitmap=bmp3, shortHelp="Save schema SQL to file")
        tb.Realize()
        tb.Bind(wx.EVT_TOOL, self.on_update_stc_schema, id=wx.ID_REFRESH)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_copy_sql(self.stc_schema, e), id=wx.ID_COPY)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_save_sql(self.stc_schema, e), id=wx.ID_SAVE)

        sizer_stc = panel2c.Sizer = wx.BoxSizer(wx.VERTICAL)
        stc = self.stc_schema = controls.SQLiteTextCtrl(parent=panel2c,
            style=wx.BORDER_STATIC)
        stc.SetText(self.db.get_sql())
        stc.SetReadOnly(True)

        sizer_schematop.Add(label_schema)
        sizer_schematop.AddStretchSpacer()
        sizer_schematop.Add(tb, flag=wx.ALIGN_RIGHT)
        sizer_stc.Add(stc, proportion=1, flag=wx.GROW)
        sizer2.Add(sizer_schematop, border=5, flag=wx.TOP | wx.RIGHT | wx.GROW)
        sizer2.Add(panel2c, proportion=1, border=5, flag=wx.TOP | wx.GROW)

        sizer.Add(panel1, proportion=1, border=5,
                  flag=wx.LEFT  | wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel2, proportion=1, border=5,
                  flag=wx.RIGHT | wx.TOP | wx.BOTTOM | wx.GROW)
        page.SetupScrolling()


    def on_sys_colour_change(self, event):
        """Handler for system colour change, refreshes content."""
        event.Skip()
        def dorefresh():
            self.label_html.SetPage(step.Template(templates.SEARCH_HELP_SHORT).expand())
            self.label_html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNFACE)
            self.label_html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
            default = step.Template(templates.SEARCH_WELCOME_HTML).expand()
            self.html_searchall.SetDefaultPage(default)
        wx.CallAfter(dorefresh) # Postpone to allow conf update


    def on_update_stc_schema(self, event):
        """Handler for clicking to refresh database schema SQL."""
        self.stc_schema.SetReadOnly(False)
        self.stc_schema.SetText(self.db.get_sql(refresh=True))
        self.stc_schema.SetReadOnly(True)


    def on_pragma_change(self, event):
        """Handler for changing a PRAGMA value."""
        if not self.pragma_edit: return
        ctrl = event.EventObject

        name = ctrl.Name.replace("pragma_", "", 1)
        if isinstance(ctrl, wx.Choice):
            vals = database.Database.PRAGMA[name]["values"]
            value = ctrl.GetString(ctrl.Selection)
            value = next(k for k, v in vals.items() if str(v) == value)
        else:
            value = ctrl.Value
            if isinstance(ctrl, wx.CheckBox) and ctrl.Is3State():
                FLAGS = {wx.CHK_CHECKED: True, wx.CHK_UNCHECKED: False,
                         wx.CHK_UNDETERMINED: None}
                value = FLAGS[ctrl.Get3StateValue()]

        if (value == self.pragma.get(name)
        or not value and bool(value) == bool(self.pragma.get(name))
        and database.Database.PRAGMA[name]["type"] in (str, unicode)):
            self.pragma_changes.pop(name, None)
        else: self.pragma_changes[name] = value

        self.stc_pragma.Freeze()
        self.stc_pragma.SetReadOnly(False)
        self.stc_pragma.Text = ""
        for name, value in sorted(self.pragma_changes.items()):
            if isinstance(value, basestring):
                value = '"%s"' % value.replace('"', '""')
            self.stc_pragma.Text += "PRAGMA %s = %s;\n\n" % (name, value)
        self.stc_pragma.SetReadOnly(True)
        self.stc_pragma.Thaw()


    def on_pragma_sql(self, event):
        """Handler for toggling PRAGMA change SQL visible."""
        self.stc_pragma.Parent.Shown = self.check_pragma_sql.Value
        self.page_pragma.Layout()


    def on_pragma_save(self, event):
        """Handler for clicking to save PRAGMA changes."""

        changes = {} # {pragma_name: value}
        for name, value in sorted(self.pragma_changes.items()):
            if value == self.pragma.get(name): continue # for name, value
            changes[name] = value

        try:
            for name, value in changes.items():
                if isinstance(value, basestring):
                    value = '"%s"' % value.replace('"', '""')
                sql = "PRAGMA %s = %s" % (name, value)
                guibase.log("Executing %s.", sql)
                self.db.execute(sql)
        except Exception:
            msg = "Error setting %s:\n\n%s" % \
                  (sql, traceback.format_exc())
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
        else:
            self.pragma.update(changes)
            self.on_pragma_cancel(None)


    def on_pragma_edit(self, event):
        """Handler for clicking to edit PRAGMA settings."""
        self.pragma_edit = True
        self.button_pragma_save.Enable()
        self.button_pragma_cancel.Enable()
        self.button_pragma_edit.Disable()
        self.check_pragma_sql.Enable()
        self.check_pragma_sql.Show()
        if self.check_pragma_sql.Value:
            self.stc_pragma.Parent.Shown = True
        for name, opts in database.Database.PRAGMA.items():
            ctrl = self.pragma_ctrls[name]
            if opts.get("write") != False and "table" != opts["type"]:
                ctrl.Enable()
        self.page_pragma.Layout()


    def on_pragma_refresh(self, event):
        """Handler for clicking to refresh PRAGMA settings."""
        flag = self.pragma_edit
        self.pragma.update(self.db.get_pragma_values())
        self.pragma_edit = False # Ignore change events in edit handler
        for name, opts in database.Database.PRAGMA.items():
            ctrl = self.pragma_ctrls[name]
            value = self.pragma.get(name)
            if "table" == opts["type"]:
                ctrl.Value = "\n".join(str(x) for x in value or ())
            elif bool == opts["type"]:
                if value is not None: ctrl.Value = value
                elif ctrl.Is3State(): ctrl.Set3StateValue(wx.CHK_UNDETERMINED)
            elif opts.get("values"):
                items = sorted(opts["values"].items(), key=lambda x: x[1])
                ctrl.Selection = [k for k, v in items].index(value)
            elif int == opts["type"]:
                ctrl.Value = value
            else:
                ctrl.Value = "" if value is None else value
        self.pragma_changes.clear()
        self.stc_pragma.SetReadOnly(False)
        self.stc_pragma.SetText("")
        self.stc_pragma.SetReadOnly(True)
        self.pragma_edit = flag


    def on_pragma_cancel(self, event):
        """Handler for clicking to cancel PRAGMA changes."""
        self.pragma_edit = False
        self.button_pragma_edit.Enable()
        self.button_pragma_save.Disable()
        self.button_pragma_cancel.Disable()
        self.check_pragma_sql.Disable()
        self.on_pragma_refresh(None)
        self.check_pragma_sql.Hide()
        self.stc_pragma.Parent.Hide()
        for name, opts in database.Database.PRAGMA.items():
            if "table" != opts["type"]: self.pragma_ctrls[name].Disable()
        self.page_pragma.Layout()


    def on_check_integrity(self, event):
        """
        Handler for checking database integrity, offers to save a fixed
        database if corruption detected.
        """
        msg = "Checking integrity of %s." % self.db.filename
        guibase.logstatus_flash(msg)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        try:
            errors = self.db.check_integrity()
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        guibase.status_flash("")
        if not errors:
            wx.MessageBox("No database errors detected.",
                          conf.Title, wx.ICON_INFORMATION)
        else:
            err = "\n- ".join(errors)
            guibase.log("Errors found in %s: %s", self.db, err)
            err = err[:500] + ".." if len(err) > 500 else err
            msg = "A number of errors were found in %s:\n\n- %s\n\n" \
                  "Recover as much as possible to a new database?" % \
                  (self.db, err)
            if wx.YES == wx.MessageBox(msg, conf.Title,
                                       wx.ICON_INFORMATION | wx.YES | wx.NO):
                directory, filename = os.path.split(self.db.filename)
                base = os.path.splitext(filename)[0]
                self.dialog_savefile.Directory = directory
                self.dialog_savefile.Filename = "%s (recovered)" % base
                self.dialog_savefile.Message = "Save recovered data as"
                self.dialog_savefile.Wildcard = "SQLite database (*.db)|*.db"
                self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
                if wx.ID_OK == self.dialog_savefile.ShowModal():
                    newfile = self.dialog_savefile.GetPath()
                    if not newfile.lower().endswith(".db"): newfile += ".db"
                    if newfile != self.db.filename:
                        guibase.status_flash("Recovering data from %s to %s.",
                                          self.db.filename, newfile)
                        m = "Recovering data from %s\nto %s."
                        busy = controls.BusyPanel(self, m % (self.db, newfile))
                        wx.YieldIfNeeded()
                        try:
                            copyerrors = self.db.recover_data(newfile)
                        finally:
                            busy.Close()
                        err = ("\n\nErrors occurred during the recovery, "
                              "more details in log window:\n\n- "
                              + "\n- ".join(copyerrors)) if copyerrors else ""
                        err = err[:500] + ".." if len(err) > 500 else err
                        guibase.status_flash("Recovery to %s complete." % newfile)
                        wx.MessageBox("Recovery to %s complete.%s" %
                                      (newfile, err), conf.Title,
                                      wx.ICON_INFORMATION)
                        util.start_file(os.path.dirname(newfile))
                    else:
                        wx.MessageBox("Cannot recover data from %s to itself."
                                      % self.db, conf.Title, wx.ICON_WARNING)


    def on_vacuum(self, event):
        """
        Handler for vacuuming the database.
        """
        msg = "Vacuuming %s." % self.db.filename
        guibase.logstatus_flash(msg)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        errors = []
        try:
            self.db.execute("VACUUM")
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        guibase.status_flash("")
        if errors:
            err = "\n- ".join(errors)
            guibase.log("Error running vacuum on %s: %s", self.db, err)
            err = err[:500] + ".." if len(err) > 500 else err
            wx.MessageBox(err, conf.Title, wx.ICON_WARNING | wx.OK)
        else:
            self.update_info_page()


    def save_page_conf(self):
        """Saves page last configuration like search text and results."""

        # Save search box state
        if conf.SearchHistory[-1:] == [""]: # Clear empty search flag
            conf.SearchHistory = conf.SearchHistory[:-1]
        util.add_unique(conf.SearchHistory, self.edit_searchall.Value,
                        1, conf.MaxSearchHistory)

        # Save last search results HTML
        search_data = self.html_searchall.GetActiveTabData()
        if search_data:
            info = {}
            if search_data.get("info"):
                info["map"] = search_data["info"].get("map")
                info["text"] = search_data["info"].get("text")
            data = {"content": search_data["content"],
                    "id": search_data["id"], "info": info,
                    "title": search_data["title"], }
            conf.LastSearchResults[self.db.filename] = data
        elif self.db.filename in conf.LastSearchResults:
            del conf.LastSearchResults[self.db.filename]

        # Save page SQL window content, if changed from previous value
        sql_text = self.stc_sql.Text
        if sql_text != conf.SQLWindowTexts.get(self.db.filename, ""):
            if sql_text:
                conf.SQLWindowTexts[self.db.filename] = sql_text
            elif self.db.filename in conf.SQLWindowTexts:
                del conf.SQLWindowTexts[self.db.filename]


    def split_panels(self):
        """
        Splits all SplitterWindow panels. To be called after layout in
        Linux wx 2.8, as otherwise panels do not get sized properly.
        """
        if not self:
            return
        sash_pos = self.Size[1] / 3
        panel1, panel2 = self.splitter_tables.Children
        self.splitter_tables.Unsplit()
        self.splitter_tables.SplitVertically(panel1, panel2, 270)
        panel1, panel2 = self.splitter_sql.Children
        self.splitter_sql.Unsplit()
        self.splitter_sql.SplitHorizontally(panel1, panel2, sash_pos)
        wx.CallLater(1000, lambda: self and
                     (self.tree_tables.SetColumnWidth(0, -1),
                      self.tree_tables.SetColumnWidth(1, -1)))


    def update_info_page(self, reload=True):
        """Updates the Information page with current data."""
        if reload:
            self.db.clear_cache()
            self.db.update_fileinfo()
        for name in ["size", "modified", "sha1", "md5"]:
            getattr(self, "edit_info_%s" % name).Value = ""

        self.edit_info_size.Value = "%s (%s)" % \
            (util.format_bytes(self.db.filesize),
             util.format_bytes(self.db.filesize, max_units=False))
        self.edit_info_modified.Value = \
            self.db.last_modified.strftime("%Y-%m-%d %H:%M:%S")
        BLOCKSIZE = 1048576
        sha1, md5 = hashlib.sha1(), hashlib.md5()
        try:
            with open(self.db.filename, "rb") as f:
                buf = f.read(BLOCKSIZE)
                while len(buf):
                    sha1.update(buf), md5.update(buf)
                    buf = f.read(BLOCKSIZE)
            self.edit_info_sha1.Value = sha1.hexdigest()
            self.edit_info_md5.Value = md5.hexdigest()
        except Exception as e:
            self.edit_info_sha1.Value = self.edit_info_md5.Value = util.format_exc(e)
        self.button_vacuum.Enabled = True
        self.button_check_integrity.Enabled = True
        self.button_refresh_fileinfo.Enabled = True


    def on_refresh_tables(self, event):
        """
        Refreshes the table tree and open table data. Asks for confirmation
        if there are uncommitted changes.
        """
        do_refresh, unsaved = True, self.get_unsaved_grids()
        if unsaved:
            response = wx.MessageBox("Some tables have unsaved data (%s).\n\n"
                "Save before refreshing (changes will be lost otherwise)?"
                % (", ".join(sorted(x.table for x in unsaved))), conf.Title,
                wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION)
            if wx.YES == response:
                do_refresh = self.save_unsaved_grids()
            elif wx.CANCEL == response:
                do_refresh = False
        if do_refresh:
            self.db.clear_cache()
            self.db_grids.clear()
            self.load_tables_data()
            if self.grid_table.Table:
                grid, table_name = self.grid_table, self.grid_table.Table.table
                scrollpos = map(grid.GetScrollPos, [wx.HORIZONTAL, wx.VERTICAL])
                cursorpos = grid.GridCursorCol, grid.GridCursorRow
                self.on_change_table(None)
                grid.Table = wx.grid.PyGridTableBase() # Clear grid visually
                grid.Freeze()
                grid.Table = None # Reset grid data to empty

                tableitem = None
                table_name = table_name.lower()
                item = self.tree_tables.GetNext(self.tree_tables.RootItem)
                while table_name in self.db.schema["table"] and item and item.IsOk():
                    table2 = self.tree_tables.GetItemPyData(item)
                    if isinstance(table2, basestring) and table2.lower() == table_name:
                        tableitem = item
                        break # while table_name
                    item = self.tree_tables.GetNextSibling(item)
                if tableitem:
                    # Only way to create state change in wx.gizmos.TreeListCtrl
                    class HackEvent(object):
                        def __init__(self, item): self._item = item
                        def GetItem(self):        return self._item
                    self.on_change_tree_tables(HackEvent(tableitem))
                    self.tree_tables.SelectItem(tableitem)
                    grid.Scroll(*scrollpos)
                    grid.SetGridCursor(*cursorpos)
                else:
                    self.label_table.Label = ""
                    for x in [wx.ID_ADD, wx.ID_DELETE, wx.ID_UNDO, wx.ID_SAVE]:
                        self.tb_grid.EnableTool(x, False)
                    self.button_reset_grid_table.Enabled = False
                    self.button_export_table.Enabled = False
                    self.button_close_grid_table.Enabled = False
                grid.Thaw()
                self.page_tables.Refresh()


    def on_scroll_grid_sql(self, event):
        """
        Handler for scrolling the SQL grid, seeks ahead if nearing the end of
        retrieved rows.
        """
        event.Skip()
        # Execute seek later, to give scroll position time to update
        wx.CallLater(50, self.seekahead_grid_sql)


    def seekahead_grid_sql(self):
        """Seeks ahead on the SQL grid if scroll position nearing the end."""
        SEEKAHEAD_POS_RATIO = 0.8
        scrollpos = self.grid_sql.GetScrollPos(wx.VERTICAL)
        scrollrange = self.grid_sql.GetScrollRange(wx.VERTICAL)
        if scrollpos > scrollrange * SEEKAHEAD_POS_RATIO:
            scrollpage = self.grid_sql.GetScrollPageSize(wx.VERTICAL)
            to_end = (scrollpos + scrollpage == scrollrange)
            # Seek to end if scrolled to the very bottom
            self.grid_sql.Table.SeekAhead(to_end)


    def on_rightclick_searchall(self, event):
        """
        Handler for right-clicking in HtmlWindow, sets up a temporary flag for
        HTML link click handler to check, in order to display a context menu.
        """
        self.html_searchall.is_rightclick = True
        def reset():
            if self.html_searchall.is_rightclick: # Flag still up: show menu
                def on_copy(event):
                    if wx.TheClipboard.Open():
                        text = self.html_searchall.SelectionToText()
                        d = wx.TextDataObject(text)
                        wx.TheClipboard.SetData(d), wx.TheClipboard.Close()

                def on_selectall(event):
                    self.html_searchall.SelectAll()
                self.html_searchall.is_rightclick = False
                menu = wx.Menu()
                item_selection = wx.MenuItem(menu, -1, "&Copy selection")
                item_selectall = wx.MenuItem(menu, -1, "&Select all")
                menu.AppendItem(item_selection)
                menu.AppendSeparator()
                menu.AppendItem(item_selectall)
                item_selection.Enable(bool(self.html_searchall.SelectionToText()))
                menu.Bind(wx.EVT_MENU, on_copy, id=item_selection.GetId())
                menu.Bind(wx.EVT_MENU, on_selectall, id=item_selectall.GetId())
                self.html_searchall.PopupMenu(menu)
        event.Skip(), wx.CallAfter(reset)


    def on_click_html_link(self, event):
        """
        Handler for clicking a link in HtmlWindow, opens the link inside
        program or in default browser, opens a popupmenu if right click.
        """
        href = event.GetLinkInfo().Href
        link_data, tab_data = None, None
        if event.EventObject != self.label_html:
            tab_data = self.html_searchall.GetActiveTabData()
        if tab_data and tab_data.get("info"):
            link_data = tab_data["info"]["map"].get(href, {})

        # Workaround for no separate wx.html.HtmlWindow link right click event
        if getattr(self.html_searchall, "is_rightclick", False):
            # Open a pop-up menu with options to copy or select text
            self.html_searchall.is_rightclick = False
            def clipboardize(text):
                if wx.TheClipboard.Open():
                    d = wx.TextDataObject(text)
                    wx.TheClipboard.SetData(d), wx.TheClipboard.Close()

            menutitle = "C&opy link location"
            if href.startswith("file://"):
                href = urllib.url2pathname(href[5:])
                if any(href.startswith(x) for x in ["\\\\\\", "///"]):
                    href = href[3:] # Strip redundant filelink slashes
                if isinstance(href, unicode):
                    # Workaround for wx.html.HtmlWindow double encoding
                    href = href.encode('latin1', errors="xmlcharrefreplace"
                           ).decode("utf-8")
                menutitle = "C&opy file location"
            elif href.startswith("mailto:"):
                href = href[7:]
                menutitle = "C&opy e-mail address"
            def handler(e):
                clipboardize(href)

            def on_copyselection(event):
                clipboardize(self.html_searchall.SelectionToText())
            def on_selectall(event):
                self.html_searchall.SelectAll()
            menu = wx.Menu()
            item_selection = wx.MenuItem(menu, -1, "&Copy selection")
            item_copy = wx.MenuItem(menu, -1, menutitle)
            item_selectall = wx.MenuItem(menu, -1, "&Select all")
            menu.AppendItem(item_selection)
            menu.AppendItem(item_copy)
            menu.AppendItem(item_selectall)
            item_selection.Enable(bool(self.html_searchall.SelectionToText()))
            menu.Bind(wx.EVT_MENU, on_copyselection, id=item_selection.GetId())
            menu.Bind(wx.EVT_MENU, handler, id=item_copy.GetId())
            menu.Bind(wx.EVT_MENU, on_selectall, id=item_selectall.GetId())
            self.html_searchall.PopupMenu(menu)
        elif link_data or href.startswith("file://"):
            # Open the link, or file, or program internal link to table
            table_name, row = link_data.get("table"), link_data.get("row")
            if href.startswith("file://"):
                filename = path = urllib.url2pathname(href[5:])
                if any(path.startswith(x) for x in ["\\\\\\", "///"]):
                    filename = href = path[3:]
                if path and os.path.exists(path):
                    util.start_file(path)
                else:
                    e = "The file \"%s\" cannot be found on this computer." % \
                        filename
                    wx.MessageBox(e, conf.Title, wx.OK | wx.ICON_INFORMATION)
            elif table_name:
                tableitem = None
                table_name = table_name.lower()
                item = self.tree_tables.GetNext(self.tree_tables.RootItem)
                while table_name in self.db.schema["table"] and item and item.IsOk():
                    table2 = self.tree_tables.GetItemPyData(item)
                    if isinstance(table2, basestring) and table2.lower() == table_name:
                        tableitem = item
                        break # while table_name
                    item = self.tree_tables.GetNextSibling(item)
                if tableitem:
                    self.notebook.SetSelection(self.pageorder[self.page_tables])
                    wx.YieldIfNeeded()
                    # Only way to create state change in wx.gizmos.TreeListCtrl
                    class HackEvent(object):
                        def __init__(self, item): self._item = item
                        def GetItem(self):        return self._item
                    self.on_change_tree_tables(HackEvent(tableitem))
                    if self.tree_tables.Selection != tableitem:
                        self.tree_tables.SelectItem(tableitem)
                        wx.YieldIfNeeded()

                    # Search for matching row and scroll to it.
                    if row:
                        grid = self.grid_table
                        if grid.Table.filters:
                            grid.Table.ClearSort(refresh=False)
                            grid.Table.ClearFilter()
                        columns = self.db.get_table_columns(table_name)
                        id_fields = [c["name"] for c in columns if c.get("pk")]
                        if not id_fields: # No primary key fields: take all
                            id_fields = [c["name"] for c in columns]
                        row_id = [row[c] for c in id_fields]
                        for i in range(grid.Table.GetNumberRows()):
                            row2 = grid.Table.GetRow(i)
                            row2_id = [row2[c] for c in id_fields]
                            if row_id == row2_id:
                                grid.MakeCellVisible(i, 0)
                                grid.SelectRow(i)
                                pagesize = grid.GetScrollPageSize(wx.VERTICAL)
                                pxls = grid.GetScrollPixelsPerUnit()
                                cell_coords = grid.CellToRect(i, 0)
                                y = cell_coords.y / (pxls[1] or 15)
                                x, y = 0, y - pagesize / 2
                                grid.Scroll(x, y)
                                break # for i
        elif href.startswith("page:"):
            # Go to database subpage
            page = href[5:]
            if "#help" == page:
                html = self.html_searchall
                if html.GetTabDataByID(0):
                    html.SetActiveTabByID(0)
                else:
                    h = step.Template(templates.SEARCH_HELP_LONG).expand()
                    html.InsertTab(html.GetTabCount(), "Search help", 0, h, None)
            elif "#search" == page:
                self.edit_searchall.SetFocus()
            else:
                thepage = getattr(self, "page_" + page, None)
                if thepage:
                    self.notebook.SetSelection(self.pageorder[thepage])
        elif href.startswith("#"): # In-page link
            event.Skip()
        elif not href.startswith("file:"):
            webbrowser.open(href)


    def on_searchall_toggle_toolbar(self, event):
        """Handler for toggling new tab setting in search toolbar."""
        """Handler for toggling a setting in search toolbar."""
        if wx.ID_INDEX == event.Id:
            conf.SearchInNames = True
            conf.SearchInTables = False
            self.label_search.Label = "&Search in table and column names and types:"
        elif wx.ID_STATIC == event.Id:
            conf.SearchInTables = True
            conf.SearchInNames = False
            self.label_search.Label = "&Search in tables:"
        self.label_search.ContainingSizer.Layout()
        if wx.ID_NEW == event.Id:
            conf.SearchUseNewTab = event.EventObject.GetToolState(event.Id)
        elif not event.EventObject.GetToolState(event.Id):
            # All others are radio tools and state might be toggled off by
            # shortkey key adapter
            event.EventObject.ToggleTool(event.Id, True)


    def on_searchall_stop(self, event):
        """
        Handler for clicking to stop a search, signals the search thread to
        close.
        """
        tab_data = self.html_searchall.GetActiveTabData()
        if tab_data and tab_data["id"] in self.workers_search:
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
            self.workers_search[tab_data["id"]].stop()
            del self.workers_search[tab_data["id"]]


    def on_change_searchall_tab(self, event):
        """Handler for changing a tab in search window, updates stop button."""
        tab_data = self.html_searchall.GetActiveTabData()
        if tab_data and tab_data["id"] in self.workers_search:
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStop.Bitmap)
        else:
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)


    def on_dclick_searchall_tab(self, event):
        """
        Handler for double-clicking a search tab header, sets the search box
        value to tab text.
        """
        text = event.Data.get("info", {}).get("text")
        if text:
            self.edit_searchall.Value = text
            self.edit_searchall.SetFocus()


    def on_searchall_result(self, event):
        """
        Handler for getting results from search thread, adds the results to
        the search window.
        """
        result = event.result
        search_id, search_done = result.get("search", {}).get("id"), False
        tab_data = self.html_searchall.GetTabDataByID(search_id)
        if tab_data:
            tab_data["info"]["map"].update(result.get("map", {}))
            tab_data["info"]["partial_html"] += result.get("output", "")
            html = tab_data["info"]["partial_html"]
            if "done" in result:
                search_done = True
            else:
                html += "</table></font>"
            text = tab_data["info"]["text"]
            title = text[:50] + ".." if len(text) > 50 else text
            title += " (%s)" % result.get("count", 0)
            self.html_searchall.SetTabDataByID(search_id, title, html,
                                               tab_data["info"])
        if search_done:
            guibase.status_flash("Finished searching for \"%s\" in %s.",
                result["search"]["text"], self.db.filename
            )
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
            if search_id in self.workers_search:
                self.workers_search[search_id].stop()
                del self.workers_search[search_id]
        if "error" in result:
            guibase.log("Error searching %s:\n\n%s", self.db, result["error"])
            errormsg = "Error searching %s:\n\n%s" % \
                       (self.db, result.get("error_short", result["error"]))
            wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_searchall_callback(self, result):
        """Callback function for SearchThread, posts the data to self."""
        if self: # Check if instance is still valid (i.e. not destroyed by wx)
            wx.PostEvent(self, WorkerEvent(result=result))


    def on_searchall(self, event):
        """
        Handler for clicking to global search the database.
        """
        text = self.edit_searchall.Value
        if text.strip():
            guibase.status_flash("Searching for \"%s\" in %s.",
                              text, self.db.filename)
            html = self.html_searchall
            data = {"id": self.counter(), "db": self.db, "text": text, "map": {},
                    "width": html.Size.width * 5/9, "table": "",
                    "partial_html": ""}
            if conf.SearchInNames:
                data["table"] = "names"
                fromtext = "table and column names and types"
            elif conf.SearchInTables:
                data["table"] = "tables"
                fromtext = "tables"
            # Partially assembled HTML for current results
            template = step.Template(templates.SEARCH_HEADER_HTML, escape=True)
            data["partial_html"] = template.expand(locals())

            worker = workers.SearchThread(self.on_searchall_callback)
            self.workers_search[data["id"]] = worker
            worker.work(data)
            bmp = images.ToolbarStop.Bitmap
            self.tb_search_settings.SetToolNormalBitmap(wx.ID_STOP, bmp)

            title = text[:50] + ".." if len(text) > 50 else text
            content = data["partial_html"] + "</table></font>"
            if conf.SearchUseNewTab or not html.GetTabCount():
                html.InsertTab(0, title, data["id"], content, data)
            else:
                # Set new ID for the existing reused tab
                html.SetTabDataByID(html.GetActiveTabData()["id"], title,
                                    content, data, data["id"])

            self.notebook.SetSelection(self.pageorder[self.page_search])
            util.add_unique(conf.SearchHistory, text.strip(), 1,
                            conf.MaxSearchHistory)
            self.TopLevelParent.dialog_search.Value = conf.SearchHistory[-1]
            self.TopLevelParent.dialog_search.SetChoices(conf.SearchHistory)
            self.edit_searchall.SetChoices(conf.SearchHistory)
            self.edit_searchall.SetFocus()
            conf.save()


    def on_delete_tab_callback(self, tab):
        """
        Function called by html_searchall after deleting a tab, stops the
        ongoing search, if any.
        """
        tab_data = self.html_searchall.GetActiveTabData()
        if tab_data and tab_data["id"] == tab["id"]:
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
        if tab["id"] in self.workers_search:
            self.workers_search[tab["id"]].stop()
            del self.workers_search[tab["id"]]


    def on_grid_key(self, grid, event):
        """
        Handler for keypress in data grid,
        copies selection to clipboard on Ctrl-C.
        """
        if not (event.KeyCode in [ord('C')] and event.ControlDown()):
            return event.Skip()

        rows, cols = [], []
        if grid.GetSelectedCols():
            cols += sorted(grid.GetSelectedCols())
            rows += range(grid.GetNumberRows())
        if grid.GetSelectedRows():
            rows += sorted(grid.GetSelectedRows())
            cols += range(grid.GetNumberCols())
        if grid.GetSelectionBlockTopLeft():
            end = grid.GetSelectionBlockBottomRight()
            for i, (r, c) in enumerate(grid.GetSelectionBlockTopLeft()):
                r2, c2 = end[i]
                rows += range(r, r2 + 1)
                cols += range(c, c2 + 1)
        if grid.GetSelectedCells():
            rows += [r for r, c in grid.GetSelectedCells()]
            cols += [c for r, c in grid.GetSelectedCells()]
        if not rows and not cols:
            if grid.GetGridCursorRow() >= 0 and grid.GetGridCursorCol() >= 0:
                rows, cols = [grid.GetGridCursorRow()], [grid.GetGridCursorCol()]
        rows, cols = (sorted(set(y for y in x if y >= 0)) for x in (rows, cols))
        if not rows or not cols: return

        if wx.TheClipboard.Open():
            data = [[grid.GetCellValue(r, c) for c in cols] for r in rows]
            text = "\n".join("\t".join(c for c in r) for r in data)
            d = wx.TextDataObject(text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()


    def on_mouse_over_grid(self, event):
        """
        Handler for moving the mouse over a grid, shows datetime tooltip for
        UNIX timestamp cells.
        """
        tip = ""
        grid = event.EventObject.Parent
        prev_cell = getattr(grid, "_hovered_cell", None)
        x, y = grid.CalcUnscrolledPosition(event.X, event.Y)
        row, col = grid.XYToCell(x, y)
        if row >= 0 and col >= 0:
            value = grid.Table.GetValue(row, col)
            col_name = grid.Table.GetColLabelValue(col).lower()
            if type(value) is int and value > 100000000 \
            and ("time" in col_name or "history" in col_name):
                try:
                    tip = self.db.stamp_to_date(value).strftime(
                          "%Y-%m-%d %H:%M:%S")
                except Exception:
                    tip = unicode(value)
            else:
                tip = unicode(value)
            tip = tip if len(tip) < 1000 else tip[:1000] + ".."
        if (row, col) != prev_cell or not (event.EventObject.ToolTip) \
        or event.EventObject.ToolTip.Tip != tip:
            event.EventObject.SetToolTipString(tip)
        grid._hovered_cell = (row, col)


    def on_button_reset_grid(self, event):
        """
        Handler for clicking to remove sorting and filtering on a grid,
        resets the grid and its view.
        """
        is_table = (event.EventObject == self.button_reset_grid_table)
        grid = self.grid_table if is_table else self.grid_sql
        if grid.Table and isinstance(grid.Table, SqliteGridBase):
            grid.Table.ClearSort(refresh=False)
            grid.Table.ClearFilter()
            grid.ContainingSizer.Layout() # React to grid size change


    def on_button_export_grid(self, event):
        """
        Handler for clicking to export wx.Grid contents to file, allows the
        user to select filename and type and creates the file.
        """
        grid_source = self.grid_table
        sql = ""
        table = ""
        if event.EventObject is self.button_export_sql:
            grid_source = self.grid_sql
            sql = getattr(self, "last_sql", "")
        if not grid_source.Table: return

        if grid_source is self.grid_table:
            table = self.db.schema["table"][grid_source.Table.table.lower()]["name"]
            title = "Table %s" % self.db.quote(table, force=True)
            self.dialog_savefile.Wildcard = export.TABLE_WILDCARD
        else:
            title = "SQL query"
            self.dialog_savefile.Wildcard = export.QUERY_WILDCARD
            grid_source.Table.SeekAhead(True)
        self.dialog_savefile.Filename = util.safe_filename(title)
        self.dialog_savefile.Message = "Save table as"
        self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
        if wx.ID_OK != self.dialog_savefile.ShowModal(): return

        filename = self.dialog_savefile.GetPath()
        exts = export.TABLE_EXTS if grid_source is self.grid_table \
               else export.QUERY_EXTS
        extname = exts[self.dialog_savefile.FilterIndex]
        if not filename.lower().endswith(".%s" % extname):
            filename += ".%s" % extname
        busy = controls.BusyPanel(self, "Exporting \"%s\"." % filename)
        guibase.status("Exporting \"%s\".", filename)
        try:
            make_iterable = grid_source.Table.GetRowIterator
            export.export_data(make_iterable, filename, title, self.db,
                               grid_source.Table.columns, sql, table)
            guibase.logstatus_flash("Exported %s.", filename)
            util.start_file(filename)
        except Exception:
            msg = "Error saving %s:\n\n%s" % \
                  (filename, traceback.format_exc())
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
        finally:
            busy.Close()


    def on_button_close_grid(self, event):
        """
        Handler for clicking to close a grid.
        """
        is_table = (event.EventObject == self.button_close_grid_table)
        grid = self.grid_table if is_table else self.grid_sql
        if not grid.Table or not isinstance(grid.Table, SqliteGridBase):
            return

        if is_table:
            info = grid.Table.GetChangedInfo()
            if grid.Table.IsChanged():
                response = wx.MessageBox(
                    "There are unsaved changes. Are you sure you want to "
                    "commit these changes (%s)?" % info,
                    conf.Title, wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION
                )
                if wx.CANCEL == response: return
                if wx.YES == response:
                    try:
                        grid.Table.SaveChanges()
                    except Exception as e:
                        template = "Error saving table %s in \"%s\".\n\n%%r" % (
                                   self.db.quote(grid.Table.table), self.db)
                        msg, msgfull = template % e, template % traceback.format_exc()
                        guibase.status_flash(msg), guibase.log(msgfull)
                        wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                        return
                else: grid.Table.UndoChanges()
                self.on_change_table(None)

            self.db_grids.pop(grid.Table.table, None)
            i = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while i:
                data = self.tree_tables.GetItemPyData(i)
                if isinstance(data, basestring) \
                and data.lower() == grid.Table.table.lower():
                    self.tree_tables.SetItemBold(i, False)
                    break # while i
                i = self.tree_tables.GetNextSibling(i)

        grid.SetTable(None)
        grid.Parent.Refresh()

        if is_table:
            self.label_table.Label = ""
            self.tb_grid.EnableTool(wx.ID_ADD, False)
            self.tb_grid.EnableTool(wx.ID_DELETE, False)
            self.button_export_table.Enabled = False
            self.button_reset_grid_table.Enabled = False
            self.button_close_grid_table.Enabled = False
            self.label_help_table.Hide()
            self.label_help_table.ContainingSizer.Layout()
        else:
            self.button_export_sql.Enabled = False
            self.button_reset_grid_sql.Enabled = False
            self.button_close_grid_sql.Enabled = False
            self.label_help_sql.Hide()
            self.label_help_sql.ContainingSizer.Layout()


    def on_open_sql(self, stc, event):
        """
        Handler for loading SQL from file, opens file dialog and loads content.
        """
        dialog = wx.FileDialog(
            parent=self, message="Open", defaultFile="",
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_FILE_MUST_EXIST | wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            stc.LoadFile(filename)
        except Exception as e:
            msg = util.format_exc(e)
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_copy_sql(self, stc, event):
        """Handler for copying SQL to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(stc.Text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()


    def on_save_sql(self, stc, event):
        """
        Handler for saving SQL to file, opens file dialog and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.filename))[0]
        if stc is self.stc_sql: filename += " SQL"
        elif stc is self.stc_pragma: filename += " PRAGMA"
        dialog = wx.FileDialog(
            parent=self, message="Save as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            stc.SaveFile(filename)
        except Exception as e:
            msg = util.format_exc(e)
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_keydown_sql(self, event):
        """
        Handler for pressing a key in SQL editor, listens for Alt-Enter and
        executes the currently selected line, or currently active line.
        """
        stc = event.GetEventObject()
        if (event.AltDown() or event.ControlDown()) and wx.WXK_RETURN == event.KeyCode:
            sql = (stc.SelectedText or stc.CurLine[0]).strip()
            if sql:
                self.execute_sql(sql)
        event.Skip() # Allow to propagate to other handlers


    def on_button_sql(self, event):
        """
        Handler for clicking to run an SQL query, runs the selected text or
        whole contents, displays its results, if any, and commits changes
        done, if any.
        """
        sql = (self.stc_sql.SelectedText or self.stc_sql.Text).strip()
        if sql:
            self.execute_sql(sql)


    def on_button_script(self, event):
        """
        Handler for clicking to run multiple SQL statements, runs the selected
        text or whole contents as an SQL script.
        """
        sql = self.stc_sql.SelectedText.strip() or self.stc_sql.Text.strip()
        try:
            if sql:
                guibase.log('Executing SQL script "%s".', sql)
                self.db.connection.executescript(sql)
                self.grid_sql.SetTable(None)
                self.grid_sql.CreateGrid(1, 1)
                self.grid_sql.SetColLabelValue(0, "Affected rows")
                self.grid_sql.SetCellValue(0, 0, "-1")
                self.button_reset_grid_sql.Enabled = False
                self.button_export_sql.Enabled = False
                self.label_help_sql.Show()
                self.label_help_sql.ContainingSizer.Layout()
                size = self.grid_sql.Size
                self.grid_sql.Fit()
                # Jiggle size by 1 pixel to refresh scrollbars
                self.grid_sql.Size = size[0], size[1]-1
                self.grid_sql.Size = size[0], size[1]
        except Exception as e:
            msg = util.format_exc(e)
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def execute_sql(self, sql):
        """Executes the SQL query and populates the SQL grid with results."""
        try:
            grid_data = None
            if sql.lower().startswith(("select", "pragma", "explain")):
                # SELECT statement: populate grid with rows
                grid_data = SqliteGridBase(self.db, sql=sql)
                self.grid_sql.SetTable(grid_data)
                self.button_reset_grid_sql.Enabled = True
                self.button_export_sql.Enabled = True
            else:
                # Assume action query
                affected_rows = self.db.execute_action(sql)
                self.grid_sql.SetTable(None)
                self.grid_sql.CreateGrid(1, 1)
                self.grid_sql.SetColLabelValue(0, "Affected rows")
                self.grid_sql.SetCellValue(0, 0, str(affected_rows))
                self.button_reset_grid_sql.Enabled = False
                self.button_export_sql.Enabled = False
            self.button_close_grid_sql.Enabled = True
            self.label_help_sql.Show()
            self.label_help_sql.ContainingSizer.Layout()
            guibase.logstatus_flash('Executed SQL "%s" (%s).', sql, self.db)
            size = self.grid_sql.Size
            self.grid_sql.Fit()
            # Jiggle size by 1 pixel to refresh scrollbars
            self.grid_sql.Size = size[0], size[1]-1
            self.grid_sql.Size = size[0], size[1]
            self.last_sql = sql
            self.grid_sql.SetColMinimalAcceptableWidth(100)
            if grid_data:
                col_range = range(grid_data.GetNumberCols())
                [self.grid_sql.AutoSizeColLabelSize(x) for x in col_range]
        except Exception as e:
            msg = util.format_exc(e)
            guibase.logstatus_flash(msg)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def get_unsaved_grids(self):
        """
        Returns a list of SqliteGridBase grids where changes have not been
        saved after changing.
        """
        return [g for g in self.db_grids.values() if g.IsChanged()]


    def save_unsaved_grids(self):
        """Saves all data in unsaved table grids, returns success/failure."""
        result = True
        for grid in (x for x in self.db_grids.values() if x.IsChanged()):
            try:
                grid.SaveChanges()
            except Exception as e:
                result = False
                template = "Error saving table %s in \"%s\".\n\n%%r" % (
                           self.db.quote(grid.table), self.db)
                msg, msgfull = template % e, template % traceback.format_exc()
                guibase.status_flash(msg), guibase.log(msgfull)
                wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                break # for grid
        return result


    def on_change_table(self, event):
        """
        Handler when table grid data is changed, refreshes icons,
        table lists and database display.
        """
        grid_data = self.grid_table.Table
        # Enable/disable commit and rollback icons
        self.tb_grid.EnableTool(wx.ID_SAVE, grid_data.IsChanged())
        self.tb_grid.EnableTool(wx.ID_UNDO, grid_data.IsChanged())
        # Highlight changed tables in the table list
        colour = conf.DBTableChangedColour if grid_data.IsChanged() \
                 else self.tree_tables.ForegroundColour
        item = self.tree_tables.GetNext(self.tree_tables.RootItem)
        while item and item.IsOk():
            list_table = self.tree_tables.GetItemPyData(item)
            if isinstance(list_table, basestring):
                if list_table.lower() == grid_data.table.lower():
                    self.tree_tables.SetItemTextColour(item, colour)
                    break # while item and item.IsOk()
            item = self.tree_tables.GetNextSibling(item)

        # Mark database as changed/pristine in the parent notebook tabs
        for i in range(self.parent_notebook.GetPageCount()):
            if self.parent_notebook.GetPage(i) == self:
                suffix = "*" if self.get_unsaved_grids() else ""
                title = self.title + suffix
                if self.parent_notebook.GetPageText(i) != title:
                    self.parent_notebook.SetPageText(i, title)
                break # for i


    def on_commit_table(self, event):
        """Handler for clicking to commit the changed database table."""
        info = self.grid_table.Table.GetChangedInfo()
        if wx.OK == wx.MessageBox(
            "Are you sure you want to commit these changes (%s)?" %
            info, conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            guibase.log("Committing %s in table %s (%s).", info,
                     self.db.quote(self.grid_table.Table.table), self.db)
            self.grid_table.Table.SaveChanges()
            self.on_change_table(None)
            # Refresh tables list with updated row counts
            tablemap = dict((t["name"], t)
                            for t in self.db.get_tables(refresh=True, full=True))
            item = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while item and item.IsOk():
                table = self.tree_tables.GetItemPyData(item)
                if isinstance(table, basestring):
                    self.tree_tables.SetItemText(item, util.plural(
                        "row", tablemap[table]["rows"]
                    ), 1)
                    if table == self.grid_table.Table.table:
                        self.tree_tables.SetItemBold(item,
                        self.grid_table.Table.IsChanged())
                item = self.tree_tables.GetNextSibling(item)
            # Refresh cell colours; without CallAfter wx 2.8 can crash
            wx.CallLater(0, self.grid_table.ForceRefresh)


    def on_rollback_table(self, event):
        """Handler for clicking to rollback the changed database table."""
        self.grid_table.Table.UndoChanges()
        self.on_change_table(None)
        # Refresh scrollbars and colours; without CallAfter wx 2.8 can crash
        wx.CallLater(0, lambda: (self.grid_table.ContainingSizer.Layout(),
                                 self.grid_table.ForceRefresh()))


    def on_insert_row(self, event):
        """
        Handler for clicking to insert a table row, lets the user edit a new
        grid line.
        """
        self.grid_table.InsertRows(pos=0, numRows=1)
        self.grid_table.SetGridCursor(0, self.grid_table.GetGridCursorCol())
        self.grid_table.Scroll(self.grid_table.GetScrollPos(wx.HORIZONTAL), 0)
        self.grid_table.Refresh()
        self.on_change_table(None)
        # Refresh scrollbars; without CallAfter wx 2.8 can crash
        wx.CallAfter(self.grid_table.ContainingSizer.Layout)


    def on_delete_row(self, event):
        """
        Handler for clicking to delete a table row, removes the row from grid.
        """
        selected_rows = self.grid_table.GetSelectedRows()
        cursor_row = self.grid_table.GetGridCursorRow()
        if cursor_row >= 0:
            selected_rows.append(cursor_row)
        for row in selected_rows:
            self.grid_table.DeleteRows(row)
        self.grid_table.ContainingSizer.Layout() # Refresh scrollbars
        self.on_change_table(None)


    def on_update_grid_table(self, event):
        """Refreshes the table grid UI components, like toolbar icons."""
        self.tb_grid.EnableTool(wx.ID_SAVE, self.grid_table.Table.IsChanged())
        self.tb_grid.EnableTool(wx.ID_UNDO, self.grid_table.Table.IsChanged())


    def on_change_tree_tables(self, event):
        """
        Handler for selecting an item in the tables list, loads the table data
        into the table grid.
        """
        item = event.GetItem()
        if not item or not item.IsOk(): return

        table = self.tree_tables.GetItemPyData(item)
        if not isinstance(table, basestring): return

        lower = table.lower()
        if not self.grid_table.Table \
        or self.grid_table.Table.table.lower() != lower:
            i = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while i:
                text = self.tree_tables.GetItemText(i).lower()
                self.tree_tables.SetItemBold(i, text == lower)
                i = self.tree_tables.GetNextSibling(i)
            guibase.log("Loading table %s (%s).", self.db.quote(table), self.db)
            busy = controls.BusyPanel(self, "Loading table %s." %
                                      self.db.quote(table, force=True))
            try:
                grid_data = self.db_grids.get(lower)
                if not grid_data:
                    grid_data = SqliteGridBase(self.db, table=table)
                    self.db_grids[lower] = grid_data
                self.label_table.Label = "Table %s:" % self.db.quote(table, force=True)
                self.grid_table.SetTable(grid_data)
                self.page_tables.Layout() # React to grid size change
                self.grid_table.Scroll(0, 0)
                self.grid_table.SetColMinimalAcceptableWidth(100)
                col_range = range(grid_data.GetNumberCols())
                [self.grid_table.AutoSizeColLabelSize(x) for x in col_range]
                self.on_change_table(None)
                self.tb_grid.EnableTool(wx.ID_ADD, True)
                self.tb_grid.EnableTool(wx.ID_DELETE, True)
                self.button_export_table.Enabled = True
                self.button_reset_grid_table.Enabled = True
                self.button_close_grid_table.Enabled = True
                self.label_help_table.Show()
                self.label_help_table.ContainingSizer.Layout()
                busy.Close()
            except Exception:
                busy.Close()
                errormsg = "Could not load table %s.\n\n%s" % \
                           (self.db.quote(table), traceback.format_exc())
                guibase.logstatus_flash(errormsg)
                wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_rclick_tree_tables(self, event):
        """
        Handler for right-clicking an item in the tables list,
        opens popup menu for choices to export data.
        """
        item, tree = event.GetItem(), self.tree_tables
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item)
        if not data: return

        def select_item(item, *a, **kw):
            tree.SelectItem(item)
        def clipboard_copy(text, *a, **kw):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
        def toggle_items(*a, **kw):
            if not tree.IsExpanded(tree.RootItem): tree.Expand(tree.RootItem)
            items, item = [], tree.GetNext(tree.RootItem)
            while item and item.IsOk():
                items.append(item)
                item = tree.GetNextSibling(item)
            if any(map(tree.IsExpanded, items)):
                for item in items: tree.Collapse(item)
            else: tree.ExpandAll(tree.RootItem)

        menu = wx.Menu()
        item_file = item_database = None
        if isinstance(data, basestring): # Single table
            item_name     = wx.MenuItem(menu, -1, 'Table %s' % self.db.quote(data, force=True))
            item_copy     = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql = wx.MenuItem(menu, -1, "Copy CREATE &SQL")
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                      id=item_name.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data),
                      id=item_copy.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, self.db.get_sql(table=data)),
                      id=item_copy_sql.GetId())

            menu.AppendItem(item_name)
            menu.AppendSeparator()
            menu.AppendItem(item_copy)
            menu.AppendItem(item_copy_sql)

            item_file     = wx.MenuItem(menu, -1, '&Export table to file')
            item_database = wx.MenuItem(menu, -1, 'Export table to another &database')
        elif isinstance(data, dict): # Column
            item_name     = wx.MenuItem(menu, -1, 'Column "%s.%s"' % (
                            self.db.quote(data["table"]), self.db.quote(data["name"])))
            item_copy     = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql = wx.MenuItem(menu, -1, "Copy column &SQL")
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                      id=item_name.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"]),
                      id=item_copy.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                self.db.get_sql(table=data["table"], column=data["name"])
            ), id=item_copy_sql.GetId())

            menu.AppendItem(item_name)
            menu.AppendSeparator()
            menu.AppendItem(item_copy)
            menu.AppendItem(item_copy_sql)

        else: # Tables list
            item_copy     = wx.MenuItem(menu, -1, "&Copy table names")
            item_expand   = wx.MenuItem(menu, -1, "&Toggle tables expanded/collapsed")
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, ", ".join(data)),
                      id=item_copy.GetId())
            menu.Bind(wx.EVT_MENU, toggle_items, id=item_expand.GetId())

            menu.AppendItem(item_copy)
            menu.AppendItem(item_expand)

            item_file     = wx.MenuItem(menu, -1, "&Export all tables to file")
            item_database = wx.MenuItem(menu, -1, "Export all tables to another &database")

        if item_file and item_database:
            menu.AppendSeparator()
            menu.AppendItem(item_file)
            menu.AppendItem(item_database)
            tables = [data] if isinstance(data, basestring) else data
            menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_file, tables),
                     id=item_file.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_base, tables),
                     id=item_database.GetId())

        item0 = tree.GetSelection()
        if item != item0: select_item(item)
        tree.PopupMenu(menu)
        if item0 and item != item0: select_item(item0)


    def on_export_data_file(self, tables, event):
        """
        Handler for exporting one or more tables to file, opens file dialog
        and performs export.
        """
        if len(tables) == 1:
            filename = "Table %s" % tables[0]
            self.dialog_savefile.Filename = util.safe_filename(filename)
            self.dialog_savefile.Message = "Save table as"
            self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
        else:
            self.dialog_savefile.Filename = "Filename will be ignored"
            self.dialog_savefile.Message = "Choose directory where to save files"
            self.dialog_savefile.WindowStyle ^= wx.FD_OVERWRITE_PROMPT
        self.dialog_savefile.Wildcard = export.TABLE_WILDCARD
        if wx.ID_OK != self.dialog_savefile.ShowModal(): return

        wx.YieldIfNeeded() # Allow UI to refresh
        extname = export.TABLE_EXTS[self.dialog_savefile.FilterIndex]
        path = self.dialog_savefile.GetPath()
        filenames = [path]
        if len(tables) > 1:
            path, _ = os.path.split(path)
            filenames, names_unique = [], []
            for t in tables:
                name = base = util.safe_filename("Table %s" % t)
                counter = 2
                while name in names_unique:
                    name, counter = "%s (%s)" % (base, counter), counter + 1
                filenames.append(os.path.join(path, name + "." + extname))
                names_unique.append(name)

            existing = next((x for x in filenames if os.path.exists(x)), None)
            if existing and wx.YES != wx.MessageBox(
                "Some files already exist, like %s.\n"
                "Do you want to replace them?" % os.path.basename(existing),
                conf.Title, wx.YES | wx.NO | wx.ICON_WARNING
            ): return

        for table, filename in zip(tables, filenames):
            if not filename.lower().endswith(".%s" % extname):
                filename += ".%s" % extname
            busy = controls.BusyPanel(self, 'Exporting %s.' % filename)
            guibase.status('Exporting %s.', filename)
            try:
                make_iterable = lambda: self.db.execute("SELECT * FROM %s" % self.db.quote(table))
                export.export_data(make_iterable, filename, "Table %s" % self.db.quote(table, force=True),
                                   self.db, self.db.get_table_columns(table), table=table)
                guibase.logstatus_flash("Exported %s.", filename)
                util.start_file(filename)
            except Exception:
                msg = "Error saving %s:\n\n%s" % \
                      (filename, traceback.format_exc())
                guibase.logstatus_flash(msg)
                return wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
            finally:
                busy.Close()


    def on_export_data_base(self, tables, event):
        """
        Handler for exporting one or more tables to another database,
        opens file dialog and performs direct copy.
        """
        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.FileDialog(
            parent=self, message="Select database to export tables to",
            defaultFile="", wildcard=wildcard,
            style=wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        wx.YieldIfNeeded() # Allow UI to refresh
        filename2 = dialog.GetPath()

        try:
            self.db.execute("ATTACH DATABASE ? AS main2", [filename2])
        except Exception as e:
            errormsg = "Could not load database %s.\n\n%s" % \
                       (filename2, traceback.format_exc())
            guibase.log(errormsg)
            errormsg = "Could not load database %s.\n\n%s" % \
                       (filename2, e)
            guibase.status_flash(errormsg)
            return wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)

        entrymsg = ('Name conflict on exporting table %(table)s as %(table2)s.\n'
                    'Database %(filename2)s %(entryheader)s '
                    'table named %(table2)s.\n\nYou can:\n'
                    '- enter another name to export table %(table)s as,\n'
                    '- keep same name to overwrite table %(table2)s,\n'
                    '- or set blank to skip table %(table)s.')
        insert_sql, success = "INSERT INTO main2.%s SELECT * FROM main.%s", False
        db1_tables = set(x["name"].lower() for x in self.db.get_tables())
        try:
            db2_tables_lower = set(x["name"].lower() for x in self.db.execute(
                "SELECT name FROM main2.sqlite_master WHERE type = 'table'"
            ).fetchall())
            tables1, tables2, tables2_lower = [], [], []

            # Check for name conflicts with existing tables and ask user choice
            for table in tables:
                t1_lower = table.lower()
                if t1_lower not in db2_tables_lower and t1_lower not in tables2_lower:
                    tables1.append(table); tables2.append(table)
                    tables2_lower.append(table.lower())
                    continue # for table

                table2 = t2_lower_prev = table
                entryheader = "already contains a"
                while table2:
                    entrydialog = wx.TextEntryDialog(self, entrymsg % {
                        "table": self.db.quote(table), "table2": self.db.quote(table2),
                        "filename2": filename2,        "entryheader": entryheader
                    }, conf.Title, table2)
                    if wx.ID_OK != entrydialog.ShowModal(): return

                    value = entrydialog.GetValue().strip()
                    if not self.db.is_valid_name(table=value):
                        msg = "%s is not a valid table name." % self.db.quote(value, force=True)
                        wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                        continue # while table2

                    t2_lower_prev, table2 = table2.lower(), value
                    t2_lower = table2.lower()

                    if not table2 \
                    or t1_lower == t2_lower == t2_lower_prev: break # while table2

                    if t2_lower in tables2_lower and t2_lower_prev != t2_lower:
                        # User entered a duplicate rename
                        entryheader = "will contain another"
                        continue # while table2
                    if t2_lower in db2_tables_lower and t2_lower_prev != t2_lower:
                        # User entered another table existing in db2
                        entryheader = "already contains a"
                        continue # while table2
                    break

                if filename2.lower() == self.db.filename.lower() \
                and t2_lower in db1_tables: # Needs rename if same file
                    continue # for table
                if table2:
                    tables1.append(table); tables2.append(table2)
                    tables2_lower.append(t2_lower)

            for table, table2 in zip(tables1, tables2):
                t1_lower, t2_lower = table.lower(), table2.lower()
                extra = "" if t1_lower == t2_lower \
                        else " as %s" % self.db.quote(table2, force=True)

                create_sql = self.db.transform_sql(
                    self.db.get_sql(table=table, format=False), "table",
                    rename={"table": "main2." + self.db.quote(table2)}
                )
                try:
                    if t2_lower in db2_tables_lower:
                        guibase.log("Dropping table %s in %s.", self.db.quote(table2), filename2)
                        self.db.execute("DROP TABLE main2.%s" % self.db.quote(table2))
                    guibase.log("Creating table %s in %s, using %s.",
                                self.db.quote(table2, force=True), filename2, create_sql)
                    self.db.execute(create_sql)

                    # Assemble table indices to copy
                    indices = [dict(x) for x in self.db.schema["index"].values()
                               if t1_lower == x["tbl_name"].lower()]
                    indices2 = [x["name"] for x in self.db.execute(
                        "SELECT name FROM main2.sqlite_master "
                        "WHERE type = 'index' AND sql != ''"
                    ).fetchall()]
                    for index in indices:
                        name = base = index["name"]; counter = 2
                        if t1_lower != t2_lower:
                            name = base = re.sub(re.escape(table), re.sub(r"\W", "", table2),
                                                 name, count=1, flags=re.I | re.U)
                        while name in indices2:
                            name, counter = "%s_%s" % (base, counter), counter + 1
                        indices2.append(name)
                        index_sql = self.db.transform_sql(
                            index["sql"], "index",
                            rename={"table": self.db.quote(table2),
                                    "index": "main2." + self.db.quote(name)}
                        )
                        guibase.log("Creating index %s on table %s in %s, using %s.",
                                    self.db.quote(name, force=True),
                                    self.db.quote(table2, force=True),
                                    filename2, index_sql)
                        self.db.execute(index_sql)

                    self.db.execute(insert_sql % (self.db.quote(table2), self.db.quote(table)))
                    guibase.status_flash("Exported table %s to %s%s.",
                                         self.db.quote(table), filename2, extra)
                    db2_tables_lower.add(t2_lower)
                except Exception as e:
                    errormsg = "Could not export table %s%s.\n\n%s" % \
                               (self.db.quote(table), extra, traceback.format_exc())
                    guibase.log(errormsg)
                    errormsg = "Could not export table %s%s.\n\n%s" % \
                               (self.db.quote(table), extra, e)
                    guibase.status_flash(errormsg)
                    wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)
                    break # for table
            else: # nobreak
                success = True
        except Exception as e:
            errormsg = 'Failed to read database %s.\n\n%s' % \
                       (filename2, traceback.format_exc())
            guibase.log(errormsg)
            errormsg = 'Failed to read database %s.\n\n%s' % \
                       (filename2, e)
            guibase.status_flash(errormsg)
            wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)
        finally:
            try: self.db.execute("DETACH DATABASE main2")
            except Exception: pass

        if success and tables1:
            same_name = (tables1[0].lower() == tables2_lower[0])
            t = "%s tables" % len(tables1) if len(tables1) > 1 \
                else "table %s" % self.db.quote(tables1[0], force=True)
            extra = "" if len(tables1) > 1 or same_name \
                    else " as %s" % self.db.quote(tables2[0], force=True)
            guibase.status_flash("Exported %s to %s%s.", t, filename2, extra)
            wx.PostEvent(self.TopLevelParent, OpenDatabaseEvent(file=filename2))


    def on_sort_grid_column(self, event):
        """
        Handler for clicking a table grid column, sorts table by the column.
        """
        grid = event.GetEventObject()
        if grid.Table and isinstance(grid.Table, SqliteGridBase):
            row, col = event.GetRow(), event.GetCol()
            # Remember scroll positions, as grid update loses them
            scroll_hor = grid.GetScrollPos(wx.HORIZONTAL)
            scroll_ver = grid.GetScrollPos(wx.VERTICAL)
            if row < 0: # Only react to clicks in the header
                grid.Table.SortColumn(col)
            grid.ContainingSizer.Layout() # React to grid size change
            grid.Scroll(scroll_hor, scroll_ver)


    def on_filter_grid_column(self, event):
        """
        Handler for right-clicking a table grid column, lets the user
        change the column filter.
        """
        grid = event.GetEventObject()
        if grid.Table and isinstance(grid.Table, SqliteGridBase):
            row, col = event.GetRow(), event.GetCol()
            # Remember scroll positions, as grid update loses them
            if row < 0: # Only react to clicks in the header
                grid_data = grid.Table
                current_filter = unicode(grid_data.filters[col]) \
                                 if col in grid_data.filters else ""
                name = self.db.quote(grid_data.columns[col]["name"], force=True)
                dialog = wx.TextEntryDialog(self,
                    "Filter column %s by:" % name,
                    "Filter", defaultValue=current_filter,
                    style=wx.OK | wx.CANCEL)
                if wx.ID_OK == dialog.ShowModal():
                    new_filter = dialog.GetValue()
                    if len(new_filter):
                        busy = controls.BusyPanel(self.page_tables,
                            'Filtering column %s by "%s".' %
                            (name, new_filter))
                        grid_data.AddFilter(col, new_filter)
                        busy.Close()
                    else:
                        grid_data.RemoveFilter(col)
            grid.ContainingSizer.Layout() # React to grid size change


    def load_data(self):
        """Loads data from our Database."""
        self.label_title.Label = 'Database "%s":' % self.db

        # Restore last search text, if any
        if conf.SearchHistory and conf.SearchHistory[-1] != "":
            self.edit_searchall.Value = conf.SearchHistory[-1]
        if conf.SearchHistory and conf.SearchHistory[-1] == "":
            # Clear the empty search flag
            conf.SearchHistory = conf.SearchHistory[:-1]
        self.edit_searchall.SetChoices(conf.SearchHistory)

        # Restore last cached search results page
        last_search = conf.LastSearchResults.get(self.db.filename)
        if last_search:
            title = last_search.get("title", "")
            html = last_search.get("content", "")
            info = last_search.get("info")
            tabid = self.counter() if 0 != last_search.get("id") else 0
            self.html_searchall.InsertTab(0, title, tabid, html, info)
        wx.CallLater(100, self.load_later_data)
        wx.CallLater(500, self.update_info_page, False)
        wx.CallLater(200, self.load_tables_data)


    def load_later_data(self):
        """
        Loads later data from the database, like table metainformation,
        used as a background callback to speed up page opening.
        """
        if self: wx.CallAfter(self.update_tabheader)


    def load_tables_data(self):
        """Loads table data into table tree and SQL editor."""
        try:
            tables = self.db.get_tables(full=True)
            # Fill table tree with information on row counts and columns
            self.tree_tables.DeleteAllItems()
            root = self.tree_tables.AddRoot("SQLITE")
            self.tree_tables.SetItemPyData(root, [x["name"] for x in tables])
            child = None
            for table in tables:
                child = self.tree_tables.AppendItem(root, table["name"])
                self.tree_tables.SetItemText(child, util.plural(
                    "row", table["rows"]
                ), 1)
                self.tree_tables.SetItemPyData(child, table["name"])

                for col in self.db.get_table_columns(table["name"]):
                    subchild = self.tree_tables.AppendItem(child, col["name"])
                    self.tree_tables.SetItemText(subchild, col["type"], 1)
                    self.tree_tables.SetItemPyData(subchild, dict(col, table=table["name"]))

            self.tree_tables.Expand(root)
            if child:
                # Nudge columns to fit and fill the header exactly.
                self.tree_tables.Expand(child)
                self.tree_tables.SetColumnWidth(0, -1)
                self.tree_tables.SetColumnWidth(1, min(70,
                    self.tree_tables.Size.width -
                    self.tree_tables.GetColumnWidth(0) - 5))
                self.tree_tables.Collapse(child)

            # Add table and column names to SQL editor autocomplete
            self.stc_sql.AutoCompClearAdded()
            for table in tables:
                coldata = self.db.get_table_columns(table["name"])
                fields = [self.db.quote(c["name"]) for c in coldata]
                self.stc_sql.AutoCompAddSubWords(self.db.quote(table["name"]), fields)
        except Exception:
            if self:
                errormsg = "Error loading table data from %s.\n\n%s" % \
                           (self.db, traceback.format_exc())
                guibase.log(errormsg)


    def update_tabheader(self):
        """Updates page tab header with option to close page."""
        if self:
            self.ready_to_close = True
        if self:
            self.TopLevelParent.update_notebook_header()



class SqliteGridBase(wx.grid.PyGridTableBase):
    """
    Table base for wx.grid.Grid, can take its data from a single table, or from
    the results of any SELECT query.
    """

    """How many rows to seek ahead for query grids."""
    SEEK_CHUNK_LENGTH = 100


    def __init__(self, db, table="", sql=""):
        super(SqliteGridBase, self).__init__()
        self.is_query = bool(sql)
        self.db = db
        self.sql = sql
        self.table = table
        # ID here is a unique value identifying rows in this object,
        # no relation to table data
        self.idx_all = [] # An ordered list of row identifiers in rows_all
        self.rows_all = {} # Unfiltered, unsorted rows {id: row, }
        self.rows_current = [] # Currently shown (filtered/sorted) rows
        self.rowids = {} # SQLite table rowids, used for UPDATE and DELETE
        self.idx_changed = set() # set of indices for changed rows in rows_all
        self.rows_backup = {} # For changed rows {id: original_row, }
        self.idx_new = [] # Unsaved added row indices
        self.rows_deleted = {} # Uncommitted deleted rows {id: deleted_row, }
        self.rowid_name = None
        self.iterator_index = -1
        self.sort_ascending = True
        self.sort_column = None # Index of column currently sorted by
        self.filters = {} # {col: value, }
        self.attrs = {} # {"new": wx.grid.GridCellAttr, }

        if not self.is_query:
            if db.has_rowid(table): self.rowid_name = "rowid"
            cols = ("%s, *" % self.rowid_name) if self.rowid_name else "*"
            self.sql = "SELECT %s FROM %s" % (cols, db.quote(table))
        self.row_iterator = db.execute(self.sql)
        if self.is_query:
            self.columns = [{"name": c[0], "type": "TEXT"}
                            for c in self.row_iterator.description or ()]
            # Doing some trickery here: we can only know the row count when we have
            # retrieved all the rows, which is preferrable not to do at first,
            # since there is no telling how much time it can take. Instead, we
            # update the row count chunk by chunk.
            self.row_count = self.SEEK_CHUNK_LENGTH
            TYPES = dict((v, k) for k, vv in {"INTEGER": (int, long, bool),
                         "REAL": (float,)}.items() for v in vv)
            # Seek ahead on rows and get column information from first values
            try: self.SeekToRow(self.SEEK_CHUNK_LENGTH - 1)
            except Exception: pass
            if self.rows_current:
                for col in self.columns:
                    value = self.rows_current[0][col["name"]]
                    col["type"] = TYPES.get(type(value), col["type"])
        else:
            self.columns = db.get_table_columns(table)
            self.row_count = next(db.execute("SELECT COUNT(*) AS rows FROM %s"
                                  % db.quote(table)))["rows"]


    def GetColLabelValue(self, col):
        label = self.columns[col]["name"]
        if col == self.sort_column:
            label += u" ↓" if self.sort_ascending else u" ↑"
        if col in self.filters:
            if "TEXT" == self.columns[col]["type"]:
                label += "\nlike \"%s\"" % self.filters[col]
            else:
                label += "\n= %s" % self.filters[col]
        return label


    def GetNumberRows(self):
        result = self.row_count
        if self.filters:
            result = len(self.rows_current)
        return result


    def GetNumberCols(self):
        return len(self.columns)


    def SeekAhead(self, to_end=False):
        """
        Seeks ahead on the query cursor, by the chunk length or until the end.

        @param   to_end  if True, retrieves all rows
        """
        seek_count = self.row_count + self.SEEK_CHUNK_LENGTH - 1
        if to_end:
            seek_count = sys.maxsize
        self.SeekToRow(seek_count)


    def SeekToRow(self, row):
        """Seeks ahead on the row iterator to the specified row."""
        rows_before = len(self.rows_all)
        while self.row_iterator and (self.iterator_index < row):
            rowdata = None
            try:
                rowdata = self.row_iterator.next()
            except Exception:
                pass
            if rowdata:
                idx = id(rowdata)
                if not self.is_query and self.rowid_name in rowdata:
                    self.rowids[idx] = rowdata[self.rowid_name]
                    del rowdata[self.rowid_name]
                rowdata["__id__"] = idx
                rowdata["__changed__"] = False
                rowdata["__new__"] = False
                rowdata["__deleted__"] = False
                self.rows_all[idx] = rowdata
                self.rows_current.append(rowdata)
                self.idx_all.append(idx)
                self.iterator_index += 1
            else:
                self.row_iterator = None
        if self.is_query:
            if (self.row_count != self.iterator_index + 1):
                self.row_count = self.iterator_index + 1
                self.NotifyViewChange(rows_before)


    def GetValue(self, row, col):
        value = None
        if row < self.row_count:
            self.SeekToRow(row)
            if row < len(self.rows_current):
                value = self.rows_current[row][self.columns[col]["name"]]
                if type(value) is buffer:
                    value = str(value).decode("latin1")
        if value and "BLOB" == self.columns[col]["type"] and isinstance(value, basestring):
            # Blobs need special handling, as the text editor does not
            # support control characters or null bytes.
            value = value.encode("unicode-escape")
        return value if value is not None else ""


    def GetRow(self, row):
        """Returns the data dictionary of the specified row."""
        value = None
        if row < self.row_count:
            self.SeekToRow(row)
            if row < len(self.rows_current):
                value = self.rows_current[row]
        return value


    def GetRowIterator(self):
        """
        Returns a separate iterator producing all grid rows,
        in current sort order and matching current filter.
        """
        def generator(cursor):
            row = next(cursor)
            while row:
                while row and self._is_row_filtered(row): row = next(cursor)
                if row: yield row
                row = next(cursor)

        sql = self.sql
        if self.sort_column is not None:
            sql = "SELECT * FROM (%s) ORDER BY %s%s" % (
                sql, self.db.quote(self.columns[self.sort_column]["name"]),
                "" if self.sort_ascending else " DESC"
            )
        cursor = self.db.execute(sql)
        return generator(cursor) if self.filters else cursor


    def SetValue(self, row, col, val):
        if not (self.is_query) and (row < self.row_count):
            accepted = False
            col_value = None
            if "INTEGER" == self.columns[col]["type"]:
                if not val: # Set column to NULL
                    accepted = True
                else:
                    try:
                        # Allow user to enter a comma for decimal separator.
                        valc = val.replace(",", ".")
                        col_value = float(valc) if ("." in valc) else int(val)
                        accepted = True
                    except Exception:
                        pass
            elif "BLOB" == self.columns[col]["type"]:
                # Blobs need special handling, as the text editor does not
                # support control characters or null bytes.
                try:
                    col_value = val.decode("unicode-escape")
                    accepted = True
                except UnicodeError: # Text is not valid escaped Unicode
                    pass
            else:
                col_value = val
                accepted = True
            if accepted:
                self.SeekToRow(row)
                data = self.rows_current[row]
                idx = data["__id__"]
                if not data["__new__"]:
                    if idx not in self.rows_backup:
                        # Backup only existing rows, new rows will be dropped
                        # on rollback anyway.
                        self.rows_backup[idx] = data.copy()
                    data["__changed__"] = True
                    self.idx_changed.add(idx)
                data[self.columns[col]["name"]] = col_value
                if self.View: self.View.Refresh()


    def IsChanged(self):
        """Returns whether there is uncommitted changed data in this grid."""
        lengths = map(len, [self.idx_changed, self.idx_new, self.rows_deleted])
        return any(lengths)


    def GetChangedInfo(self):
        """Returns an info string about the uncommited changes in this grid."""
        infolist = []
        values = {"new": len(self.idx_new), "changed": len(self.idx_changed),
                  "deleted": len(self.rows_deleted), }
        for label, count in values.items():
            if count:
                infolist.append("%s %s row%s"
                    % (count, label, "s" if count != 1 else ""))
        return ", ".join(infolist)


    def GetAttr(self, row, col, kind):
        if not self.attrs:
            for n in ["new", "default", "row_changed", "cell_changed",
            "newblob", "defaultblob", "row_changedblob", "cell_changedblob"]:
                self.attrs[n] = wx.grid.GridCellAttr()
            for n in ["new", "newblob"]:
                self.attrs[n].SetBackgroundColour(conf.GridRowInsertedColour)
            for n in ["row_changed", "row_changedblob"]:
                self.attrs[n].SetBackgroundColour(conf.GridRowChangedColour)
            for n in ["cell_changed", "cell_changedblob"]:
                self.attrs[n].SetBackgroundColour(conf.GridCellChangedColour)
            for n in ["newblob", "defaultblob",
            "row_changedblob", "cell_changedblob"]:
                self.attrs[n].SetEditor(wx.grid.GridCellAutoWrapStringEditor())
        # Sanity check, UI controls can still be referring to a previous table
        col = min(col, len(self.columns) - 1)

        blob = "blob" if (self.columns[col]["type"].lower() == "blob") else ""
        attr = self.attrs["default%s" % blob]
        if row < len(self.rows_current):
            if self.rows_current[row]["__changed__"]:
                idx = self.rows_current[row]["__id__"]
                value = self.rows_current[row][self.columns[col]["name"]]
                backup = self.rows_backup[idx][self.columns[col]["name"]]
                if backup != value:
                    attr = self.attrs["cell_changed%s" % blob]
                else:
                    attr = self.attrs["row_changed%s" % blob]
            elif self.rows_current[row]["__new__"]:
                attr = self.attrs["new%s" % blob]
        attr.IncRef()
        return attr


    def InsertRows(self, row, numRows):
        """Inserts new, unsaved rows at position 0 (row is ignored)."""
        rows_before = len(self.rows_current)
        for i in range(numRows):
            # Construct empty dict from column names
            rowdata = dict((col["name"], None) for col in self.columns)
            idx = id(rowdata)
            rowdata["__id__"] = idx
            rowdata["__changed__"] = False
            rowdata["__new__"] = True
            rowdata["__deleted__"] = False
            # Insert rows at the beginning, so that they can be edited
            # immediately, otherwise would need to retrieve all rows first.
            self.idx_all.insert(0, idx)
            self.rows_current.insert(0, rowdata)
            self.rows_all[idx] = rowdata
            self.idx_new.append(idx)
        self.row_count += numRows
        self.NotifyViewChange(rows_before)


    def DeleteRows(self, row, numRows):
        """Deletes rows from a specified position."""
        if row + numRows - 1 < self.row_count:
            self.SeekToRow(row + numRows - 1)
            rows_before = len(self.rows_current)
            for i in range(numRows):
                data = self.rows_current[row]
                idx = data["__id__"]
                del self.rows_current[row]
                if idx in self.rows_backup:
                    # If row was changed, switch to its backup data
                    data = self.rows_backup[idx]
                    del self.rows_backup[idx]
                    self.idx_changed.remove(idx)
                if not data["__new__"]:
                    # Drop new rows on delete, rollback can't restore them.
                    data["__changed__"] = False
                    data["__deleted__"] = True
                    self.rows_deleted[idx] = data
                else:
                    self.idx_new.remove(idx)
                    self.idx_all.remove(idx)
                    del self.rows_all[idx]
                self.row_count -= numRows
            self.NotifyViewChange(rows_before)


    def NotifyViewChange(self, rows_before):
        """
        Notifies the grid view of a change in the underlying grid table if
        current row count is different.
        """
        if self.View:
            args = None
            rows_now = len(self.rows_current)
            if rows_now < rows_before:
                args = [self, wx.grid.GRIDTABLE_NOTIFY_ROWS_DELETED,
                        rows_now, rows_before - rows_now]
            elif rows_now > rows_before:
                args = [self, wx.grid.GRIDTABLE_NOTIFY_ROWS_APPENDED,
                        rows_now - rows_before]
            if args:
                self.View.ProcessTableMessage(wx.grid.GridTableMessage(*args))



    def AddFilter(self, col, val):
        """
        Adds a filter to the grid data on the specified column. Ignores the
        value if invalid for the column (e.g. a string for an integer column).

        @param   col   column index
        @param   val   a simple value for filtering. For numeric columns, the
                       value is matched exactly, and for text columns,
                       matched by substring.
        """
        accepted_value = None
        if "INTEGER" == self.columns[col]["type"]:
            try:
                # Allow user to enter a comma for decimal separator.
                accepted_value = float(val.replace(",", ".")) \
                                 if ("." in val or "," in val) \
                                 else int(val)
            except ValueError:
                pass
        else:
            accepted_value = val
        if accepted_value is not None:
            self.filters[col] = accepted_value
            self.Filter()


    def RemoveFilter(self, col):
        """Removes filter on the specified column, if any."""
        if col in self.filters:
            del self.filters[col]
        self.Filter()


    def ClearFilter(self, refresh=True):
        """Clears all added filters."""
        self.filters.clear()
        if refresh:
            self.Filter()


    def ClearSort(self, refresh=True):
        """Clears current sort."""
        self.sort_column = None
        if refresh:
            self.rows_current[:].sort(
                key=lambda x: self.idx_all.index(x["__id__"])
            )
            if self.View:
                self.View.ForceRefresh()


    def Filter(self):
        """
        Filters the grid table with the currently added filters.
        """
        self.SeekToRow(self.row_count - 1)
        rows_before = len(self.rows_current)
        del self.rows_current[:]
        for idx in self.idx_all:
            row = self.rows_all[idx]
            if not row["__deleted__"] and not self._is_row_filtered(row):
                self.rows_current.append(row)
        if self.sort_column is not None:
            pass #if self.View: self.View.Fit()
        else:
            self.sort_ascending = not self.sort_ascending
            self.SortColumn(self.sort_column)
        self.NotifyViewChange(rows_before)


    def SortColumn(self, col):
        """
        Sorts the grid data by the specified column, reversing the previous
        sort order, if any.
        """
        self.SeekToRow(self.row_count - 1)
        self.sort_ascending = not self.sort_ascending
        self.sort_column = col
        compare = cmp
        if 0 <= col < len(self.columns):
            col_name = self.columns[col]["name"]
            def compare(a, b):
                aval, bval = a[col_name], b[col_name]
                aval = aval.lower() if hasattr(aval, "lower") else aval
                bval = bval.lower() if hasattr(bval, "lower") else bval
                return cmp(aval, bval)
        self.rows_current.sort(cmp=compare, reverse=not self.sort_ascending)
        if self.View:
            self.View.ForceRefresh()


    def SaveChanges(self):
        """
        Saves the rows that have been changed in this table. Drops undo-cache.
        """
        try:
            for idx in self.idx_changed.copy():
                row = self.rows_all[idx]
                self.db.update_row(self.table, row, self.rows_backup[idx],
                                   self.rowids.get(idx))
                row["__changed__"] = False
                self.idx_changed.remove(idx)
                del self.rows_backup[idx]
            # Save all newly inserted rows
            pks = [c["name"] for c in self.columns if c["pk"]]
            col_map = dict((c["name"], c) for c in self.columns)
            for idx in self.idx_new[:]:
                row = self.rows_all[idx]
                insert_id = self.db.insert_row(self.table, row)
                if len(pks) == 1 and row[pks[0]] in (None, ""):
                    if "INTEGER" == col_map[pks[0]]["type"]:
                        # Autoincremented row: update with new value
                        row[pks[0]] = insert_id
                    elif insert_id: # For non-integers, insert returns ROWID
                        self.rowids[idx] = insert_id
                row["__new__"] = False
                self.idx_new.remove(idx)
            # Delete all newly deleted rows
            for idx, row in self.rows_deleted.copy().items():
                self.db.delete_row(self.table, row, self.rowids.get(idx))
                del self.rows_deleted[idx]
                del self.rows_all[idx]
                self.idx_all.remove(idx)
        except Exception as e:
            guibase.logstatus("Error saving changes in %s.\n\n%s",
                              self.db.quote(self.table), traceback.format_exc())
            wx.MessageBox(util.format_exc(e), conf.Title,
                          wx.OK | wx.ICON_WARNING)
        if self.View: self.View.Refresh()


    def UndoChanges(self):
        """Undoes the changes made to the rows in this table."""
        rows_before = len(self.rows_current)
        # Restore all changed row data from backup
        for idx in self.idx_changed.copy():
            row = self.rows_backup[idx]
            row["__changed__"] = False
            self.rows_all[idx].update(row)
            self.idx_changed.remove(idx)
            del self.rows_backup[idx]
        # Discard all newly inserted rows
        for idx in self.idx_new[:]:
            row = self.rows_all[idx]
            del self.rows_all[idx]
            if row in self.rows_current: self.rows_current.remove(row)
            self.idx_new.remove(idx)
            self.idx_all.remove(idx)
        # Undelete all newly deleted items
        for idx, row in self.rows_deleted.items():
            row["__deleted__"] = False
            del self.rows_deleted[idx]
            if not self._is_row_filtered(row):
                self.rows_current.append(row)
            self.row_count += 1
        self.NotifyViewChange(rows_before)
        if self.View: self.View.Refresh()


    def _is_row_filtered(self, rowdata):
        """
        Returns whether the row is filtered out by the current filtering
        criteria, if any.
        """
        is_unfiltered = True
        for col, filter_value in self.filters.items():
            column_data = self.columns[col]
            if "INTEGER" == column_data["type"]:
                is_unfiltered &= (filter_value == rowdata[column_data["name"]])
            elif "TEXT" == column_data["type"]:
                str_value = (rowdata[column_data["name"]] or "").lower()
                is_unfiltered &= str_value.find(filter_value.lower()) >= 0
        return not is_unfiltered



class AboutDialog(wx.Dialog):

    def __init__(self, parent, title, content):
        wx.Dialog.__init__(self, parent, title=title,
                           style=wx.CAPTION | wx.CLOSE_BOX)
        html = self.html = wx.html.HtmlWindow(self)
        self.content = content
        button_update = wx.Button(self, label="Check for &updates")

        html.SetPage(content() if callable(content) else content)
        html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                  lambda e: webbrowser.open(e.GetLinkInfo().Href))
        button_update.Bind(wx.EVT_BUTTON, parent.on_check_update)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(html, proportion=1, flag=wx.GROW)
        sizer_buttons = self.CreateButtonSizer(wx.OK)
        sizer_buttons.Insert(0, button_update, border=50, flag=wx.RIGHT)
        self.Sizer.Add(sizer_buttons, border=8, flag=wx.ALIGN_CENTER | wx.ALL)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)

        self.Layout()
        self.Size = (self.Size[0], html.VirtualSize[1] + 60)
        self.CenterOnParent()


    def OnSysColourChange(self, event):
        """Handler for system colour change, refreshes content."""
        event.Skip()
        def dorefresh():
            self.html.SetPage(self.content() if callable(self.content) else self.content)
            self.html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)
            self.html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
        wx.CallAfter(dorefresh) # Postpone to allow conf to update
