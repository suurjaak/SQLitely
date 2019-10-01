# -*- coding: utf-8 -*-
"""
SQLitely UI application main window class and project-specific UI classes.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    01.10.2019
------------------------------------------------------------------------------
"""
import ast
import base64
from collections import defaultdict, Counter, OrderedDict
import copy
import datetime
import functools
import hashlib
import inspect
import logging
import os
import re
import shutil
import sys
import tempfile
import textwrap
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
from . lib import wx_accel
from . lib.vendor import step

from . import conf
from . import database
from . import export
from . import grammar
from . import guibase
from . import images
from . import support
from . import templates
from . import workers

logger = logging.getLogger(__name__)


"""Custom application events for worker results."""
SearchEvent,       EVT_SEARCH        = wx.lib.newevent.NewEvent()
DetectionEvent,    EVT_DETECTION     = wx.lib.newevent.NewEvent()
AddFolderEvent,    EVT_ADD_FOLDER    = wx.lib.newevent.NewEvent()
OpenDatabaseEvent, EVT_OPEN_DATABASE = wx.lib.newevent.NewCommandEvent()


class MainWindow(guibase.TemplateFrameMixIn, wx.Frame):
    """Program main window."""

    TRAY_ICON = (images.Icon16x16_32bit if "linux2" != sys.platform
                 else images.Icon24x24_32bit)

    def __init__(self):
        wx.Frame.__init__(self, parent=None, title=conf.Title, size=conf.WindowSize)
        guibase.TemplateFrameMixIn.__init__(self)

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
        self.db_datas = {}  # added DBs {filename: {name, size, last_modified,
                            #            tables, title, error},}
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
            agwStyle=wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
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

        # Memory file system for showing images in wx.HtmlWindow
        self.memoryfs = {"files": {}, "handler": wx.MemoryFSHandler()}
        wx.FileSystem_AddHandler(self.memoryfs["handler"])
        self.load_fs_images()

        self.worker_detection = \
            workers.DetectDatabaseThread(self.on_detect_databases_callback)
        self.worker_folder = \
            workers.ImportFolderThread(self.on_add_from_folder_callback)
        self.Bind(EVT_DETECTION, self.on_detect_databases_result)
        self.Bind(EVT_ADD_FOLDER, self.on_add_from_folder_result)
        self.Bind(EVT_OPEN_DATABASE, self.on_open_database_event)
        self.Bind(EVT_DATABASE_PAGE, self.on_database_page_event)

        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)
        self.Bind(wx.EVT_CLOSE, self.on_exit)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOVE, self.on_move)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_page)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                      self.on_close_page)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_DROPPED,
                      self.on_dragdrop_page)


        # Register Ctrl-F4 close and Ctrl-1..9 tab handlers
        def on_close_hotkey(event):
            notebook and notebook.DeletePage(notebook.GetSelection())
        def on_tab_hotkey(number, event):
            if notebook and notebook.GetSelection() != number \
            and number < notebook.GetPageCount():
                notebook.SetSelection(number)
                self.on_change_page(None)

        id_close = wx.NewId()
        accelerators = [(wx.ACCEL_CTRL, k, id_close) for k in [wx.WXK_F4]]
        for i in range(9):
            id_tab = wx.NewId()
            accelerators += [(wx.ACCEL_CTRL, ord(str(i + 1)), id_tab)]
            notebook.Bind(wx.EVT_MENU, functools.partial(on_tab_hotkey, i), id=id_tab)

        notebook.Bind(wx.EVT_MENU, on_close_hotkey, id=id_close)
        notebook.SetAcceleratorTable(wx.AcceleratorTable(accelerators))


        class FileDrop(wx.FileDropTarget):
            """A simple file drag-and-drop handler for application window."""
            def __init__(self, window):
                super(self.__class__, self).__init__()
                self.window = window

            def OnDropFiles(self, x, y, filenames):
                # CallAfter to allow UI to clear up the dragged icons
                wx.CallAfter(self.ProcessFiles, filenames)

            def ProcessFiles(self, filenames):
                self.window.update_database_list(filenames)
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
        self.trayicon.Bind(wx.EVT_TASKBAR_RIGHT_DOWN, self.on_open_tray_menu)

        if conf.WindowIconized:
            conf.WindowIconized = False
            wx.CallAfter(self.on_toggle_iconize)
        else:
            self.Show(True)
        wx.CallLater(20000, self.update_check)
        wx.CallLater(0, self.populate_database_list)
        logger.info("Started application.")


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
        topdata = defaultdict(lambda: None, name="Home")
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
            ("folder", "&Import from folder", images.ButtonFolder,
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
            valtext = wx.TextCtrl(parent=panel_detail, value="", size=(300, 35),
                style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH | wx.TE_NO_VSCROLL)
            ColourManager.Manage(valtext, "BackgroundColour", "WidgetColour")
            ColourManager.Manage(valtext, "ForegroundColour", wx.SYS_COLOUR_WINDOWTEXT)
            valtext.SetEditable(False)
            ColourManager.Manage(lbltext, "ForegroundColour", "DisabledColour")
            sizer_labels.Add(lbltext, border=5, flag=wx.LEFT)
            sizer_labels.Add(valtext, proportion=1, flag=wx.GROW)
            setattr(self, "label_" + field, valtext)
        sizer_labels.AddGrowableCol(1, proportion=1)
        sizer_labels.AddGrowableRow(0, proportion=1)
        sizer_labels.AddGrowableRow(3, proportion=1)

        BUTTONS_DETAIL = [
            ("open", "&Open", images.ButtonOpen,
             "Open the database."),
            ("saveas", "Save &as..", images.ButtonSaveAs,
             "Save a copy under another name."),
            ("remove", "Remove", images.ButtonRemove,
             "Remove from list."), ]
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
            help="Create a new SQLite database"
        )
        menu_open_database = self.menu_open_database = menu_file.Append(
            id=wx.ID_ANY, text="&Open database...\tCtrl-O",
            help="Choose a database file to open"
        )
        menu_save_database = self.menu_save_database = menu_file.Append(
            id=wx.ID_ANY, text="&Save",
            help="Save changes to the active database"
        )
        menu_save_database_as = self.menu_save_database_as = menu_file.Append(
            id=wx.ID_ANY, text="Save &as...",
            help="Save the active database under a new name"
        )
        menu_save_database.Enable(False)
        menu_save_database_as.Enable(False)
        menu_recent = self.menu_recent = wx.Menu()
        menu_file.AppendMenu(id=wx.ID_ANY, text="&Recent files",
            submenu=menu_recent, help="Recently opened databases")
        menu_file.AppendSeparator()
        menu_options = self.menu_options = \
            menu_file.Append(id=wx.ID_ANY, text="Advanced opt&ions",
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
        self.Bind(wx.EVT_MENU, self.on_save_active_database, menu_save_database)
        self.Bind(wx.EVT_MENU, self.on_save_active_database_as, menu_save_database_as)
        self.Bind(wx.EVT_MENU, self.on_open_options, menu_options)
        self.Bind(wx.EVT_MENU, self.on_exit, menu_exit)
        self.Bind(wx.EVT_MENU, self.on_toggle_iconize, menu_iconize)
        self.Bind(wx.EVT_MENU, self.on_check_update, menu_update)
        self.Bind(wx.EVT_MENU, self.on_menu_homepage, menu_homepage)
        self.Bind(wx.EVT_MENU, self.on_showhide_log, menu_log)
        self.Bind(wx.EVT_MENU, self.on_toggle_console, menu_console)
        self.Bind(wx.EVT_MENU, self.on_toggle_trayicon, menu_tray)
        self.Bind(wx.EVT_MENU, self.on_toggle_autoupdate_check,
                  menu_autoupdate_check)
        self.Bind(wx.EVT_MENU, self.on_about, menu_about)


    def update_check(self):
        """
        Checks for an updated program version if sufficient time
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


    def on_toggle_iconize(self, event=None):
        """Handler for toggling main window to tray and back."""
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


    def on_open_tray_menu(self, event):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()
        menu_recent = wx.Menu()
        menu_all = wx.Menu()

        def on_recent_file(event):
            if conf.WindowIconized: self.on_toggle_iconize()
            filename = history_file.GetHistoryFile(event.Id - wx.ID_FILE1)
            self.load_database_page(filename)
        def open_item(filename, *_, **__):
            if conf.WindowIconized: self.on_toggle_iconize()
            self.load_database_page(filename)

        history_file = wx.FileHistory(conf.MaxRecentFiles)
        history_file.UseMenu(menu_recent)
        # Reverse list, as FileHistory works like a stack
        [history_file.AddFileToHistory(f) for f in conf.RecentFiles[::-1]]
        history_file.UseMenu(menu_recent)

        label = ["Minimize to", "Restore from"][conf.WindowIconized] + " &tray"
        item_toggle = wx.MenuItem(menu, -1, label)
        item_icon = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                text="Show &icon in notification area")
        item_console = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                   text="Show Python &console")
        item_exit = wx.MenuItem(menu, -1, "E&xit %s" % conf.Title)

        boldfont = item_toggle.Font
        boldfont.SetWeight(wx.FONTWEIGHT_BOLD)
        boldfont.SetFaceName(self.Font.FaceName)
        boldfont.SetPointSize(self.Font.PointSize)

        curpage = self.notebook.GetCurrentPage()
        curfile = curpage.db.name if isinstance(curpage, DatabasePage) else None

        openfiles = [(os.path.split(db.name)[-1], p)
                     for p, db in self.db_pages.items()]
        for filename, page in sorted(openfiles):
            item = wx.MenuItem(menu, -1, filename)
            if page.db.name == curfile or len(openfiles) < 2:
                item.Font = boldfont
            menu.AppendItem(item)
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, page.db.name),
                      id=item.GetId())
        if openfiles: menu.AppendSeparator()

        allfiles = [(os.path.split(k)[-1], k) for k, v in self.db_datas.items()
                    if "name" in v]
        for i, (filename, path) in enumerate(sorted(allfiles)):
            label = "&%s %s" % ((i + 1), filename)
            item = wx.MenuItem(menu, -1, label)
            if len(allfiles) > 1 and (path == curfile if curfile
            else len(openfiles) == 1 and path in self.dbs):
                item.Font = boldfont
            menu_all.AppendItem(item)
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, path),
                      id=item.GetId())
        if allfiles:
            menu.AppendMenu(-1, "All &files", submenu=menu_all)

        item_recent = menu.AppendMenu(-1, "&Recent files", submenu=menu_recent)
        menu.Enable(item_recent.Id, bool(conf.RecentFiles))
        menu.AppendSeparator()
        menu.AppendItem(item_toggle)
        menu.AppendItem(item_icon)
        menu.AppendItem(item_console)
        menu.AppendSeparator()
        menu.AppendItem(item_exit)
        item_icon.Check(True)
        item_console.Check(self.frame_console.Shown)

        wx.EVT_MENU_RANGE(menu, wx.ID_FILE1, wx.ID_FILE1 + conf.MaxRecentFiles,
                          on_recent_file)
        menu.Bind(wx.EVT_MENU, self.on_toggle_iconize, id=item_toggle.GetId())
        menu.Bind(wx.EVT_MENU, self.on_toggle_trayicon, id=item_icon.GetId())
        menu.Bind(wx.EVT_MENU, self.on_toggle_console, id=item_console.GetId())
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item_exit.GetId())
        self.trayicon.PopupMenu(menu)


    def on_change_page(self, event):
        """
        Handler for changing a page in the main Notebook, remembers the visit.
        """
        if getattr(self, "_ignore_paging", False): return
        if event: event.Skip() # Pass event along to next handler
        p = self.notebook.GetCurrentPage()
        if not self.pages_visited or self.pages_visited[-1] != p:
            self.pages_visited.append(p)
        self.Title = conf.Title
        if hasattr(p, "title"):
            subtitle = p.title
            if isinstance(p, DatabasePage): # Use parent/file.db or C:/file.db
                path, file = os.path.split(p.db.name)
                subtitle = os.path.join(os.path.split(path)[-1] or path, file)
            self.Title += " - " + subtitle
        self.menu_save_database.Enable(isinstance(p, DatabasePage) and
                                       (p.db.temporary or bool(p.get_unsaved())))
        self.menu_save_database_as.Enable(isinstance(p, DatabasePage))
        self.update_notebook_header()


    def on_dragdrop_page(self, event):
        """
        Handler for dragging notebook tabs, keeps main-tab first and log-tab last.
        """
        self.notebook.Freeze()
        self._ignore_paging = True
        cur_page = self.notebook.GetCurrentPage()
        idx_main = self.notebook.GetPageIndex(self.page_main)
        if idx_main > 0:
            text = self.notebook.GetPageText(idx_main)
            self.notebook.RemovePage(idx_main)
            self.notebook.InsertPage(0, page=self.page_main, text=text)
        idx_log = self.notebook.GetPageIndex(self.page_log)
        if 0 <= idx_log < self.notebook.GetPageCount() - 1:
            text = self.notebook.GetPageText(idx_log)
            self.notebook.RemovePage(idx_log)
            self.notebook.AddPage(page=self.page_log, text=text)
        delattr(self, "_ignore_paging")
        if self.notebook.GetCurrentPage() != cur_page:
            self.notebook.SetSelection(self.notebook.GetPageIndex(cur_page))
        self.notebook.Thaw()


    def on_size(self, event):
        """Handler for window size event, tweaks controls and saves size."""
        event.Skip()
        conf.WindowSize = [-1, -1] if self.IsMaximized() else self.Size[:]
        conf.save()
        # Right panel scroll
        wx.CallAfter(lambda: self and (self.list_db.RefreshRows(),
                                       self.panel_db_main.Parent.Layout()))


    def on_move(self, event):
        """Handler for window move event, saves position."""
        event.Skip()
        conf.WindowPosition = event.Position[:]
        conf.save()


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
        if not self: return

        p = self.notebook.GetCurrentPage()
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


    def on_database_page_event(self, event):
        """Handler for notification from DatabasePage, updates UI."""
        idx = self.notebook.GetPageIndex(event.source)
        ready, modified = (getattr(event, x, None) for x in ("ready", "modified"))
        rename = getattr(event, "rename", None)

        if rename:
            self.dbs.pop(event.filename1, None)
            self.dbs[event.filename2] = event.source.db

            if event.temporary: self.db_datas.pop(event.filename1, None)
            self.update_database_list(event.filename2)
            for i in range(1, self.list_db.GetItemCount()):
                fn = self.list_db.GetItemText(i)
                if fn in (event.filename1, event.filename2):
                    self.list_db.Select(i, on=(fn == event.filename2))
            if event.filename2 in conf.RecentFiles: # Remove earlier position
                idx = conf.RecentFiles.index(event.filename2)
                try: self.history_file.RemoveFileFromHistory(idx)
                except Exception: pass
            self.history_file.AddFileToHistory(event.filename2)
            util.add_unique(conf.RecentFiles, event.filename2, -1,
                            conf.MaxRecentFiles)
            conf.save()


        if ready or rename: self.update_notebook_header()

        if rename or modified is not None:
            suffix = "*" if modified else ""
            title1 = self.db_datas[event.source.db.filename].get("title") \
                     or self.get_unique_tab_title(event.source.db.name)
            self.db_datas[event.source.db.filename]["title"] = title1
            title2 = title1 + suffix
            if self.notebook.GetPageText(idx) != title2:
                self.notebook.SetPageText(idx, title2)
            if self.notebook.GetCurrentPage() is event.source:
                saveable = event.source.db.temporary or bool(modified)
                self.menu_save_database.Enable(saveable)


    def on_list_db_key(self, event):
        """
        Handler for pressing a key in dblist, loads selected database on Enter,
        removes from list on Delete, refreshes columns on F5,
        focuses filter on Ctrl-F.
        """
        event.Skip()
        if event.KeyCode in [wx.WXK_F5]:
            items, selected_files, selected_home = [], [], False
            selected = self.list_db.GetFirstSelected()
            while selected >= 0:
                if selected:
                    selected_files.append(self.list_db.GetItemText(selected))
                else: selected_home = True
                selected = self.list_db.GetNextSelected(selected)

            for filename in conf.DBFiles:
                data = defaultdict(lambda: None, name=filename)
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
            if event.GetIndex():
                files, selecteds = [event.GetText()], [event.GetIndex()]
        if not files:
            menu = wx.Menu()
            label1 = "Stop &import from folder" if self.worker_folder.is_working() \
                     else "&Import from folder"
            label2 = "Stop detecting databases" if self.worker_detection.is_working() \
                     else "Detect databases"
            item_new     = wx.MenuItem(menu, -1, "&New database")
            item_open    = wx.MenuItem(menu, -1, "&Open a database..")
            item_import  = wx.MenuItem(menu, -1, label1)
            item_detect  = wx.MenuItem(menu, -1, label2)
            item_missing = wx.MenuItem(menu, -1, "Remove missing")
            item_clear   = wx.MenuItem(menu, -1, "C&lear list")

            menu.Bind(wx.EVT_MENU, self.on_new_database,     id=item_new.GetId())
            menu.Bind(wx.EVT_MENU, self.on_open_database,    id=item_open.GetId())
            menu.Bind(wx.EVT_MENU, self.on_add_from_folder,  id=item_import.GetId())
            menu.Bind(wx.EVT_MENU, self.on_detect_databases, id=item_detect.GetId())
            menu.Bind(wx.EVT_MENU, self.on_remove_missing,   id=item_missing.GetId())
            menu.Bind(wx.EVT_MENU, self.on_clear_databases,  id=item_clear.GetId())

            menu.AppendItem(item_new)
            menu.AppendItem(item_open)
            menu.AppendItem(item_import)
            menu.AppendItem(item_detect)
            menu.AppendSeparator()
            menu.AppendItem(item_missing)
            menu.AppendItem(item_clear)

            return wx.CallAfter(self.list_db.PopupMenu, menu)


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

        boldfont = item_name.Font
        boldfont.SetWeight(wx.FONTWEIGHT_BOLD)
        boldfont.SetFaceName(self.Font.FaceName)
        boldfont.SetPointSize(self.Font.PointSize)
        item_name.Font = boldfont

        item_open    = wx.MenuItem(menu, -1, "&Open")
        item_save    = wx.MenuItem(menu, -1, "&Save as")
        item_remove  = wx.MenuItem(menu, -1, "&Remove from list")
        item_missing = wx.MenuItem(menu, -1, "Remove &missing from list")
        item_delete  = wx.MenuItem(menu, -1, "Delete from disk")

        menu.Bind(wx.EVT_MENU, clipboard_copy,                id=item_copy.GetId())
        menu.Bind(wx.EVT_MENU, open_folder,                   id=item_folder.GetId())
        menu.Bind(wx.EVT_MENU, self.on_open_current_database, id=item_open.GetId())
        menu.Bind(wx.EVT_MENU, self.on_save_database_as,      id=item_save.GetId())
        menu.Bind(wx.EVT_MENU, self.on_remove_database,       id=item_remove.GetId())
        menu.Bind(wx.EVT_MENU, self.on_delete_database,       id=item_delete.GetId())
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
        menu.AppendItem(item_delete)

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
        event.Skip()
        self.list_db.SetFilter(event.String.strip())
        self.update_database_count()


    def on_menu_homepage(self, event):
        """Handler for opening program webpage from menu,"""
        webbrowser.open(conf.HomeUrl)


    def on_about(self, event):
        """
        Handler for clicking "About program" menu, opens a small info frame.
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
            guibase.status("New %s version %s available.",
                           conf.Title, version, flash=True)
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


    def populate_database_list(self):
        """
        Inserts all databases into the list, updates UI buttons.
        """
        items, selected_files = [], []
        for filename in conf.DBFiles:
            filename = util.to_unicode(filename)
            data = defaultdict(lambda: None, name=filename)
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
        if selected_files: wx.CallLater(100, self.update_database_detail)


    def update_database_list(self, filenames=()):
        """
        Inserts the database into the list, if not there already, and updates
        UI buttons.

        @param   filename  possibly new filename, if any (single string or list)
        @return            True if was file was new or changed, False otherwise
        """
        result = False
        # Insert into database lists, if not already there
        if isinstance(filenames, basestring): filenames = [filenames]
        for filename in filenames:
            filename = util.to_unicode(filename)
            if filename not in conf.DBFiles:
                conf.DBFiles.append(filename)
                conf.save()
            data = defaultdict(lambda: None, name=filename)
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
            if not data_old or "name" not in data_old \
            or data_old["size"] != data["size"] \
            or data_old["last_modified"] != data["last_modified"]:
                if not data_old or "name" not in data_old:
                    self.list_db.AppendRow(data, [1])
                self.db_datas.setdefault(filename, {}).update(data)
                result = True

        self.button_missing.Show(self.list_db.GetItemCount() > 1)
        self.button_clear.Show(self.list_db.GetItemCount() > 1)
        self.update_database_count()
        return result


    def update_database_count(self):
        """Updates database count label."""
        count = self.list_db.GetItemCount() - 1
        total = len([v for v in self.db_datas.values() if "name" in v])
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

        for name in ["path", "size", "modified", "tables"]:
            getattr(self, "label_%s" % name).MinSize = (-1, -1)
        wx.CallLater(100, self.panel_db_detail.Layout)



    def on_clear_databases(self, event):
        """Handler for clicking to clear the database list."""
        if (self.list_db.GetItemCount() > 1) and wx.OK == wx.MessageBox(
            "Are you sure you want to clear the list of all databases?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ):
            self.list_db.Populate([])
            del conf.DBFiles[:]
            del conf.LastSelectedFiles[:]
            del conf.RecentFiles[:]
            conf.LastSearchResults.clear()
            while self.history_file.Count:
                self.history_file.RemoveFileFromHistory(0)
            del self.dbs_selected[:]
            for v in self.db_datas.values(): v.pop("name", None)
            self.dbs.clear()
            conf.save()
            self.update_database_list()


    def on_save_database_as(self, event=None):
        """Handler for clicking to save a copy of a database in the list."""
        filenames = filter(os.path.exists, self.dbs_selected)
        if not filenames:
            m = "None of the selected files" if len(self.dbs_selected) > 1 \
                else "The file \"%s\" does not" % self.dbs_selected[0]
            return wx.MessageBox("%s exist on this computer." % m, conf.Title,
                                 wx.OK | wx.ICON_INFORMATION)

        dialog = wx.DirDialog(self,
            message="Choose directory where to save databases",
            defaultPath=os.getcwd(),
            style=wx.DD_DIR_MUST_EXIST | wx.RESIZE_BORDER
        ) if len(filenames) > 1 else wx.FileDialog(self,
            message="Save a copy..",
            defaultDir=os.path.split(filenames[0])[0],
            defaultFile=os.path.basename(filenames[0]),
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        path = dialog.GetPath()
        wx.YieldIfNeeded() # Allow dialog to disappear

        new_filenames = []
        for filename in filenames:
            _, basename = os.path.split(filename)
            newpath = os.path.join(path, basename) if len(filenames) > 1 else path
            if filename == newpath:
                logger.error("Attempted to save %s as itself.", filename)
                wx.MessageBox("Cannot overwrite %s with itself." % filename,
                              conf.Title, wx.OK | wx.ICON_ERROR)
                continue # for filename
            try: shutil.copyfile(filename, newpath)
            except Exception as e:
                logger.exception("%r when trying to copy %s to %s.",
                                 e, basename, newpath)
                wx.MessageBox('Failed to copy "%s" to "%s":\n\n%s' %
                              (basename, newpath, util.format_exc(e)),
                              conf.Title, wx.OK | wx.ICON_ERROR)
            else:
                guibase.status("Saved a copy of %s as %s.", filename, newpath,
                               log=True, flash=True)
                self.update_database_list(newpath)
                new_filenames.append(newpath)

        if not new_filenames: return
        for i in range(1, self.list_db.GetItemCount()):
            self.list_db.Select(i, on=self.list_db.GetItemText(i) in new_filenames)


    def on_save_active_database(self, event=None):
        """
        Handler for clicking to save changes to the active database,
        commits unsaved changes.
        """
        page = self.notebook.GetCurrentPage()
        if isinstance(page, DatabasePage): page.save_database()


    def on_save_active_database_as(self, event=None):
        """
        Handler for clicking to save the active database under a new name,
        opens a save as dialog, copies file and commits unsaved changes.
        """
        page = self.notebook.GetCurrentPage()
        if isinstance(page, DatabasePage): page.save_database(rename=True)


    def on_remove_database(self, event):
        """Handler for clicking to remove an item from the database list."""
        if not self.dbs_selected: return

        msg = "%s files" % len(self.dbs_selected)
        if len(self.dbs_selected) == 1: msg = self.dbs_selected[0]
        if wx.OK != wx.MessageBox(
            "Remove %s from database list?" % msg,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        for filename in self.dbs_selected:
            for lst in conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles:
                if filename in lst: lst.remove(filename)
            for dct in conf.LastSearchResults, self.dbs:
                dct.pop(filename, None)
            self.db_datas.get(filename, {}).pop("name", None)
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
            conf.LastSearchResults.pop(filename, None)
            self.db_datas.get(filename, {}).pop("name", None)
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


    def on_delete_database(self, event=None):
        """Handler for clicking to delete a database from disk."""
        if not self.dbs_selected: return

        msg = "%s files" % len(self.dbs_selected)
        if len(self.dbs_selected) == 1: msg = self.dbs_selected[0]
        if wx.OK != wx.MessageBox(
            "Delete %s from disk?" % msg,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        unsaved_pages = {}
        for page, db in self.db_pages.items():
            if db.filename in self.dbs_selected and page and page.get_unsaved():
                unsaved_pages[page] = db.filename
        if unsaved_pages:
            if wx.OK != wx.MessageBox(
                "There are unsaved changes in files\n(%s).\n\n"
                "Are you sure you want to discard them?" %
                "\n".join(textwrap.wrap(", ".join(sorted(unsaved_pages.values())))),
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
            ): return

        errors = []
        for filename in self.dbs_selected[:]:
            try:
                page = next((k for k, v in self.db_pages.items()
                             if v.filename == filename), None)
                if page:
                    page.set_ignore_unsaved()
                    self.notebook.DeletePage(self.notebook.GetPageIndex(page))

                os.unlink(filename)

                for lst in conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles:
                    if filename in lst: lst.remove(filename)
                for dct in conf.LastSearchResults, self.dbs:
                    dct.pop(filename, None)
                self.db_datas.get(filename, {}).pop("name", None)

                for i in range(self.list_db.GetItemCount())[::-1]:
                    if self.list_db.GetItemText(i) == filename:
                        self.list_db.DeleteItem(i)

                # Remove from recent file history
                historyfiles = [(i, self.history_file.GetHistoryFile(i))
                                for i in range(self.history_file.Count)]
                for i in [i for i, f in historyfiles if f == filename][::-1]:
                    self.history_file.RemoveFileFromHistory(i)
                self.dbs_selected.remove(filename)
            except Exception as e:
                logger.exception("Error deleting %s.", filename)
                errors.append("%s: %s" % (filename, util.format_exc(e)))

        self.list_db.Select(0)
        self.update_database_list()
        conf.save()
        if errors:
            wx.MessageBox("Error removing %s:\n\n%s" % (
                          util.plural("file", errors, False),
                          "\n".join(errors)), conf.Title, wx.OK | wx.ICON_ERROR)


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
        Handler for new database menu or button, opens a temporary file database.
        """
        self.load_database_page(None)


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


    def on_detect_databases(self, event):
        """
        Handler for clicking to auto-detect databases, starts the
        detection in a background thread.
        """
        if self.button_detect.FindFocus() == self.button_detect:
            self.list_db.SetFocus()
        if self.worker_detection.is_working():
            self.worker_detection.stop_work()
            self.button_detect.Label = "Detect databases"
        else:
            guibase.status("Searching local computer for databases..", log=True)
            self.button_detect.Label = "Stop detecting databases"
            self.worker_detection.work(True)


    def on_detect_databases_callback(self, result):
        """Callback for DetectDatabaseThread, posts the data to self."""
        if self: # Check if instance is still valid (i.e. not destroyed by wx)
            wx.PostEvent(self, DetectionEvent(result=result))


    def on_detect_databases_result(self, event):
        """
        Handler for getting results from database detection thread, adds the
        results to the database list.
        """
        result = event.result
        if "filenames" in result:
            filenames = [f for f in result["filenames"] if f not in conf.DBFiles]
            if filenames:
                self.update_database_list(filenames)
                for f in filenames: logger.info("Detected database %s.", f)
        if "count" in result:
            name = ("" if result["count"] else "additional ") + "database"
            guibase.status("Detected %s.", util.plural(name, result["count"]),
                           log=True, flash=True)
        if result.get("done", False):
            self.button_detect.Label = "Detect databases"
            wx.Bell()


    def on_add_from_folder(self, event):
        """
        Handler for clicking to select folder where to search for databases,
        updates database list.
        """
        if self.button_folder.FindFocus() == self.button_folder:
            self.list_db.SetFocus()
        if self.worker_folder.is_working():
            self.worker_folder.stop_work()
            self.button_folder.Label = "&Import from folder"
        else:
            if wx.ID_OK != self.dialog_selectfolder.ShowModal(): return
            folder = self.dialog_selectfolder.GetPath()
            guibase.status("Detecting databases under %s.", folder, log=True)
            self.button_folder.Label = "Stop &import from folder"
            self.worker_folder.work(folder)


    def on_add_from_folder_callback(self, result):
        """Callback for ImportFolderThread, posts the data to self."""
        if self: # Check if instance is still valid (i.e. not destroyed by wx)
            wx.PostEvent(self, AddFolderEvent(result=result))


    def on_add_from_folder_result(self, event):
        """
        Handler for getting results from import folder thread, adds the
        results to the database list.
        """
        result = event.result
        if "filenames" in result:
            filenames = [f for f in result["filenames"] if f not in conf.DBFiles]
            if filenames:
                self.update_database_list(filenames)
                for f in filenames: logger.info("Detected database %s.", f)
        if "count" in result:
            guibase.status("Detected %s under %s.",
                           util.plural("database", result["count"]),
                           result["folder"], log=True, flash=True)
        if result.get("done"):
            self.button_folder.Label = "&Import from folder"
            wx.Bell()


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
            logger.exception("Error opening %s.", filename)
            return
        try:
            tables = db.get_category("table").values()
            self.label_tables.Value = str(len(tables))
            if tables:
                s = ""
                for t in tables:
                    s += (", " if s else "") + grammar.quote(t["name"])
                    if len(s) > 400:
                        s += ", .."
                        break # for t
                self.label_tables.Value += " (%s)" % s

            data = self.db_datas.get(filename, {})
            data["tables"] = self.label_tables.Value
        except Exception as e:
            self.label_tables.Value = util.format_exc(e)
            self.label_tables.ForegroundColour = conf.LabelErrorColour
            logger.exception("Error loading data from %s.", filename)
        if db and not db.has_consumers():
            db.close()
            self.dbs.pop(filename, None)


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
        unsaved_pages = {} # {DatabasePage: filename, }
        for page, db in self.db_pages.items():
            if page and page.get_unsaved():
                unsaved_pages[page] = db.name
        if unsaved_pages:
            resp = wx.MessageBox(
                "There are unsaved changes in files\n(%s).\n\n"
                "Do you want to save the changes?" %
                "\n".join(textwrap.wrap(", ".join(sorted(unsaved_pages.values())))),
                conf.Title, wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION
            )
            if wx.CANCEL == resp: return
            for page in unsaved_pages if wx.YES == resp else ():
                if not page.save_database(): return

        for page, db in self.db_pages.items():
            if not page: continue # continue for page, if dead object
            active_idx = page.notebook.Selection
            if active_idx and not db.temporary:
                conf.LastActivePage[db.filename] = active_idx
            elif page.db.filename in conf.LastActivePage:
                del conf.LastActivePage[page.db.filename]
            page.save_page_conf()
            for worker in page.workers_search.values(): worker.stop()
            page.worker_analyzer.stop()
            db.close()
        self.worker_detection.stop()
        self.worker_folder.stop()

        # Save last selected files in db lists, to reselect them on rerun
        conf.LastSelectedFiles[:] = self.dbs_selected[:]
        if not conf.WindowIconized: conf.WindowPosition = self.Position[:]
        conf.WindowSize = [-1, -1] if self.IsMaximized() else self.Size[:]
        conf.save()
        self.trayicon.Destroy()
        wx.CallAfter(sys.exit) # Immediate exit fails if exiting from tray


    def on_close_page(self, event):
        """
        Handler for closing a page, asks the user about saving unsaved data,
        if any, removes page from main notebook and updates accelerators.
        """
        if getattr(self, "_ignore_paging", False): return
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
        unsaved = page.get_unsaved()
        if unsaved:
            if unsaved.pop("temporary", None) and not unsaved:
                msg = "%s has modifications.\n\n" % page.db
            else:
                info = ""
                if unsaved.get("pragma"): info = "PRAGMA settings"
                if unsaved.get("table"):
                    info += (", and " if info else "")
                    info += util.plural("table", unsaved["table"], with_items=False)
                    info += " " + ", ".join(map(grammar.quote, sorted(unsaved["table"])))
                if unsaved.get("schema"):
                    info += (", and " if info else "") + "schema changes"
                if unsaved.get("temporary"):
                    info += (", and " if info else "") + "temporary file"
                msg = "There are unsaved changes in %s:\n%s.\n\n" % (page.db, info)

            resp = wx.MessageBox(msg + "Do you want to save the changes?", conf.Title,
                                 wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION)
            if wx.CANCEL == resp: return event.Veto()
            if wx.YES == resp:
                if not page.save_database(): return event.Veto()

        if page.notebook.Selection and not page.db.temporary:
            conf.LastActivePage[page.db.filename] = page.notebook.Selection
        elif page.db.filename in conf.LastActivePage:
            del conf.LastActivePage[page.db.filename]

        for worker in page.workers_search.values(): worker.stop()
        page.worker_analyzer.stop()
        page.save_page_conf()

        if page in self.db_pages:
            del self.db_pages[page]
        logger.info("Closed database tab for %s.", page.db)
        conf.save()

        # Close databases, if not used in any other page
        page.db.unregister_consumer(page)
        if not page.db.has_consumers():
            if page.db.name in self.dbs:
                del self.dbs[page.db.name]
            page.db.close()
            conf.DBsOpen.pop(page.db.filename, None)
            self.db_datas.get(page.db.filename, {}).pop("title", None)
            logger.info("Closed database %s.", page.db)
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
        if wx.OK != wx.MessageBox("Clear search history?", conf.Title,
                                  wx.OK | wx.CANCEL | wx.ICON_INFORMATION):
            return
        conf.SearchHistory = []
        for page in self.db_pages:
            page.edit_searchall.SetChoices(conf.SearchHistory)
            page.edit_searchall.ShowDropDown(False)
            page.edit_searchall.Value = ""
        conf.save()


    def load_database(self, filename):
        """
        Tries to load the specified database, if not already open, and returns
        it. If filename is None, creates a temporary file database.
        """
        db = self.dbs.get(filename)
        if not db:
            if not filename or os.path.exists(filename):
                try:
                    db = database.Database(filename)
                except Exception:
                    logger.exception("some error")
                    is_accessible = False
                    if filename:
                        try:
                            with open(filename, "rb"):
                                is_accessible = True
                        except Exception: pass
                    if filename and not is_accessible:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Some other process may be using the file."
                            % filename, conf.Title, wx.OK | wx.ICON_ERROR)
                    elif filename:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Not a valid SQLITE database?" % filename,
                            conf.Title, wx.OK | wx.ICON_ERROR)
                if db:
                    logger.info("Opened %s (%s).", db, util.format_bytes(db.filesize))
                    guibase.status("Reading database %s.", db, flash=True)
                    self.dbs[db.name] = db
                    # Add filename to Recent Files menu and conf, if needed
                    if filename:
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
                              conf.Title, wx.OK | wx.ICON_ERROR)
        return db


    def load_database_page(self, filename):
        """
        Tries to load the specified database, if not already open, create a
        subpage for it, if not already created, and focuses the subpage.
        If filename is None, creates a temporary file database.

        @return  database page instance
        """
        page, db = None, self.dbs.get(filename)
        if db: page = next((x for x in self.db_pages if x and x.db == db), None)
        if not page:
            if not db: db = self.load_database(filename)
            if db:
                guibase.status("Opening database %s." % db, flash=True)
                tab_title = self.get_unique_tab_title(db.name)
                self.db_datas.setdefault(db.filename, {})["title"] = tab_title
                page = DatabasePage(self.notebook, tab_title, db, self.memoryfs)
                conf.DBsOpen[db.filename] = db
                self.db_pages[page] = db
                self.UpdateAccelerators()
                conf.save()
                self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS,
                          self.on_clear_searchall, page.edit_searchall)
        if page:
            if filename:
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


    def get_unique_tab_title(self, title):
        """
        Returns a title that is unique for the current notebook - if the
        specified title already exists, appends a counter to the end,
        e.g. "..longpath\myname.db (2)". Title is shortened from the left
        if longer than allowed.
        """
        if len(title) > conf.MaxTabTitleLength:
            title = "..%s" % title[-conf.MaxTabTitleLength:]
        unique = title_base = title
        all_titles = [self.notebook.GetPageText(i)
                      for i in range(self.notebook.GetPageCount())]
        i = 2 # Start counter from 1
        while unique in all_titles:
            unique = "%s (%d)" % (title_base, i)
            i += 1
        return unique



DatabasePageEvent, EVT_DATABASE_PAGE = wx.lib.newevent.NewCommandEvent()

class DatabasePage(wx.Panel):
    """
    A wx.Notebook page for managing a single database file, has its own
    Notebook with a number of pages for searching, browsing, SQL, information.
    """

    def __init__(self, parent_notebook, title, db, memoryfs):
        wx.Panel.__init__(self, parent=parent_notebook)
        self.parent_notebook = parent_notebook

        self.pageorder = {} # {page: notebook index, }
        self.ready_to_close = False
        self.db = db
        self.db.register_consumer(self)
        self.ignore_unsaved = False
        self.save_underway  = False
        self.statistics = {} # {?error: message, ?data: {..}}
        self.pragma         = db.get_pragma_values() # {pragma_name: value}
        self.pragma_changes = {}    # {pragma_name: value}
        self.pragma_ctrls   = {}    # {pragma_name: wx control}
        self.pragma_items   = {}    # {pragma_name: [all wx components for directive]}
        self.pragma_edit = False    # Whether in PRAGMA edit mode
        self.pragma_fullsql = False # Whether show SQL for all PRAGMAs, changed or not
        self.pragma_filter = ""     # Current PRAGMA filter
        self.last_sql = ""          # Last executed SQL
        self.memoryfs = memoryfs
        parent_notebook.InsertPage(1, self, title)
        busy = controls.BusyPanel(self, 'Loading "%s".' % db.name)
        self.counter = lambda x={"c": 0}: x.update(c=1+x["c"]) or x["c"]
        ColourManager.Manage(self, "BackgroundColour", "WidgetColour")
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)

        # Create search structures and threads
        self.Bind(EVT_SEARCH, self.on_searchall_result)
        self.workers_search = {} # {search ID: workers.SearchThread, }
        self.search_data_contact = {"id": None} # Current contacts search data

        self.worker_analyzer = workers.AnalyzerThread(self.on_analyzer_result)

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        label_title = self.label_title = wx.StaticText(parent=self, label="Database")
        edit_title = self.edit_title = wx.TextCtrl(parent=self,
            style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH | wx.TE_NO_VSCROLL)
        edit_title.SetEditable(False)
        ColourManager.Manage(edit_title, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(edit_title, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
        sizer_header.Add(label_title, border=5, flag=wx.RIGHT | wx.TOP)
        sizer_header.Add(edit_title, proportion=1, border=5, flag=wx.TOP | wx.GROW)


        self.label_search = wx.StaticText(self, -1, "&Search in messages:")
        sizer_header.Add(self.label_search, border=5,
                         flag=wx.RIGHT | wx.TOP | wx.ALIGN_RIGHT)
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
                     flag=wx.RIGHT | wx.ALIGN_RIGHT)
        sizer_header.Add(tb, border=5, flag=wx.ALIGN_RIGHT | wx.GROW)
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

        self.create_page_search(notebook)
        self.create_page_data(notebook)
        self.create_page_schema(notebook)
        self.create_page_sql(notebook)
        self.create_page_pragma(notebook)
        self.create_page_info(notebook)

        IMAGES = [images.PageSearch, images.PageTables, images.PageSchema,
                  images.PageSQL, images.PagePragma, images.PageInfo]
        il = wx.ImageList(32, 32)
        idxs = [il.Add(x.Bitmap) for x in IMAGES]
        notebook.AssignImageList(il)
        for i, idx in enumerate(idxs): notebook.SetPageImage(i, idx)

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
            guibase.status("Opened database %s." % db, flash=True)
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
        label_html.SetPage(step.Template(templates.SEARCH_HELP_SHORT_HTML).expand())
        label_html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNFACE)
        label_html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)

        tb = self.tb_search_settings = \
            wx.ToolBar(parent=page, style=wx.TB_FLAT | wx.TB_NODIVIDER | wx.TB_HORZ_TEXT)
        tb.SetToolBitmapSize((24, 24))
        tb.AddRadioLabelTool(wx.ID_STATIC, "Data", bitmap=images.ToolbarTables.Bitmap,
            shortHelp="Search in all columns of all database tables")
        tb.AddRadioLabelTool(wx.ID_INDEX, "Meta", bitmap=images.ToolbarTitle.Bitmap,
            shortHelp="Search in database CREATE SQL")
        tb.AddSeparator()
        tb.AddCheckLabelTool(wx.ID_NEW, "Tabs", bitmap=images.ToolbarTabs.Bitmap,
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

        self.label_search.Label = "&Search in table data:"
        if conf.SearchInNames:
            self.label_search.Label = "&Search in database CREATE SQL:"

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
        self.register_notebook_hotkeys(html)
        ColourManager.Manage(html, "TabAreaColour", "WidgetColour")
        html.Font.PixelSize = (0, 8)

        sizer_top.Add(label_html, proportion=1, flag=wx.GROW)
        sizer_top.Add(tb, border=5, flag=wx.TOP | 
                      wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        sizer.Add(sizer_top, border=5, flag=wx.TOP | wx.RIGHT | wx.GROW)
        sizer.Add(html, border=5, proportion=1,
                  flag=wx.GROW | wx.LEFT | wx.RIGHT | wx.BOTTOM)
        wx.CallAfter(label_html.Show)


    def create_page_data(self, notebook):
        """Creates a page for listing and browsing tables and views."""
        page = self.page_data = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Data")

        self.data_pages = defaultdict(dict) # {category: {name: DataObjectPage}}

        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = self.splitter_data = wx.SplitterWindow(
            parent=page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(100)

        panel1 = wx.Panel(parent=splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_topleft = wx.BoxSizer(wx.HORIZONTAL)
        sizer_topleft.Add(wx.StaticText(parent=panel1, label="Data:"),
                          flag=wx.ALIGN_CENTER_VERTICAL)
        button_refresh = self.button_refresh_data = \
            wx.Button(panel1, label="Refresh")
        sizer_topleft.AddStretchSpacer()
        sizer_topleft.Add(button_refresh)
        tree = self.tree_data = wx.gizmos.TreeListCtrl(
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
        self.Bind(wx.EVT_BUTTON, self.on_refresh_data, button_refresh)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_change_tree_data, tree)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_rclick_tree_data, tree)

        sizer1.Add(sizer_topleft, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer1.Add(tree, proportion=1,
                   border=5, flag=wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM)

        panel2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_data = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=panel2, size=(-1, 27),
            agwStyle=wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_X_ON_TAB |
                     wx.lib.agw.flatnotebook.FNB_VC8)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        sizer2.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 400)

        self.Bind(EVT_DATA_PAGE, self.on_data_page_event)
        nb.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                self.on_close_data_page)
        self.register_notebook_hotkeys(nb)


    def create_page_schema(self, notebook):
        """Creates a page for browsing and modifying schema."""
        page = self.page_schema = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Schema")

        self.schema_pages = defaultdict(dict) # {category: {name: SchemaObjectPage}}

        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = self.splitter_schema = wx.SplitterWindow(
            parent=page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(100)

        panel1 = wx.Panel(parent=splitter)
        button_refresh = wx.Button(panel1, label="Refresh")
        button_new = wx.Button(panel1, label="Create ne&w ..")
        tree = self.tree_schema = wx.gizmos.TreeListCtrl(
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

        isz = (16,16)
        il = wx.ImageList(16, 16)
        self.tree_schema_images = {
            "table":    il.Add(wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW,     wx.ART_TOOLBAR, il.GetSize(0))),
            "index":    il.Add(wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE,     wx.ART_TOOLBAR, il.GetSize(0))),
            "trigger":  il.Add(wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE, wx.ART_TOOLBAR, il.GetSize(0))),
            "view":     il.Add(wx.ArtProvider.GetBitmap(wx.ART_HELP_PAGE,       wx.ART_TOOLBAR, il.GetSize(0))),
            "columns":  il.Add(wx.ArtProvider.GetBitmap(wx.ART_FOLDER,          wx.ART_TOOLBAR, il.GetSize(0))),
        }
        tree.AssignImageList(il)

        tree.AddColumn("Object")
        tree.AddColumn("Info")
        tree.AddRoot("Loading schema..")
        tree.SetMainColumn(0)
        tree.SetColumnAlignment(1, wx.ALIGN_RIGHT)

        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_topleft = wx.BoxSizer(wx.HORIZONTAL)
        sizer_topleft.Add(wx.StaticText(parent=panel1, label="Schema:"),
                          flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_topleft.AddStretchSpacer()
        sizer_topleft.Add(button_refresh)
        sizer_topleft.Add(button_new, border=5, flag=wx.LEFT)

        sizer1.Add(sizer_topleft, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer1.Add(tree, proportion=1,
                   border=5, flag=wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM)

        panel2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_schema = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=panel2, size=(-1, 27),
            agwStyle=wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_X_ON_TAB |
                     wx.lib.agw.flatnotebook.FNB_VC8)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        sizer2.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 400)

        self.Bind(wx.EVT_BUTTON, self.on_refresh_schema, button_refresh)
        self.Bind(wx.EVT_BUTTON, self.on_schema_create, button_new)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_change_tree_schema, tree)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_rclick_tree_schema, tree)
        self.Bind(EVT_SCHEMA_PAGE, self.on_schema_page_event)
        nb.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                self.on_close_schema_page)
        self.register_notebook_hotkeys(nb)


    def create_page_sql(self, notebook):
        """Creates a page for executing arbitrary SQL."""
        page = self.page_sql = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "SQL")

        self.sql_pages = defaultdict(dict) # {name: SQLPage}
        self.sql_page_counter = 0

        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_sql = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=page, size=(-1, 27),
            agwStyle=wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_X_ON_TAB |
                     wx.lib.agw.flatnotebook.FNB_VC8)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        for x in conf.SQLWindowTexts.get(self.db.filename, []):
            name, text = x.items()[0]
            self.add_sql_page(name, text)
        if self.sql_pages:
            self.sql_page_counter = max(
                int(re.sub(r"[^\d]", "", x) or 0) for x in self.sql_pages
            ) or len(self.sql_pages)
        else: self.add_sql_page()
        nb.AddPage(page=wx.Panel(page), text="+")

        sizer.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        nb.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_sql_page)
        nb.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                self.on_close_sql_page)
        nb.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_DROPPED,
                self.on_dragdrop_sql_page)
        self.register_notebook_hotkeys(nb)


    def create_page_pragma(self, notebook):
        """Creates a page for database PRAGMA settings."""
        page = self.page_pragma = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Pragma")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)

        panel_wrapper = wx.lib.scrolledpanel.ScrolledPanel(page)
        panel_pragma = wx.Panel(panel_wrapper)
        panel_sql = wx.Panel(page)
        sizer_wrapper = panel_wrapper.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_pragma = panel_pragma.Sizer = wx.FlexGridSizer(cols=4, vgap=4, hgap=10)
        sizer_sql = panel_sql.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_sql_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_footer = wx.BoxSizer(wx.HORIZONTAL)

        label_header = wx.StaticText(page, label="Database PRAGMA settings")
        label_header.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                    wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        edit_filter = self.edit_pragma_filter = controls.SearchCtrl(page, "Filter settings")
        edit_filter.SetToolTipString("Filter PRAGMA directive list (Ctrl-F)")

        def on_help(ctrl, text, event):
            """Handler for clicking help bitmap, shows text popup."""
            wx.TipWindow(ctrl, text, maxLength=300)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_QUESTION, wx.ART_TOOLBAR, (16, 16))
        cursor_pointer = wx.StockCursor(wx.CURSOR_HAND)
        lastopts = {}
        for name, opts in sorted(database.Database.PRAGMA.items(),
            key=lambda x: (bool(x[1].get("deprecated")), x[1]["label"])
        ):
            value = self.pragma.get(name)
            description = "%s:\n\n%s%s" % (name,
                "DEPRECATED.\n\n" if opts.get("deprecated") else "", opts["description"]
            )
            if opts.get("read")  is False: description += "\n\nWrite-only."
            if opts.get("write") is False: description += "\n\nRead-only."
                
            ctrl_name, label_name = "pragma_%s" % name, "pragma_%s_label" % name

            label = wx.StaticText(panel_pragma, label=opts["label"], name=label_name)
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
                ctrl = wx.TextCtrl(panel_pragma, name=ctrl_name)
                ctrl.Value = "" if value is None else value
                ctrl.Bind(wx.EVT_TEXT, self.on_pragma_change)
            label_text = wx.StaticText(panel_pragma, label=opts["short"])
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
                for i in range(4): sizer_pragma.AddSpacer(20)
                label_deprecated = self.label_deprecated = wx.StaticText(panel_pragma, label="DEPRECATED:")
                ColourManager.Manage(label_deprecated, "ForegroundColour", "DisabledColour")
                sizer_pragma.Add(label_deprecated, border=10, flag=wx.LEFT)
                for i in range(3): sizer_pragma.AddSpacer(20)

            sizer_pragma.Add(label, border=10, flag=wx.LEFT)
            sizer_pragma.Add(ctrl)
            sizer_pragma.Add(label_text)
            sizer_pragma.Add(help_bmp)
            self.pragma_items[name] = [label, ctrl, label_text, help_bmp]
            lastopts = opts

        # Set uniform width to all columns, avoiding reposition on filter
        widths = {i: 0 for i in range(4)}
        for xx in self.pragma_items.values():
            for i, x in enumerate(xx): widths[i] = max(widths[i], x.Size[0])
        for xx in self.pragma_items.values():
            for i, x in enumerate(xx):
                if not isinstance(x, wx.CheckBox):
                    sizer_pragma.SetItemMinSize(x, (widths[i], -1))
        for i, w in widths.items():
            sizer_pragma.AddSpacer((w, -1))

        check_sql = self.check_pragma_sql = \
            wx.CheckBox(panel_sql, label="See change S&QL")
        check_sql.SetToolTipString("See SQL statements for PRAGMA changes")
        check_sql.Value = True
        check_fullsql = self.check_pragma_fullsql = \
            wx.CheckBox(panel_sql, label="See f&ull SQL")
        check_fullsql.SetToolTipString("See SQL statements for "
                                       "setting all current PRAGMA values")
        check_fullsql.Hide()

        stc = self.stc_pragma = controls.SQLiteTextCtrl(
            panel_sql, style=wx.BORDER_STATIC)
        stc.SetReadOnly(True)
        tb = self.tb_pragma = wx.ToolBar(panel_sql,
                                         style=wx.TB_FLAT | wx.TB_NODIVIDER)
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

        button_edit = self.button_pragma_edit = \
            wx.Button(page, label="Edit")
        button_refresh = self.button_pragma_refresh = \
            wx.Button(page, label="Refresh")
        button_cancel = self.button_pragma_cancel = \
            wx.Button(page, label="Cancel")

        button_edit.SetToolTipString("Change PRAGMA values")
        button_refresh.SetToolTipString("Reload PRAGMA values from database")
        button_cancel.SetToolTipString("Cancel PRAGMA changes")
        button_cancel.Enabled = False

        self.Bind(wx.EVT_BUTTON,     self.on_pragma_edit,    button_edit)
        self.Bind(wx.EVT_BUTTON,     self.on_pragma_refresh, button_refresh)
        self.Bind(wx.EVT_BUTTON,     self.on_pragma_cancel,  button_cancel)
        self.Bind(wx.EVT_CHECKBOX,   self.on_pragma_sql,     check_sql)
        self.Bind(wx.EVT_CHECKBOX,   self.on_pragma_fullsql, check_fullsql)
        page.Bind(wx.EVT_CHAR_HOOK,  self.on_pragma_key)
        edit_filter.Bind(wx.EVT_TEXT_ENTER, self.on_pragma_filter)

        sizer_header.AddSpacer((edit_filter.Size[0], -1))
        sizer_header.AddStretchSpacer()
        sizer_header.Add(label_header)
        sizer_header.AddStretchSpacer()
        sizer_header.Add(edit_filter, border=16, flag=wx.RIGHT)

        sizer_wrapper.Add(panel_pragma, proportion=1, border=20, flag=wx.TOP | wx.GROW)

        sizer_sql_header.Add(check_sql, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_sql_header.AddStretchSpacer()
        sizer_sql_header.Add(check_fullsql, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_sql_header.Add(tb)

        sizer_sql.Add(sizer_sql_header, flag=wx.GROW)
        sizer_sql.Add(stc, proportion=1, flag=wx.GROW)

        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_edit)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_refresh)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(button_cancel)
        sizer_footer.AddStretchSpacer()

        sizer.Add(sizer_header, border=10, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel_wrapper, proportion=1, border=5, flag=wx.LEFT | wx.GROW)
        sizer.Add(panel_sql, border=5, flag=wx.LEFT | wx.TOP | wx.GROW)
        sizer.Add(sizer_footer, border=10, flag=wx.BOTTOM | wx.TOP | wx.GROW)

        panel_sql.Hide()
        ColourManager.Manage(panel_wrapper, "BackgroundColour", "BgColour")
        panel_wrapper.SetupScrolling(scroll_x=False)


    def create_page_info(self, notebook):
        """Creates a page for seeing general database information."""
        page = self.page_info = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Information")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        splitter = self.splitter_info = wx.SplitterWindow(
            page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(300)

        panel1, panel2 = wx.Panel(splitter), wx.Panel(splitter)
        panel1c = wx.Panel(parent=panel1)
        ColourManager.Manage(panel1c, "BackgroundColour", "BgColour")
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_file = panel1c.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_info = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        label_file = wx.StaticText(parent=panel1, label="Database information")
        label_file.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                  wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)

        names = ["edit_info_path", "edit_info_size", "edit_info_created",
                 "edit_info_modified", "edit_info_sha1", "edit_info_md5", ]
        labels = ["Full path", "File size", "Created", "Last modified",
                  "SHA-1 checksum", "MD5 checksum",  ]
        for name, label in zip(names, labels):
            if not name and not label:
                sizer_info.AddSpacer(20), sizer_info.AddSpacer(20)
                continue # for name, label
            labeltext = wx.StaticText(parent=panel1c, label="%s:" % label,
                                      name=name+"_label")
            ColourManager.Manage(labeltext, "ForegroundColour", "DisabledColour")
            valuetext = wx.TextCtrl(parent=panel1c, value="Analyzing..", name=name,
                style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH | wx.TE_NO_VSCROLL)
            valuetext.MinSize = (-1, 35)
            valuetext.SetEditable(False)
            sizer_info.Add(labeltext, border=5, flag=wx.LEFT | wx.TOP)
            sizer_info.Add(valuetext, border=5, flag=wx.TOP | wx.GROW)
            setattr(self, name, valuetext)
        self.edit_info_path.Value = "<temporary file>" if self.db.temporary \
                                    else self.db.filename

        button_fks      = self.button_check_fks       = wx.Button(panel1c, label="Check foreign keys")
        button_check    = self.button_check_integrity = wx.Button(panel1c, label="Check for corruption")
        button_optimize = self.button_optimize        = wx.Button(panel1c, label="Optimize")

        button_vacuum      = self.button_vacuum       = wx.Button(panel1c, label="Vacuum")
        button_open_folder = self.button_open_folder  = wx.Button(panel1c, label="Open directory")
        button_refresh     = self.button_refresh_info = wx.Button(panel1c, label="Refresh")
        button_fks.Enabled = button_check.Enabled = button_optimize.Enabled = False
        button_vacuum.Enabled = button_open_folder.Enabled = button_refresh.Enabled = False
        button_fks.SetToolTipString("Check for foreign key violations")
        button_check.SetToolTipString("Check database integrity for "
                                      "corruption and recovery")
        button_optimize.SetToolTipString("Attempt to optimize the database, "
                                         "running ANALYZE on tables")
        button_vacuum.SetToolTipString("Rebuild the database file, repacking "
                                       "it into a minimal amount of disk space")
        button_fks.SetToolTipString("Open database file directory")
        button_refresh.SetToolTipString("Refresh file information")

        sizer_buttons = wx.FlexGridSizer(cols=5, vgap=5)
        sizer_buttons.AddGrowableCol(1)
        sizer_buttons.AddGrowableCol(3)

        sizer_buttons.Add(button_fks, flag=wx.GROW)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_check, flag=wx.GROW)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_optimize, flag=wx.GROW)
        sizer_buttons.Add(button_vacuum, flag=wx.GROW)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_open_folder, flag=wx.GROW)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_refresh, flag=wx.GROW)
        self.Bind(wx.EVT_BUTTON, self.on_check_fks, button_fks)
        self.Bind(wx.EVT_BUTTON, self.on_check_integrity, button_check)
        self.Bind(wx.EVT_BUTTON, self.on_optimize, button_optimize)
        self.Bind(wx.EVT_BUTTON, self.on_vacuum, button_vacuum)
        self.Bind(wx.EVT_BUTTON, lambda e: util.start_file(os.path.split(self.db.filename)[0]),
                  button_open_folder)
        self.Bind(wx.EVT_BUTTON, lambda e: self.update_info_panel(),
                  button_refresh)

        sizer_info.AddGrowableCol(1, proportion=1)
        sizer_file.Add(sizer_info, proportion=1, border=10, flag=wx.LEFT | wx.GROW)
        sizer_file.Add(sizer_buttons, border=10, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.GROW)
        sizer1.Add(label_file, border=5, flag=wx.ALL)
        sizer1.Add(panel1c, border=6, proportion=1, flag=wx.TOP | wx.GROW)

        nb = self.notebook_info = wx.Notebook(panel2)
        panel_stats, panel_schema = wx.Panel(nb), wx.Panel(nb)
        panel_stats.Sizer  = wx.BoxSizer(wx.VERTICAL)
        panel_schema.Sizer = wx.BoxSizer(wx.VERTICAL)

        bmp1 = images.ToolbarRefresh.Bitmap
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_COPY, wx.ART_TOOLBAR,
                                        (16, 16))
        bmp3 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR,
                                        (16, 16))
        tb_stats = self.tb_stats = wx.ToolBar(panel_stats,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        tb_stats.SetToolBitmapSize(bmp1.Size)
        tb_stats.AddLabelTool(wx.ID_REFRESH, "", bitmap=bmp1, shortHelp="Refresh statistics")
        tb_stats.AddLabelTool(wx.ID_COPY,    "", bitmap=bmp2, shortHelp="Copy statistics to clipboard as text")
        tb_stats.AddLabelTool(wx.ID_SAVE,    "", bitmap=bmp3, shortHelp="Save statistics HTML to file")
        tb_stats.Realize()
        tb_stats.EnableTool(wx.ID_COPY, False)
        tb_stats.EnableTool(wx.ID_SAVE, False)
        tb_stats.Bind(wx.EVT_TOOL, self.on_update_statistics, id=wx.ID_REFRESH)
        tb_stats.Bind(wx.EVT_TOOL, self.on_copy_statistics,   id=wx.ID_COPY)
        tb_stats.Bind(wx.EVT_TOOL, self.on_save_statistics,   id=wx.ID_SAVE)

        html_stats = self.html_stats = wx.html.HtmlWindow(panel_stats)
        html_stats.Bind(wx.EVT_SCROLLWIN, self.on_scroll_html_stats)
        html_stats.Bind(wx.EVT_SIZE,      self.on_size_html_stats)

        tb_sql = self.tb_sql = wx.ToolBar(panel_schema,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        tb_sql.SetToolBitmapSize(bmp1.Size)
        tb_sql.AddLabelTool(wx.ID_REFRESH, "", bitmap=bmp1, shortHelp="Refresh schema SQL")
        tb_sql.AddLabelTool(wx.ID_COPY,    "", bitmap=bmp2, shortHelp="Copy schema SQL to clipboard")
        tb_sql.AddLabelTool(wx.ID_SAVE,    "", bitmap=bmp3, shortHelp="Save schema SQL to file")
        tb_sql.Realize()
        tb_sql.EnableTool(wx.ID_COPY, False)
        tb_sql.EnableTool(wx.ID_SAVE, False)
        tb_sql.Bind(wx.EVT_TOOL, self.on_update_stc_schema, id=wx.ID_REFRESH)
        tb_sql.Bind(wx.EVT_TOOL, lambda e: self.on_copy_sql(self.stc_schema, e), id=wx.ID_COPY)
        tb_sql.Bind(wx.EVT_TOOL, lambda e: self.on_save_sql(self.stc_schema, e), id=wx.ID_SAVE)

        stc = self.stc_schema = controls.SQLiteTextCtrl(panel_schema,
            style=wx.BORDER_STATIC)
        stc.SetText("Parsing..")
        stc.SetReadOnly(True)

        panel_stats.Sizer.Add(tb_stats, border=5, flag=wx.ALL)
        panel_stats.Sizer.Add(html_stats, proportion=1, flag=wx.GROW)

        panel_schema.Sizer.Add(tb_sql, border=5, flag=wx.ALL)
        panel_schema.Sizer.Add(stc, proportion=1, flag=wx.GROW)

        nb.AddPage(panel_stats,  "Statistics")
        nb.AddPage(panel_schema, "Schema")
        sizer2.Add(nb, proportion=1, flag=wx.GROW)

        sizer.Add(splitter, border=5, proportion=1, flag=wx.ALL | wx.GROW)
        splitter.SplitVertically(panel1, panel2, self.Size[0] / 2 - 60)

        self.populate_statistics()


    def on_sys_colour_change(self, event):
        """Handler for system colour change, refreshes content."""
        event.Skip()
        def dorefresh():
            self.label_html.SetPage(step.Template(templates.SEARCH_HELP_SHORT_HTML).expand())
            self.label_html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNFACE)
            self.label_html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
            default = step.Template(templates.SEARCH_WELCOME_HTML).expand()
            self.html_searchall.SetDefaultPage(default)
            self.populate_statistics()
        wx.CallAfter(dorefresh) # Postpone to allow conf update


    def register_notebook_hotkeys(self, notebook):
        """Register Ctrl-W close handler to notebook pages."""
        def on_close_hotkey(event):
            notebook and notebook.DeletePage(notebook.GetSelection())

        id_close = wx.NewId()
        accelerators = [(wx.ACCEL_CTRL, k, id_close) for k in [ord('W')]]
        notebook.Bind(wx.EVT_MENU, on_close_hotkey, id=id_close)
        notebook.SetAcceleratorTable(wx.AcceleratorTable(accelerators))


    def on_update_stc_schema(self, event=None):
        """Handler for clicking to refresh database schema SQL."""
        scrollpos = self.stc_schema.GetScrollPos(wx.VERTICAL)

        self.stc_schema.SetReadOnly(False)
        self.stc_schema.SetText("Parsing..")
        self.stc_schema.SetReadOnly(True)
        self.tb_sql.EnableTool(wx.ID_COPY, False)
        self.tb_sql.EnableTool(wx.ID_SAVE, False)

        self.db.populate_schema(parse=True)
        self.stc_schema.SetReadOnly(False)
        self.stc_schema.SetText(self.db.get_sql())
        self.stc_schema.SetReadOnly(True)
        self.stc_schema.ScrollToLine(scrollpos)
        self.tb_sql.EnableTool(wx.ID_COPY, True)
        self.tb_sql.EnableTool(wx.ID_SAVE, True)


    def on_update_statistics(self, event=None):
        """
        Handler for refreshing database statistics, sets loading-content
        and tasks worker.
        """
        self.statistics = {}
        self.populate_statistics()
        self.worker_analyzer.work(self.db.filename)


    def on_copy_statistics(self, event=None):
        """Handler for copying database statistics to clipboard."""
        if wx.TheClipboard.Open():
            ns = {"db_filename": self.db.name,
                  "db_filesize": self.statistics["data"]["filesize"]}
            content = step.Template(templates.DATA_STATISTICS_TXT, strip=False).expand(
                dict(ns, **self.statistics)
            )
            d = wx.TextDataObject(content)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied database statistics to clipboard", flash=True)


    def on_save_statistics(self, event=None):
        """
        Handler for saving database statistics to file, pops open file dialog
        and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.name))[0]
        filename = filename.rstrip() + " statistics"
        dialog = wx.FileDialog(
            parent=self, message="Save statistics as", defaultFile=filename,
            wildcard="HTML file (*.html)|*.html|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            ns = {"title": "Database statistics", "db_filename": self.db.name,
                  "db_filesize": self.statistics["data"]["filesize"]}
            content = step.Template(templates.DATA_STATISTICS_HTML, escape=True).expand(
                dict(ns, **self.statistics)
            )
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving statistics to %s." % filename
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def on_analyzer_result(self, result):
        """
        Handler for getting results from analyzer thread, populates statistics.
        """
        self.statistics = result
        self.populate_statistics()


    def on_size_html_stats(self, event):
        """
        Handler for sizing html_stats, sets new scroll position based
        previously stored one (HtmlWindow loses its scroll position on resize).
        """
        html = self.html_stats
        if hasattr(html, "_last_scroll_pos"):
            for i in range(2):
                orient = wx.VERTICAL if i else wx.HORIZONTAL
                # Division can be > 1 on first resizings, bound it to 1.
                ratio = min(1, util.safedivf(html._last_scroll_pos[i],
                    html._last_scroll_range[i]
                ))
                html._last_scroll_pos[i] = ratio * html.GetScrollRange(orient)
            # Execute scroll later as something resets it after this handler
            scroll_func = lambda: html and html.Scroll(*html._last_scroll_pos)
            wx.CallLater(50, scroll_func)
        event.Skip() # Allow event to propagate wx handler


    def on_scroll_html_stats(self, event):
        """
        Handler for scrolling the HTML stats, stores scroll position
        (HtmlWindow loses it on resize).
        """
        wx.CallAfter(self.store_html_stats_scroll)
        event.Skip() # Allow event to propagate wx handler


    def store_html_stats_scroll(self):
        """
        Stores the statistics HTML scroll position, needed for getting around
        its quirky scroll updating.
        """
        if not self:
            return
        self.html_stats._last_scroll_pos = [
            self.html_stats.GetScrollPos(wx.HORIZONTAL),
            self.html_stats.GetScrollPos(wx.VERTICAL)
        ]
        self.html_stats._last_scroll_range = [
            self.html_stats.GetScrollRange(wx.HORIZONTAL),
            self.html_stats.GetScrollRange(wx.VERTICAL)
        ]


    def populate_statistics(self):
        """Populates statistics HTML window."""
        previous_scrollpos = getattr(self.html_stats, "_last_scroll_pos", None)
        html = step.Template(templates.STATISTICS_HTML, escape=True).expand(dict(self.statistics))
        self.html_stats.Freeze()
        self.html_stats.SetPage(html)
        self.html_stats.BackgroundColour = conf.BgColour
        if previous_scrollpos:
            self.html_stats.Scroll(*previous_scrollpos)
        self.html_stats.Thaw()
        self.tb_stats.EnableTool(wx.ID_COPY, "data" in self.statistics)
        self.tb_stats.EnableTool(wx.ID_SAVE, "data" in self.statistics)


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

        self.populate_pragma_sql()


    def populate_pragma_sql(self):
        """Populates PRAGMA SQL STC with PRAGMA values-"""
        scrollpos = self.stc_pragma.GetScrollPos(wx.VERTICAL)
        self.stc_pragma.Freeze()
        self.stc_pragma.SetReadOnly(False)
        self.stc_pragma.Text = ""
        values = dict(self.pragma_changes)
        if self.pragma_fullsql:
            values = dict(self.pragma, **values)
            for name, opts in database.Database.PRAGMA.items():
                if opts.get("read") or opts.get("write") is False:
                    values.pop(name, None)

        lastopts = {}
        for name, opts in sorted(database.Database.PRAGMA.items(),
            key=lambda x: (bool(x[1].get("deprecated")), x[1]["label"])
        ):
            if name not in values:
                lastopts = opts
                continue # for name, opts

            if opts.get("deprecated") \
            and bool(lastopts.get("deprecated")) != bool(opts.get("deprecated")):
                self.stc_pragma.Text += "-- DEPRECATED:\n\n"

            value = values[name]
            if isinstance(value, basestring):
                value = '"%s"' % value.replace('"', '""')
            elif isinstance(value, bool): value = str(value).upper()
            self.stc_pragma.Text += "PRAGMA %s = %s;\n\n" % (name, value)
            lastopts = opts
        self.stc_pragma.SetReadOnly(True)
        self.stc_pragma.ScrollToLine(scrollpos)
        self.stc_pragma.Thaw()
        self.update_page_header()


    def on_pragma_sql(self, event=None):
        """Handler for toggling PRAGMA change SQL visible."""
        self.stc_pragma.Shown = self.check_pragma_sql.Value
        self.check_pragma_fullsql.Shown = self.check_pragma_sql.Value
        self.tb_pragma.Shown = self.check_pragma_sql.Value
        self.page_pragma.Layout()


    def on_pragma_fullsql(self, event=None):
        """Handler for toggling full PRAGMA SQL."""
        self.pragma_fullsql = self.check_pragma_fullsql.Value
        self.populate_pragma_sql()


    def on_pragma_filter(self, event):
        """Handler for filtering PRAGMA list, shows/hides components."""
        search = event.String.strip()
        if search == self.pragma_filter: return
            
        patterns = map(re.escape, search.split())
        values = dict(self.pragma, **self.pragma_changes)
        show_deprecated = False
        self.page_pragma.Freeze()
        for name, opts in database.Database.PRAGMA.items():
            texts = [name, opts["label"], opts["short"],
                     self.pragma_ctrls[name].ToolTipString]
            for kv in opts.get("values", {}).items(): texts.extend(map(str, kv))
            if name in values: texts.append(str(values[name]))
            show = all(any(re.search(p, x, re.I | re.U) for x in texts)
                       for p in patterns)
            if opts.get("deprecated"): show_deprecated |= show
            if self.pragma_ctrls[name].Shown == show: continue # for name
            [x.Show(show) for x in self.pragma_items[name]]
        if show_deprecated != self.label_deprecated.Shown:
            self.label_deprecated.Show(show_deprecated)
        self.pragma_filter = search
        self.page_pragma.Layout()
        self.page_pragma.Thaw()


    def on_pragma_key(self, event):
        """
        Handler for pressing a key in pragma page, focuses filter on Ctrl-F.
        """
        if event.ControlDown() and event.KeyCode in [ord('F')]:
            self.edit_pragma_filter.SetFocus()
        else: event.Skip()


    def on_pragma_save(self, event=None):
        """Handler for clicking to save PRAGMA changes."""
        result = True

        changes = {} # {pragma_name: value}
        for name, value in sorted(self.pragma_changes.items()):
            if value == self.pragma.get(name): continue # for name, value
            changes[name] = value

        try:
            for name, value in changes.items():
                if isinstance(value, basestring):
                    value = '"%s"' % value.replace('"', '""')
                elif isinstance(value, bool): value = str(value).upper()
                sql = "PRAGMA %s = %s" % (name, value)
                logger.info("Executing %s.", sql)
                self.db.execute(sql)
        except Exception as e:
            result = False
            msg = "Error setting %s:\n\n%s" % (sql, util.format_exc(e))
            logger.exception(msg)
            guibase.status(msg, flash=True)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)
        else:
            self.on_pragma_cancel()
        return result


    def on_pragma_edit(self, event=None):
        """Handler for clicking to edit PRAGMA settings."""
        if self.pragma_edit: return self.on_pragma_save()

        self.pragma_edit = True
        self.button_pragma_edit.Label = "Save"
        self.button_pragma_cancel.Enable()
        self.check_pragma_sql.Parent.Show()
        if self.check_pragma_sql.Value:
            self.stc_pragma.Shown = True
            self.check_pragma_fullsql.Shown = True
            self.tb_pragma.Shown = True
        for name, opts in database.Database.PRAGMA.items():
            ctrl = self.pragma_ctrls[name]
            if opts.get("write") != False and "table" != opts["type"]:
                ctrl.Enable()
        self.page_pragma.Layout()


    def on_pragma_refresh(self, event=None):
        """Handler for clicking to refresh PRAGMA settings."""
        editmode = self.pragma_edit
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
        self.populate_pragma_sql()
        self.pragma_edit = editmode
        self.update_page_header()


    def on_pragma_cancel(self, event=None):
        """Handler for clicking to cancel PRAGMA changes."""
        if event and self.pragma_changes and wx.OK != wx.MessageBox(
            "You have unsaved changes, are you sure you want to discard them?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        self.pragma_edit = False
        self.button_pragma_edit.Label = "Edit"
        self.button_pragma_cancel.Disable()
        self.on_pragma_refresh(None)
        self.check_pragma_sql.Parent.Hide()
        for name, opts in database.Database.PRAGMA.items():
            if "table" != opts["type"]: self.pragma_ctrls[name].Disable()
        self.page_pragma.Layout()
        self.update_page_header()


    def on_check_fks(self, event=None):
        """
        Handler for checking foreign key violations, pops open dialog with
        violation results.
        """
        rows = self.db.execute("PRAGMA foreign_key_check").fetchall()
        if not rows:
            wx.MessageBox("No foreign key violations detected.",
                          conf.Title, wx.OK | wx.ICON_INFORMATION)
            return

        # {table: {parent: {fkid: [rowid, ]}}}
        data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        fks  = {} # {table: {fkid: (fkcol, parent, pkcol)}}
        for row in rows:
            data[row["table"]][row["parent"]][row["fkid"]].append(row["rowid"])
        for table in data:
            fks[table] = {x["id"]: (x["from"], x["table"], x["to"])
                         for x in self.db.execute("PRAGMA foreign_key_list(%s)" %
                         grammar.quote(table)).fetchall()}
        lines = []
        for table in sorted(data, key=lambda x: x.lower()):
            for parent in data[table]:
                for fkid, rowids in data[table][parent].items():
                    fk, _, pk = fks[table][fkid]
                    args = tuple(map(grammar.quote, (table, fk, parent, pk))) + (util.plural("row", rowids),)
                    line = "%s.%s REFERENCING %s.%s: %s" % args
                    if any(rowids): # NULL values: table WITHOUT ROWID
                        vals = [x[fk] for x in self.db.execute(
                            "SELECT %s FROM %s WHERE rowid IN (%s)" %
                            (grammar.quote(fk), grammar.quote(table), ", ".join(map(str, rowids)))
                        ).fetchall()]
                        if vals: line += "\nKeys: (%s)" % ", ".join(map(unicode, sorted(vals)))
                    lines.append(line)

        msg = "Detected %s in %s:\n\n%s" % (
              util.plural("foreign key violation", rows), util.plural("table", data), "\n\n".join(lines))
        wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_optimize(self, event=None):
        """
        Handler for running optimize on database.
        """
        self.db.execute("PRAGMA optimize")


    def on_check_integrity(self, event=None):
        """
        Handler for checking database integrity, offers to save a fixed
        database if corruption detected.
        """
        msg = "Checking integrity of %s." % self.db.filename
        guibase.status(msg, log=True, flash=True)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        try:
            errors = self.db.check_integrity()
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        guibase.status("")
        if not errors:
            wx.MessageBox("No database errors detected.",
                          conf.Title, wx.ICON_INFORMATION)
        else:
            err = "\n- ".join(errors)
            logger.info("Errors found in %s: %s", self.db, err)
            err = err[:500] + ".." if len(err) > 500 else err
            msg = "A number of errors were found in %s:\n\n- %s\n\n" \
                  "Recover as much as possible to a new database?" % \
                  (self.db, err)
            if wx.YES == wx.MessageBox(msg, conf.Title,
                                       wx.ICON_WARNING | wx.YES | wx.NO):
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
                        guibase.status("Recovering data from %s to %s.",
                                       self.db.filename, newfile, flash=True)
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
                        guibase.status("Recovery to %s complete." % newfile, flash=True)
                        wx.PostEvent(self, OpenDatabaseEvent(-1, file=newfile))
                        wx.MessageBox("Recovery to %s complete.%s" %
                                      (newfile, err), conf.Title,
                                      wx.ICON_INFORMATION)
                    else:
                        wx.MessageBox("Cannot recover data from %s to itself."
                                      % self.db, conf.Title, wx.ICON_ERROR)


    def on_vacuum(self, event=None):
        """
        Handler for vacuuming the database.
        """
        msg = "Vacuuming %s." % self.db.name
        guibase.status(msg, log=True, flash=True)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        errors = []
        try:
            self.db.execute("VACUUM")
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        guibase.status("")
        if errors:
            err = "\n- ".join(errors)
            logger.info("Error running vacuum on %s: %s", self.db, err)
            err = err[:500] + ".." if len(err) > 500 else err
            wx.MessageBox(err, conf.Title, wx.OK | wx.ICON_ERROR)
        else:
            self.update_info_panel()


    def save_page_conf(self):
        """Saves page last configuration like search text and results."""
        if self.db.temporary: return

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

        # Save page SQL windows content, if changed from previous value
        sqls = [{k: v.GetText()} for k, v in self.sql_pages.items() if v.GetText()]
        if sqls != conf.SQLWindowTexts.get(self.db.filename):
            if sqls: conf.SQLWindowTexts[self.db.filename] = sqls
            else: conf.SQLWindowTexts.pop(self.db.filename, None)


    def split_panels(self):
        """
        Splits all SplitterWindow panels. To be called after layout in
        Linux wx 2.8, as otherwise panels do not get sized properly.
        """
        if not self:
            return
        for splitter in self.splitter_data, self.splitter_schema, self.splitter_info:
            panel1, panel2 = splitter.Children
            splitter.Unsplit()
            splitter.SplitVertically(panel1, panel2, 270)
        wx.CallLater(1000, lambda: self and
                     (self.tree_data.SetColumnWidth(0, -1),
                      self.tree_data.SetColumnWidth(1, -1)))


    def update_info_panel(self, reload=True):
        """Updates the Information page panel with current data."""
        if reload:
            self.db.populate_schema()
            self.db.update_fileinfo()
        for name in ["size", "created", "modified", "sha1", "md5"]:
            getattr(self, "edit_info_%s" % name).Value = ""

        self.edit_info_path.Value = "<temporary file>" if self.db.temporary \
                                    else self.db.filename
        if self.db.filesize:
            self.edit_info_size.Value = "%s (%s)" % \
                (util.format_bytes(self.db.filesize),
                 util.format_bytes(self.db.filesize, max_units=False))
        else:
            self.edit_info_size.Value = "0 bytes"
        self.edit_info_created.Value = \
            self.db.date_created.strftime("%Y-%m-%d %H:%M:%S")
        self.edit_info_modified.Value = \
            self.db.last_modified.strftime("%Y-%m-%d %H:%M:%S")
        BLOCKSIZE = 1048576
        if not self.db.temporary or self.db.filesize:
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

        for name in ["size", "created", "modified", "sha1", "md5", "path"]:
            getattr(self, "edit_info_%s" % name).MinSize = (-1, -1)
        self.edit_info_path.ContainingSizer.Layout()

        self.button_vacuum.Enabled = self.button_check_fks.Enabled = True
        self.button_optimize.Enabled = self.button_check_integrity.Enabled = True
        self.button_refresh_info.Enabled = True
        self.button_open_folder.Enabled = not self.db.temporary


    def on_refresh_data(self, event):
        """Refreshes the data tree."""
        self.load_tree_data(refresh=True)


    def on_rightclick_searchall(self, event):
        """
        Handler for right-clicking in HtmlWindow, sets up a temporary flag for
        HTML link click handler to check, in order to display a context menu.
        """
        event.Skip()
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
        wx.CallAfter(reset)


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
                item = self.tree_data.GetNext(self.tree_data.GetNext(self.tree_data.RootItem))
                tablemap = self.db.get_category("table")
                while table_name in tablemap and item and item.IsOk():
                    data = self.tree_data.GetItemPyData(item)
                    if isinstance(data, dict) and "table" == data.get("type") \
                    and data["name"].lower() == table_name:
                        tableitem = item
                        break # while table_name
                    item = self.tree_data.GetNextSibling(item)
                if tableitem:
                    self.notebook.SetSelection(self.pageorder[self.page_data])
                    wx.YieldIfNeeded()
                    # Only way to create state change in wx.gizmos.TreeListCtrl
                    class HackEvent(object):
                        def __init__(self, item): self._item = item
                        def GetItem(self):        return self._item
                    self.on_change_tree_data(HackEvent(tableitem))
                    if self.tree_data.Selection != tableitem:
                        self.tree_data.SelectItem(tableitem)
                        wx.YieldIfNeeded()

                    if row: # Scroll to matching row
                        p = self.data_pages["table"][tablemap[table_name]["name"]]
                        if p: p.ScrollToRow(row)

        elif href.startswith("page:"):
            # Go to database subpage
            page = href[5:]
            if "#help" == page:
                html = self.html_searchall
                if html.GetTabDataByID(0):
                    html.SetActiveTabByID(0)
                else:
                    h = step.Template(templates.SEARCH_HELP_LONG_HTML).expand()
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
            self.label_search.Label = "&Search in database CREATE SQL:"
        elif wx.ID_STATIC == event.Id:
            conf.SearchInTables = True
            conf.SearchInNames = False
            self.label_search.Label = "&Search in table data:"
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
            guibase.status('Finished searching for "%s" in %s.',
                           result["search"]["text"], self.db, flash=True)
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
            if search_id in self.workers_search:
                self.workers_search[search_id].stop()
                del self.workers_search[search_id]
        if "error" in result:
            msg = "Error searching %s:\n\n%s"
            logger.info(msg, self.db, result["error"])
            error = msg % (self.db, result.get("error_short", result["error"]))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_searchall_callback(self, result):
        """Callback function for SearchThread, posts the data to self."""
        if self: # Check if instance is still valid (i.e. not destroyed by wx)
            wx.PostEvent(self, SearchEvent(result=result))


    def on_searchall(self, event):
        """
        Handler for clicking to global search the database.
        """
        text = self.edit_searchall.Value
        if text.strip():
            guibase.status('Searching for "%s" in %s.',
                           text, self.db, flash=True)
            html = self.html_searchall
            data = {"id": self.counter(), "db": self.db, "text": text, "map": {},
                    "width": html.Size.width * 5/9, "table": "",
                    "partial_html": ""}
            if conf.SearchInNames:
                data["table"] = "meta"
                fromtext = "database CREATE SQL"
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


    def on_copy_sql(self, stc, event):
        """Handler for copying SQL to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(stc.Text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied SQL to clipboard", flash=True)


    def on_save_sql(self, stc, event):
        """
        Handler for saving SQL to file, opens file dialog and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.name))[0]
        if stc is self.stc_pragma: filename += " PRAGMA"
        dialog = wx.FileDialog(
            parent=self, message="Save SQL as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            content = step.Template(templates.CREATE_SQL, strip=False).expand(
                title="Database schema.", db_filename=self.db.name, sql=stc.GetText())
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving SQL to %s." % filename
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def set_ignore_unsaved(self, ignore=True):
        """Sets page to ignore unsaved changes on close."""
        self.ignore_unsaved = True


    def get_unsaved(self):
        """
        Returns whether page has unsaved changes,
        as {?"pragma": [pragma_name, ], ?"table": [table, ],
            ?"schema": True, ?"temporary"? True}.
        """
        result = {}
        if self.ignore_unsaved or not hasattr(self, "data_pages"): return result

        if self.pragma_changes: result["pragma"] = list(self.pragma_changes)
        grids = self.get_unsaved_grids()
        if grids: result["table"] = [x.Name for x in grids]
        schemas = self.get_unsaved_schemas()
        if schemas: result["schema"] = True
        if not result and self.db.temporary:
            self.db.populate_schema()
            if any(self.db.schema.values()): result["temporary"] = True
        return result


    def get_unsaved_grids(self):
        """
        Returns a list of data page objects where changes have not been
        saved after changing.
        """
        return [y for x in self.data_pages.values()
                for y in x.values() if y.IsChanged()]


    def get_unsaved_schemas(self):
        """
        Returns a list of schema page objects where changes have not been
        saved after changing.
        """
        return [y for x in self.schema_pages.values()
                for y in x.values() if y.IsChanged()]


    def save_database(self, rename=False):
        """Saves the database, under a new name if specified, returns success."""
        is_temporary = self.db.temporary
        filename1, filename2, tempname = self.db.filename, self.db.filename, None

        if is_temporary or rename:
            exts = ";".join("*" + x for x in conf.DBExtensions)
            wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
            title = "Save %s as.." % os.path.split(self.db.name)[-1]
            dialog = wx.FileDialog(self,
                message=title, wildcard=wildcard,
                defaultDir="" if is_temporary else os.path.split(self.db.filename)[0],
                defaultFile=os.path.basename(self.db.name),
                style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
            )
            if wx.ID_OK != dialog.ShowModal(): return

            filename2 = dialog.GetPath()
            if filename1 != filename2 and filename2 in conf.DBsOpen: return wx.MessageBox(
                "%s is already open in %s." % (filename2, conf.Title),
                conf.Title, wx.OK | wx.ICON_WARNING
            )
        rename = (filename1 != filename2)

        if rename:
            # Use a tertiary file in case something fails
            fh, tempname = tempfile.mkstemp(".db")
            os.close(fh)

        file_existed = os.path.exists(filename2)

        try:
            if rename:
                shutil.copy(filename1, tempname)
                self.db.reopen(tempname)
        except Exception as e:
            logger.exception("Error saving %s as %s.", self.db, filename2)
            self.db.reopen(filename1)
            self.reload_grids(pending=True)
            try: os.unlink(tempname)
            except Exception: pass
            wx.MessageBox("Error saving %s as %s:\n\n" % 
                          (filename1, filename2, util.format_exc(e)),
                          conf.Title, wx.OK | wx.ICON_ERROR)
            return

        success, error = True, None
        self.save_underway = True
        schemas_saved = {} # {category: {key: page}}
        try:
            for dct in self.data_pages, self.schema_pages:
                for category, key, page in ((c, k, p) for c, m in dct.items()
                                            for k, p in m.items()):
                    if not page.IsChanged(): continue # for category
                    success = page.Save(backup=True)
                    if not success: break # for category
                    if isinstance(page, SchemaObjectPage):
                        schemas_saved.setdefault(category, {})[key] = page
                if not success: break # for group
                        
            if success and self.pragma_changes:
                success = self.on_pragma_save()
        except Exception as e:
            logger.exception("Error saving changes in %s.", self.db)
            error = "Error saving changes:\n\n%s" % util.format_exc(e)
            try: self.db.execute("ROLLBACK")
            except Exception: pass
        self.save_underway = False

        if success and rename:
            try:
                shutil.copy(tempname, filename2)
                self.db.reopen(filename2)
            except Exception as e:
                error = "Error saving %s as %s:\n\n" % util.format_exc(e)
                logger.exception("Error saving temporary file %s as %s.",
                                 tempname, filename2)
            
        if not success and rename:
            self.db.reopen(filename1)

        if success or not rename:
            self.reload_schema(count=True, parse=True)
            if success: self.reload_grids()

        if not success and rename:
            self.db.reopen(filename1)
            for category, key, page in ((c, k, p) for c, m in schemas_saved.items()
                                        for k, p in m.items()):
                pagedict = getattr(self, group)
                pagedict[category][key] = pagedict[category].pop(page.Name)
                page.RestoreBackup()

            self.reload_grids(pending=True)

        try: tempname and os.unlink(tempname)
        except Exception: pass

        if not success:
            if error: wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
            return
            
        self.db.name, self.db.temporary = filename2, False
        if rename:
            evt = DatabasePageEvent(-1, source=self, rename=True, temporary=is_temporary,
                                    filename1=filename1, filename2=filename2)
            wx.PostEvent(self, evt)
            self.load_data()
        return True


    def reload_grids(self, pending=False):
        """
        Reloads all grids in data and SQL tabs,
        optionally retaining pending data changes.
        """
        for p in self.data_pages["table"].values(): p.Reload(pending=pending)
        for p in self.sql_pages.values():           p.Reload()


    def update_page_header(self):
        """Mark database as changed/pristine in the parent notebook tabs."""
        wx.PostEvent(self, DatabasePageEvent(-1, source=self, modified=self.get_unsaved()))


    def on_change_tree_data(self, event):
        """Handler for activating a schema item, loads object."""
        item, tree = event.GetItem(), self.tree_schema
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item) or {}
        data = data if data.get("type") in database.Database.CATEGORIES \
               else data.get("parent") if "column" == data.get("type") else None

        if data:
            nb = self.notebook_data
            p = self.data_pages[data["type"]].get(data["name"])
            if p: nb.SetSelection(nb.GetPageIndex(p))
            else:
                data = self.db.get_category(data["type"], data["name"])
                self.add_data_page(data)
            tree.Expand(tree.GetItemParent(item))
        else:
            tree.Collapse(item) if tree.IsExpanded(item) else tree.Expand(item)


    def add_data_page(self, data):
        """Opens a data object page for specified object data."""
        title = "%s %s" % (data["type"].capitalize(), grammar.quote(data["name"]))
        p = DataObjectPage(self.notebook_schema, self.db, data)
        self.data_pages[data["type"]][data.get("name") or id(p)] = p
        self.notebook_data.InsertPage(0, page=p, text=title, select=True)
        self.TopLevelParent.UpdateAccelerators() # Add panel accelerators


    def add_sql_page(self, name="", text=""):
        """Opens an SQL page with specified text."""
        self.sql_page_counter += 1
        if not name:
            name = "SQL"
            if not self.sql_pages: self.sql_page_counter = 1
            if self.sql_page_counter > 1:
                name += " (%s)" % self.sql_page_counter
        p = SQLPage(self.notebook_schema, self.db)
        p.SetText(text)
        self.sql_pages[name] = p
        self.notebook_sql.InsertPage(0, page=p, text=name, select=True)
        self.TopLevelParent.UpdateAccelerators() # Add panel accelerators


    def on_rclick_tree_data(self, event):
        """
        Handler for right-clicking an item in the tables list,
        opens popup menu for choices to export data.
        """
        item, tree = event.GetItem(), self.tree_data
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item)
        if not data: return

        # Only way to create state change in wx.gizmos.TreeListCtrl
        class HackEvent(object):
            def __init__(self, item): self._item = item
            def GetItem(self):        return self._item

        def select_item(item, expand=False, *_, **__):
            tree.SelectItem(item)
            if expand: tree.Expand(item)
        def open_item(item, *_, **__):
            self.on_change_tree_data(HackEvent(item))
            wx.CallAfter(select_item, item)
        def open_meta(item, *_, **__):
            self.notebook.SetSelection(self.pageorder[self.page_schema])
            self.on_change_tree_schema(HackEvent(item))
        def clipboard_copy(text, *_, **__):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
        def toggle_items(node, *_, **__):
            items, it = [node], tree.GetNext(node)
            while it and it.IsOk():
                items.append(it)
                it = tree.GetNextSibling(it)
            if any(map(tree.IsExpanded, items)):
                for it in items: tree.Collapse(it)
            else: tree.ExpandAll(node)

        boldfont = wx.Font(self.Font.PointSize, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)

        menu = wx.Menu()
        item_file = item_database = None
        if data.get("type") in ("table", "view"): # Single table/view
            item_name = wx.MenuItem(menu, -1, '%s %s' % (
                        data["type"].capitalize(), util.unprint(grammar.quote(data["name"], force=True))))
            item_open = wx.MenuItem(menu, -1, "&Open %s" % data["type"])
            item_open_meta = wx.MenuItem(menu, -1, "Open %s &schema" % data["type"])
            item_copy = wx.MenuItem(menu, -1, "&Copy name")
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item, True),
                      id=item_name.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(open_meta, item), id=item_open_meta.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"]),
                      id=item_copy.GetId())

            item_name.Font = boldfont

            menu.AppendItem(item_name)
            menu.AppendSeparator()
            menu.AppendItem(item_open)
            menu.AppendItem(item_open_meta)
            menu.AppendItem(item_copy)

            item_file     = wx.MenuItem(menu, -1, '&Export %s to file' % data["type"])
            if "table" == data["type"]:
                item_database = wx.MenuItem(menu, -1, 'Export table to another &database')

        elif "column" == data.get("type"): # Column
            item_name = wx.MenuItem(menu, -1, 'Column "%s.%s"' % (
                        util.unprint(grammar.quote(data["parent"]["name"])),
                        util.unprint(grammar.quote(data["name"]))))
            item_open = wx.MenuItem(menu, -1, "&Open table")
            item_copy = wx.MenuItem(menu, -1, "&Copy name")
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item, False),
                      id=item_name.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, tree.GetItemParent(item)),
                      id=item_open.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"]),
                      id=item_copy.GetId())

            item_name.Font = boldfont

            menu.AppendItem(item_name)
            menu.AppendSeparator()
            menu.AppendItem(item_open)
            menu.AppendItem(item_copy)

        elif "category" == data.get("type"): # Category list
            item_copy     = wx.MenuItem(menu, -1, "&Copy %s names" % data["category"])
            item_file     = wx.MenuItem(menu, -1, "&Export all %s to file" % util.plural(data["category"]))
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, ", ".join(data["items"])),
                      id=item_copy.GetId())

            menu.AppendItem(item_copy)

            if "table" == data["category"]:
                item_database = wx.MenuItem(menu, -1, "Export all tables to another &database")
            if not data["items"]:
                item_copy.Enable(False)
                item_file.Enable(False)
                if item_database:      item_database.Enable(False)

        if item_file:
            menu.AppendSeparator()
            menu.AppendItem(item_file)
            if item_database:      menu.AppendItem(item_database)
            names = data["items"] if "category" == data["type"] else [data["name"]]
            category = data["category"] if "category" == data["type"] else data["type"]
            menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_file, category, names),
                     id=item_file.GetId())
            if item_database:
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_base, names, True),
                         id=item_database.GetId())

        if tree.HasChildren(item):
            item_expand   = wx.MenuItem(menu, -1, "&Toggle expanded/collapsed")
            menu.Bind(wx.EVT_MENU, functools.partial(toggle_items, item), id=item_expand.GetId())
            if menu.MenuItemCount: menu.AppendSeparator()
            menu.AppendItem(item_expand)

        item0 = tree.GetSelection()
        if item != item0: select_item(item)
        tree.PopupMenu(menu)
        if item0 and item != item0: select_item(item0)


    def on_rclick_tree_schema(self, event):
        """
        Handler for right-clicking an item in the schema tree,
        opens popup menu for choices.
        """
        item, tree = event.GetItem(), self.tree_schema
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item)
        if not data: return

        # Only way to create state change in wx.gizmos.TreeListCtrl
        class HackEvent(object):
            def __init__(self, item): self._item = item
            def GetItem(self):        return self._item

        def select_item(it, expand, *_, **__):
            tree.SelectItem(it)
            if expand: tree.Expand(it)
        def clipboard_copy(text, *_, **__):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text() if callable(text) else text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
        def toggle_items(node, *_, **__):
            items, it = [node], tree.GetNext(node)
            while it and it.IsOk():
                items.append(it)
                it = tree.GetNextSibling(it)
            if any(map(tree.IsExpanded, items)):
                for it in items: tree.Collapse(it)
            else: tree.ExpandAll(node)
        def open_item(item, *_, **__):
            self.on_change_tree_schema(HackEvent(item))
            select_item(item, True)
        def open_data(item, *_, **__):
            self.notebook.SetSelection(self.pageorder[self.page_data])
            self.on_change_tree_data(HackEvent(item))
        def create_object(category, *_, **__):
            newdata = {"type": category,
                       "meta": {"__type__": "CREATE %s" % category.upper()}}
            if category in ("index", "trigger"):
                if data.get("parent") and "table" == data["parent"]["type"]:
                    newdata["meta"]["table"] = data["parent"]["name"]
                elif "table" == data["type"]:
                    newdata["meta"]["table"] = data["name"]
            self.add_schema_page(newdata)
            tree.Expand(item)
        def delete_items(items, *_, **__):
            extra = "\n\nAll data, and any associated indexes and triggers will be lost." \
                    if "table" == items[0]["type"] else ""
            itemtext = util.plural(items[0]["type"], items)
            if len(items) == 1:
                itemtext = " ".join((items[0]["type"], grammar.quote(items[0]["name"], force=True)))
                
            if wx.OK != wx.MessageBox(
                "Are you sure you want to delete the %s?%s" % (itemtext, extra),
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING
            ): return

            if "table" == items[0]["type"] and any(x.get("count") for x in items) \
            and wx.OK != wx.MessageBox(
                "Are you REALLY sure you want to delete the %s?\n\n"
                "%s currently %s %s." %
                (itemtext, "They" if len(items) > 1 else "It",
                 "contain" if len(items) > 1 else "contains",
                 util.plural("row", sum(x.get("count") or 0 for x in items))),
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING
            ): return
            deleteds = []
            try:
                for x in items:
                    self.db.execute("DROP %s %s" % (x["type"].upper(), grammar.quote(x["name"])))
                    deleteds += [x]
            finally:
                if not deleteds: return
                for x in deleteds:
                    page = self.schema_pages[x["type"]].get(x["name"])
                    if page: page.Close(force=True)
                    page = self.data_pages.get(x["type"], {}).get(x["name"])
                    if page: page.Close(force=True)
                self.reload_schema(count=True)

        menu = wx.Menu()
        boldfont = self.Font
        boldfont.SetWeight(wx.FONTWEIGHT_BOLD)
        boldfont.SetFaceName(self.Font.FaceName)
        boldfont.SetPointSize(self.Font.PointSize)

        if "schema" == data["type"]:
            submenu, keys = wx.Menu(), []
            if any(self.db.schema.values()):
                item_copy_sql = wx.MenuItem(menu, -1, "Copy %s &SQL" % data["type"])
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, self.db.get_sql),
                          id=item_copy_sql.GetId())
                menu.AppendItem(item_copy_sql)

            menu.AppendMenu(id=-1, text="Create &new ..", submenu=submenu)
            for category in database.Database.CATEGORIES:
                key = next((x for x in category if x not in keys), category[0])
                keys.append(key)
                it = wx.MenuItem(submenu, -1, 'New ' + category.replace(key, "&" + key, 1))
                submenu.AppendItem(it)
                menu.Bind(wx.EVT_MENU, functools.partial(create_object, category), id=it.GetId())
        elif "category" == data["type"]:
            sqlkws = {"category": data["category"]}
            if data.get("parent"): sqlkws["name"] = [x["name"] for x in data["items"]]
            names = [x["name"] for x in data["items"]]

            if names:
                item_delete = wx.MenuItem(menu, -1, 'Delete all %s' % util.plural(data["category"]))
                item_copy     = wx.MenuItem(menu, -1, "&Copy %s names" % data["category"])
                item_copy_sql = wx.MenuItem(menu, -1, "Copy %s &SQL" % util.plural(data["category"]))

                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, delete_items, data["items"]),
                          id=item_delete.GetId())
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, lambda: "\n".join(map(grammar.quote, names))),
                          id=item_copy.GetId())
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                          functools.partial(self.db.get_sql, **sqlkws)), id=item_copy_sql.GetId())

            item_create = wx.MenuItem(menu, -1, "Create &new %s" % data["category"])

            if names:
                menu.AppendItem(item_copy)
                menu.AppendItem(item_copy_sql)

                if "table" == data["category"]:
                    item_database_meta = wx.MenuItem(menu, -1, "Export all %s str&uctures to another database" % data["category"])
                    menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_base, names, False),
                             id=item_database_meta.GetId())
                    menu.AppendItem(item_database_meta)

                menu.AppendSeparator()
                menu.AppendItem(item_delete)
            menu.AppendItem(item_create)
            menu.Bind(wx.EVT_MENU, functools.partial(create_object, data["category"]), id=item_create.GetId())
        elif "column" == data["type"]:
            has_name, has_sql, table = True, True, {}
            if "view" == data["parent"]["type"]:
                has_sql = False
            elif "index" == data["parent"]["type"]:
                has_name = "name" in data
                table = self.db.get_category("table", data["parent"]["meta"]["table"])
                sqltext = " ".join(filter(bool, (
                    grammar.quote(data["name"]) if has_name else data.get("expr"),
                    "COLLATE %s" % data["collate"] if data.get("collate") else "",
                    data.get("order"),
                )))
            else:
                table = self.db.get_category("table", data["parent"]["name"])
                sqlkws = {"category": "table", "name": table["name"], "column": data["name"]}
                sqltext = functools.partial(self.db.get_sql, **sqlkws)

            if has_name:
                item_name = wx.MenuItem(menu, -1, 'Column "%s"' % ".".join(
                    util.unprint(grammar.quote(x)) for x in (table.get("name"), data["name"]) if x
                ))
                item_name.Font = boldfont
                item_copy = wx.MenuItem(menu, -1, "&Copy name")

            if has_sql:
                names = [data["type"]]
                if "index" == data["parent"]["type"]: names.insert(0, data["parent"]["type"])
                item_copy_sql = wx.MenuItem(menu, -1, "Copy %s &SQL" % " ".join(names))

            if has_name:
                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item, True),
                          id=item_name.GetId())
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"]),
                          id=item_copy.GetId())
            if has_sql:
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                          sqltext), id=item_copy_sql.GetId())

            if has_name:
                menu.AppendItem(item_name)
                menu.AppendSeparator()
                menu.AppendItem(item_copy)
            if has_sql:
                menu.AppendItem(item_copy_sql)
        elif "columns" == data["type"]:
            names = [x["name"] for x in data["parent"]["columns"]]
            item_copy     = wx.MenuItem(menu, -1, "&Copy column names")
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, lambda: "\n".join(map(grammar.quote, names))),
                      id=item_copy.GetId())
            menu.AppendItem(item_copy)
        else: # Single category item, like table
            sqlkws = {"category": data["type"], "name": data["name"]}

            item_name   = wx.MenuItem(menu, -1, '%s %s' % (
                          data["type"].capitalize(),
                          util.unprint(grammar.quote(data["name"], force=True))))
            item_open = wx.MenuItem(menu, -1, "&Open %s" % data["type"])
            item_open_data = wx.MenuItem(menu, -1, "Open %s &data" % data["type"])
            item_copy      = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql  = wx.MenuItem(menu, -1, "Copy %s &SQL" % data["type"])
            item_delete    = wx.MenuItem(menu, -1, 'Delete %s' % data["type"])

            item_name.Font = boldfont

            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item, True),
                      id=item_name.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, item), id=item_open.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(open_data, item), id=item_open_data.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"]),
                      id=item_copy.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                      functools.partial(self.db.get_sql, **sqlkws)), id=item_copy_sql.GetId())
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, delete_items, [data]),
                      id=item_delete.GetId())

            menu.AppendItem(item_name)
            menu.AppendSeparator()
            menu.AppendItem(item_open)
            menu.AppendItem(item_open_data)
            menu.AppendItem(item_copy)
            menu.AppendItem(item_copy_sql)

            if "table" == data["type"]:
                item_database_meta = wx.MenuItem(menu, -1, 'Export %s str&ucture to another database' % data["type"])
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_base, [data["name"]], False),
                         id=item_database_meta.GetId())
                menu.AppendItem(item_database_meta)

            menu.AppendSeparator()

            if "table" == data["type"]:
                submenu, keys = wx.Menu(), []
                menu.AppendMenu(id=-1, text="Create &new ..", submenu=submenu)
                for category in database.Database.CATEGORIES:
                    key = next((x for x in category if x not in keys), category[0])
                    keys.append(key)
                    if category == data["type"]: continue # for category
                    it = wx.MenuItem(submenu, -1, 'New ' + category.replace(key, "&" + key, 1))
                    submenu.AppendItem(it)
                    menu.Bind(wx.EVT_MENU, functools.partial(create_object, category), id=it.GetId())

            menu.AppendItem(item_delete)

        if tree.HasChildren(item):
            item_expand   = wx.MenuItem(menu, -1, "&Toggle expanded/collapsed")
            menu.Bind(wx.EVT_MENU, functools.partial(toggle_items, item), id=item_expand.GetId())
            if menu.MenuItemCount: menu.AppendSeparator()
            menu.AppendItem(item_expand)

        item0 = tree.GetSelection()
        if item != item0: select_item(item, False)
        tree.PopupMenu(menu)
        if item0 and item != item0: select_item(item0, False)


    def on_refresh_schema(self, event):
        """Refreshes database schema tree and panel."""
        self.load_tree_schema(refresh=True)


    def on_schema_create(self, event):
        """Opens popup menu for CREATE options."""
        
        def create_object(category, *_, **__):
            newdata = {"type": category,
                       "meta": {"__type__": "CREATE %s" % category.upper()}}
            self.add_schema_page(newdata)

        menu, keys = wx.Menu(), []
        for category in database.Database.CATEGORIES:
            key = next((x for x in category if x not in keys), category[0])
            keys.append(key)
            it = wx.MenuItem(menu, -1, 'New ' + category.replace(key, "&" + key, 1))
            menu.AppendItem(it)
            menu.Bind(wx.EVT_MENU, functools.partial(create_object, category), id=it.GetId())
        event.EventObject.PopupMenu(menu, tuple(event.EventObject.Size))


    def on_change_tree_schema(self, event):
        """Handler for activating a schema item, loads object."""
        item, tree = event.GetItem(), self.tree_schema
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item) or {}
        data = data if data.get("type") in database.Database.CATEGORIES \
               else data.get("parent") if "column" == data.get("type") else None

        if data:
            nb = self.notebook_schema
            p = self.schema_pages[data["type"]].get(data["name"])
            if p: nb.SetSelection(nb.GetPageIndex(p))
            else:
                data = self.db.get_category(data["type"], data["name"])
                self.add_schema_page(data)
            tree.Expand(tree.GetItemParent(item))
        else:
            tree.Collapse(item) if tree.IsExpanded(item) else tree.Expand(item)


    def add_schema_page(self, data):
        """Opens a schema object page for specified object data."""
        if "name" in data:
            title = "%s %s" % (data["type"].capitalize(), grammar.quote(data["name"]))
        else:
            title = "* New %s *" % data["type"]
        p = SchemaObjectPage(self.notebook_schema, self.db, data)
        self.schema_pages[data["type"]][data.get("name") or id(p)] = p
        self.notebook_schema.InsertPage(0, page=p, text=title, select=True)
        self.TopLevelParent.UpdateAccelerators() # Add panel accelerators


    def on_close_schema_page(self, event):
        """Handler for closing a schema object page."""
        page = self.notebook_schema.GetPage(event.GetSelection())
        if page.IsChanged():
            if wx.OK != wx.MessageBox(
                "There are unsaved changes, "
                "are you sure you want to discard them?",
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
            ): return event.Veto()

        for c, k, p in ((c, k, p) for c, m in self.schema_pages.items() for k, p in m.items()):
            if p is page:
                self.schema_pages[c].pop(k)
                break # for c, k, p
        self.TopLevelParent.UpdateAccelerators() # Remove panel accelerators
        self.update_page_header()


    def on_schema_page_event(self, event):
        """Handler for a message from SchemaObjectPage."""
        idx = self.notebook_schema.GetPageIndex(event.source)
        close, modified, updated = (getattr(event, x, None)
                                    for x in ("close", "modified", "updated"))
        category, name = (event.item.get(x) for x in ("type", "name"))
        if close:
            self.notebook_schema.DeletePage(idx)
        if (modified is not None or updated is not None) and event.source:
            if name:
                suffix = "*" if event.source.IsChanged() else ""
                title = "%s %s%s" % (category.capitalize(),
                                     grammar.quote(name), suffix)
                if self.notebook_schema.GetPageText(idx) != title:
                    self.notebook_schema.SetPageText(idx, title)
            if not self.save_underway: self.update_page_header()
        if updated:
            for k, p in self.schema_pages[category].items():
                if p is event.source:
                    self.schema_pages[category].pop(k)
                    self.schema_pages[category][name] = p
                    break # for k, p
        if updated and not self.save_underway:
            self.reload_schema(count=True, parse=True)
            self.on_update_statistics()
            if name not in self.db.schema[category] \
            and name in self.data_pages.get(category, {}):
                self.data_pages[category][name].Close(force=True)


    def on_change_sql_page(self, event):
        """Handler for SQL notebook tab change, adds new window if adder-tab."""
        if "+" == self.notebook_sql.GetPageText(self.notebook_sql.GetSelection()):
            self.notebook_sql.Freeze() # Avoid flicker from changing tab
            self.add_sql_page()
            wx.CallAfter(self.notebook_sql.Thaw)


    def on_dragdrop_sql_page(self, event):
        """Handler for dragging tabs in SQL window, moves adder-tab to end."""
        nb = self.notebook_sql
        if "+" != nb.GetPageText(nb.GetPageCount() - 1):
            i = next(i for i in range(nb.GetPageCount())
                     if "+" == nb.GetPageText(i))
            p = nb.GetPage(i)
            self._ignore_adder_close = True
            nb.RemovePage(i)
            delattr(self, "_ignore_adder_close")
            nb.AddPage(p, text="+")


    def on_close_sql_page(self, event):
        """Handler for closing an SQL page."""
        if "+" == self.notebook_sql.GetPageText(event.GetSelection()):
            if not getattr(self, "_ignore_adder_close", False): event.Veto()
            return
        self.notebook_sql.Freeze() # Avoid flicker when closing last
        page = self.notebook_sql.GetPage(event.GetSelection())

        for k, p in self.sql_pages.items():
            if p is page:
                self.sql_pages.pop(k)
                break # for k, p
        self.TopLevelParent.UpdateAccelerators() # Remove panel accelerators
        wx.CallAfter(self.notebook_sql.Thaw)


    def on_close_data_page(self, event):
        """Handler for closing data object page."""
        page = self.notebook_data.GetPage(event.GetSelection())
        if page.IsChanged():
            if wx.OK != wx.MessageBox(
                "There are unsaved changes, "
                "are you sure you want to discard them?",
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
            ): return event.Veto()

        for c, k, p in ((c, k, p) for c, m in self.data_pages.items() for k, p in m.items()):
            if p is page:
                self.data_pages[c].pop(k)
                break # for c, k, p
        self.TopLevelParent.UpdateAccelerators() # Remove panel accelerators
        self.update_page_header()


    def on_data_page_event(self, event):
        """Handler for a message from DataObjectPage."""
        idx = self.notebook_data.GetPageIndex(event.source)
        close, modified, updated = (getattr(event, x, None)
                                    for x in ("close", "modified", "updated"))
        category, name = (event.item.get(x) for x in ("type", "name"))
        if close:
            self.notebook_data.DeletePage(idx)
        if (modified is not None or updated is not None) and event.source:
            if name:
                suffix = "*" if event.source.IsChanged() else ""
                title = "%s %s%s" % (category.capitalize(),
                                     grammar.quote(name), suffix)
                if self.notebook_data.GetPageText(idx) != title:
                    self.notebook_data.SetPageText(idx, title)
            if not self.save_underway: self.update_page_header()
        if updated and not self.save_underway:
            self.db.populate_schema(count=True, category=category, name=name)
            self.load_tree_data()


    def on_export_data_file(self, category, items, event=None):
        """
        Handler for exporting one or more tables/views to file, opens file dialog
        and performs export.
        """
        WILDCARD, EXTS = export.TABLE_WILDCARD, export.TABLE_EXTS
        if "view" == category:
            WILDCARD, EXTS = export.QUERY_WILDCARD, export.QUERY_EXTS

        if len(items) == 1:
            filename = "%s %s" % (category.capitalize(), items[0])
            self.dialog_savefile.Filename = util.safe_filename(filename)
            self.dialog_savefile.Message = "Save %s as" % category
            self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
        else:
            self.dialog_savefile.Filename = "Filename will be ignored"
            self.dialog_savefile.Message = "Choose directory where to save files"
            self.dialog_savefile.WindowStyle ^= wx.FD_OVERWRITE_PROMPT
        self.dialog_savefile.Wildcard = WILDCARD
        if wx.ID_OK != self.dialog_savefile.ShowModal(): return

        wx.YieldIfNeeded() # Allow dialog to disappear
        extname = EXTS[self.dialog_savefile.FilterIndex]
        path = self.dialog_savefile.GetPath()
        filenames = [path]
        if len(items) > 1:
            path, _ = os.path.split(path)
            filenames, names_unique = [], []
            for t in items:
                name = base = util.safe_filename("%s %s" % (category.capitalize(),  t))
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

        for name, filename in zip(items, filenames):
            if not filename.lower().endswith(".%s" % extname):
                filename += ".%s" % extname
            busy = controls.BusyPanel(self, 'Exporting %s.' % filename)
            guibase.status('Exporting %s.', filename)
            try:
                sql = "SELECT * FROM %s" % grammar.quote(name)
                make_iterable = functools.partial(self.db.execute, sql)
                export.export_data(make_iterable, filename,
                    "%s %s" % (category.capitalize(), grammar.quote(name, force=True)),
                    self.db, self.db.get_category(category, name)["columns"],
                    category=category, name=name
                )
                guibase.status("Exported %s.", filename, log=True, flash=True)
                util.start_file(filename)
            except Exception as e:
                msg = "Error saving %s." % filename
                logger.exception(msg); guibase.status(msg, flash=True)
                error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
                wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
                break # for name, filename
            finally:
                busy.Close()


    def on_export_data_base(self, tables, data=True, event=None):
        """
        Handler for exporting one or more tables to another database,
        opens file dialog and performs direct copy.
        By default copies both structure and data.
        """
        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.FileDialog(
            parent=self, message="Select database to export tables to",
            defaultFile="", wildcard=wildcard,
            style=wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        wx.YieldIfNeeded() # Allow dialog to disappear
        filename2 = dialog.GetPath()

        try:
            self.db.execute("ATTACH DATABASE ? AS main2", [filename2])
        except Exception as e:
            msg = "Could not load database %s." % filename2
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            return wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)

        entrymsg = ('Name conflict on exporting table %(table)s as %(table2)s.\n'
                    'Database %(filename2)s %(entryheader)s '
                    'table named %(table2)s.\n\nYou can:\n'
                    '- keep same name to overwrite table %(table2)s,\n'
                    '- enter another name to export table %(table)s as,\n'
                    '- or set blank to skip table %(table)s.')
        insert_sql, success = "INSERT INTO main2.%s SELECT * FROM main.%s", False
        db1_tables = set(self.db.get_category("table"))
        try:
            db2_tables_lower = set(x["name"].lower() for x in self.db.execute(
                "SELECT name FROM main2.sqlite_master WHERE type = 'table' "
                "AND sql != '' AND name NOT LIKE 'sqlite_%'"
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
                        "table": grammar.quote(table), "table2": grammar.quote(table2),
                        "filename2": filename2,        "entryheader": entryheader
                    }, conf.Title, table2)
                    if wx.ID_OK != entrydialog.ShowModal(): return

                    value = entrydialog.GetValue().strip()
                    if not self.db.is_valid_name(table=value):
                        msg = "%s is not a valid table name." % grammar.quote(value, force=True)
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
                        else " as %s" % grammar.quote(table2, force=True)

                create_sql = self.db.get_sql("table", table,
                    transform={"renames": {"schema": "main2", "table": {table: table2}}},
                )
                try:
                    if t2_lower in db2_tables_lower:
                        logger.info("Dropping table %s in %s.", grammar.quote(table2), filename2)
                        self.db.execute("DROP TABLE main2.%s" % grammar.quote(table2))
                    logger.info("Creating table %s in %s, using %s.",
                                grammar.quote(table2, force=True), filename2, create_sql)
                    self.db.execute(create_sql)
                    if data: self.db.execute(insert_sql % (grammar.quote(table2),
                                             grammar.quote(table)))

                    # Copy table indexes and triggers
                    for category in "index", "trigger":

                        items = self.db.get_category(category, table=table).values()
                        items2 = [x["name"] for x in self.db.execute(
                            "SELECT name FROM main2.sqlite_master "
                            "WHERE type = ? AND sql != '' AND name NOT LIKE 'sqlite_%'", [category]
                        ).fetchall()]
                        for item in items:
                            name = base = item["name"]; counter = 2
                            if t1_lower != t2_lower:
                                name = base = re.sub(re.escape(table), re.sub(r"\W", "", table2),
                                                     name, count=1, flags=re.I | re.U)
                            while name in items2:
                                name, counter = "%s_%s" % (base, counter), counter + 1
                            items2.append(name)
                            item_sql, err = grammar.transform(item["sql"], renames={
                                category: name, "table": table2, "schema": "main2",
                            })
                            if err: raise Exception(err)
                            logger.info("Creating %s %s on table %s in %s, using %s.",
                                        category, grammar.quote(name, force=True),
                                        grammar.quote(table2, force=True),
                                        filename2, item_sql)
                            self.db.execute(item_sql)

                    guibase.status("Exported table %s to %s%s.",
                                   grammar.quote(table), filename2, extra, flash=True)
                    db2_tables_lower.add(t2_lower)
                except Exception as e:
                    msg = "Could not export table %s%s." % \
                          (grammar.quote(table), extra)
                    logger.exception(msg); guibase.status(msg, flash=True)
                    error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
                    wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
                    break # for table
            else: # nobreak
                success = True
        except Exception as e:
            msg = "Failed to read database %s." % filename2
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally:
            try: self.db.execute("DETACH DATABASE main2")
            except Exception: pass

        if success and tables1:
            same_name = (tables1[0].lower() == tables2_lower[0])
            t = "%s tables" % len(tables1) if len(tables1) > 1 \
                else "table %s" % grammar.quote(tables1[0], force=True)
            extra = "" if len(tables1) > 1 or same_name \
                    else " as %s" % grammar.quote(tables2[0], force=True)
            guibase.status("Exported %s to %s%s.", t, filename2, extra, flash=True)
            wx.PostEvent(self, OpenDatabaseEvent(-1, file=filename2))


    def load_data(self):
        """Loads data from our Database."""
        if self.db.temporary:
            self.label_title.Shown = self.edit_title.Shown = False
        else:
            self.label_title.Shown = self.edit_title.Shown = True
            self.edit_title.Value = self.db.name
        self.edit_title.ContainingSizer.Layout()

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
        wx.CallLater(100, self.update_tabheader)
        wx.CallLater(200, self.load_tree_data)
        wx.CallLater(500, self.update_info_panel, False)
        wx.CallLater(1000, self.reload_schema, count=True, parse=True)
        self.worker_analyzer.work(self.db.filename)


    def reload_schema(self, count=False, parse=False):
        """Reloads database schema and refreshes relevant controls"""
        self.db.populate_schema(count=count, parse=parse)
        self.load_tree_data()
        self.load_tree_schema()
        self.on_update_stc_schema()
        self.update_autocomp()


    def get_tree_state(self, tree, root):
        """
        Returns ({data, children: [{data, children}]} for expanded nodes,
                 {selected item data}).
        """
        item = tree.GetNext(root) if tree.IsExpanded(root) else None
        state, sel = {"data": tree.GetItemPyData(root)} if item else None, None
        while item and item.IsOk():
            if tree.IsExpanded(item):
                childstate, _ = self.get_tree_state(tree, item)
                state.setdefault("children", []).append(childstate)
            item = tree.GetNextSibling(item)
        if root == tree.RootItem:
            item = tree.GetSelection()
            sel = tree.GetItemPyData(item) if item and item.IsOk() else None
        return state, sel


    def set_tree_state(self, tree, root, state):
        """Sets tree expanded state."""
        state, sel = state
        if not state and not sel: return

        key_match = lambda x, y, k: x.get(k) and x[k] == y.get(k)
        has_match = lambda x, y: x == y or (
            key_match(y, x, "category") if "category" == y.get("type")
            else key_match(y, x, "type") and key_match(y, x, "name")
        )

        if state: tree.Expand(root)
        item = tree.GetNext(root)
        while item and item.IsOk():
            mydata = tree.GetItemPyData(item)
            if sel and has_match(sel, mydata):
                tree.SelectItem(item)
            mystate = next((x for x in state["children"] if has_match(x["data"], mydata)), None) \
                      if state and "children" in state else None
            if mystate: self.set_tree_state(tree, item, (mystate, sel))
            item = tree.GetNextSibling(item)


    def load_tree_data(self, refresh=False):
        """Loads table and view data into data tree."""
        tree = self.tree_data
        expandeds = self.get_tree_state(tree, tree.RootItem)
        tree.DeleteAllItems()
        tree.AddRoot("Loading data..")
        try:
            if refresh: self.db.populate_schema(count=True)
        except Exception:
            if not self: return
            msg = "Error loading data from %s." % self.db
            logger.exception(msg)
            return wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)

        tree.DeleteAllItems()
        root = tree.AddRoot("SQLITE")
        tree.SetItemPyData(root, {"type": "data"})

        tops = []
        for category in "table", "view":
            # Fill data tree with information on row counts and columns
            items = self.db.get_category(category).values()
            categorydata = {"type": "category", "category": category,
                            "items": [x["name"] for x in items]}

            t = util.plural(category).capitalize()
            if items: t += " (%s)" % len(items)
            top = tree.AppendItem(root, t)
            tree.SetItemPyData(top, categorydata)
            tops.append(top)
            for item in items:
                itemdata = dict(item, parent=categorydata)
                child = tree.AppendItem(top, util.unprint(item["name"]))
                tree.SetItemPyData(child, itemdata)

                if "count" in item:
                    t = "ERROR" if item["count"] is None else util.plural("row", item["count"])
                else: t = "" if "view" == category else "Counting.."
                tree.SetItemText(child, t, 1)

                for col in item["columns"]:
                    subchild = tree.AppendItem(child, util.unprint(col["name"]))
                    tree.SetItemText(subchild, col.get("type", ""), 1)
                    tree.SetItemPyData(subchild, dict(col, parent=item, type="column"))

        tree.Expand(root)
        for top in tops: tree.Expand(top)
        tree.SetColumnWidth(1, 100)
        tree.SetColumnWidth(0, tree.Size[0] - 130)
        self.set_tree_state(tree, tree.RootItem, expandeds)


    def load_tree_schema(self, refresh=False):
        """Loads database schema into schema tree."""
        tree = self.tree_schema
        expandeds = self.get_tree_state(tree, tree.RootItem)
        tree.DeleteAllItems()
        tree.AddRoot("Loading schema..")
        try:
            if refresh: self.db.populate_schema(parse=True)
        except Exception:
            if not self: return
            msg = "Error loading schema data from %s." % self.db
            logger.exception(msg)
            return wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)

        tree.DeleteAllItems()
        root = tree.AddRoot("SQLITE")
        tree.SetItemPyData(root, {"type": "schema"})
        imgs = self.tree_schema_images
        tops = []
        for category in database.Database.CATEGORIES:
            items = self.db.get_category(category).values()
            categorydata = {"type": "category", "category": category, "items": items}

            t = util.plural(category).capitalize()
            if items: t += " (%s)" % len(items)
            top = tree.AppendItem(root, t)
            tree.SetItemPyData(top, categorydata)
            tops.append(top)
            for item in items:
                itemdata = dict(item, parent=categorydata)
                child = tree.AppendItem(top, util.unprint(item["name"]))
                tree.SetItemPyData(child, itemdata)
                columns, subcategories, childtext = None, [], ""

                subcategories = ["table"]
                if "table" == category:
                    columns = item.get("columns") or []
                    subcategories = ["index", "trigger", "view"]
                elif "index" == category:
                    childtext = "ON " + grammar.quote(item["meta"]["table"])
                    columns = copy.deepcopy(item["meta"].get("columns") or [])
                    table = self.db.get_category("table", item["meta"]["table"])
                    for col in columns:
                        if table.get("columns") and col.get("name"):
                            tcol = next((x for x in table["columns"]
                                         if x["name"] == col["name"]), None)
                            if tcol: col["type"] = tcol.get("type", "")
                elif "trigger" == category:
                    childtext = " ".join(filter(bool, (item["meta"].get("upon"), item["meta"]["action"],
                                                       "ON", grammar.quote(item["meta"]["table"]))))
                elif "view" == category:
                    childtext = "ON " + ", ".join(grammar.quote(x)
                        for x in item["meta"].get("__tables__") or [])
                    columns = item.get("columns") or []

                tree.SetItemText(child, childtext, 1)

                if columns is not None:
                    colchild = tree.AppendItem(child, "Columns (%s)" % len(columns))
                    tree.SetItemPyData(colchild, {"type": "columns", "parent": itemdata})
                    tree.SetItemImage(colchild, imgs["columns"], wx.TreeItemIcon_Normal)
                    for col in columns:
                        subchild = tree.AppendItem(colchild, util.unprint(col["name"]))
                        tree.SetItemText(subchild, col.get("type", ""), 1)
                        tree.SetItemPyData(subchild, dict(col, parent=itemdata, type="column"))
                for subcategory in subcategories:
                    subitems = []
                    if "table" == category:
                         subitems = self.db.get_category(subcategory, table=item["name"]).values()
                    elif item["meta"].get("__tables__"):
                         subitems = filter(bool, (self.db.get_category(subcategory, x)
                                                  for x in item["meta"]["__tables__"]))

                    t = util.plural(subcategory).capitalize()
                    if subitems: t += " (%s)" % len(subitems)
                    categchild = tree.AppendItem(child, t)
                    subcategorydata = {"type": "category", "category": subcategory, "items": subitems, "parent": itemdata}
                    tree.SetItemPyData(categchild, subcategorydata)
                    if subcategory in imgs:
                        tree.SetItemImage(categchild, imgs[subcategory], wx.TreeItemIcon_Normal)

                    for subitem in subitems:
                        subchild = tree.AppendItem(categchild, util.unprint(subitem["name"]))
                        tree.SetItemPyData(subchild, dict(subitem, parent=itemdata))
                        t = ""
                        if "index" == subcategory:
                            t = ", ".join(x.get("name", x.get("expr")) for x in subitem["meta"]["columns"])
                        elif "trigger" == subcategory:
                            t = " ".join(filter(bool, (subitem["meta"].get("upon"), subitem["meta"]["action"])))
                        tree.SetItemText(subchild, t, 1)

            tree.Collapse(top)
        tree.SetColumnWidth(0, tree.Size[0] - 180)
        tree.SetColumnWidth(1, 150)
        tree.Expand(root)
        for top in tops: tree.Expand(top)
        self.set_tree_state(tree, tree.RootItem, expandeds)


    def update_autocomp(self):
        """Add PRAGMAS, and table/view/column names to SQL autocomplete."""
        words = list(database.Database.PRAGMA) + database.Database.EXTRA_PRAGMAS
        subwords = {}

        for category in ("table", "view"):
            for item in self.db.get_category(category).values():
                myname = grammar.quote(item["name"])
                words.append(myname)
                if not item.get("columns"): continue # for item
                subwords[myname] = [grammar.quote(c["name"]) for c in item["columns"]]
        for p in self.sql_pages.values(): p.SetAutoComp(words, subwords)


    def update_tabheader(self):
        """Updates page tab header with option to close page."""
        if not self: return
        self.ready_to_close = True
        wx.PostEvent(self, DatabasePageEvent(-1, source=self, ready=True))



class SQLiteGridBase(wx.grid.PyGridTableBase):
    """
    Table base for wx.grid.Grid, can take its data from a single table/view, or from
    the results of any SELECT query.
    """

    """How many rows to seek ahead for query grids."""
    SEEK_CHUNK_LENGTH = 100


    def __init__(self, db, category="", name="", sql=""):
        super(SQLiteGridBase, self).__init__()
        self.is_query = bool(sql)
        self.db = db
        self.sql = sql
        self.category = category
        self.name = name
        self.id_counter = 0
        # ID here is a unique value identifying rows in this object,
        # no relation to table data
        self.idx_all = []      # An ordered list of row identifiers in rows_all
        self.rows_all = {}     # Unfiltered, unsorted rows {id: row, }
        self.rows_current = [] # Currently shown (filtered/sorted) rows
        self.rowids = {} # SQLite table rowids, used for UPDATE and DELETE
        self.idx_changed = set() # set of indexes for changed rows in rows_all
        self.rows_backup = {}    # For changed rows {id: original_row, }
        self.idx_new = []        # Unsaved added row indexes
        self.rows_deleted = {}   # Uncommitted deleted rows {id: deleted_row, }
        self.rowid_name = None
        self.row_count = 0
        self.iterator_index = -1
        self.sort_ascending = True
        self.sort_column = None # Index of column currently sorted by
        self.filters = {} # {col index: value, }
        self.attrs = {} # {"new": wx.grid.GridCellAttr, }

        if not self.is_query:
            if "table" == category and db.has_rowid(name): self.rowid_name = "rowid"
            cols = ("%s, *" % self.rowid_name) if self.rowid_name else "*"
            self.sql = "SELECT %s FROM %s" % (cols, grammar.quote(name))
        self.row_iterator = self.db.execute(self.sql)
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
                    col["type"] = TYPES.get(type(value), col.get("type", ""))
        else:
            self.columns = self.db.get_category(category, name)["columns"]
            try:
                res = self.db.execute("SELECT COUNT(*) AS count FROM %s"
                                      % grammar.quote(self.name)).fetchone()
                self.row_count = res["count"]
            except Exception:
                logger.exception("Error getting row count for %s in %s",
                                 grammar.quote(name), db)
                self.SeekAhead(to_end=True)
                self.row_count = self.iterator_index + 1
                self.NotifyViewChange(0)


    def GetColLabelValue(self, col):
        label = self.columns[col]["name"]
        if col == self.sort_column:
            label += u" ↓" if self.sort_ascending else u" ↑"
        if col in self.filters:

            if self.db.get_affinity(self.columns[col]) in ("INTEGER", "REAL"):
                label += "\n= %s" % self.filters[col]
            else:
                label += '\nlike "%s"' % self.filters[col]
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
                idx = self._make_id(rowdata)
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
        if value and "BLOB" == self.columns[col].get("type") and isinstance(value, basestring):
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
        Returns an iterator producing all current grid rows if query grid,
        or a cursor producing all rows from database if category grid,
        both in current sort order and matching current filter.
        """
        if self.is_query:
            self.SeekAhead(True)
            return iter(self.rows_current)

        sql, args = "SELECT * FROM %s" % grammar.quote(self.name), {}

        where, order = "", ""
        if self.filters:
            col_data, col_vals = [], {}
            for i, v in self.filters.items():
                col_data.append(self.columns[i])
                col_vals[self.columns[i]["name"]] = v
            args = self.db.make_args(col_data, col_vals)

            for col, key in zip(col_data, args):
                op = "="
                if self.db.get_affinity(col) not in ("INTEGER", "REAL"):
                    op, args[key] = "LIKE", "%" + args[key] + "%"
                part = "%s %s :%s" % (grammar.quote(col["name"]), op, key)
                where += (" AND " if where else "WHERE ") + part
        if self.sort_column is not None: order = "ORDER BY %s%s" % (
            grammar.quote(self.columns[self.sort_column]["name"]),
            "" if self.sort_ascending else " DESC"
        )
        if where: sql += " " + where
        if order: sql += " " + order

        return self.db.execute(sql, args)


    def SetValue(self, row, col, val):
        if self.is_query or "view" == self.category or row >= self.row_count:
            return

        accepted = False
        col_value = None
        if self.db.get_affinity(self.columns[col]) in ("INTEGER", "REAL"):
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
        elif "BLOB" == self.columns[col].get("type"):
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
        return any(map(len, [self.idx_changed, self.idx_new, self.rows_deleted]))


    def GetChanges(self):
        """
        Returns {?"new": [{row}], ?"changed": [], ?"deleted": []},
        usable for SetChanges().
        """
        result = {}
        if self.idx_new:
            result["new"] = [self.rows_all[x] for x in self.idx_new]
        if self.idx_changed:
            result["changed"] = [self.rows_all[x] for x in self.idx_changed]
        if self.rows_deleted:
            result["deleted"] = self.rows_deleted.values()
        return copy.deepcopy(result)


    def SetChanges(self, changes):
        """Applies changes to grid, as returned from GetChanges()."""
        if not changes: return
        rows_before = rows_after = self.row_count
        self.SeekToRow(self.row_count)

        if changes.get("changed"):
            self.idx_changed = set(x["__id__"] for x in changes["changed"])
            for row in changes["changed"]:
                myid = row["__id__"]
                if myid in self.rows_all:
                    self.rows_backup[myid] = copy.deepcopy(self.rows_all[myid])
                    self.rows_all[myid].update(row)

        if changes.get("deleted"):
            rowmap = {x["__id__"]: x for x in changes["deleted"]}
            idxs = {r["__id__"]: i for i, r in enumerate(self.rows_current)
                    if r["__id__"] in rowmap}
            for idx in sorted(idxs.values(), reverse=True):
                del self.rows_current[idx]
            self.rows_deleted = {x: rowmap[x] for x in idxs}
            rows_after -= len(idxs)

        if changes.get("new"):
            for row in reversed(changes["new"]):
                idx = row["__id__"]
                self.idx_all.insert(0, idx)
                self.rows_current.insert(0, row)
                self.rows_all[idx] = row
                self.idx_new.append(idx)
            rows_after += len(changes["new"])

        self.row_count = rows_after
        self.NotifyViewChange(rows_before)


    def GetFilterSort(self):
        """
        Returns current filter and sort state,
        as {?"sort": {col index: direction}, ?"filter": {col index: value}}.
        """
        result = {}
        if self.sort_column: result["sort"]   = {self.sort_column: self.sort_ascending}
        if self.filters:     result["filter"] = dict(self.filters)
        return result


    def SetFilterSort(self, state):
        """
        Sets current filter and sort state, as returned from GetFilterSort().
        as {?"sort": {col index: direction}, ?"filter": {col index: value}}.
        """
        if not state: return
        if "sort" in state:
            self.sort_column, self.sort_ascending = state["sort"].items()[0]
        if "filter" in state:
            self.filters = state["filter"]
        self.Filter()


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

        blob = "blob" if (self.columns[col].get("type", "").lower() == "blob") else ""
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
        for _ in range(numRows):
            # Construct empty dict from column names
            rowdata = dict((col["name"], None) for col in self.columns)
            idx = self._make_id(rowdata)
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
            for _ in range(numRows):
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
        if self.db.get_affinity(self.columns[col]) in ("INTEGER", "REAL"):
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
        if col not in self.filters: return
        self.filters.pop(col)
        self.Filter()


    def ClearFilter(self, refresh=True):
        """Clears all added filters."""
        self.filters.clear()
        if refresh: self.Filter()


    def ClearSort(self, refresh=True):
        """Clears current sort."""
        self.sort_column = None
        if not refresh: return
        self.rows_current.sort(key=lambda x: self.idx_all.index(x["__id__"]))
        if self.View: self.View.ForceRefresh()


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
        def compare(a, b):
            aval, bval = a[col_name], b[col_name]
            aval = aval.lower() if hasattr(aval, "lower") else aval
            bval = bval.lower() if hasattr(bval, "lower") else bval
            return cmp(aval, bval)

        self.SeekToRow(self.row_count - 1)
        self.sort_ascending = not self.sort_ascending
        self.sort_column = col
        mycmp = cmp
        if 0 <= col < len(self.columns):
            col_name, mycmp = self.columns[col]["name"], compare
        self.rows_current.sort(cmp=mycmp, reverse=not self.sort_ascending)
        if self.View: self.View.ForceRefresh()


    def SaveChanges(self):
        """
        Saves the rows that have been changed in this table. Drops undo-cache.
        Returns success.
        """
        result = False
        try:
            for idx in self.idx_changed.copy():
                row = self.rows_all[idx]
                self.db.update_row(self.name, row, self.rows_backup[idx],
                                   self.rowids.get(idx))
                row["__changed__"] = False
                self.idx_changed.remove(idx)
                del self.rows_backup[idx]
            # Save all newly inserted rows
            pks = [c["name"] for c in self.columns if "pk" in c]
            col_map = dict((c["name"], c) for c in self.columns)
            for idx in self.idx_new[:]:
                row = self.rows_all[idx]
                insert_id = self.db.insert_row(self.name, row)
                if len(pks) == 1 and row[pks[0]] in (None, ""):
                    if "INTEGER" == self.db.get_affinity(col_map[pks[0]]):
                        # Autoincremented row: update with new value
                        row[pks[0]] = insert_id
                    elif insert_id: # For non-integers, insert returns ROWID
                        self.rowids[idx] = insert_id
                row["__new__"] = False
                self.idx_new.remove(idx)
            # Delete all newly deleted rows
            for idx, row in self.rows_deleted.copy().items():
                self.db.delete_row(self.name, row, self.rowids.get(idx))
                del self.rows_deleted[idx]
                del self.rows_all[idx]
                self.idx_all.remove(idx)
            result = True
        except Exception as e:
            msg = "Error saving changes in %s." % grammar.quote(self.name)
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        if self.View: self.View.Refresh()
        return result


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
            value = rowdata[column_data["name"]]
            if self.db.get_affinity(column_data) in ("INTEGER", "REAL"):
                is_unfiltered &= (filter_value == value)
            else:
                if not isinstance(value, basestring):
                    value = "" if value is None else str(value)
                is_unfiltered &= filter_value.lower() in value.lower()
        return not is_unfiltered


    def _make_id(self, row):
        """Returns unique identifier for row."""
        self.id_counter += 1
        return self.id_counter
        



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



class SQLPage(wx.PyPanel):
    """
    Component for running SQL queries and seeing results in a grid.
    """

    def __init__(self, parent, db, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize):
        """
        @param   page  target to send EVT_SCHEMA_PAGE events to
        """
        wx.PyPanel.__init__(self, parent, pos=pos, size=size)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(self, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)

        self._db       = db
        self._hovered_cell  = None # (row, col)

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)

        splitter = wx.SplitterWindow(parent=self, style=wx.BORDER_NONE)
        splitter.SetMinimumPaneSize(100)

        panel1 = wx.Panel(parent=splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)

        tb = self._tb = wx.ToolBar(panel1, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = wx.ArtProvider.GetBitmap(wx.ART_COPY,      wx.ART_TOOLBAR, (16, 16))
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, (16, 16))
        bmp3 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR, (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_COPY, "", bitmap=bmp1, shortHelp="Copy SQL to clipboard")
        tb.AddLabelTool(wx.ID_OPEN, "", bitmap=bmp2, shortHelp="Load SQL from file")
        tb.AddLabelTool(wx.ID_SAVE, "", bitmap=bmp3, shortHelp="Save SQL to file")
        tb.Realize()

        stc = self._stc = controls.SQLiteTextCtrl(panel1,
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)

        panel2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        label_help_stc = wx.StaticText(panel2, label=
            "Alt-Enter/Ctrl-Enter runs the query contained in currently selected "
            "text or on the current line. Ctrl-Space shows autocompletion list.")
        ColourManager.Manage(label_help_stc, "ForegroundColour", "DisabledColour")
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_sql    = wx.Button(panel2, label="Execute S&QL")
        button_script = wx.Button(panel2, label="Execute scrip&t")
        button_reset  = self._button_reset  = wx.Button(panel2, label="&Reset filter/sort")
        button_export = self._button_export = wx.Button(panel2, label="&Export to file")
        button_close  = self._button_close  = wx.Button(panel2, label="&Close query")

        button_sql.ToolTipString    = "Execute a single statement from the SQL window"
        button_script.ToolTipString = "Execute multiple SQL statements, separated by semicolons"
        button_reset.ToolTipString  = "Resets all applied sorting and filtering"
        button_export.ToolTipString = "Export result to a file"
        button_close.ToolTipString  = "Close data grid"

        button_reset.Enabled = button_export.Enabled = button_close.Enabled = False

        grid = self._grid = wx.grid.Grid(parent=panel2)
        ColourManager.Manage(grid, "DefaultCellBackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(grid, "DefaultCellTextColour",       wx.SYS_COLOUR_WINDOWTEXT)
        ColourManager.Manage(grid, "LabelBackgroundColour",       wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(grid, "LabelTextColour",             wx.SYS_COLOUR_WINDOWTEXT)

        label_help = self._label_help = wx.StaticText(panel2,
            label="Double-click on column header to sort, right click to filter.")
        ColourManager.Manage(label_help, "ForegroundColour", "DisabledColour")

        self.Bind(wx.EVT_TOOL,     self._OnCopySQL,       id=wx.ID_COPY)
        self.Bind(wx.EVT_TOOL,     self._OnLoadSQL,       id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL,     self._OnSaveSQL,       id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON,   self._OnExecuteSQL,    button_sql)
        self.Bind(wx.EVT_BUTTON,   self._OnExecuteScript, button_script)
        self.Bind(wx.EVT_BUTTON,   self._OnResetView,     button_reset)
        self.Bind(wx.EVT_BUTTON,   self._OnExport,        button_export)
        self.Bind(wx.EVT_BUTTON,   self._OnGridClose,     button_close)
        stc.Bind(wx.EVT_KEY_DOWN,                         self._OnSTCKey)
        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK,     self._OnSort)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK,     self._OnFilter)
        grid.Bind(wx.EVT_SCROLLWIN,                       self._OnGridScroll)
        grid.Bind(wx.EVT_SCROLL_THUMBRELEASE,             self._OnGridScroll)
        grid.Bind(wx.EVT_SCROLL_CHANGED,                  self._OnGridScroll)
        grid.Bind(wx.EVT_KEY_DOWN,                        self._OnGridScroll)
        grid.GridWindow.Bind(wx.EVT_MOTION,               self._OnGridMouse)
        grid.GridWindow.Bind(wx.EVT_CHAR_HOOK,            self._OnGridKey)

        sizer_header.Add(tb)
        sizer1.Add(sizer_header, border=5, flag=wx.TOP | wx.BOTTOM)
        sizer1.Add(stc, proportion=1, flag=wx.GROW)

        sizer_buttons.Add(button_sql, flag=wx.ALIGN_LEFT)
        sizer_buttons.Add(button_script, border=5, flag=wx.LEFT | wx.ALIGN_LEFT)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_reset, border=5, flag=wx.ALIGN_RIGHT | wx.RIGHT)
        sizer_buttons.Add(button_export, border=5, flag=wx.RIGHT | wx.ALIGN_RIGHT)
        sizer_buttons.Add(button_close, flag=wx.ALIGN_RIGHT)

        sizer2.Add(label_help_stc, border=5, flag=wx.BOTTOM | wx.GROW)
        sizer2.Add(sizer_buttons, border=5, flag=wx.RIGHT | wx.BOTTOM | wx.GROW)
        sizer2.Add(grid, proportion=1, flag=wx.GROW)
        sizer2.Add(label_help, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        label_help.Hide()
        self.Layout()
        wx.CallAfter(lambda: splitter.SplitHorizontally(panel1, panel2, sashPosition=self.Size[1] * 2/5))


    def GetText(self):
        """Returns the current contents of the SQL window."""
        return self._stc.Text


    def SetText(self, text):
        """Sets the contents of the SQL window."""
        self._stc.SetText(text)
        self._stc.EmptyUndoBuffer() # So that undo does not clear the STC


    def SetAutoComp(self, words=[], subwords={}):
        """Sets additional words to use in STC autocompletion."""
        self._stc.AutoCompClearAdded()
        self._stc.AutoCompAddWords(words)
        for word, subwords in subwords.items():
            self._stc.AutoCompAddSubWords(word, subwords)


    def ExecuteSQL(self, sql):
        """Executes the SQL query and populates the SQL grid with results."""
        try:
            grid_data = None
            if sql.lower().startswith(("select", "pragma", "explain")):
                # SELECT statement: populate grid with rows
                grid_data = SQLiteGridBase(self._db, sql=sql)
                self._grid.Table = grid_data
                self._button_reset.Enabled = True
                self._button_export.Enabled = True
            else:
                # Assume action query
                affected_rows = self._db.execute_action(sql)
                self._grid.Table = None
                self._grid.CreateGrid(1, 1)
                self._grid.SetColLabelValue(0, "Affected rows")
                self._grid.SetCellValue(0, 0, str(affected_rows))
                self._button_reset.Enabled = False
                self._button_export.Enabled = False
            self._button_close.Enabled = True
            self._label_help.Show()
            self._label_help.ContainingSizer.Layout()
            guibase.status('Executed SQL "%s" (%s).', sql, self._db,
                           log=True, flash=True)
            size = self._grid.Size
            self._grid.Fit()
            # Jiggle size by 1 pixel to refresh scrollbars
            self._grid.Size = size[0], size[1]-1
            self._grid.Size = size[0], size[1]
            self.last_sql = sql
            self._grid.SetColMinimalAcceptableWidth(100)
            if grid_data:
                col_range = range(grid_data.GetNumberCols())
                [self._grid.AutoSizeColLabelSize(x) for x in col_range]
        except Exception as e:
            logger.exception("Error running SQL %s.", sql)
            guibase.status("Error running SQL.", flash=True)
            error = "Error running SQL:\n\n%s" % util.format_exc(e)
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def Reload(self):
        """Reloads current data grid, if any."""
        if not self._grid.Table: return
        if not isinstance(self._grid.Table, SQLiteGridBase): # Action query
            self._OnGridClose()
            return

        scrollpos = map(self._grid.GetScrollPos, [wx.HORIZONTAL, wx.VERTICAL])
        cursorpos = [self._grid.GridCursorRow, self._grid.GridCursorCol]
        self._grid.Freeze()
        grid_data = SQLiteGridBase(self._db, sql=self._grid.Table.sql)
        self._grid.Table = None # Reset grid data to empty
        self._grid.Table = grid_data
        self._grid.Scroll(*scrollpos)
        maxpos = self._grid.GetNumberRows() - 1, self._grid.GetNumberCols() - 1
        cursorpos = [min(x) for x in zip(cursorpos, maxpos)]
        self._grid.SetGridCursor(*cursorpos)
        self._grid.Thaw()


    def _OnExport(self, event=None):
        """
        Handler for clicking to export grid contents to file, allows the
        user to select filename and type and creates the file.
        """
        if not self._grid.Table: return

        self._grid.Table.SeekAhead(True)

        title = "SQL query"
        dialog = wx.FileDialog(self, defaultDir=os.getcwd(),
            message="Save query as",
            defaultFile=util.safe_filename(title),
            wildcard=export.QUERY_WILDCARD,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        extname = export.QUERY_EXTS[dialog.FilterIndex]
        if not filename.lower().endswith(".%s" % extname):
            filename += ".%s" % extname
        busy = controls.BusyPanel(self, 'Exporting "%s".' % filename)
        guibase.status('Exporting "%s".', filename)
        try:
            make_iterable = self._grid.Table.GetRowIterator
            export.export_data(make_iterable, filename, title, self._db,
                               self._grid.Table.columns,
                               sql_query=self._grid.Table.sql)
            guibase.status('Exported "%s".', filename, log=True, flash=True)
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving %s."
            logger.exception(msg, filename)
            guibase.status(msg, flash=True)
            error = "Error saving %s:\n\n%s" % (filename, util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally:
            busy.Close()


    def _OnFilter(self, event):
        """
        Handler for right-clicking a table grid column, lets the user
        change the column filter.
        """
        row, col = event.GetRow(), event.GetCol()
        # Remember scroll positions, as grid update loses them
        if row >= 0: return # Only react to clicks in the header

        grid_data = self._grid.Table
        current_filter = unicode(grid_data.filters[col]) \
                         if col in grid_data.filters else ""
        name = grammar.quote(grid_data.columns[col]["name"], force=True)
        dialog = wx.TextEntryDialog(self,
            "Filter column %s by:" % name, "Filter", defaultValue=current_filter,
            style=wx.OK | wx.CANCEL)
        if wx.ID_OK != dialog.ShowModal(): return

        new_filter = dialog.GetValue()
        if len(new_filter):
            busy = controls.BusyPanel(self,
                'Filtering column %s by "%s".' %
                (name, new_filter))
            grid_data.AddFilter(col, new_filter)
            busy.Close()
        else:
            grid_data.RemoveFilter(col)
        self.Layout() # React to grid size change


    def _OnSort(self, event):
        """
        Handler for clicking a table grid column, sorts table by the column.
        """
        row, col = event.GetRow(), event.GetCol()
        # Remember scroll positions, as grid update loses them
        scroll_hor = self._grid.GetScrollPos(wx.HORIZONTAL)
        scroll_ver = self._grid.GetScrollPos(wx.VERTICAL)
        if row < 0: # Only react to clicks in the header
            self._grid.Table.SortColumn(col)
        self.Layout() # React to grid size change
        self._grid.Scroll(scroll_hor, scroll_ver)


    def _OnResetView(self, event):
        """
        Handler for clicking to remove sorting and filtering,
        resets the grid and its view.
        """
        self._grid.Table.ClearFilter()
        self._grid.Table.ClearSort()
        self.Layout() # React to grid size change


    def _OnGridScroll(self, event):
        """
        Handler for scrolling the grid, seeks ahead if nearing the end of
        retrieved rows.
        """
        SEEKAHEAD_POS_RATIO = 0.8
        event.Skip()

        def seekahead():
            scrollpos = self._grid.GetScrollPos(wx.VERTICAL)
            scrollrange = self._grid.GetScrollRange(wx.VERTICAL)
            if scrollpos > scrollrange * SEEKAHEAD_POS_RATIO:
                scrollpage = self._grid.GetScrollPageSize(wx.VERTICAL)
                to_end = (scrollpos + scrollpage == scrollrange)
                # Seek to end if scrolled to the very bottom
                self._grid.Table.SeekAhead(to_end)

        wx.CallLater(50, seekahead) # Give scroll position time to update


    def _OnGridKey(self, event):
        """Handler for grid keypress, copies selection to clipboard on Ctrl-C."""
        if not event.ControlDown() or ord('C') != event.KeyCode:
            return event.Skip()

        rows, cols = [], []
        if self._grid.GetSelectedCols():
            cols += sorted(self._grid.GetSelectedCols())
            rows += range(self._grid.GetNumberRows())
        if self._grid.GetSelectedRows():
            rows += sorted(self._grid.GetSelectedRows())
            cols += range(self._grid.GetNumberCols())
        if self._grid.GetSelectionBlockTopLeft():
            end = self._grid.GetSelectionBlockBottomRight()
            for i, (r, c) in enumerate(self._grid.GetSelectionBlockTopLeft()):
                r2, c2 = end[i]
                rows += range(r, r2 + 1)
                cols += range(c, c2 + 1)
        if self._grid.GetSelectedCells():
            rows += [r for r, c in self._grid.GetSelectedCells()]
            cols += [c for r, c in self._grid.GetSelectedCells()]
        if not rows and not cols:
            if self._grid.GetGridCursorRow() >= 0 and self._grid.GetGridCursorCol() >= 0:
                rows, cols = [self._grid.GetGridCursorRow()], [self._grid.GetGridCursorCol()]
        rows, cols = (sorted(set(y for y in x if y >= 0)) for x in (rows, cols))
        if not rows or not cols: return

        if wx.TheClipboard.Open():
            data = [[self._grid.GetCellValue(r, c) for c in cols] for r in rows]
            text = "\n".join("\t".join(c for c in r) for r in data)
            d = wx.TextDataObject(text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()


    def _OnGridMouse(self, event):
        """
        Handler for moving the mouse over a grid, shows datetime tooltip for
        UNIX timestamp cells.
        """
        tip = ""
        prev_cell = self._hovered_cell
        x, y = self._grid.CalcUnscrolledPosition(event.X, event.Y)
        row, col = self._grid.XYToCell(x, y)
        if row >= 0 and col >= 0:
            value = self._grid.Table.GetValue(row, col)
            col_name = self._grid.Table.GetColLabelValue(col).lower()
            if type(value) is int and value > 100000000 \
            and ("time" in col_name or "date" in col_name):
                try:
                    tip = datetime.datetime.fromtimestamp(value).strftime(
                          "%Y-%m-%d %H:%M:%S")
                except Exception:
                    tip = unicode(value)
            else:
                tip = unicode(value)
            tip = tip if len(tip) < 1000 else tip[:1000] + ".."
        if (row, col) != prev_cell or not (event.EventObject.ToolTip) \
        or event.EventObject.ToolTip.Tip != tip:
            event.EventObject.SetToolTipString(tip)
        self._hovered_cell = (row, col)


    def _OnSTCKey(self, event):
        """
        Handler for pressing a key in STC, listens for Alt-Enter and
        executes the currently selected line, or currently active line.
        """
        event.Skip() # Allow to propagate to other handlers
        stc = event.GetEventObject()
        if (event.AltDown() or event.ControlDown()) and wx.WXK_RETURN == event.KeyCode:
            sql = (stc.SelectedText or stc.CurLine[0]).strip()
            if sql: self.ExecuteSQL(sql)


    def _OnExecuteSQL(self, event=None):
        """
        Handler for clicking to run an SQL query, runs the selected text or
        whole contents, displays its results, if any, and commits changes
        done, if any.
        """
        sql = (self._stc.SelectedText or self._stc.Text).strip()
        if sql: self.ExecuteSQL(sql)


    def _OnExecuteScript(self, event=None):
        """
        Handler for clicking to run multiple SQL statements, runs the selected
        text or whole contents as an SQL script.
        """
        sql = (self._stc.SelectedText or self._stc.Text).strip()
        if not sql: return
            
        try:
            logger.info('Executing SQL script "%s".', sql)
            self._db.connection.executescript(sql)
            self._grid.SetTable(None)
            self._grid.CreateGrid(1, 1)
            self._grid.SetColLabelValue(0, "Affected rows")
            self._grid.SetCellValue(0, 0, "-1")
            self._button_reset.Enabled = False
            self._button_export.Enabled = False
            self._label_help.Show()
            self._label_help.ContainingSizer.Layout()
            size = self._grid.Size
            self._grid.Fit()
            # Jiggle size by 1 pixel to refresh scrollbars
            self._grid.Size = size[0], size[1]-1
            self._grid.Size = size[0], size[1]
        except Exception as e:
            msg = "Error running SQL script."
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def _OnGridClose(self, event=None):
        """Handler for clicking to close the results grid."""
        self._grid.Table = None
        self.Refresh()
        self._button_export.Enabled = False
        self._button_reset.Enabled = False
        self._button_close.Enabled = False
        self._label_help.Hide()
        self._label_help.ContainingSizer.Layout()


    def _OnCopySQL(self, event):
        """Handler for copying SQL to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(self._stc.Text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied SQL to clipboard", flash=True)


    def _OnLoadSQL(self, event):
        """
        Handler for loading SQL from file, opens file dialog and loads content.
        """
        dialog = wx.FileDialog(
            self, message="Open", defaultFile="",
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_FILE_MUST_EXIST | wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            self._stc.LoadFile(filename)
        except Exception as e:
            msg = "Error loading SQL from %s." % filename
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def _OnSaveSQL(self, event):
        """
        Handler for saving SQL to file, opens file dialog and saves content.
        """
        filename = "%s SQL" % os.path.splitext(os.path.basename(self._db.name))[0]
        dialog = wx.FileDialog(
            self, message="Save as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        try:
            content = step.Template(templates.CREATE_SQL, strip=False).expand(
                title="SQL window.", db_filename=self._db.name, sql=self._stc.Text)
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving SQL to %s." % filename
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)



DataPageEvent, EVT_DATA_PAGE = wx.lib.newevent.NewCommandEvent()

class DataObjectPage(wx.PyPanel):
    """
    Component for viewing and editing data objects like tables and views.
    """

    def __init__(self, parent, db, item, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize):
        wx.PyPanel.__init__(self, parent, pos=pos, size=size)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(self, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)

        self._db       = db
        self._category = item["type"]
        self._item     = copy.deepcopy(item)
        self._backup   = None # Pending changes for Reload(pending=True)
        self._ignore_change = False
        self._hovered_cell  = None # (row, col)

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_header       = wx.BoxSizer(wx.HORIZONTAL)

        tb = self._tb = wx.ToolBar(self, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = images.ToolbarInsert.Bitmap
        bmp2 = images.ToolbarDelete.Bitmap
        bmp3 = images.ToolbarRefresh.Bitmap
        bmp4 = images.ToolbarCommit.Bitmap
        bmp5 = images.ToolbarRollback.Bitmap
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_ADD,     "", bitmap=bmp1, shortHelp="Add new row")
        tb.AddLabelTool(wx.ID_DELETE,  "", bitmap=bmp2, shortHelp="Delete current row")
        tb.AddSeparator()
        tb.AddLabelTool(wx.ID_REFRESH, "", bitmap=bmp3, shortHelp="Reload data")
        tb.AddSeparator()
        tb.AddLabelTool(wx.ID_SAVE,    "", bitmap=bmp4, shortHelp="Commit changes to database")
        tb.AddLabelTool(wx.ID_UNDO,    "", bitmap=bmp5, shortHelp="Rollback changes and restore original values")
        tb.EnableTool(wx.ID_UNDO, False)
        tb.EnableTool(wx.ID_SAVE, False)
        if "view" == self._category:
            tb.EnableTool(wx.ID_ADD, False)
            tb.EnableTool(wx.ID_DELETE, False)
        tb.Realize()

        button_reset  = wx.Button(self, label="&Reset filter/sort")
        button_export = wx.Button(self, label="&Export to file")
        button_reset.ToolTipString  = "Reset all applied sorting and filtering"
        button_export.ToolTipString = "Export rows to a file"

        grid = self._grid = wx.grid.Grid(self)
        grid.ToolTipString = "Double click on column header to sort, right click to filter."
        ColourManager.Manage(grid, "DefaultCellBackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(grid, "DefaultCellTextColour",       wx.SYS_COLOUR_WINDOWTEXT)
        ColourManager.Manage(grid, "LabelBackgroundColour",       wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(grid, "LabelTextColour",             wx.SYS_COLOUR_WINDOWTEXT)

        label_help = wx.StaticText(self, label="Double-click on column header to sort, right click to filter.")
        ColourManager.Manage(label_help, "ForegroundColour", "DisabledColour")

        self.Bind(wx.EVT_TOOL,   self._OnInsert,    id=wx.ID_ADD)
        self.Bind(wx.EVT_TOOL,   self._OnDelete,    id=wx.ID_DELETE)
        self.Bind(wx.EVT_TOOL,   self._OnRefresh,   id=wx.ID_REFRESH)
        self.Bind(wx.EVT_TOOL,   self._OnCommit,    id=wx.ID_SAVE)
        self.Bind(wx.EVT_TOOL,   self._OnRollback,  id=wx.ID_UNDO)
        self.Bind(wx.EVT_BUTTON, self._OnResetView, button_reset)
        self.Bind(wx.EVT_BUTTON, self._OnExport,    button_export)
        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK, self._OnSort)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK, self._OnFilter)
        grid.Bind(wx.grid.EVT_GRID_CELL_CHANGE,       self._OnChange)
        grid.GridWindow.Bind(wx.EVT_MOTION,           self._OnGridMouse)
        grid.GridWindow.Bind(wx.EVT_CHAR_HOOK,        self._OnGridKey)

        sizer_header.Add(tb)
        sizer_header.AddStretchSpacer()
        sizer_header.Add(button_reset, border=5, flag=wx.RIGHT)
        sizer_header.Add(button_export)

        sizer.Add(sizer_header, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)
        sizer.Add(grid, proportion=1, flag=wx.GROW)
        sizer.Add(label_help, border=5, flag=wx.TOP | wx.BOTTOM)
        self._Populate()
        self._grid.SetFocus()


    def GetName(self):
        return self._item["name"]
    Name = property(GetName)


    def Close(self, force=False):
        """Closes the page, asking for confirmation if modified and not force."""
        if force: self._ignore_change = True
        self._OnClose()


    def IsChanged(self):
        """Returns whether there are unsaved changes."""
        return not self._ignore_change and self._grid.Table.IsChanged()


    def ScrollToRow(self, row):
        """Scrolls to row matching given row dict."""
        columns = self._item["columns"]
        id_fields = [c["name"] for c in columns if "pk" in c]
        if not id_fields: # No primary key fields: take all
            id_fields = [c["name"] for c in columns]
        row_id = [row[c] for c in id_fields]
        for i in range(self._grid.Table.GetNumberRows()):
            row2 = self._grid.Table.GetRow(i)
            if not row2: break # for i                

            row2_id = [row2[c] for c in id_fields]
            if row_id == row2_id:
                self._grid.MakeCellVisible(i, 0)
                self._grid.SelectRow(i)
                pagesize = self._grid.GetScrollPageSize(wx.VERTICAL)
                pxls = self._grid.GetScrollPixelsPerUnit()
                cell_coords = self._grid.CellToRect(i, 0)
                y = cell_coords.y / (pxls[1] or 15)
                x, y = 0, y - pagesize / 2
                self._grid.Scroll(x, y)
                break # for i


    def Save(self, backup=False):
        """
        Saves unsaved changes, if any, returns success.

        @param   backup  back up unsaved changes for Reload(pending=True)
        """
        info = self._grid.Table.GetChangedInfo()
        if not info: return True

        self._backup = self._grid.Table.GetChanges() if backup else None

        logger.info("Committing %s in table %s (%s).", info,
                    grammar.quote(self._item["name"]), self._db)
        if not self._grid.Table.SaveChanges(): return False

        self._OnChange()
        # Refresh cell colours; without CallLater wx 2.8 can crash
        wx.CallLater(0, self._grid.ForceRefresh)
        return True


    def Reload(self, pending=False):
        """
        Reloads current data grid, making a new query.

        @param   pending  retain unsaved pending changes
        """
        self._OnRefresh(pending=pending)


    def _Populate(self):
        """Loads data to grid."""
        grid_data = SQLiteGridBase(self._db, category=self._category, name=self._item["name"])
        self._grid.SetTable(grid_data)
        self._grid.Scroll(0, 0)
        self._grid.SetColMinimalAcceptableWidth(100)
        col_range = range(grid_data.GetNumberCols())
        [self._grid.AutoSizeColLabelSize(x) for x in col_range]


    def _PostEvent(self, **kwargs):
        """Posts an EVT_DATA_PAGE event to parent."""
        wx.PostEvent(self, DataPageEvent(-1, source=self, item=self._item, **kwargs))


    def _OnChange(self, event=None):
        """Refresh toolbar icons based on data change state, notifies parent."""
        changed = self._grid.Table.IsChanged()
        self._tb.EnableTool(wx.ID_SAVE, changed)
        self._tb.EnableTool(wx.ID_UNDO, changed)
        self._PostEvent(modified=changed)


    def _OnClose(self, event=None):
        """Handler for clicking to close the item, sends message to parent."""
        if self.IsChanged() and wx.OK != wx.MessageBox(
            "There are unsaved changes, "
            "are you sure you want to discard them?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return
        self._PostEvent(close=True)


    def _OnExport(self, event=None):
        """
        Handler for clicking to export grid contents to file, allows the
        user to select filename and type and creates the file.
        """
        WILDCARD, EXTS = export.TABLE_WILDCARD, export.TABLE_EXTS
        if "view" == self._category:
            WILDCARD, EXTS = export.QUERY_WILDCARD, export.QUERY_EXTS

        title = "%s %s" % (self._category.capitalize(),
                           grammar.quote(self._item["name"], force=True))
        dialog = wx.FileDialog(self, defaultDir=os.getcwd(),
            message="Save %s as" % self._category,
            defaultFile=util.safe_filename(title),
            wildcard=WILDCARD,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        extname = EXTS[dialog.FilterIndex]
        if not filename.lower().endswith(".%s" % extname):
            filename += ".%s" % extname
        busy = controls.BusyPanel(self, 'Exporting "%s".' % filename)
        guibase.status('Exporting "%s".', filename)
        try:
            make_iterable = self._grid.Table.GetRowIterator
            export.export_data(make_iterable, filename, title, self._db,
                               self._grid.Table.columns, category=self._category,
                               name=self._item["name"])
            guibase.status('Exported "%s".', filename, log=True, flash=True)
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving %s."
            logger.exception(msg, filename)
            guibase.status(msg, flash=True)
            error = "Error saving %s:\n\n%s" % (filename, util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally:
            busy.Close()


    def _OnInsert(self, event):
        """
        Handler for clicking to insert a table row, lets the user edit a new
        grid line.
        """
        self._grid.InsertRows(pos=0, numRows=1)
        self._grid.SetGridCursor(0, self._grid.GetGridCursorCol())
        self._grid.Scroll(self._grid.GetScrollPos(wx.HORIZONTAL), 0)
        self._grid.Refresh()
        self._grid.SetGridCursor(0, 0)
        # Refresh scrollbars; without CallAfter wx 2.8 can crash
        wx.CallAfter(self.Layout)
        self._OnChange()


    def _OnDelete(self, event):
        """
        Handler for clicking to delete a table row, removes the row from grid.
        """
        selected_rows = self._grid.GetSelectedRows()
        cursor_row = self._grid.GetGridCursorRow()
        if cursor_row >= 0: selected_rows.append(cursor_row)
        for row in selected_rows: self._grid.DeleteRows(row)
        self.Layout() # Refresh scrollbars
        self._OnChange()


    def _OnCommit(self, event=None):
        """Handler for clicking to commit the changed database table."""
        info = self._grid.Table.GetChangedInfo()
        if wx.OK != wx.MessageBox(
            "Are you sure you want to commit these changes (%s)?" %
            info, conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        logger.info("Committing %s in table %s (%s).", info,
                    grammar.quote(self._item["name"]), self._db)
        if not self._grid.Table.SaveChanges(): return

        self._backup = None
        self._OnChange()
        # Refresh cell colours; without CallLater wx 2.8 can crash
        wx.CallLater(0, self._grid.ForceRefresh)


    def _OnRollback(self, event=None):
        """Handler for clicking to rollback the changed database table."""
        info = self._grid.Table.GetChangedInfo()
        if wx.OK != wx.MessageBox(
            "Are you sure you want to discard these changes (%s)?" %
            info, conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        self._grid.Table.UndoChanges()
        # Refresh scrollbars and colours; without CallAfter wx 2.8 can crash
        wx.CallLater(0, lambda: (self._grid.ContainingSizer.Layout(),
                                 self._grid.ForceRefresh()))
        self._backup = None
        self._OnChange()


    def _OnRefresh(self, event=None, pending=False):
        """
        Handler for refreshing grid data, asks for confirmation if changed.
        
        @param   pending  retain unsaved pending changes
        """
        if not pending and self.IsChanged() and wx.OK != wx.MessageBox(
            "There are unsaved changes (%s).\n\n"
            "Are you sure you want to discard them?" % 
            self._grid.Table.GetChangedInfo(), 
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        scrollpos = map(self._grid.GetScrollPos, [wx.HORIZONTAL, wx.VERTICAL])
        cursorpos = [self._grid.GridCursorRow, self._grid.GridCursorCol]
        state = self._grid.Table.GetFilterSort()
        self._grid.Freeze()
        self._grid.Table = None # Reset grid data to empty
        self._Populate()

        if pending: self._grid.Table.SetChanges(self._backup)
        else: self._backup = None

        self._grid.Table.SetFilterSort(state)
        self._grid.Scroll(*scrollpos)
        maxpos = self._grid.GetNumberRows() - 1, self._grid.GetNumberCols() - 1
        cursorpos = [max(0, min(x)) for x in zip(cursorpos, maxpos)]
        self._grid.SetGridCursor(*cursorpos)
        self._grid.Thaw()
        self._OnChange()


    def _OnFilter(self, event):
        """
        Handler for right-clicking a table grid column, lets the user
        change the column filter.
        """
        row, col = event.GetRow(), event.GetCol()
        # Remember scroll positions, as grid update loses them
        if row >= 0: return # Only react to clicks in the header

        grid_data = self._grid.Table
        current_filter = unicode(grid_data.filters[col]) \
                         if col in grid_data.filters else ""
        name = grammar.quote(grid_data.columns[col]["name"], force=True)
        dialog = wx.TextEntryDialog(self,
            "Filter column %s by:" % name, "Filter", defaultValue=current_filter,
            style=wx.OK | wx.CANCEL)
        if wx.ID_OK != dialog.ShowModal(): return

        new_filter = dialog.GetValue()
        if len(new_filter):
            busy = controls.BusyPanel(self,
                'Filtering column %s by "%s".' %
                (name, new_filter))
            grid_data.AddFilter(col, new_filter)
            busy.Close()
        else:
            grid_data.RemoveFilter(col)
        self.Layout() # React to grid size change


    def _OnSort(self, event):
        """
        Handler for clicking a table grid column, sorts table by the column.
        """
        row, col = event.GetRow(), event.GetCol()
        # Remember scroll positions, as grid update loses them
        scroll_hor = self._grid.GetScrollPos(wx.HORIZONTAL)
        scroll_ver = self._grid.GetScrollPos(wx.VERTICAL)
        if row < 0: # Only react to clicks in the header
            self._grid.Table.SortColumn(col)
        self.Layout() # React to grid size change
        self._grid.Scroll(scroll_hor, scroll_ver)


    def _OnResetView(self, event):
        """
        Handler for clicking to remove sorting and filtering,
        resets the grid and its view.
        """
        self._grid.Table.ClearFilter()
        self._grid.Table.ClearSort()
        self.Layout() # React to grid size change


    def _OnGridKey(self, event):
        """Handler for grid keypress, copies selection to clipboard on Ctrl-C."""
        if not event.ControlDown() or ord('C') != event.KeyCode:
            return event.Skip()

        rows, cols = [], []
        if self._grid.GetSelectedCols():
            cols += sorted(self._grid.GetSelectedCols())
            rows += range(self._grid.GetNumberRows())
        if self._grid.GetSelectedRows():
            rows += sorted(self._grid.GetSelectedRows())
            cols += range(self._grid.GetNumberCols())
        if self._grid.GetSelectionBlockTopLeft():
            end = self._grid.GetSelectionBlockBottomRight()
            for i, (r, c) in enumerate(self._grid.GetSelectionBlockTopLeft()):
                r2, c2 = end[i]
                rows += range(r, r2 + 1)
                cols += range(c, c2 + 1)
        if self._grid.GetSelectedCells():
            rows += [r for r, c in self._grid.GetSelectedCells()]
            cols += [c for r, c in self._grid.GetSelectedCells()]
        if not rows and not cols:
            if self._grid.GetGridCursorRow() >= 0 and self._grid.GetGridCursorCol() >= 0:
                rows, cols = [self._grid.GetGridCursorRow()], [self._grid.GetGridCursorCol()]
        rows, cols = (sorted(set(y for y in x if y >= 0)) for x in (rows, cols))
        if not rows or not cols: return

        if wx.TheClipboard.Open():
            data = [[self._grid.GetCellValue(r, c) for c in cols] for r in rows]
            text = "\n".join("\t".join(c for c in r) for r in data)
            d = wx.TextDataObject(text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()


    def _OnGridMouse(self, event):
        """
        Handler for moving the mouse over a grid, shows datetime tooltip for
        UNIX timestamp cells.
        """
        tip = ""
        prev_cell = self._hovered_cell
        x, y = self._grid.CalcUnscrolledPosition(event.X, event.Y)
        row, col = self._grid.XYToCell(x, y)
        if row >= 0 and col >= 0:
            value = self._grid.Table.GetValue(row, col)
            col_name = self._grid.Table.GetColLabelValue(col).lower()
            if type(value) is int and value > 100000000 \
            and ("time" in col_name or "date" in col_name):
                try:
                    tip = datetime.datetime.fromtimestamp(value).strftime(
                          "%Y-%m-%d %H:%M:%S")
                except Exception:
                    tip = unicode(value)
            else:
                tip = unicode(value)
            tip = tip if len(tip) < 1000 else tip[:1000] + ".."
        if (row, col) != prev_cell or not (event.EventObject.ToolTip) \
        or event.EventObject.ToolTip.Tip != tip:
            event.EventObject.SetToolTipString(tip)
        self._hovered_cell = (row, col)



SchemaPageEvent, EVT_SCHEMA_PAGE = wx.lib.newevent.NewCommandEvent()

class SchemaObjectPage(wx.PyPanel):
    """
    Component for viewing and editing schema objects like tables and triggers.
    """

    ORDER      = ["", "ASC", "DESC"]
    COLLATE    = ["", "BINARY", "NOCASE", "RTRIM"]
    UPON       = ["", "BEFORE", "AFTER", "INSTEAD OF"]
    ACTION     = ["DELETE", "INSERT", "UPDATE"]
    MATCH      = ["SIMPLE", "FULL", "PARTIAL"]
    ON_ACTION  = ["SET NULL", "SET DEFAULT", "CASCADE", "RESTRICT", "NO ACTION"]
    CONFLICT   = ["", "ROLLBACK", "ABORT", "FAIL", "IGNORE", "REPLACE"]
    DEFERRABLE = ["DEFERRED", "IMMEDIATE"]
    TABLECONSTRAINT = ["PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK"]
    TABLECONSTRAINT_DEFAULTS = {
        "PRIMARY KEY": {"type": "PRIMARY KEY", "key": [{}]},
        "UNIQUE":      {"type": "UNIQUE",      "key": [{}]},
        "FOREIGN KEY": {"type": "FOREIGN KEY", "key": [], "columns": []},
        "CHECK":       {"type": "CHECK"},
    }
    DEFAULTS = {
        "table":   {"name": "new_table", "columns": [{"name": "new_column"}]},
        "index":   {"name": "new_index"},
        "trigger": {"name": "new_trigger"},
        "view":    {"name": "new_view"},
    }


    def __init__(self, parent, db, item, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize):
        wx.PyPanel.__init__(self, parent, pos=pos, size=size)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(self, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)

        self._db       = db
        self._category = item["type"]
        self._newmode  = "name" not in item
        self._editmode = self._newmode

        if self._newmode:
            item = dict(item, meta=dict(copy.deepcopy(self.DEFAULTS[item["type"]]),
                                        **item.get("meta", {})))
        item = dict(item, meta=self._AssignColumnIDs(item["meta"]))
        self._item     = copy.deepcopy(item)
        self._original = copy.deepcopy(item)

        self._ctrls    = {}  # {}
        self._buttons  = {}  # {name: wx.Button}
        self._sizers   = {}  # {child sizer: parent sizer}
        self._col_updater = None # Column update cascade callback timer
        # Pending column updates as {__id__: {col: {}, ?rename: newname, ?remove: bool}}
        self._col_updates = {}
        self._ignore_change = False
        self._has_alter     = False
        self._show_alter    = False
        self._fks_on        = db.execute("PRAGMA foreign_keys", log=False).fetchone()["foreign_keys"]
        self._backup        = None # State variables copy for RestoreBackup
        self._types    = self._GetColumnTypes()
        self._tables   = [x["name"] for x in db.get_category("table").values()]
        self._views    = [x["name"] for x in db.get_category("view").values()]


        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_name         = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons      = wx.BoxSizer(wx.HORIZONTAL)
        sizer_sql_header   = wx.BoxSizer(wx.HORIZONTAL)

        splitter = wx.SplitterWindow(parent=self, style=wx.BORDER_NONE)
        panel1, panel2 = wx.Panel(splitter), wx.Panel(splitter)
        panel1.Sizer, panel2.Sizer = wx.BoxSizer(wx.VERTICAL), wx.BoxSizer(wx.VERTICAL)

        label_name = wx.StaticText(panel1, label="&Name:")
        edit_name = self._ctrls["name"] = wx.TextCtrl(panel1)

        if   "table"   == item["type"]: creator = self._CreateTable
        elif "index"   == item["type"]: creator = self._CreateIndex
        elif "trigger" == item["type"]: creator = self._CreateTrigger
        elif "view"    == item["type"]: creator = self._CreateView
        categorypanel = self._panel_category = creator(panel1)

        label_stc = self._label_sql = wx.StaticText(panel2, label="CREATE SQL:")
        check_alter = None

        if "table" == item["type"]:
            check_alter = self._ctrls["alter"] = wx.CheckBox(panel2, label="Show A&LTER SQL")
            check_alter.ToolTipString = "Show SQL statements used for performing table change"
            check_alter.Shown = self._has_alter = not self._newmode

        tb = wx.ToolBar(parent=panel2, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = wx.ArtProvider.GetBitmap(wx.ART_COPY, wx.ART_TOOLBAR, (16, 16))
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR, (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddLabelTool(wx.ID_COPY, "", bitmap=bmp1, shortHelp="Copy SQL to clipboard")
        tb.AddLabelTool(wx.ID_SAVE, "", bitmap=bmp2, shortHelp="Save SQL to file")
        tb.Realize()

        stc = self._ctrls["sql"] = controls.SQLiteTextCtrl(panel2,
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        stc.SetReadOnly(True)
        stc._toggle = "skip"

        button_edit    = self._buttons["edit"]    = wx.Button(panel2, label="Edit")
        button_refresh = self._buttons["refresh"] = wx.Button(panel2, label="Refresh")
        button_import  = self._buttons["import"]  = wx.Button(panel2, label="Import SQL")
        button_cancel  = self._buttons["cancel"]  = wx.Button(panel2, label="Cancel")
        button_delete  = self._buttons["delete"]  = wx.Button(panel2, label="Delete")
        button_close   = self._buttons["close"]   = wx.Button(panel2, label="Close")
        button_edit._toggle   = button_refresh._toggle = "skip"
        button_delete._toggle = button_close._toggle   = "disable"
        button_refresh.ToolTipString = "Reload statement, and database tables"
        button_import.ToolTipString  = "Import %s definition from external SQL" % item["type"]

        sizer_name.Add(label_name, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_name.Add(edit_name, proportion=1)

        for i, n in enumerate(["edit", "refresh", "import", "cancel", "delete", "close"]):
            if i: sizer_buttons.AddStretchSpacer()
            sizer_buttons.Add(self._buttons[n])

        sizer_sql_header.Add(label_stc, flag=wx.ALIGN_BOTTOM)
        sizer_sql_header.AddStretchSpacer()
        if check_alter:
            sizer_sql_header.Add(check_alter, border=1, flag=wx.BOTTOM | wx.ALIGN_BOTTOM)
            sizer_sql_header.AddStretchSpacer()
        sizer_sql_header.Add(tb, border=5, flag=wx.TOP | wx.ALIGN_RIGHT)

        panel1.Sizer.Add(sizer_name,       border=10, flag=wx.TOP | wx.RIGHT | wx.GROW)
        panel1.Sizer.Add(categorypanel,    border=10, proportion=2, flag=wx.RIGHT | wx.GROW)
        panel2.Sizer.Add(sizer_sql_header, border=10, flag=wx.RIGHT | wx.GROW)
        panel2.Sizer.Add(stc,              border=10, proportion=1, flag=wx.RIGHT | wx.GROW)
        panel2.Sizer.Add(sizer_buttons,    border=10, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        tb.Bind(wx.EVT_TOOL, self._OnCopySQL, id=wx.ID_COPY)
        tb.Bind(wx.EVT_TOOL, self._OnSaveSQL, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._OnSaveOrEdit, button_edit)
        self.Bind(wx.EVT_BUTTON, self._OnRefresh,    button_refresh)
        self.Bind(wx.EVT_BUTTON, self._OnImportSQL,  button_import)
        self.Bind(wx.EVT_BUTTON, self._OnToggleEdit, button_cancel)
        self.Bind(wx.EVT_BUTTON, self._OnDelete,     button_delete)
        self.Bind(wx.EVT_BUTTON, self._OnClose,      button_close)
        self._BindDataHandler(self._OnChange, edit_name, ["name"])
        if check_alter: self.Bind(wx.EVT_CHECKBOX, self._OnToggleAlterSQL, check_alter)
        self.Bind(wx.EVT_SIZE, lambda e: wx.CallAfter(self.Layout))

        self._Populate()
        self._ToggleControls(self._editmode)
        if "sql" not in self._original and "sql" in self._item:
            self._original["sql"] = self._item["sql"]

        splitter.SetMinimumPaneSize(100)
        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitHorizontally(panel1, panel2, splitter.Size[1] - 200)
        if self._newmode: edit_name.SetFocus(), edit_name.SelectAll()            


    def Close(self, force=False):
        """Closes the page, asking for confirmation if modified and not force."""
        if force: self._editmode = self._newmode = False
        self._OnClose()


    def IsChanged(self):
        """Returns whether there are unsaved changes."""
        result = False
        if self._editmode:
            result = (self._original.get("sql") != self._item.get("sql"))
        return result


    def Save(self, backup=False):
        """
        Saves unsaved changes, if any, returns success.

        @param   backup  back up unsaved changes for RestoreBackup
        """
        VARS = ["_newmode", "_editmode", "_item", "_original", "_has_alter",
                "_types", "_tables", "_views"]
        myvars = {x: copy.deepcopy(getattr(self, x)) for x in VARS} if backup else None
        result = self._OnSave()
        if result and backup: self._backup = myvars
        return result


    def RestoreBackup(self):
        """
        Restores page state from before last successful .Save(backup=True), if any.
        """
        if not self._backup: return            
        for k, v in self._backup.items(): setattr(self, k, v)
        self._Populate()
        self._ToggleControls(self._editmode)
        self._PostEvent(modified=True)


    def _AssignColumnIDs(self, meta):
        """Populates table meta coluns with __id__ fields."""
        result, counts = copy.deepcopy(meta), Counter()
        if grammar.SQL.CREATE_TABLE == result["__type__"]:
            for c in result.get("columns", []):
                name = c.get("name", "").lower()
                c["__id__"] = "%s_%s" % (name, counts[name])
                counts[name] += 1
        return result


    def _CreateTable(self, parent):
        """Returns control panel for CREATE TABLE page."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_flags   = wx.BoxSizer(wx.HORIZONTAL)

        check_temp   = self._ctrls["temporary"] = wx.CheckBox(panel, label="TE&MPORARY")
        check_exists = self._ctrls["exists"]    = wx.CheckBox(panel, label="IF NOT &EXISTS")
        check_rowid  = self._ctrls["without"]   = wx.CheckBox(panel, label="WITHOUT &ROWID")

        nb = self._notebook_table = wx.Notebook(panel)

        panel_columnwrapper = wx.Panel(nb)
        sizer_columnwrapper = panel_columnwrapper.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_columnstop    = wx.FlexGridSizer(cols=4, hgap=10)
        sizer_columnflags   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_columnbuttons = wx.BoxSizer(wx.HORIZONTAL)

        panel_columns = self._panel_columns = wx.lib.scrolledpanel.ScrolledPanel(panel_columnwrapper, style=wx.BORDER_STATIC)
        panel_columns.Sizer = wx.FlexGridSizer(cols=5, vgap=4, hgap=10)
        panel_columns.Sizer.AddGrowableCol(3)

        button_add_column = self._buttons["add_column"] = wx.Button(panel_columnwrapper, label="&Add column")

        panel_constraintwrapper = wx.Panel(nb)
        sizer_constraintwrapper = panel_constraintwrapper.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_constraintbuttons = wx.BoxSizer(wx.HORIZONTAL)

        panel_constraints = self._panel_constraints = wx.lib.scrolledpanel.ScrolledPanel(panel_constraintwrapper, style=wx.BORDER_STATIC)
        panel_constraints.Sizer = wx.FlexGridSizer(cols=3, vgap=4, hgap=10)
        panel_constraints.Sizer.AddGrowableCol(1)

        button_add_constraint = self._buttons["add_constraint"] = wx.Button(panel_constraintwrapper, label="&Add constraint")

        sizer_flags.Add(check_temp)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_exists)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_rowid)

        for l, t in [("P", grammar.SQL.PRIMARY_KEY), ("I", grammar.SQL.AUTOINCREMENT),
                     ("N", grammar.SQL.NOT_NULL),    ("U", grammar.SQL.UNIQUE)]:
            label = wx.StaticText(panel_columnwrapper, label=l, size=(14, -1))
            label.ToolTipString = t
            sizer_columnflags.Add(label)
            
        sizer_columnstop.Add(wx.StaticText(panel_columnwrapper, label="Name",    size=(150, -1)), border=7, flag=wx.LEFT)
        sizer_columnstop.Add(wx.StaticText(panel_columnwrapper, label="Type",    size=(100, -1)))
        sizer_columnstop.Add(wx.StaticText(panel_columnwrapper, label="Default", size=(100, -1)))
        sizer_columnstop.Add(sizer_columnflags)

        sizer_columnbuttons.AddStretchSpacer()
        sizer_columnbuttons.Add(button_add_column)
        sizer_constraintbuttons.AddStretchSpacer()
        sizer_constraintbuttons.Add(button_add_constraint)

        sizer_columnwrapper.Add(sizer_columnstop, border=5, flag=wx.LEFT | wx.TOP | wx.BOTTOM | wx.GROW)
        sizer_columnwrapper.Add(panel_columns, border=5, proportion=1, flag=wx.LEFT | wx.RIGHT | wx.GROW)
        sizer_columnwrapper.Add(sizer_columnbuttons, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        sizer_constraintwrapper.Add(panel_constraints, border=5, proportion=1, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)
        sizer_constraintwrapper.Add(sizer_constraintbuttons, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        nb.AddPage(panel_columnwrapper,     "Columns")
        nb.AddPage(panel_constraintwrapper, "Constraints")

        sizer.Add(sizer_flags, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(nb, proportion=1, border=5, flag=wx.TOP | wx.GROW)

        self._BindDataHandler(self._OnChange,  check_temp,   ["temporary"])
        self._BindDataHandler(self._OnChange,  check_exists, ["exists"])
        self._BindDataHandler(self._OnChange,  check_rowid,  ["without"])
        self._BindDataHandler(self._OnAddItem, button_add_column, ["columns"], {"name": ""})
        self.Bind(wx.EVT_BUTTON, self._OnAddConstraint, button_add_constraint)

        panel_columns.SetupScrolling()
        return panel


    def _CreateIndex(self, parent):
        """Returns control panel for CREATE INDEX page."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_table   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_flags   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_where   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_columnstop = wx.FlexGridSizer(cols=3, hgap=10)

        label_table = wx.StaticText(panel, label="&Table:")
        list_table = self._ctrls["table"] = wx.ComboBox(panel,
            style=wx.CB_DROPDOWN | wx.CB_READONLY)

        check_unique = self._ctrls["unique"] = wx.CheckBox(panel, label="&UNIQUE")
        check_exists = self._ctrls["exists"] = wx.CheckBox(panel, label="IF NOT &EXISTS")

        panel_wrapper = wx.Panel(panel, style=wx.BORDER_STATIC)
        sizer_wrapper = panel_wrapper.Sizer = wx.BoxSizer(wx.VERTICAL)

        panel_columns = self._panel_columns = wx.lib.scrolledpanel.ScrolledPanel(panel_wrapper)
        panel_columns.Sizer = wx.FlexGridSizer(cols=4, vgap=4, hgap=10)
        panel_columns.Sizer.AddGrowableCol(3)

        button_add_column = self._buttons["add_column"] = wx.Button(panel_wrapper, label="&Add column")
        button_add_expr =   self._buttons["add_expr"] =   wx.Button(panel_wrapper, label="Add ex&pression")

        label_where = wx.StaticText(panel, label="WHE&RE:")
        stc_where   = self._ctrls["where"] = controls.SQLiteTextCtrl(panel,
            size=(-1, 40),
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        label_where.ToolTipString = "Optional WHERE-clause to create a partial index"

        sizer_table.Add(label_table, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_table.Add(list_table, flag=wx.GROW)

        sizer_flags.Add(check_unique)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_exists)

        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Column",  size=(250, -1)))
        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Collate", size=( 80, -1)))
        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Order",   size=( 60, -1)))

        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_add_column)
        sizer_buttons.Add(button_add_expr)

        sizer_wrapper.Add(sizer_columnstop, border=5, flag=wx.LEFT | wx.TOP | wx.BOTTOM | wx.GROW)
        sizer_wrapper.Add(panel_columns, border=5, proportion=1, flag=wx.LEFT | wx.RIGHT | wx.GROW)
        sizer_wrapper.Add(sizer_buttons, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        sizer_where.Add(label_where, border=5, flag=wx.RIGHT)
        sizer_where.Add(stc_where, proportion=1, flag=wx.GROW)

        sizer.Add(sizer_table, border=5, flag=wx.TOP | wx.GROW)
        sizer.Add(sizer_flags, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel_wrapper, proportion=1, flag=wx.GROW)
        sizer.Add(sizer_where, border=5, flag=wx.TOP | wx.GROW)

        self._BindDataHandler(self._OnChange,  list_table,   ["table"])
        self._BindDataHandler(self._OnChange,  check_unique, ["unique"])
        self._BindDataHandler(self._OnChange,  check_exists, ["exists"])
        self._BindDataHandler(self._OnChange,  stc_where,    ["where"])
        self._BindDataHandler(self._OnAddItem, button_add_column, ["columns"], {"name": ""})
        self._BindDataHandler(self._OnAddItem, button_add_expr,   ["columns"], {"expr": ""})

        panel_columns.SetupScrolling()
        return panel


    def _CreateTrigger(self, parent):
        """Returns control panel for CREATE TRIGGER page."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_table   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_flags   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_body    = wx.BoxSizer(wx.HORIZONTAL)
        sizer_when    = wx.BoxSizer(wx.HORIZONTAL)

        label_table = self._ctrls["label_table"] = wx.StaticText(panel, label="&Table:")
        list_table = self._ctrls["table"] = wx.ComboBox(panel,
            style=wx.CB_DROPDOWN | wx.CB_READONLY)
        label_upon = wx.StaticText(panel, label="&Upon:")
        list_upon = self._ctrls["upon"] = wx.ComboBox(panel,
            style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=self.UPON)
        label_action = wx.StaticText(panel, label="&Action:")
        list_action = self._ctrls["action"] = wx.ComboBox(panel,
            style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=self.ACTION)
        label_table._toggle = "skip"

        check_temp   = self._ctrls["temporary"] = wx.CheckBox(panel, label="TE&MPORARY")
        check_exists = self._ctrls["exists"]    = wx.CheckBox(panel, label="IF NOT &EXISTS")
        check_for    = self._ctrls["for"]       = wx.CheckBox(panel, label="FOR EACH &ROW")

        panel_wrapper = wx.Panel(panel, style=wx.BORDER_STATIC)
        sizer_wrapper = panel_wrapper.Sizer = wx.BoxSizer(wx.VERTICAL)

        panel_columns = self._panel_columns = wx.lib.scrolledpanel.ScrolledPanel(panel_wrapper)
        panel_columns.Sizer = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)
        panel_columns.Sizer.AddGrowableCol(1)

        button_add_column = self._buttons["add_column"] = wx.Button(panel_wrapper, label="&Add column")

        label_body = wx.StaticText(panel, label="&Body:")
        stc_body   = self._ctrls["body"] = controls.SQLiteTextCtrl(panel,
            size=(-1, 40),
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        label_body.ToolTipString = "Trigger body SQL"

        label_when = wx.StaticText(panel, label="WHEN:")
        stc_when   = self._ctrls["when"] = controls.SQLiteTextCtrl(panel,
            size=(-1, 40),
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        label_when.ToolTipString = "Trigger WHEN expression"

        sizer_table.Add(label_table, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_table.Add(list_table, flag=wx.GROW)
        sizer_table.AddSpacer((20, -1))
        sizer_table.Add(label_upon, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_table.Add(list_upon, flag=wx.GROW)
        sizer_table.AddSpacer((20, -1))
        sizer_table.Add(label_action, border=5, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_table.Add(list_action, flag=wx.GROW)

        sizer_flags.Add(check_temp)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_exists)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_for)

        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_add_column)

        sizer_wrapper.Add(panel_columns, border=5, proportion=1, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)
        sizer_wrapper.Add(sizer_buttons, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        sizer_body.Add(label_body, border=5, flag=wx.RIGHT)
        sizer_body.Add(stc_body, proportion=1, flag=wx.GROW)

        sizer_when.Add(label_when, border=5, flag=wx.RIGHT)
        sizer_when.Add(stc_when, proportion=1, flag=wx.GROW)

        sizer.Add(sizer_table, border=5, flag=wx.TOP | wx.GROW)
        sizer.Add(sizer_flags, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel_wrapper, proportion=2, flag=wx.GROW)
        sizer.Add(sizer_body, proportion=3, border=5, flag=wx.TOP | wx.GROW)
        sizer.Add(sizer_when, proportion=1, border=5, flag=wx.TOP | wx.GROW)

        self._BindDataHandler(self._OnChange,  list_table,    ["table"])
        self._BindDataHandler(self._OnChange,  list_upon,     ["upon"])
        self._BindDataHandler(self._OnChange,  list_action,   ["action"])
        self._BindDataHandler(self._OnChange,  check_temp,    ["temporary"])
        self._BindDataHandler(self._OnChange,  check_exists,  ["exists"])
        self._BindDataHandler(self._OnChange,  check_for,     ["for"])
        self._BindDataHandler(self._OnChange,  stc_body,      ["body"])
        self._BindDataHandler(self._OnChange,  stc_when,      ["when"])
        self._BindDataHandler(self._OnAddItem, button_add_column, ["columns"], "")

        panel_columns.SetupScrolling(scroll_x=False)
        return panel


    def _CreateView(self, parent):
        """Returns control panel for CREATE VIEW page."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_flags   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_select  = wx.BoxSizer(wx.HORIZONTAL)

        check_temp   = self._ctrls["temporary"] = wx.CheckBox(panel, label="TE&MPORARY")
        check_exists = self._ctrls["exists"]    = wx.CheckBox(panel, label="IF NOT &EXISTS")

        splitter = wx.SplitterWindow(panel, style=wx.BORDER_NONE)
        panel1, panel2 = wx.Panel(splitter, style=wx.BORDER_STATIC), wx.Panel(splitter)
        panel1.Sizer, panel2.Sizer = wx.BoxSizer(wx.VERTICAL), wx.BoxSizer(wx.HORIZONTAL)

        panel_columns = self._panel_columns = wx.lib.scrolledpanel.ScrolledPanel(panel1)
        panel_columns.Sizer = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)
        panel_columns.Sizer.AddGrowableCol(1)

        button_add_column = self._buttons["add_column"] = wx.Button(panel1, label="&Add column")

        label_body = wx.StaticText(panel2, label="Se&lect:")
        stc_body = self._ctrls["select"] = controls.SQLiteTextCtrl(panel2,
            size=(-1, 40),
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        label_body.ToolTipString = "SELECT statement for view"

        sizer_flags.Add(check_temp)
        sizer_flags.AddSpacer((100, -1))
        sizer_flags.Add(check_exists)

        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_add_column)

        panel1.Sizer.Add(panel_columns, border=5, proportion=1, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)
        panel1.Sizer.Add(sizer_buttons, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.GROW)

        panel2.Sizer.Add(label_body, border=5, flag=wx.RIGHT)
        panel2.Sizer.Add(stc_body, proportion=1, flag=wx.GROW)

        sizer.Add(sizer_flags, border=5, flag=wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(splitter, proportion=1, flag=wx.GROW)

        self._BindDataHandler(self._OnChange,  check_temp,   ["temporary"])
        self._BindDataHandler(self._OnChange,  check_exists, ["exists"])
        self._BindDataHandler(self._OnChange,  stc_body,     ["select"])
        self._BindDataHandler(self._OnAddItem, button_add_column, ["columns"], "")

        panel_columns.SetupScrolling(scroll_x=False)
        splitter.SetMinimumPaneSize(100)
        splitter.SplitHorizontally(panel1, panel2, 100)
        return panel


    def _Populate(self):
        """Populates panel with item data."""
        data, meta = self._item, self._item.get("meta") or {}
        self._ignore_change = True
        self.Freeze()

        self._ctrls["name"].Value = meta.get("name") or ""

        self._sizers.clear()
        if   "table"   == data["type"]: self._PopulateTable()
        elif "index"   == data["type"]: self._PopulateIndex()
        elif "trigger" == data["type"]: self._PopulateTrigger()
        elif "view"    == data["type"]: self._PopulateView()

        self._PopulateSQL()
        self._ignore_change = False
        self.Layout()
        self.Thaw()


    def _PopulateTable(self):
        """Populates panel with table-specific data."""
        data, meta = self._item, self._item.get("meta") or {}

        self._ctrls["temporary"].Value = bool(meta.get("temporary"))
        self._ctrls["exists"].Value    = bool(meta.get("exists"))
        self._ctrls["without"].Value   = bool(meta.get("without"))

        self._EmptyControl(self._panel_columns)
        for i, col in enumerate(meta.get("columns") or ()):
            self._AddRowTable(["columns"], i, col)
        self._panel_columns.Layout()

        self._EmptyControl(self._panel_constraints)
        for i, cnstr in enumerate(meta.get("constraints") or ()):
            self._AddRowTableConstraint(["constraints"], i, cnstr)
        self._panel_constraints.Layout()

        lencol, lencnstr =  (len(meta.get(x) or ()) for x in ("columns", "constraints"))
        self._notebook_table.SetPageText(0, "Columns"     if not lencol   else "Columns (%s)" % lencol)
        self._notebook_table.SetPageText(1, "Constraints" if not lencnstr else "Constraints (%s)" % lencnstr)
        self._notebook_table.Layout()


    def _PopulateIndex(self):
        """Populates panel with index-specific data."""
        data, meta = self._item, self._item.get("meta") or {}
        self._ctrls["table"].SetItems(self._tables)
        self._ctrls["table"].Value = meta.get("table") or ""

        self._ctrls["unique"].Value = bool(meta.get("unique"))
        self._ctrls["exists"].Value = bool(meta.get("exists"))
        self._ctrls["where"].SetText(meta.get("where") or "")

        self._EmptyControl(self._panel_columns)
        for i, col in enumerate(meta.get("columns") or ()):
            self._AddRowIndex(["columns"], i, col)


    def _PopulateTrigger(self):
        """Populates panel with trigger-specific data."""
        data, meta = self._item, self._item.get("meta") or {}

        if grammar.SQL.INSTEAD_OF == meta.get("upon"):
            self._ctrls["label_table"].Label = "&View:"
            self._item["meta"].pop("columns", None)
            self._ctrls["table"].SetItems(self._views)
        else:
            self._ctrls["label_table"].Label = "&Table:"
            self._ctrls["table"].SetItems(self._tables)

        self._ctrls["table"].Value = meta.get("table") or ""
        self._ctrls["temporary"].Value = bool(meta.get("temporary"))
        self._ctrls["exists"].Value    = bool(meta.get("exists"))
        self._ctrls["for"].Value       = bool(meta.get("for"))
        self._ctrls["upon"].Value      = meta.get("upon") or ""
        self._ctrls["action"].Value    = meta.get("action") or ""
        self._ctrls["body"].SetText(meta.get("body") or "")
        self._ctrls["when"].SetText(meta.get("when") or "")

        panel = self._panel_columns
        self._EmptyControl(panel)
        if  grammar.SQL.UPDATE     == meta.get("action") \
        and grammar.SQL.INSTEAD_OF == meta.get("upon") \
        and self._db.has_view_columns():
            panel.Parent.Show()
            for i, col in enumerate(meta.get("columns") or ()):
                self._AddRowTrigger(["columns"], i, col)
        else:
            panel.Parent.Hide()
        self._panel_category.Layout()


    def _PopulateView(self):
        """Populates panel with view-specific data."""
        data, meta = self._item, self._item.get("meta") or {}

        self._ctrls["temporary"].Value = bool(meta.get("temporary"))
        self._ctrls["exists"].Value = bool(meta.get("exists"))
        self._ctrls["select"].SetText(meta.get("select") or "")

        panel = self._panel_columns
        self._EmptyControl(panel)

        if self._db.has_view_columns():
            for i, col in enumerate(meta.get("columns") or ()):
                self._AddRowView(["columns"], i, col)
        else: panel.Parent.Hide()


    def _AddRowTable(self, path, i, col, insert=False, focus=False):
        """Adds a new row of controls for table columns."""
        first, last = not i, (i == len(util.get(self._item["meta"], path)) - 1)
        meta, rowkey = self._item.get("meta") or {}, wx.NewId()
        panel = self._panel_columns

        sizer_flags = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        text_name     = wx.TextCtrl(panel)
        list_type     = wx.ComboBox(panel, choices=self._types, style=wx.CB_DROPDOWN)
        text_default  = controls.SQLiteTextCtrl(panel, singleline=True)

        check_pk      = wx.CheckBox(panel)
        check_autoinc = wx.CheckBox(panel)
        check_notnull = wx.CheckBox(panel)
        check_unique  = wx.CheckBox(panel)
        check_pk.ToolTipString      = grammar.SQL.PRIMARY_KEY
        check_autoinc.ToolTipString = grammar.SQL.AUTOINCREMENT
        check_notnull.ToolTipString = grammar.SQL.NOT_NULL
        check_unique.ToolTipString  = grammar.SQL.UNIQUE

        button_open   = wx.Button(panel, label=u"O", size=(20, -1))
        button_up     = wx.Button(panel, label=u"\u2191", size=(20, -1))
        button_down   = wx.Button(panel, label=u"\u2193", size=(20, -1))
        button_remove = wx.Button(panel, label=u"\u2715", size=(20, -1))

        text_name.MinSize    = (150, -1)
        list_type.MinSize    = (100, -1)
        text_default.MinSize = (100, text_name.Size[1])
        check_autoinc._toggle = lambda: "disable" if self._editmode and col.get("pk") is None else ""
        button_open._toggle = "skip"
        button_remove._toggle = "show"
        button_up._toggle   = self._GetMoveButtonToggle(button_up,   -1)
        button_down._toggle = self._GetMoveButtonToggle(button_down, +1)
        if first: button_up.Enable(False)
        if last: button_down.Enable(False)
        button_open.ToolTipString   = "Open advanced options"
        button_up.ToolTipString     = "Move one step higher"
        button_down.ToolTipString   = "Move one step lower"
        button_remove.ToolTipString = "Remove"                    

        text_name.Value     = col.get("name") or ""
        list_type.Value     = col.get("type") or ""
        text_default.Value  = col.get("default") or ""
        check_pk.Value      = col.get("pk") is not None
        check_autoinc.Value = bool(col.get("pk", {}).get("autoincrement"))
        check_notnull.Value = col.get("notnull") is not None
        check_unique.Value  = col.get("unique")  is not None
        check_autoinc.Enable(check_pk.Value)

        sizer_flags.Add(check_pk)
        sizer_flags.Add(check_autoinc)
        sizer_flags.Add(check_notnull)
        sizer_flags.Add(check_unique)

        sizer_buttons.Add(button_open)
        sizer_buttons.Add(button_up)
        sizer_buttons.Add(button_down)
        sizer_buttons.Add(button_remove)

        vertical = (wx.TOP if first else wx.BOTTOM if last else 0)
        if insert:
            start = panel.Sizer.Cols * i
            panel.Sizer.Insert(start,   text_name,     border=5, flag=vertical | wx.LEFT)
            panel.Sizer.Insert(start+1, list_type,     border=5, flag=vertical)
            panel.Sizer.Insert(start+2, text_default,  border=5, flag=vertical)
            self._AddSizer(panel.Sizer, sizer_flags,   border=5, flag=vertical | wx.ALIGN_CENTER_VERTICAL,  insert=start+3)
            self._AddSizer(panel.Sizer, sizer_buttons, border=5, flag=vertical | wx.RIGHT | wx.ALIGN_RIGHT, insert=start+4)
        else:
            panel.Sizer.Add(text_name,     border=5, flag=vertical | wx.LEFT)
            panel.Sizer.Add(list_type,     border=5, flag=vertical)
            panel.Sizer.Add(text_default,  border=5, flag=vertical)
            self._AddSizer(panel.Sizer, sizer_flags,   border=5, flag=vertical | wx.ALIGN_CENTER_VERTICAL)
            self._AddSizer(panel.Sizer, sizer_buttons, border=5, flag=vertical | wx.RIGHT | wx.ALIGN_RIGHT)

        self._BindDataHandler(self._OnChange,      text_name,     ["columns", text_name,    "name"])
        self._BindDataHandler(self._OnChange,      list_type,     ["columns", list_type,    "type"])
        self._BindDataHandler(self._OnChange,      text_default,  ["columns", text_default, "default"])
        self._BindDataHandler(self._OnToggleColumnFlag, check_pk,      ["columns", check_pk,      "pk"],      rowkey)
        self._BindDataHandler(self._OnToggleColumnFlag, check_notnull, ["columns", check_notnull, "notnull"], rowkey)
        self._BindDataHandler(self._OnToggleColumnFlag, check_unique,  ["columns", check_unique,  "unique"],  rowkey)
        self._BindDataHandler(self._OnChange,      check_autoinc, ["columns", check_autoinc, "pk", "autoincrement"])
        self._BindDataHandler(self._OnOpenItem,    button_open,   ["columns", button_open])
        self._BindDataHandler(self._OnMoveItem,    button_up,     ["columns", button_up],   -1)
        self._BindDataHandler(self._OnMoveItem,    button_down,   ["columns", button_down], +1)
        self._BindDataHandler(self._OnRemoveItem,  button_remove, ["columns", button_remove])

        self._ctrls.update({"columns.name.%s"     % rowkey: text_name,
                            "columns.type.%s"     % rowkey: list_type,
                            "columns.default.%s"  % rowkey: text_default,
                            "columns.pk.%s"       % rowkey: check_pk,
                            "columns.autoinc.%s"  % rowkey: check_autoinc,
                            "columns.notnull.%s"  % rowkey: check_notnull,
                            "columns.unique.%s"   % rowkey: check_unique, })
        self._buttons.update({"columns.open.%s"   % rowkey: button_open,
                              "columns.up.%s"     % rowkey: button_up,
                              "columns.down.%s"   % rowkey: button_down,
                              "columns.remove.%s" % rowkey: button_remove, })
        if focus: text_name.SetFocus()


    def _AddRowTableConstraint(self, path, i, cnstr, insert=False, focus=False):
        """Adds a new row of controls for table constraints."""
        first, last = not i, (i == len(util.get(self._item["meta"], path)) - 1)
        meta, rowkey = self._item.get("meta") or {}, wx.NewId()
        panel = self._panel_constraints

        mycolumns = [x["name"] for x in meta.get("columns") or () if x["name"]]

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_item    = wx.BoxSizer(wx.HORIZONTAL)

        label_type = wx.StaticText(panel, label=cnstr["type"])

        if grammar.SQL.PRIMARY_KEY == cnstr["type"] \
        or grammar.SQL.UNIQUE      == cnstr["type"]:
            kcols = [x.get("name") or "" for x in cnstr.get("key") or ()]

            if len(kcols) > 1:
                ctrl_cols  = wx.TextCtrl(panel)
                ctrl_cols.SetEditable(False); ctrl_cols._toggle = "disable"
            else:
                ctrl_cols  = wx.ComboBox(panel, choices=mycolumns, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            label_conflict = wx.StaticText(panel, label=grammar.SQL.ON_CONFLICT + ":")
            list_conflict  = wx.ComboBox(panel, choices=self.CONFLICT, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            button_open = wx.Button(panel, label="O", size=(20, -1))

            ctrl_cols.MinSize = (150, -1)
            button_open._toggle = "skip"
            button_open.ToolTipString   = "Open advanced options"

            ctrl_cols.Value = ", ".join(kcols)
            list_conflict.Value = cnstr.get("conflict") or ""

            sizer_item.Add(ctrl_cols)
            sizer_item.Add(label_conflict, border=5, flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL)
            sizer_item.Add(list_conflict,  border=5, flag=wx.LEFT)

            sizer_buttons.Add(button_open)

            self._BindDataHandler(self._OnChange,   ctrl_cols,     ["constraints", ctrl_cols,     "key", 0, "name"])
            self._BindDataHandler(self._OnChange,   list_conflict, ["constraints", list_conflict, "conflict"])
            self._BindDataHandler(self._OnOpenItem, button_open,   ["constraints", button_open])

            self._ctrls.update({"constraints.columns.%s"  % rowkey: ctrl_cols,
                                "constraints.conflict.%s" % rowkey: list_conflict})
            self._buttons.update({"constraints.open.%s"   % rowkey: button_open})

        elif grammar.SQL.FOREIGN_KEY == cnstr["type"]:
            ftable = self._db.get_category("table", cnstr["table"]) if cnstr.get("table") else {}
            fcolumns = [x["name"] for x in ftable.get("columns") or ()]
            kcols  = cnstr.get("columns") or ()
            fkcols = cnstr.get("key")     or ()

            sizer_foreign = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)

            if len(kcols) > 1:
                ctrl_cols  = wx.TextCtrl(panel)
                ctrl_cols.SetEditable(False); ctrl_cols._toggle = "disable"
            else:
                ctrl_cols = wx.ComboBox(panel, choices=mycolumns, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            label_table = wx.StaticText(panel, label="Foreign table:")
            list_table  = wx.ComboBox(panel, choices=self._tables, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            label_keys  = wx.StaticText(panel, label="Foreign column:")
            if len(fkcols) > 1:
                ctrl_keys  = wx.TextCtrl(panel)
                ctrl_keys.SetEditable(False); ctrl_keys._toggle = "disable"
            else:
                ctrl_keys = wx.ComboBox(panel, choices=fcolumns, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            button_open = wx.Button(panel, label="O", size=(20, -1))

            ctrl_cols.MinSize  = (150, -1)
            list_table.MinSize = (150, -1)
            ctrl_keys.MinSize  = (150, -1)
            button_open._toggle = "skip"
            button_open.ToolTipString   = "Open advanced options"

            ctrl_cols.Value  = ", ".join(kcols)
            list_table.Value = cnstr.get("table") or ""
            ctrl_keys.Value  = ", ".join(fkcols)

            sizer_foreign.Add(label_table, flag=wx.ALIGN_CENTER_VERTICAL)
            sizer_foreign.Add(list_table)
            sizer_foreign.Add(label_keys,  flag=wx.ALIGN_CENTER_VERTICAL)
            sizer_foreign.Add(ctrl_keys)

            sizer_item.Add(ctrl_cols, flag=wx.ALIGN_CENTER_VERTICAL)
            self._AddSizer(sizer_item, sizer_foreign, border=5, flag=wx.LEFT)

            sizer_buttons.Add(button_open)

            self._BindDataHandler(self._OnChange,   ctrl_cols,   ["constraints", ctrl_cols,  "columns"])
            self._BindDataHandler(self._OnChange,   list_table,  ["constraints", list_table, "table"])
            self._BindDataHandler(self._OnChange,   ctrl_keys,   ["constraints", ctrl_keys,  "key"])
            self._BindDataHandler(self._OnOpenItem, button_open, ["constraints", button_open])

            self._ctrls.update({"constraints.columns.%s" % rowkey: ctrl_cols,
                                "constraints.table.%s"   % rowkey: list_table,
                                "constraints.keys.%s"    % rowkey: ctrl_keys})
            self._buttons.update({"constraints.open.%s"  % rowkey: button_open})

        elif grammar.SQL.CHECK == cnstr["type"]:
            stc_check = controls.SQLiteTextCtrl(panel, size=(-1, 40))

            label_type.ToolTipString = "Expression yielding a NUMERIC 0 on " \
                                       "constraint violation,\ncannot contain a subquery."

            sizer_item.Add(stc_check, proportion=1)

            self._BindDataHandler(self._OnChange, stc_check, ["constraints", stc_check, "check"])

            self._ctrls.update({"constraints.check.%s" % rowkey: stc_check})


        button_up     = wx.Button(panel, label=u"\u2191", size=(20, -1))
        button_down   = wx.Button(panel, label=u"\u2193", size=(20, -1))
        button_remove = wx.Button(panel, label=u"\u2715", size=(20, -1))

        button_remove._toggle = "show"
        button_up._toggle   = self._GetMoveButtonToggle(button_up,   -1)
        button_down._toggle = self._GetMoveButtonToggle(button_down, +1)
        if first: button_up.Enable(False)
        if last:  button_down.Enable(False)
        button_up.ToolTipString     = "Move one step higher"
        button_down.ToolTipString   = "Move one step lower"
        button_remove.ToolTipString = "Remove"                    

        sizer_buttons.Add(button_up)
        sizer_buttons.Add(button_down)
        sizer_buttons.Add(button_remove)

        vertical = (wx.TOP if first else wx.BOTTOM if last else 0)
        if insert:
            start = panel.Sizer.Cols * i
            panel.Sizer.Insert(start, label_type, border=5, flag=vertical | wx.LEFT  | wx.ALIGN_CENTER_VERTICAL)
            self._AddSizer(panel.Sizer, sizer_item,     border=5, flag=vertical | wx.LEFT  | wx.ALIGN_CENTER_VERTICAL | wx.GROW, insert=start+1)
            self._AddSizer(panel.Sizer, sizer_buttons,  border=5, flag=vertical | wx.RIGHT | wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL, insert=start+2)
        else:
            panel.Sizer.Add(label_type, border=5, flag=vertical | wx.LEFT  | wx.ALIGN_CENTER_VERTICAL)
            self._AddSizer(panel.Sizer, sizer_item,     border=5, flag=vertical | wx.LEFT  | wx.ALIGN_CENTER_VERTICAL | wx.GROW)
            self._AddSizer(panel.Sizer, sizer_buttons,  border=5, flag=vertical | wx.RIGHT | wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)

        self._BindDataHandler(self._OnMoveItem,   button_up,     ["constraints", button_up],   -1)
        self._BindDataHandler(self._OnMoveItem,   button_down,   ["constraints", button_down], +1)
        self._BindDataHandler(self._OnRemoveItem, button_remove, ["constraints", button_remove])

        self._buttons.update({"constraints.up.%s"     % rowkey: button_up,
                              "constraints.down.%s"   % rowkey: button_down,
                              "constraints.remove.%s" % rowkey: button_remove, })
        if focus: sizer_item.Children[0].Window.SetFocus()


    def _AddRowIndex(self, path, i, col, insert=False, focus=False):
        """Adds a new row of controls for index columns."""
        first, last = not i, (i == len(util.get(self._item["meta"], path)) - 1)
        meta, rowkey = self._item.get("meta") or {}, wx.NewId()
        table = self._db.get_category("table", meta["table"]) \
                if meta.get("table") else {}
        tablecols = [x["name"] for x in table.get("columns") or ()]
        panel = self._panel_columns

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        if "name" in col:
            ctrl_index = wx.ComboBox(panel, choices=tablecols,
                style=wx.CB_DROPDOWN | wx.CB_READONLY)
        else:
            ctrl_index = controls.SQLiteTextCtrl(panel, singleline=True)
        list_collate  = wx.ComboBox(panel, choices=self.COLLATE, style=wx.CB_DROPDOWN)
        list_order    = wx.ComboBox(panel, choices=self.ORDER, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        button_up     = wx.Button(panel, label=u"\u2191", size=(20, -1))
        button_down   = wx.Button(panel, label=u"\u2193", size=(20, -1))
        button_remove = wx.Button(panel, label=u"\u2715", size=(20, -1))

        ctrl_index.MinSize =   (250, -1 if "name" in col else list_collate.Size[1])
        list_collate.MinSize = ( 80, -1)
        list_order.MinSize =   ( 60, -1)
        button_remove._toggle = "show"
        button_up._toggle   = self._GetMoveButtonToggle(button_up,   -1)
        button_down._toggle = self._GetMoveButtonToggle(button_down, +1)
        if first: button_up.Enable(False)
        if last:  button_down.Enable(False)
        button_up.ToolTipString     = "Move one step higher"
        button_down.ToolTipString   = "Move one step lower"
        button_remove.ToolTipString = "Remove"                    

        ctrl_index.Value   = col.get("name") or col.get("expr") or ""
        list_collate.Value = col.get("collate") or ""
        list_order.Value   = col.get("order") or ""

        sizer_buttons.Add(button_up)
        sizer_buttons.Add(button_down)
        sizer_buttons.Add(button_remove)

        if insert:
            start = panel.Sizer.Cols * i
            panel.Sizer.Insert(start,   ctrl_index)
            panel.Sizer.Insert(start+1, list_collate)
            panel.Sizer.Insert(start+2, list_order)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT, insert=start+3)
        else:
            panel.Sizer.Add(ctrl_index)
            panel.Sizer.Add(list_collate)
            panel.Sizer.Add(list_order)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT)

        self._BindDataHandler(self._OnChange,     ctrl_index,    ["columns", ctrl_index,   "name" if "name" in col else "expr"])
        self._BindDataHandler(self._OnChange,     list_collate,  ["columns", list_collate, "collate"])
        self._BindDataHandler(self._OnChange,     list_order,    ["columns", list_order,   "order"])
        self._BindDataHandler(self._OnMoveItem,   button_up,     ["columns", button_up],   -1)
        self._BindDataHandler(self._OnMoveItem,   button_down,   ["columns", button_down], +1)
        self._BindDataHandler(self._OnRemoveItem, button_remove, ["columns", button_remove])

        self._ctrls.update({"columns.index.%s"    % rowkey: ctrl_index,
                            "columns.collate.%s"  % rowkey: list_collate,
                            "columns.order.%s"    % rowkey: list_order, })
        self._buttons.update({"columns.up.%s"     % rowkey: button_up,
                              "columns.down.%s"   % rowkey: button_down,
                              "columns.remove.%s" % rowkey: button_remove, })
        if focus: ctrl_index.SetFocus()


    def _AddRowTrigger(self, path, i, value, insert=False, focus=False):
        """Adds a new row of controls for trigger columns."""
        first, last = not i, (i == len(util.get(self._item["meta"], path)) - 1)
        meta, rowkey = self._item.get("meta") or {}, wx.NewId()
        if "INSTEAD OF" == meta.get("upon"):
            self._ctrls["label_table"].Label = "&View:"
            self._ctrls["table"].SetItems(self._views)
            table = self._db.get_category("view", meta["table"]) \
                    if meta.get("table") else {}
        else:
            self._ctrls["label_table"].Label = "&Table:"
            self._ctrls["table"].SetItems(self._tables)
            table = self._db.get_category("table", meta["table"]) \
                    if meta.get("table") else {}
        tablecols = [x["name"] for x in table.get("columns") or ()]
        panel = self._panel_columns

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        list_column = wx.ComboBox(panel, choices=tablecols,
            style=wx.CB_DROPDOWN | wx.CB_READONLY)
        button_up     = wx.Button(panel, label=u"\u2191", size=(20, -1))
        button_down   = wx.Button(panel, label=u"\u2193", size=(20, -1))
        button_remove = wx.Button(panel, label=u"\u2715", size=(20, -1))

        list_column.MinSize = (200, -1)
        button_remove._toggle = "show"
        button_up._toggle   = self._GetMoveButtonToggle(button_up,   -1)
        button_down._toggle = self._GetMoveButtonToggle(button_down, +1)
        if first: button_up.Enable(False)
        if last:  button_down.Enable(False)
        button_up.ToolTipString     = "Move one step higher"
        button_down.ToolTipString   = "Move one step lower"
        button_remove.ToolTipString = "Remove"                    

        list_column.Value = value

        sizer_buttons.Add(button_up)
        sizer_buttons.Add(button_down)
        sizer_buttons.Add(button_remove)

        if insert:
            start = panel.Sizer.Cols * i
            panel.Sizer.Insert(start, list_column)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT, insert=start+1)
        else:
            panel.Sizer.Add(list_column)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT)

        self._BindDataHandler(self._OnChange,      list_column,   ["columns", list_column])
        self._BindDataHandler(self._OnMoveItem,    button_up,     ["columns", button_up],   -1)
        self._BindDataHandler(self._OnMoveItem,    button_down,   ["columns", button_down], +1)
        self._BindDataHandler(self._OnRemoveItem,  button_remove, ["columns", button_remove])

        self._ctrls.update({"columns.name.%s"     % rowkey: list_column})
        self._buttons.update({"columns.up.%s"     % rowkey: button_up,
                              "columns.down.%s"   % rowkey: button_down,
                              "columns.remove.%s" % rowkey: button_remove})
        if focus: list_column.SetFocus()


    def _AddRowView(self, path, i, value, insert=False, focus=False):
        """Adds a new row of controls for view columns."""
        first, last = not i, (i == len(util.get(self._item["meta"], path)) - 1)
        panel = self._panel_columns
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        text_column = controls.SQLiteTextCtrl(panel, singleline=True)
        button_up     = wx.Button(panel, label=u"\u2191", size=(20, -1))
        button_down   = wx.Button(panel, label=u"\u2193", size=(20, -1))
        button_remove = wx.Button(panel, label=u"\u2715", size=(20, -1))

        text_column.MinSize = (200, button_up.Size[1])
        button_remove._toggle = "show"
        button_up._toggle   = self._GetMoveButtonToggle(button_up,   -1)
        button_down._toggle = self._GetMoveButtonToggle(button_down, +1)
        if first: button_up.Enable(False)
        if last:  button_down.Enable(False)
        button_up.ToolTipString     = "Move one step higher"
        button_down.ToolTipString   = "Move one step lower"
        button_remove.ToolTipString = "Remove"                    

        text_column.Value = value

        sizer_buttons.Add(button_up)
        sizer_buttons.Add(button_down)
        sizer_buttons.Add(button_remove)

        if insert:
            start = panel.Sizer.Cols * i
            panel.Sizer.Insert(start, text_column)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT, insert=start+1)
        else:
            panel.Sizer.Add(text_column)
            self._AddSizer(panel.Sizer, sizer_buttons, flag=wx.ALIGN_RIGHT)

        self._BindDataHandler(self._OnChange,     text_column,   ["columns", text_column])
        self._BindDataHandler(self._OnMoveItem,   button_up,     ["columns", button_up],   -1)
        self._BindDataHandler(self._OnMoveItem,   button_down,   ["columns", button_down], +1)
        self._BindDataHandler(self._OnRemoveItem, button_remove, ["columns", button_remove])

        self._ctrls.update({"columns.name.%s"     % id(text_column): text_column})
        self._buttons.update({"columns.up.%s"     % id(text_column): button_up,
                              "columns.down.%s"   % id(text_column): button_down,
                              "columns.remove.%s" % id(text_column): button_remove})
        if focus: text_column.SetFocus()


    def _BindDataHandler(self, handler, ctrl, path, *args):
        """
        Binds handler(path, *args) handler to control.
        If path contains ctrl, ctrl is assumed to be in a row under FlexGridSizer,
        and path will have row index instead of ctrl when invoking handler.
        """
        if isinstance(ctrl, wx.stc.StyledTextCtrl): events = [wx.stc.EVT_STC_CHANGE]
        elif isinstance(ctrl, wx.Button):   events = [wx.EVT_BUTTON]
        elif isinstance(ctrl, wx.CheckBox): events = [wx.EVT_CHECKBOX]
        elif isinstance(ctrl, wx.ComboBox): events = [wx.EVT_TEXT, wx.EVT_COMBOBOX]
        else: events = [wx.EVT_TEXT]
        for e in events:
            self.Bind(e, functools.partial(self._OnDataEvent, handler, path, *args), ctrl)


    def _OnDataEvent(self, handler, path, *args):
        """
        Intermediary handler for data control, calculates control row index
        and invokes handler with indexed path, if control in path.

        @param   path    [key, .., ctrl, ..] ctrl will be replaced with row index
        """
        event = args[-1]
        ctrl = event.EventObject
        if ctrl in path:
            indexitem, parentsizer = ctrl, ctrl.ContainingSizer
            while parentsizer is not ctrl.Parent.Sizer:
                indexitem = parentsizer
                parentsizer = self._sizers.get(indexitem)
            index = ctrl.Parent.Sizer.GetItemIndex(indexitem) / ctrl.Parent.Sizer.Cols
            path = [index if x is ctrl else x for x in path]
        handler(path, *args)


    def _EmptyControl(self, window):
        """Empties a component of children, updates _ctrls and _buttons."""
        buttonmap = {v: k for k, v in self._buttons.items()}
        ctrlmap   = {v: k for k, v in self._ctrls.items()}
        while window.Sizer and window.Sizer.Children:
            sizeritem = window.Sizer.Children[0]
            if sizeritem.IsSizer(): self._RemoveSizer(sizeritem.GetSizer())
            window.Sizer.Remove(0)
        for c in window.Children:
            if c in buttonmap: self._buttons.pop(buttonmap.pop(c))
            elif c in ctrlmap: self._ctrls  .pop(ctrlmap.pop(c))
            c.Destroy()


    def _ToggleControls(self, edit):
        """Toggles controls editable/readonly, updates buttons state."""
        self.Freeze()
        for b in self._buttons.values():
            action = getattr(b, "_toggle", None) or []
            if callable(action): action = action() or []
            if "disable" in action: b.Enable(not edit)
            if "show"    in action: b.Show(edit)
            if not ("disable" in action or "skip" in action): b.Enable(edit)
        self._buttons["edit"].Label = "Save" if edit else "Edit"
        for c in self._ctrls.values():
            action = getattr(c, "_toggle", None) or []
            if callable(action): action = action() or []
            if   "skip"    in action: continue # for c
            if "disable" in action: c.Enable(not edit)                
            if "disable" not in action:
                if isinstance(c, (wx.ComboBox, wx.stc.StyledTextCtrl)): c.Enable(edit)
                else:
                    try: c.SetEditable(edit)
                    except Exception: c.Enable(edit)
        self._PopulateAutoComp()
        if "table" == self._category:
            self._ctrls["alter"].Show(edit and self._has_alter)
            self._ctrls["alter"].ContainingSizer.Layout()
        for c in (c for n, c in vars(self).items() if n.startswith("_panel_")):
            c.Layout()
        self.Layout()
        self.Thaw()


    def _PopulateAutoComp(self):
        """Populate SQLiteTextCtrl autocomplete."""
        if not self._editmode: return
            
        words, subwords, singlewords = [], {}, []

        for category in ("table", "view"):
            for item in self._db.get_category(category).values():
                if self._category in ("trigger", "view"):
                    myname = grammar.quote(item["name"])
                    words.append(myname)
                if not item.get("columns"): continue # for item
                ww = [grammar.quote(c["name"]) for c in item["columns"]]

                if "table" == self._category \
                and item["name"] == self._original.get("name") \
                or self._category in ("index", "trigger") \
                and item["name"] == self._item["meta"].get("table"):
                    singlewords = ww
                if self._category in ("trigger", "view"): subwords[myname] = ww

        for c in self._ctrls.values():
            if not isinstance(c, controls.SQLiteTextCtrl): continue # for c
            c.AutoCompClearAdded()
            if c is self._ctrls.get("when"):
                for w in "OLD", "NEW": c.AutoCompAddSubWords(w, singlewords)
            elif not words or c.IsSingleLine(): c.AutoCompAddWords(singlewords)
            elif words:
                c.AutoCompAddWords(words)
                for w, ww in subwords.items(): c.AutoCompAddSubWords(w, ww)



    def _PopulateSQL(self):
        """Populates CREATE SQL window."""
        sql, _ = grammar.generate(self._item["meta"])
        if sql is not None: self._item["sql"] = sql
        if self._show_alter: sql = self._GetAlterSQL()
        if sql is None: return
        scrollpos = self._ctrls["sql"].GetScrollPos(wx.VERTICAL)
        self._ctrls["sql"].SetReadOnly(False)
        self._ctrls["sql"].SetText(sql + "\n")
        self._ctrls["sql"].SetReadOnly(True)
        self._ctrls["sql"].ScrollToLine(scrollpos)


    def _GetAlterSQL(self):
        """
        Returns ALTER SQL for table changes.
        """
        result = ""
        old, new = self._original["meta"], self._item["meta"]

        can_simple = True
        cols1, cols2 = (x.get("columns", []) for x in (old, new))
        colmap1 = {c["__id__"]: c for c in cols1}
        colmap2 = {c["__id__"]: c for c in cols2}

        for k in "temporary", "exists", "without", "constraints":
            if bool(new.get(k)) != bool(old.get(k)):
                can_simple = False # Top-level flag or constraints existence changed
        if can_simple:
            cnstr1_sqls = [grammar.generate(dict(c, __type__="constraint"))[0]
                          for c in old.get("constraints") or []]
            cnstr2_sqls = [grammar.generate(dict(c, __type__="constraint"))[0]
                          for c in new.get("constraints") or []]
            # Table constraints changed
            can_simple = (cnstr1_sqls == cnstr2_sqls)
        if can_simple and any(x not in colmap2 for x in colmap1):
            can_simple = False # There are deleted columns
        if can_simple and any(colmap2[x]["name"] != colmap1[x]["name"] for x in colmap1):
            can_simple = self._db.has_rename_column() # There are renamed columns
        if can_simple:
            if any(x["__id__"] not in colmap1 and cols2[i+1]["__id__"] in colmap1
                   for i, x in enumerate(cols2[:-1])):
                can_simple = False # There are new columns in between
        if can_simple:
            for i, c1 in enumerate(cols1):
                if cols2[i]["__id__"] != c1["__id__"]:
                    can_simple = False # Column order changed
                    break # for i, c1
        if can_simple:
            cols1_sqls = [grammar.generate(dict(c, name="", __type__="column"))[0]
                          for c in cols1]
            cols2_sqls = [grammar.generate(dict(c, name="", __type__="column"))[0]
                          for c in cols2]
            can_simple = (cols1_sqls == cols2_sqls) # Column definition changed


        if can_simple:
            # Possible to use just simple ALTER TABLE statements
            sqls, base = [], dict(name=old["name"], __type__="ALTER TABLE")

            for c2 in cols2:
                c1 = colmap1.get(c2["__id__"])
                if c1 and c1["name"] != c2["name"]:
                    args = dict(rename={"column": {c1["name"]: c2["name"]}}, **base)
                    sqls.append(grammar.generate(args)[0])

            for c2 in cols2:
                c1 = colmap1.get(c2["__id__"])
                if not c1:
                    sqls.append(grammar.generate(dict(add=c2, **base))[0])

            if old["name"] != new["name"]:
                args = dict(rename={"table": new["name"]}, **base)
                sqls.append(grammar.generate(args)[0])
            result = ";\n\n".join(sqls) + (";" if sqls else "")

        else:
            # Need to re-create table, first under temporary name to copy data.
            tables_existing = list(self._db.schema["table"])
            def make_tempname(name):
                tempname, counter = "%s_temp" % name.lower(), 2
                while tempname in tables_existing:
                    counter += 1
                    tempname = "%s_temp_%s" % (name.lower(), counter)
                tables_existing.append(tempname)
                return tempname

            tempname = make_tempname(new["name"])
            meta = copy.deepcopy(self._item["meta"])
            util.walk(meta, (lambda x, *_: isinstance(x, dict)
                             and x.get("table") == old["name"]
                             and x.update(table=tempname))) # Rename in constraints
            meta["name"] = tempname

            args = {"name": old["name"], "name2": new["name"], "tempname": tempname,
                    "fks": self._fks_on, "meta": meta, "__type__": "COMPLEX ALTER TABLE",
                    "columns": [(colmap1[c2["__id__"]]["name"], c2["name"])
                                for c2 in cols2 if c2["__id__"] in colmap1]}

            renames = {"table":  {old["name"]: new["name"]}
                                 if old["name"] != new["name"] else {},
                       "column": {colmap1[c2["__id__"]]["name"]: c2["name"]
                                  for c2 in cols2 if c2["__id__"] in colmap1
                                  and colmap1[c2["__id__"]]["name"] != c2["name"]}}
            for k, v in renames.items(): renames.pop(k) if not v else None
            for category in "table", "index", "trigger", "view":
                if not renames and category in ("view", "table"):
                    continue # for category
                for item in self._db.get_category(category, table=old["name"]).values():
                    if "table" == category and item["name"] == old["name"]:
                        continue # for item

                    mytempname = make_tempname(item["name"])
                    myrenames = dict(renames)
                    myrenames.setdefault("table", {})[item["name"]] = mytempname
                    sql, _ = grammar.transform(item["sql"], renames=myrenames)
                    myitem = dict(item, sql=sql, tempname=mytempname)
                    args.setdefault(category, []).append(myitem)

                    for subcategory in ("index", "trigger") if "table" == category else ():
                        # Re-create table indexes and triggers
                        for subitem in self._db.get_category(subcategory, table=item["name"]).values():
                            if subitem["meta"]["table"].lower() == item["name"].lower():
                                sql, _ = grammar.transform(subitem["sql"], renames=renames) \
                                         if renames else subitem["sql"]
                                args.setdefault(subcategory, []).append(dict(subitem, sql=sql))

            result, _ = grammar.generate(args)

        return result


    def _GetColumnTypes(self):
        """
        Returns a list of available column types,
        SQLite defaults + defined in database + defined locally.
        """
        result = set([""] + list(database.Database.AFFINITY))
        uppers = set(x.upper() for x in result)
        tt = self._db.get_category("table").values()
        if "table" == self._category: tt.append(self._item)
        for table in tt:
            for c in table.get("columns") or ():
                t = c.get("type")
                if not t or t.upper() in uppers: continue # for c
                result.add(t); uppers.add(t.upper())
        return sorted(result)


    def _GetMoveButtonToggle(self, button, direction):
        """
        Returns function, returning a list with ["show", "disable"]
        depending on editmode and direction.
        """
        def inner():
            result = ["show"]
            if not self._editmode: return result

            indexitem, parentsizer = button, button.ContainingSizer
            while parentsizer is not button.Parent.Sizer:
                indexitem = parentsizer
                parentsizer = self._sizers.get(indexitem)
            index = button.Parent.Sizer.GetItemIndex(indexitem) / button.Parent.Sizer.Cols
            count = len(button.Parent.Sizer.Children) / button.Parent.Sizer.Cols

            if index + direction < 0 or index + direction >= count:
                result.append("disable")
            return result
        return inner


    def _GetSizerChildren(self, sizer):
        """Returns all the nested child components of a sizer."""
        result = []
        for x in sizer.Children:
            if x.IsWindow() : result.append(x.GetWindow())
            elif x.IsSizer(): result.extend(self._GetSizerChildren(x.GetSizer()))
        return result
        

    def _GetFormDialogProps(self, path, data):
        """Returns (title, field properties) for table column or constraint FormDialog."""
        
        def get_foreign_cols(data):
            result = []
            if data and data.get("table"):
                ftable = self._db.get_category("table", data["table"])
                result = [x["name"] for x in ftable.get("columns") or ()]
            return result

        def get_table_cols(data):
            return [x["name"] for x in self._item["meta"].get("columns") or ()]


        if "columns" == path[0]: return [
            {"name": "name",    "label": "Name"},
            {"name": "type",    "label": "Type", "choices": self._types, "choicesedit": True},
            {"name": "default", "label": "Default", "component": controls.SQLiteTextCtrl},
            {"name": "pk", "label": "PRIMARY KEY", "toggle": True, "children": [
                {"name": "autoincrement", "label": "AUTOINCREMENT", "type": bool},
                {"name": "order", "label": "Order", "toggle": True, "choices": self.ORDER,
                 "help": "If DESC, an integer key is not an alias for ROWID."},
                {"name": "conflict", "label": "ON CONFLICT", "toggle": True, "choices": self.CONFLICT},
            ]},
            {"name": "notnull", "label": "NOT NULL", "toggle": True, "children": [
                {"name": "conflict", "label": "ON CONFLICT", "toggle": True, "choices": self.CONFLICT},
            ]},
            {"name": "unique", "label": "UNIQUE", "toggle": True, "children": [
                {"name": "conflict", "label": "ON CONFLICT", "toggle": True, "choices": self.CONFLICT},
            ]},
            {"name": "fk", "label": "FOREIGN KEY", "toggle": True, "children": [
                {"name": "table",  "label": "Foreign table", "choices": self._tables, "link": "key"},
                {"name": "key",    "label": "Foreign column", "choices": get_foreign_cols},
                {"name": "delete", "label": "ON DELETE", "toggle": True, "choices": self.ON_ACTION},
                {"name": "update", "label": "ON UPDATE", "toggle": True, "choices": self.ON_ACTION},
                {"name": "match",   "label": "MATCH", "toggle": True, "choices": self.MATCH,
                 "help": "Not enforced by SQLite."},
                {"name": "defer",  "label": "DEFERRABLE", "toggle": True,
                 "help": "Foreign key constraint enforced on COMMIT vs immediately",
                 "children": [
                    {"name": "not",     "label": "NOT", "type": bool, "help": "Whether enforced immediately"},
                    {"name": "initial", "label": "INITIALLY", "choices": self.DEFERRABLE},
                ]},
            ]},
            {"name": "check",   "label": "CHECK",   "toggle": True, "component": controls.SQLiteTextCtrl,
             "help": "Expression yielding a NUMERIC 0 on constraint violation,\ncannot contain a subquery."},
            {"name": "collate", "label": "COLLATE", "toggle": True, "choices": self.COLLATE, "choicesedit": True,
             "help": "Collating sequence to use for the column (defaults to BINARY)."},
        ]

        if grammar.SQL.FOREIGN_KEY == data["type"]: return [
            {"name": "columns", "label": "Local column", "type": list, "choices": get_table_cols},
            {"name": "table",   "label": "Foreign table", "choices": self._tables, "link": "key"},
            {"name": "key",     "label": "Foreign column", "type": list, "choices": get_foreign_cols},
            {"name": "delete",  "label": "ON DELETE", "toggle": True, "choices": self.ON_ACTION},
            {"name": "update",  "label": "ON UPDATE", "toggle": True, "choices": self.ON_ACTION},
            {"name": "match",   "label": "MATCH", "toggle": True, "choices": self.MATCH,
             "help": "Not enforced by SQLite."},
            {"name": "defer",   "label": "DEFERRABLE", "toggle": True,
             "help": "Foreign key constraint enforced on COMMIT vs immediately",
             "children": [
                {"name": "not",     "label": "NOT", "type": bool, "help": "Whether enforced immediately"},
                {"name": "initial", "label": "INITIALLY", "choices": self.DEFERRABLE},
            ]},
        ]

        if data["type"] in (grammar.SQL.PRIMARY_KEY, grammar.SQL.UNIQUE): return [
            {"name": "columns",  "label": "Index",
             "type": (lambda *a, **kw: self._CreateDialogConstraints(*a, **kw))},
            {"name": "conflict", "label": "ON CONFLICT", "choices": self.CONFLICT},
        ]


    def _CreateDialogConstraints(self, dialog, field, parent, data):
        """Populates FormDialog with primary key / unique constraints."""

        def on_add(event=None):
            data["key"].append({"name": ""})
            populate_rows(focus=True)

        def on_move(index, direction, event=None):
            index2, ptr = index + direction, data["key"]
            ptr[index], ptr[index2] = ptr[index2], ptr[index]
            populate_rows()

        def on_remove(index, event=None):
            del data["key"][index]
            populate_rows()

        def populate_rows(focus=False):
            """"""
            dialog.Freeze()
            self._EmptyControl(panel_columns)
            for i, col in enumerate(data.get("key") or ()): add_row(i, col, focus)
            dialog.Layout()
            dialog.Thaw()

        def size_dialog():
            w = 530 if dialog._editmode else 460
            dialog.Size = dialog.MinSize = (w, dialog.Size[1])


        tablecols = [x["name"] for x in self._item["meta"].get("columns") or ()]

        panel_wrapper = wx.Panel(parent, style=wx.BORDER_STATIC)
        sizer_wrapper = panel_wrapper.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_columnstop = wx.FlexGridSizer(cols=3, hgap=10)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

        panel_columns = wx.lib.scrolledpanel.ScrolledPanel(panel_wrapper)
        panel_columns.Sizer = wx.FlexGridSizer(cols=4, vgap=4, hgap=10)
        panel_columns.Sizer.AddGrowableCol(3)

        button_add_column = wx.Button(panel_wrapper, label="&Add column")

        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Column",  size=(250, -1)))
        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Collate", size=( 80, -1)))
        sizer_columnstop.Add(wx.StaticText(panel_wrapper, label="Order",   size=( 60, -1)))

        sizer_wrapper.Add(sizer_columnstop, border=5, flag=wx.LEFT | wx.TOP | wx.BOTTOM | wx.GROW)
        sizer_wrapper.Add(panel_columns, border=5, proportion=1, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.GROW)
        sizer_wrapper.Add(button_add_column, border=5, flag=wx.TOP | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT)

        parent.Sizer.Add(panel_wrapper, border=10, pos=(dialog._rows, 0), span=(1, 12), flag=wx.BOTTOM)

        if not dialog._editmode: button_add_column.Hide()
        panel_columns.MinSize = (-1, 60)
        panel_columns.SetupScrolling(scroll_x=False)
        dialog._BindHandler(on_add, button_add_column)
        wx.CallAfter(size_dialog)

        def add_row(i, col, focus=False):
            """Adds a new row of controls for key column."""
            first, last = not i, (i == len(data["key"]) - 1)

            sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)

            ctrl_index = wx.ComboBox(panel_columns, choices=tablecols,
                style=wx.CB_DROPDOWN | wx.CB_READONLY)
            list_collate  = wx.ComboBox(panel_columns, choices=self.COLLATE, style=wx.CB_DROPDOWN)
            list_order    = wx.ComboBox(panel_columns, choices=self.ORDER, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            button_up     = wx.Button(panel_columns, label=u"\u2191", size=(20, -1))
            button_down   = wx.Button(panel_columns, label=u"\u2193", size=(20, -1))
            button_remove = wx.Button(panel_columns, label=u"\u2715", size=(20, -1))

            ctrl_index.MinSize =   (250, -1)
            list_collate.MinSize = ( 80, -1)
            list_order.MinSize =   ( 60, -1)
            if first: button_up.Enable(False)
            if last:  button_down.Enable(False)
            button_up.ToolTipString     = "Move one step higher"
            button_down.ToolTipString   = "Move one step lower"
            button_remove.ToolTipString = "Remove"                    

            ctrl_index.Value   = col.get("name") or ""
            list_collate.Value = col.get("collate") or ""
            list_order.Value   = col.get("order") or ""

            sizer_buttons.Add(button_up)
            sizer_buttons.Add(button_down)
            sizer_buttons.Add(button_remove)

            panel_columns.Sizer.Add(ctrl_index)
            panel_columns.Sizer.Add(list_collate)
            panel_columns.Sizer.Add(list_order)
            panel_columns.Sizer.Add(sizer_buttons, border=5, flag=wx.RIGHT | wx.ALIGN_RIGHT)

            if dialog._editmode:
                path = ["key", i]
                dialog._BindHandler(dialog._OnChange, ctrl_index,   {"name": "name"},   path)
                dialog._BindHandler(dialog._OnChange, list_collate, {"name": "collate"}, path)
                dialog._BindHandler(dialog._OnChange, list_order,   {"name": "order"},   path)
                dialog._BindHandler(on_move,   button_up,     i, -1)
                dialog._BindHandler(on_move,   button_down,   i, +1)
                dialog._BindHandler(on_remove, button_remove, i)
            else:
                ctrl_index.Enable(False)
                list_collate.Enable(False)
                list_order.Enable(False)
                sizer_buttons.ShowItems(False)
            if focus: ctrl_index.SetFocus()

        wx_accel.accelerate(panel_wrapper)
        populate_rows()


    def _PostEvent(self, **kwargs):
        """Posts an EVT_SCHEMA_PAGE event to parent."""
        wx.PostEvent(self, SchemaPageEvent(-1, source=self, item=self._item, **kwargs))


    def _AddSizer(self, parentsizer, childsizer, *args, **kwargs):
        """
        Adds the child sizer to parent sizer and registers the nesting,
        for index lookup in handlers.

        @param   insert  if numeric, sizer is inserted at index instead of added
        """
        index = kwargs.pop("insert", None)
        if index is None: parentsizer.Add(childsizer, *args, **kwargs)
        else: parentsizer.Insert(index, childsizer, *args, **kwargs)
        self._sizers[childsizer] = parentsizer        


    def _RemoveSizer(self, sizer):
        """
        Clears registered sizer and all its registered child sizers.
        """
        self._sizers.pop(sizer, None)
        for x in sizer.Children:
            if x.IsSizer(): self._RemoveSizer(x.GetSizer())


    def _AddRow(self, path, i, value, insert=False, focus=False):
        """Adds a new row of controls for value at path index."""
        panel = self._panel_columns
        if "table" == self._category:
            adder = self._AddRowTable
            if "constraints" == path[-1]:
                adder, panel = self._AddRowTableConstraint, self._panel_constraints
        elif "index"   == self._category: adder = self._AddRowIndex
        elif "trigger" == self._category: adder = self._AddRowTrigger
        elif "view"    == self._category: adder = self._AddRowView
        adder(path, i, value, insert=insert, focus=focus)
        panel.Layout()

        if "table" == self._category:
            label, count = path[0].capitalize(), len(self._item["meta"].get(path[0]) or ())
            if count: label = "%s (%s)" % (label, count)
            self._notebook_table.SetPageText(0 if ["columns"] == path else 1, label)
        self._panel_category.Layout()


    def _RemoveRow(self, path, index):
        """
        Removes row components from parent's FlexGridSizer.
        """
        buttonmap = {v: k for k, v in self._buttons.items()}
        ctrlmap   = {v: k for k, v in self._ctrls.items()}
        parent = self._panel_columns if "columns" == path[-1] else self._panel_constraints
        comps, cols = [], parent.Sizer.Cols
        for i in range(cols * index, cols * index + cols)[::-1]:
            sizeritem = parent.Sizer.Children[i]
            if sizeritem.IsWindow(): comps.append(sizeritem.GetWindow())
            elif sizeritem.IsSizer():
                comps.extend(self._GetSizerChildren(sizeritem.GetSizer()))
            parent.Sizer.Remove(i)
        for c in comps:
            if c in buttonmap: self._buttons.pop(buttonmap.pop(c))
            elif c in ctrlmap: self._ctrls  .pop(ctrlmap.pop(c))
            c.Destroy()

        if "table" == self._category:
            label, count = path[0].capitalize(), len(self._item["meta"].get(path[0]) or ())
            if count: label = "%s (%s)" % (label, count)
            self._notebook_table.SetPageText(0 if ["columns"] == path else 1, label)
        parent.Layout()


    def _OnAddConstraint(self, event):
        """Opens popup for choosing constraint type."""
        menu = wx.Menu()

        def add_constraint(ctype, *_, **__):
            constraint = copy.deepcopy(self.TABLECONSTRAINT_DEFAULTS[ctype])
            constraints = self._item["meta"].setdefault("constraints", [])
            constraints.append(constraint)
            self._AddRowTableConstraint(["constraints"], len(constraints) - 1,
                                        constraint, focus=True)
            self._ToggleControls(self._editmode)

            label, count = "Constraints", len(self._item["meta"].get("constraints") or ())
            if count: label = "%s (%s)" % (label, count)
            self._notebook_table.SetPageText(1, label)

            self._panel_constraints.Layout()
            self._panel_category.Layout()

        menu = wx.Menu()
        for ctype in self.TABLECONSTRAINT:
            it = wx.MenuItem(menu, -1, ctype)
            menu.AppendItem(it)
            menu.Bind(wx.EVT_MENU, functools.partial(add_constraint, ctype), id=it.GetId())
        event.EventObject.PopupMenu(menu, tuple(event.EventObject.Size))


    def _OnAddItem(self, path, value, event=None):
        """Adds value to object meta at path, adds item controls."""
        ptr = parent = self._item["meta"]
        for i, p in enumerate(path):
            ptr = ptr.get(p)
            if ptr is None: ptr = parent[p] = {} if i < len(path) - 1 else []
            parent = ptr
        if "table" == self._category and "columns" == path[-1]:
            value = dict(value, __id__=wx.NewId())
        ptr.append(copy.deepcopy(value))
        panel = self._panel_columns if "columns" == path[-1] else self._panel_constraints
        self.Freeze()
        self._AddRow(path, len(ptr) - 1, value, focus=True)
        self._PopulateSQL()
        self._ToggleControls(self._editmode)
        self.Layout()
        self.Thaw()
        self._PostEvent(modified=True)


    def _OnRemoveItem(self, path, event=None):
        """Removes item from object meta and item controls from panel at path."""
        path, index = path[:-1], path[-1]
        ptr = self._item["meta"]
        for i, p in enumerate(path): ptr = ptr.get(p)
        mydata = ptr[index]
        ptr[index:index+1] = []
        self.Freeze()
        self._RemoveRow(path, index)

        if "table" == self._category and "columns" == path[0]:
            # Queue removing column from constraints
            myid = mydata["__id__"]
            if myid in self._col_updates:
                self._col_updates[myid]["remove"] = True
            else:
                self._col_updates[myid] = {"col": copy.deepcopy(mydata), "remove": True}
            if self._col_updater: self._col_updater.Stop()
            self._col_updater = wx.CallLater(1000, self._OnCascadeColumnUpdates)

        self._PopulateSQL()
        self._ToggleControls(self._editmode)
        self.Layout()
        self.Thaw()
        self._PostEvent(modified=True)


    def _OnMoveItem(self, path, direction, event=None):
        """Swaps the order of two meta items at path."""
        path, index = path[:-1], path[-1]
        ptr = self._item["meta"]
        for i, p in enumerate(path): ptr = ptr.get(p)
        index2 = index + direction
        ptr[index], ptr[index2] = ptr[index2], ptr[index]
        self.Freeze()
        self._RemoveRow(path, index)
        self._AddRow(path, index2, ptr[index2], insert=True)
        self._PopulateSQL()
        self._ToggleControls(self._editmode)
        self.Thaw()
        self._PostEvent(modified=True)


    def _OnOpenItem(self, path, event=None):
        """Opens a FormDialog for row item."""
        data  = util.get(self._item["meta"], path)
        props = self._GetFormDialogProps(path, data)

        words = []
        for category in ("table", "view") if self._editmode else ():
            for item in self._db.get_category(category).values():
                if not item.get("columns"): continue # for item
                if "table" == self._category and item["name"] == self._original.get("name") \
                or "index" == self._category and item["name"] == self._item["meta"].get("table"):
                    words = [grammar.quote(c["name"]) for c in item["columns"]]
                    break

        title = "Table column"
        if "constraints" == path[0]:
            title = "%s constraint" % data["type"]
        dlg = controls.FormDialog(self.TopLevelParent, title, props, data,
                                  self._editmode, autocomp=words)
        wx_accel.accelerate(dlg)
        if wx.OK != dlg.ShowModal() or not self._editmode: return
        data2 = dlg.GetData()
        if data == data2: return

        util.set(self._item["meta"], data2, path)
        self.Freeze()
        path2, index = path[:-1], path[-1]
        self._RemoveRow(path2, index)
        self._AddRow(path2, index, data2, insert=True)
        self._PopulateSQL()
        self._ToggleControls(self._editmode)
        self.Thaw()
        self._PostEvent(modified=True)


    def _OnChange(self, path, event):
        """Handler for changing a value in a control, updates data and SQL."""
        if self._ignore_change: return

        path = [path] if isinstance(path, basestring) else path
        rebuild, meta = False, self._item["meta"]
        value0 = util.get(meta, path)

        value = event.EventObject.Value
        if isinstance(value, basestring) \
        and (not isinstance(event.EventObject, wx.stc.StyledTextCtrl)
        or not value.strip()): value = value.strip()
        if isinstance(value0, list) and not isinstance(value, list):
            value = [value]

        if value == value0: return
        util.set(meta, value, path)

        if "trigger" == self._category:
            # Trigger special: INSTEAD OF UPDATE triggers on a view
            if ["upon"] == path and grammar.SQL.INSTEAD_OF in (value0, value) \
            or ["action"] == path and grammar.SQL.INSTEAD_OF == meta.get("upon") \
            and grammar.SQL.UPDATE in (value0, value):
                rebuild = True
                meta.pop("columns", None), meta.pop("table", None)
            if ["table"] == path: self._PopulateAutoComp()
        elif "table" == self._category:
            if "constraints" == path[0] and "table" == path[-1]:
                # Foreign table changed, clear foreign cols
                path2, fkpath, index = path[:-2], path[:-1], path[-2]
                data2 = util.get(meta, fkpath)
                if data2.get("key"): data2["key"][:] = []
                self.Freeze()
                self._RemoveRow(path2, index)
                self._AddRow(path2, index, data2, insert=True)
                self.Thaw()
            elif "columns" == path[0] and "name" == path[-1]:
                col = util.get(meta, path[:-1])
                if value0 and not value: col["name_last"] = value0
                myid = col["__id__"]
                if myid in self._col_updates:
                    self._col_updates[myid].update(rename=value)
                else:
                    col = copy.deepcopy(dict(col, name=value0))
                    self._col_updates[myid] = {"col": col, "rename": value}

                if self._col_updater: self._col_updater.Stop()
                self._col_updater = wx.CallLater(1000, self._OnCascadeColumnUpdates)
                
        elif ["table"] == path:
            rebuild = meta.get("columns")
            meta.pop("columns", None)
                

        self._Populate() if rebuild else self._PopulateSQL()
        self._PostEvent(modified=True)


    def _OnCascadeColumnUpdates(self):
        """Handler for column updates, rebuilds constraints on rename/remove."""
        self._col_updater = None
        constraints = self._item["meta"].get("constraints") or []
        changed, renames = False, {} # {old column name: new name}

        for myid, opts in self._col_updates.items():
            name = opts["col"].get("name") or opts["col"].get("name_last")

            if opts.get("remove"):
                # Skip constraint drop if we have no name to match
                if not name: continue # for myid, opts

                for i, cnstr in list(enumerate(constraints))[::-1]:
                    if cnstr["type"] in (grammar.SQL.PRIMARY_KEY, grammar.SQL.UNIQUE):
                        keys, keychanged = cnstr.get("key") or [], False
                        for j, col in list(enumerate(keys))[::-1]:
                            if col.get("name") == name:
                                del keys[j]
                                changed = keychanged = True
                        if not keys and keychanged: del constraints[i]

                    elif cnstr["type"] in (grammar.SQL.FOREIGN_KEY, ):
                        keychanged = False
                        if name in cnstr.get("columns", []):
                            cnstr["columns"] = [x for x in cnstr["columns"] if x != name]
                            changed = keychanged = True
                        if cnstr.get("table") == self._item.get("name") \
                        and name in cnstr.get("key", []):
                            cnstr["key"] = [x for x in cnstr["key"] if x != name]
                            changed = True
                        if keychanged and not cnstr["columns"]: del constraints[i]
                continue # for myid, opts

            if name and opts.get("rename"):
                renames[name] = opts["rename"]

        self._col_updates = {}
        if not changed and not renames: return

        if renames:
            sql, err = grammar.transform(self._item["sql"], renames={"column": renames})
            if err: return
            meta, err = grammar.parse(sql)
            if err: return

            for i, c in enumerate(self._item["meta"]["columns"]):
                meta["columns"][i]["__id__"] = c["__id__"]
            self._item.update(sql=sql, meta=meta)
            constraints = self._item["meta"].get("constraints") or []

        self.Freeze()
        self._EmptyControl(self._panel_constraints)
        for i, cnstr in enumerate(constraints):
            self._AddRowTableConstraint(["constraints"], i, cnstr)
        self._panel_constraints.Layout()
        self._notebook_table.SetPageText(1, "Constraints" if not constraints
                                         else "Constraints (%s)" % len(constraints))
        self._PopulateSQL()
        self.Thaw()


    def _OnToggleColumnFlag(self, path, rowkey, event):
        """Toggles PRIMARY KEY / NOT NULL / UNIQUE flag."""
        path, flag = path[:-1], path[-1]
        col = util.get(self._item["meta"], path)

        check_autoinc = self._ctrls["columns.autoinc.%s" % rowkey]
        if event.EventObject.Value:
            col[flag] = {}
            if "pk" == flag: check_autoinc.Enable()
        else:
            col.pop(flag, None)
            if "pk" == flag:
                check_autoinc.Enable(False)
                check_autoinc.Value = False
        self._PopulateSQL()


    def _OnToggleAlterSQL(self, event=None):
        """Toggles showing ALTER SQL statement instead of CREATE SQL."""
        self._show_alter = not self._show_alter
        self._label_sql.Label = "ALTER TABLE SQL:" if self._show_alter else "CREATE SQL:"
        self._ctrls["alter"].Value = self._show_alter
        self._PopulateSQL()


    def _OnCopySQL(self, event=None):
        """Handler for copying SQL to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(self._ctrls["sql"].GetText())
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied SQL to clipboard", flash=True)


    def _OnSaveSQL(self, event=None):
        """
        Handler for saving SQL to file, opens file dialog and saves content.
        """
        action, category = "CREATE", self._category.upper()
        name = self._item["meta"].get("name") or ""
        if self._show_alter:
            action, name = "ALTER", self._original["name"]
        filename = " ".join((action, category, name))
        dialog = wx.FileDialog(
            parent=self, message="Save as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = dialog.GetPath()
        title = " ".join(filter(bool, (category, grammar.quote(name))))
        if self._show_alter: title = " ".join((action, title))
        try:
            content = step.Template(templates.CREATE_SQL, strip=False).expand(
                title=title, db_filename=self._db.name,
                sql=self._ctrls["sql"].GetText())
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving SQL to %s." % filename
            logger.exception(msg); guibase.status(msg, flash=True)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def _OnImportSQL(self, event=None):
        """Handler for importing from external SQL, opens dialog."""
        props = [{"name": "sql", "label": "SQL:", "component": controls.SQLiteTextCtrl,
                  "tb": [{"type": "paste", "help": "Paste from clipboard"},
                         {"type": "open",  "help": "Load from file"}, ]}]
        title = "Import definition from SQL"
        dlg = controls.FormDialog(self.TopLevelParent, title, props)
        wx_accel.accelerate(dlg)
        if wx.OK != dlg.ShowModal(): return
        sql = dlg.GetData().get("sql", "").strip()
        if not sql: return
            
        logger.info("Importing %s definition from SQL:\n\n%s", self._category, sql)
        meta, err = grammar.parse(sql, self._category)
        if not meta:
            return wx.MessageBox("Failed to parse SQL.\n\n%s" % err,
                                 conf.Title, wx.OK | wx.ICON_ERROR)

        if "table" == self._category:
            if self._show_alter: self._OnToggleAlterSQL()
            self._has_alter = False

        self._item.update(sql=sql, meta=self._AssignColumnIDs(meta))
        self._Populate()
        self._ToggleControls(self._editmode)


    def _OnRefresh(self, event=None):
        """Handler for clicking refresh, updates database data in controls."""
        self._db.populate_schema()
        prevs = {"_types": self._types, "_tables": self._tables,
                 "_views": self._views, "_item": self._item}
        self._types = self._GetColumnTypes()
        self._tables = [x["name"] for x in self._db.get_category("table").values()]
        self._views  = [x["name"] for x in self._db.get_category("view").values()]
        if not self._editmode:
            item = self._db.get_category(self._category, self._item["name"])
            if not item: return wx.MessageBox(
                "%s %s no longer present in the database." %
                (self._category.capitalize(), grammar.quote(self._item["name"])),
                conf.Title, wx.OK | wx.ICON_ERROR
            )

            item = dict(item, meta=self._AssignColumnIDs(item["meta"]))
            self._item, self._original = copy.deepcopy(item), copy.deepcopy(item)

        if any(prevs[x] == getattr(self, x) for x in prevs):
            self._Populate()
            self._ToggleControls(self._editmode)


    def _OnSaveOrEdit(self, event=None):
        """Handler for clicking save in edit mode, or edit in view mode."""
        self._OnSave() if self._editmode else self._OnToggleEdit()


    def _OnToggleEdit(self, event=None):
        """Handler for toggling edit mode."""
        is_changed =  self.IsChanged()
        if is_changed and wx.OK != wx.MessageBox(
            "There are unsaved changes, "
            "are you sure you want to discard them?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        self._editmode = not self._editmode

        if self._newmode and not self._editmode:
            self._newmode = False
            self._PostEvent(close=True)
            return

        if self._editmode:
            self._has_alter = ("table" == self._category)
            self._ToggleControls(self._editmode)
        else:
            if self._show_alter: self._OnToggleAlterSQL()
            if is_changed: self._OnRefresh()
            else:
                self._item = copy.deepcopy(self._original)
                self._ToggleControls(self._editmode)
        self._PostEvent(modified=True)


    def _OnClose(self, event=None):
        """Handler for clicking to close the item, sends message to parent."""
        if self._editmode and self.IsChanged() and wx.OK != wx.MessageBox(
            "There are unsaved changes, "
            "are you sure you want to discard them?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return
        self._editmode = self._newmode = False
        self._PostEvent(close=True)


    def _OnSave(self, event=None):
        """Handler for clicking to save the item, validates and saves, returns success."""
        if not self._newmode and not self.IsChanged():
            self._OnToggleEdit()
            return True

        errors, meta, meta2 = [], self._item["meta"], None
        name = meta.get("name") or ""

        if not name:
            errors += ["Name is required."]
        if self._category in ("index", "trigger") and not meta.get("table"):
            if "trigger" == self._category and "INSTEAD OF" == meta.get("upon"):
                errors += ["View is required."]
            else:
                errors += ["Table is required."]
        if "trigger" == self._category and not meta.get("body"):
            errors += ["Body is required."]
        if "view"    == self._category and not meta.get("select"):
            errors += ["Select is required."]
        if "table"   == self._category and not meta.get("columns"):
            errors += ["Columns are required."]

        if (self._newmode or name.lower() != self._item["name"].lower()) \
        and self._db.get_category(self._category, name):
            errors += ["%s named %s already exists." % (self._category.capitalize(),
                       grammar.quote(name, force=True))]
        if not errors:
            meta2, err = grammar.parse(self._item["sql"])
            if not meta2: errors += [err[:200] + (".." if len(err) > 200 else "")]
        if errors:
            wx.MessageBox("Errors:\n\n%s" % "\n\n".join(errors),
                          conf.Title, wx.OK | wx.ICON_WARNING)
            return

        sql, drop = self._item["sql"] + ";", not self._newmode
        oldname = None if self._newmode else grammar.quote(self._item["name"])
        if "table" == self._category and self._has_alter:
            # Do ALTER TABLE if table has any content
            if self._db.execute("SELECT 1 FROM %s LIMIT 1" % oldname).fetchone():
                sql, drop = self._GetAlterSQL(), False

        fullsql = sql
        if oldname:
            fullsql = "SAVEPOINT save;\n\n%s%s\n\nRELEASE SAVEPOINT save;" % \
                      ("DROP %s %s;\n\n" % (self._category.upper(), oldname)
                       if drop else "", sql)

        logger.info("Executing schema SQL:\n\n%s", fullsql)
        try: self._db.connection.executescript(fullsql)
        except Exception as e:
            logger.exception("Error executing SQL.")
            try: oldname and self._db.execute("ROLLBACK")
            except Exception: pass
            try: self._fks_on and self._db.execute("PRAGMA foreign_keys = on")
            except Exception: pass
            msg = "Error saving changes:\n\n%s" % util.format_exc(e)
            wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
            return

        self._item.update(name=name, meta=self._AssignColumnIDs(meta2))
        self._original = copy.deepcopy(self._item)
        self._newmode = self._editmode = False
        if self._show_alter: self._OnToggleAlterSQL()
        self._has_alter = ("table" == self._category)
        self._ToggleControls(self._editmode)
        self._PostEvent(updated=True)
        return True


    def _OnDelete(self, event=None):
        """Handler for clicking to delete the item, asks for confirmation."""
        extra = "\n\nAll data, and any associated indexes and triggers will be lost." \
                if "table" == self._category else ""                    
        if wx.OK != wx.MessageBox(
            "Are you sure you want to delete the %s %s?%s" %
            (self._category, grammar.quote(self._item["name"], force=True), extra),
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING
        ): return

        if "table" == self._category and self._item.get("count") \
        and wx.OK != wx.MessageBox(
            "Are you REALLY sure you want to delete the %s %s?\n\n"
            "It currently contains %s." %
            (self._category, grammar.quote(self._item["name"], force=True),
             util.plural("row", self._item["count"])),
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING
        ): return

        self._db.execute("DROP %s %s" % (self._category, grammar.quote(self._item["name"])))
        self._editmode = False
        self._PostEvent(close=True, updated=True)
