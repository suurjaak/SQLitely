# -*- coding: utf-8 -*-
"""
SQLitely UI application main window class and database page class.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    02.04.2022
------------------------------------------------------------------------------
"""
import ast
from collections import defaultdict, OrderedDict
import copy
import datetime
import functools
import inspect
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import webbrowser

import six
from six.moves import urllib
import wx
import wx.adv
import wx.html
import wx.lib
import wx.lib.agw.fmresources
import wx.lib.agw.labelbook
import wx.lib.agw.flatnotebook
import wx.lib.agw.ultimatelistctrl
import wx.lib.newevent

from . lib import controls
from . lib.controls import ColourManager
from . lib import util
from . lib import wx_accel
from . lib.vendor import step

from . import components
from . import conf
from . import database
from . import grammar
from . import guibase
from . import images
from . import importexport
from . import support
from . import templates
from . import workers
from . database import fmt_entity

logger = logging.getLogger(__name__)


"""Custom application events for worker results."""
SearchEvent,       EVT_SEARCH        = wx.lib.newevent.NewEvent()
DetectionEvent,    EVT_DETECTION     = wx.lib.newevent.NewEvent()
AddFolderEvent,    EVT_ADD_FOLDER    = wx.lib.newevent.NewEvent()
OpenDatabaseEvent, EVT_OPEN_DATABASE = wx.lib.newevent.NewCommandEvent()
DatabasePageEvent, EVT_DATABASE_PAGE = wx.lib.newevent.NewCommandEvent()


class MainWindow(guibase.TemplateFrameMixIn, wx.Frame):
    """Program main window."""

    TRAY_ICON = (images.Icon16x16_32bit if "linux" not in sys.platform
                 else images.Icon24x24_32bit)

    def __init__(self):
        wx.Frame.__init__(self, parent=None, title=conf.Title, size=conf.WindowSize)
        guibase.TemplateFrameMixIn.__init__(self)

        ColourManager.Init(self, conf, colourmap={
            "FgColour":                wx.SYS_COLOUR_BTNTEXT,
            "BgColour":                wx.SYS_COLOUR_WINDOW,
            "DisabledColour":          wx.SYS_COLOUR_GRAYTEXT,
            "MainBgColour":            wx.SYS_COLOUR_WINDOW,
            "WidgetColour":            wx.SYS_COLOUR_BTNFACE,
        }, darkcolourmap={
            "DBListForegroundColour":  wx.SYS_COLOUR_BTNTEXT,
            "DBListBackgroundColour":  wx.SYS_COLOUR_WINDOW,
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
        self.db_filter = "" # Current database list filter
        self.db_filter_timer = None # Database list filter callback timer
        self.db_menustate    = {}   # {filename: {} if refresh or {full: True} if reload}
        self.columndlg = None       # Dummy column dialog for Help -> Show value editor
        self.page_db_latest = None  # Last opened database page
        # List of Notebook pages user has visited, used for choosing page to
        # show when closing one.
        self.pages_visited = []
        self.ipc_listener = None # workers.IPCListener instance
        self.is_started = False
        self.is_minimizing = False
        self.is_dragging_page = False
        self.wizard_import = None # components.ImportWizard

        # Restore cached parse results; memoize cache is {(sql, ..): (meta, error)}
        cache = {(k, ): (v, None) for k, v in (conf.ParseCache or {}).items()}
        util.memoize.set_cache(grammar.parse, cache)

        icons = images.get_appicons()
        self.SetIcons(icons)

        self.trayicon = wx.adv.TaskBarIcon()
        if self.trayicon.IsAvailable():
            if conf.TrayIconEnabled:
                self.trayicon.SetIcon(self.TRAY_ICON.Icon, conf.Title)
            self.trayicon.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_toggle_to_tray)
            self.trayicon.Bind(wx.adv.EVT_TASKBAR_RIGHT_DOWN,  self.on_open_tray_menu)
        else:
            conf.WindowMinimizedToTray = False

        panel = self.panel_main = wx.Panel(self)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        self.frame_console.SetIcons(icons)

        notebook = self.notebook = wx.lib.agw.flatnotebook.FlatNotebook(
            panel, style=wx.NB_TOP,
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
        self.populate_menu()

        self.dialog_selectfolder = wx.DirDialog(
            self, message="Choose a directory where to search for databases",
            defaultPath=six.moves.getcwd(),
            style=wx.DD_DIR_MUST_EXIST | wx.RESIZE_BORDER)
        self.dialog_savefile = wx.FileDialog(self, defaultDir=six.moves.getcwd(),
            style=wx.FD_SAVE | wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )

        # Memory file system for showing images in wx.HtmlWindow
        self.memoryfs = {"files": {}, "handler": wx.MemoryFSHandler()}
        wx.FileSystem.AddHandler(self.memoryfs["handler"])
        self.load_fs_images()
        self.adapt_colours()

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
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_page, notebook)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                      self.on_close_page, notebook)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_DROPPED,
                      self.on_dragdrop_page, notebook)


        # Register Ctrl-F4 close and Ctrl-1..9 tab handlers
        def on_close_hotkey(event):
            notebook and notebook.DeletePage(notebook.GetSelection())
        def on_tab_hotkey(number, event):
            if notebook and notebook.GetSelection() != number \
            and number < notebook.GetPageCount():
                notebook.SetSelection(number)
                self.on_change_page(None)

        id_close = wx.NewIdRef().Id
        accelerators = [(wx.ACCEL_CMD, k, id_close) for k in [wx.WXK_F4]]
        for i in range(9):
            id_tab = wx.NewIdRef().Id
            accelerators += [(wx.ACCEL_CMD, ord(str(i + 1)), id_tab)]
            notebook.Bind(wx.EVT_MENU, functools.partial(on_tab_hotkey, i), id=id_tab)

        notebook.Bind(wx.EVT_MENU, on_close_hotkey, id=id_close)
        notebook.SetAcceleratorTable(wx.AcceleratorTable(accelerators))

        dropargs = dict(on_files=self.on_drop_files, on_folders=self.on_drop_folders)
        self.DropTarget = controls.FileDrop(**dropargs)
        self.notebook.DropTarget = controls.FileDrop(**dropargs)

        self.MinSize = conf.MinWindowSize
        if conf.WindowMaximized:
            self.Maximize()
        elif conf.WindowPosition and conf.WindowSize:
            self.Size = conf.WindowSize
            if not conf.WindowMinimizedToTray:
                self.Position = conf.WindowPosition
        else:
            self.Center(wx.HORIZONTAL)
            self.Position.top = 50
        self.list_db.SetFocus()

        if not conf.AllowMultipleInstances:
            args = conf.IPCName, conf.IPCPort, self.on_ipc
            self.ipc_listener = workers.IPCListener(*args)
            self.ipc_listener.start()

        if conf.WindowMinimizedToTray:
            conf.WindowMinimizedToTray = False
            wx.CallAfter(self.on_toggle_to_tray)
        else:
            self.Show(True)
        wx.CallLater(20000, self.update_check)
        wx.CallLater(1, self.populate_database_list)
        logger.info("Started application.")
        wx.CallAfter(setattr, self, "is_started", True)


    def create_page_main(self, notebook):
        """Creates the main page with database list and buttons."""
        page = self.page_main = wx.Panel(notebook)
        ColourManager.Manage(page, "BackgroundColour", "MainBgColour")
        notebook.AddPage(page, "Databases")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer_list = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)

        label_count = self.label_count = wx.StaticText(page)
        edit_filter = self.edit_filter = controls.HintedTextCtrl(page, "Filter list",
                                                                 style=wx.TE_PROCESS_ENTER)
        edit_filter.ToolTip = "Filter database list (%s-F)" % controls.KEYS.NAME_CTRL
        list_db = self.list_db = controls.SortableUltimateListCtrl(page,
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

        panel_right = wx.ScrolledWindow(page)
        panel_right.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_right.SetScrollRate(0, 20)

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
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName=self.Font.FaceName)
        BUTTONS_MAIN = [
            ("button_new", "&New database", images.ButtonNew,
             "Create a blank SQLite database."),
            ("button_import", "Import from &data file", images.ButtonImport,
             "Import spreadsheet or JSON to a new or existing database."),
            ("button_opena", "&Open a database..", images.ButtonOpenA,
             "Choose a database from your computer to open."),
            ("button_folder", "&Import from folder", images.ButtonFolder,
             "Select a folder where to look for databases."),
            ("button_detect", "Detect databases", images.ButtonDetect,
             "Auto-detect databases from user folders."),
            ("button_missing", "Remove missing", images.ButtonRemoveMissing,
             "Remove non-existing files from the database list."),
            ("button_clear", "C&lear list", images.ButtonClear,
             "Clear the current database list."), ]
        for name, label, img, note in BUTTONS_MAIN:
            button = controls.NoteButton(panel_main, label, note, img.Bitmap)
            setattr(self, name, button)
        self.button_missing.Hide(); self.button_clear.Hide()

        # Create detail page labels, values and buttons
        label_db = self.label_db = wx.TextCtrl(panel_detail, value="",
            style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH)
        label_db.Font = wx.Font(12, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName=self.Font.FaceName)
        ColourManager.Manage(label_db, "BackgroundColour", "WidgetColour")
        label_db.SetEditable(False)

        sizer_labels = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        LABELS = [("path", "Location"), ("size", "Size"),
                  ("modified", "Last modified"), ("tables", "Tables")]
        for field, title in LABELS:
            lbltext = wx.StaticText(panel_detail, label="%s:" % title)
            valtext = wx.TextCtrl(panel_detail, value="", size=(300, 35),
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
        sizer_labels.AddGrowableRow(3, proportion=10)

        BUTTONS_DETAIL = [
            ("button_open", "&Open", images.ButtonOpen,
             "Open the database."),
            ("button_saveas", "Save &as..", images.ButtonSaveAs,
             "Save a copy under another name."),
            ("button_remove", "Remove", images.ButtonRemoveType,
             "Remove from list."),
            ("button_delete", "Delete", images.ButtonRemove,
             "Delete from disk."), ]
        for name, label, img, note in BUTTONS_DETAIL:
            button = controls.NoteButton(panel_detail, label, note, img.Bitmap)
            setattr(self, name, button)

        children = list(panel_main.Children) + list(panel_detail.Children)
        for c in [panel_main, panel_detail] + children:
            ColourManager.Manage(c, "BackgroundColour", "MainBgColour")
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
        self.button_import.Bind(wx.EVT_BUTTON,    self.on_import_data)
        self.button_opena.Bind(wx.EVT_BUTTON,     self.on_open_database)
        self.button_detect.Bind(wx.EVT_BUTTON,    self.on_detect_databases)
        self.button_folder.Bind(wx.EVT_BUTTON,    self.on_add_from_folder)
        self.button_missing.Bind(wx.EVT_BUTTON,   self.on_remove_missing)
        self.button_clear.Bind(wx.EVT_BUTTON,     self.on_clear_databases)
        self.button_open.Bind(wx.EVT_BUTTON,      self.on_open_current_database)
        self.button_saveas.Bind(wx.EVT_BUTTON,    self.on_save_database_as)
        self.button_remove.Bind(wx.EVT_BUTTON,    self.on_remove_database)
        self.button_delete.Bind(wx.EVT_BUTTON,    self.on_delete_database)

        panel_main.Sizer.Add(label_main, border=10, flag=wx.ALL)
        panel_main.Sizer.Add((0, 10))
        panel_main.Sizer.Add(self.button_new,    flag=wx.GROW)
        panel_main.Sizer.Add(self.button_import, flag=wx.GROW)
        panel_main.Sizer.Add(self.button_opena,  flag=wx.GROW)
        panel_main.Sizer.Add(self.button_folder, flag=wx.GROW)
        panel_main.Sizer.Add(self.button_detect, flag=wx.GROW)
        panel_main.Sizer.AddStretchSpacer()
        panel_main.Sizer.Add(self.button_missing, flag=wx.GROW)
        panel_main.Sizer.Add(self.button_clear,   flag=wx.GROW)
        panel_detail.Sizer.Add(label_db,     border=10, flag=wx.ALL | wx.GROW)
        panel_detail.Sizer.Add(sizer_labels, border=10, flag=wx.ALL | wx.GROW,
                               proportion=2 if "linux" in sys.platform else 0)
        panel_detail.Sizer.AddStretchSpacer()
        panel_detail.Sizer.Add(self.button_open,   flag=wx.GROW)
        panel_detail.Sizer.Add(self.button_saveas, flag=wx.GROW)
        panel_detail.Sizer.Add(self.button_remove, flag=wx.GROW)
        panel_detail.Sizer.Add(self.button_delete, flag=wx.GROW)
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
            wx.ID_ANY, "&New database\t%s-N" % controls.KEYS.NAME_CTRL, "Create a blank SQLite database"
        )
        menu_import_data = self.menu_import_data = menu_file.Append(
            wx.ID_ANY, "Import from &data file", "Import spreadsheet or JSON to a new or existing database"
        )
        menu_open_database = self.menu_open_database = menu_file.Append(
            wx.ID_ANY, "&Open database...\t%s-O" % controls.KEYS.NAME_CTRL, "Choose a database file to open"
        )
        menu_file.AppendSeparator()
        menu_close_database = self.menu_close_database = menu_file.Append(
            wx.ID_ANY, "&Close", "Close active database"
        )
        menu_save_database = self.menu_save_database = menu_file.Append(
            wx.ID_ANY, "&Save", "Save changes to the active database"
        )
        menu_save_database_as = self.menu_save_database_as = menu_file.Append(
            wx.ID_ANY, "Save &as...", "Save the active database under a new name"
        )
        menu_recent = wx.Menu()
        menu_file.AppendSubMenu(menu_recent, "&Recent files", "Recently opened databases")
        menu_file.AppendSeparator()

        menu_options = wx.Menu()
        menu_file.AppendSubMenu(menu_options, "Opt&ions")
        if self.trayicon.IsAvailable():
            menu_tray = self.menu_tray = menu_options.Append(wx.ID_ANY,
                "Display &icon in notification area",
                "Show/hide %s icon in system tray" % conf.Title, kind=wx.ITEM_CHECK)
        menu_autoupdate_check = self.menu_autoupdate_check = menu_options.Append(
            wx.ID_ANY, "Automatic &update check",
            "Automatically check for program updates periodically", kind=wx.ITEM_CHECK)
        menu_allow_multi = self.menu_allow_multi = menu_options.Append(
            wx.ID_ANY, "Allow &multiple instances",
            "Allow multiple %s instances to run at the same time" % conf.Title,
            kind=wx.ITEM_CHECK)
        menu_options.AppendSeparator()
        menu_advanced = self.menu_advanced = menu_options.Append(wx.ID_ANY,
            "&Advanced options", "Edit advanced program options")

        if self.trayicon.IsAvailable():
            menu_to_tray = self.menu_to_tray = menu_file.Append(wx.ID_ANY,
                "Minimize to &tray", "Minimize %s window to notification area" % conf.Title)
        menu_exit = self.menu_exit = \
            menu_file.Append(wx.ID_ANY, "E&xit\tAlt-X", "Exit")

        menu_view = self.menu_view = wx.Menu()
        menu.Append(menu_view, "&View")
        menu_view_data = wx.Menu()
        self.menu_view_data = menu_view.AppendSubMenu(menu_view_data, "&Data")
        self.menu_view_data_table = menu_view_data.AppendSubMenu(wx.Menu(), "&Table")
        self.menu_view_data_view  = menu_view_data.AppendSubMenu(wx.Menu(), "&View")
        menu_view.AppendSeparator()
        menu_view_refresh = self.menu_view_refresh = menu_view.Append(wx.ID_ANY,
            "&Refresh", "Refresh all data")
        menu_view_folder = self.menu_view_folder = menu_view.Append(wx.ID_ANY,
            "Show in &folder", "Open database file directory")
        menu_view_locks = self.menu_view_locks = menu_view.Append(
            wx.ID_ANY, "Current &locks", "Show all current database locks (for pending changes, ongoing exports, statistics etc)")
        menu_view_changes = self.menu_view_changes = menu_view.Append(
            wx.ID_ANY, "&Unsaved changes", "Show unsaved changes")
        menu_view_history = self.menu_view_history = menu_view.Append(
            wx.ID_ANY, "Action &history", "Show database action log for current session")

        menu_edit = self.menu_edit = wx.Menu()
        menu.Append(menu_edit, "&Edit")
        menu_edit_table    = wx.Menu()
        menu_edit_index    = wx.Menu()
        menu_edit_trigger  = wx.Menu()
        menu_edit_view     = wx.Menu()
        menu_edit_clone    = wx.Menu()
        menu_edit_drop     = wx.Menu()
        menu_edit_truncate = wx.Menu()
        self.menu_edit_table   = menu_edit.AppendSubMenu(menu_edit_table,   "&Table")
        self.menu_edit_index   = menu_edit.AppendSubMenu(menu_edit_index,   "&Index")
        self.menu_edit_trigger = menu_edit.AppendSubMenu(menu_edit_trigger, "T&rigger")
        self.menu_edit_view    = menu_edit.AppendSubMenu(menu_edit_view,    "&View")
        menu_edit.AppendSeparator()
        menu_edit_save = self.menu_edit_save = menu_edit.Append(
            wx.ID_ANY, "&Save unsaved changes", "Save all unsaved changes")
        menu_edit_cancel = self.menu_edit_cancel = menu_edit.Append(
            wx.ID_ANY, "&Cancel unsaved changes", "Roll back all unsaved changes")
        menu_edit.AppendSeparator()
        self.menu_edit_clone    = menu_edit.AppendSubMenu(menu_edit_clone,    "&Clone")
        self.menu_edit_truncate = menu_edit.AppendSubMenu(menu_edit_truncate, "Tr&uncate")
        self.menu_edit_drop     = menu_edit.AppendSubMenu(menu_edit_drop,     "&Drop")
        menu_edit_clone_table   = wx.Menu()
        menu_edit_clone_view    = wx.Menu()
        menu_edit_drop_table    = wx.Menu()
        menu_edit_drop_index    = wx.Menu()
        menu_edit_drop_trigger  = wx.Menu()
        menu_edit_drop_view     = wx.Menu()
        self.menu_edit_clone_table  = menu_edit_clone.AppendSubMenu(menu_edit_clone_table, "&Table")
        self.menu_edit_clone_view   = menu_edit_clone.AppendSubMenu(menu_edit_clone_view,  "&View")
        self.menu_edit_drop_table   = menu_edit_drop .AppendSubMenu(menu_edit_drop_table,   "&Table")
        self.menu_edit_drop_index   = menu_edit_drop .AppendSubMenu(menu_edit_drop_index,   "&Index")
        self.menu_edit_drop_trigger = menu_edit_drop .AppendSubMenu(menu_edit_drop_trigger, "T&rigger")
        self.menu_edit_drop_view    = menu_edit_drop .AppendSubMenu(menu_edit_drop_view,    "&View")
        menu_edit_drop.AppendSeparator()
        menu_edit_drop_schema       = self.menu_edit_drop_schema = menu_edit_drop.Append(
            wx.ID_ANY, "Drop everything", "Drop all entities in the database")

        menu_tools = self.menu_tools = wx.Menu()
        menu.Append(menu_tools, "&Tools")
        menu_tools_optimize = self.menu_tools_optimize = menu_tools.Append(
            wx.ID_ANY, "&Optimize",
            "Attempt to optimize the database, running ANALYZE on tables")
        menu_tools_reindex = self.menu_tools_reindex = menu_tools.Append(
            wx.ID_ANY, "&Reindex all",
            "Recreate all table indexes from scratch")
        menu_tools_vacuum = self.menu_tools_vacuum = menu_tools.Append(
            wx.ID_ANY, "&Vacuum",
            "Rebuild the database file, repacking it into a minimal amount of disk space")
        menu_tools_integrity = self.menu_tools_integrity = menu_tools.Append(
            wx.ID_ANY, "Check for &corruption",
            "Check database integrity for corruption and recovery")
        menu_tools_fks = self.menu_tools_fks = menu_tools.Append(
            wx.ID_ANY, "Check &foreign keys",
            "Check for foreign key violations")
        menu_tools.AppendSeparator()
        menu_tools_import = self.menu_tools_import = menu_tools.Append(
            wx.ID_ANY, "&Import data",
            "Import data into table from spreadsheet or JSON file")
        menu_tools_export = wx.Menu()
        self.menu_tools_export = menu_tools.AppendSubMenu(menu_tools_export, "&Export")
        menu_tools_export_tables = self.menu_tools_export_tables = menu_tools_export.Append(
            wx.ID_ANY, "All tables to &file",
            "Export all tables to individual files")
        menu_tools_export_spreadsheet = self.menu_tools_export_spreadsheet = menu_tools_export.Append(
            wx.ID_ANY, "All tables to single spreads&heet",
            "Export all tables to a single Excel spreadsheet, "
            "each table in separate worksheet")
        menu_tools_export_data = self.menu_tools_export_data = menu_tools_export.Append(
            wx.ID_ANY, "All tables to another data&base",
            "Export table schemas and data to another SQLite database")
        menu_tools_export_structure = self.menu_tools_export_structure = menu_tools_export.Append(
            wx.ID_ANY, "All table structures to &another database",
            "Export table schemas to another SQLite database")
        menu_tools_export.AppendSeparator()
        menu_tools_export_pragma = self.menu_tools_export_pragma = menu_tools_export.Append(
            wx.ID_ANY, "&PRAGMA settings as SQL",
            "Export all current database PRAGMA settings as SQL")
        menu_tools_export_schema = self.menu_tools_export_schema = menu_tools_export.Append(
            wx.ID_ANY, "Database schema as S&QL",
            "Export database schema as SQL")
        menu_tools_export_dump = self.menu_tools_export_dump = menu_tools_export.Append(
            wx.ID_ANY, "Full database d&ump as SQL",
            "Dump entire database as SQL")
        menu_tools_export.AppendSeparator()
        menu_tools_export_stats = self.menu_tools_export_stats = menu_tools_export.Append(
            wx.ID_ANY, "Database &statistics",
            "Export database schema information and statistics")

        menu_help = wx.Menu()
        menu.Append(menu_help, "&Help")

        menu_update = self.menu_update = menu_help.Append(wx.ID_ANY,
            "Check for &updates",
            "Check whether a new version of %s is available" % conf.Title)
        menu_homepage = self.menu_homepage = menu_help.Append(wx.ID_ANY,
            "Go to &homepage",
            "Open the %s homepage, %s" % (conf.Title, conf.HomeUrl))
        menu_help.AppendSeparator()
        menu_log = self.menu_log = menu_help.Append(wx.ID_ANY,
            "Show &log window", "Show/hide the log messages window",
            kind=wx.ITEM_CHECK)
        menu_console = self.menu_console = menu_help.Append(wx.ID_ANY,
            "Show Python &console\t%s-E" % controls.KEYS.NAME_CTRL,
            "Show/hide a Python shell environment window", kind=wx.ITEM_CHECK)
        menu_editor = self.menu_editor = menu_help.Append(wx.ID_ANY,
            "Show value &editor",
            "Show/hide a dummy column value editor", kind=wx.ITEM_CHECK)
        menu_help.AppendSeparator()
        menu_about = self.menu_about = menu_help.Append(
            wx.ID_ANY, "&About %s" % conf.Title,
            "Show program information and copyright")

        self.history_file = wx.FileHistory(conf.MaxRecentFiles)
        self.history_file.UseMenu(menu_recent)
        # Reverse list, as FileHistory works like a stack
        [self.history_file.AddFileToHistory(f) for f in conf.RecentFiles[::-1]]
        self.Bind(wx.EVT_MENU_RANGE, self.on_recent_file, id=wx.ID_FILE1,
                  id2=wx.ID_FILE1 + conf.MaxRecentFiles)
        if self.trayicon.IsAvailable():
            menu_tray.Check(conf.TrayIconEnabled)
        menu_autoupdate_check.Check(conf.UpdateCheckAutomatic)
        menu_allow_multi.Check(conf.AllowMultipleInstances)
        menu_tools_export_spreadsheet.Enabled = bool(importexport.xlsxwriter)

        menu.Bind(wx.EVT_MENU_OPEN, self.on_menu_open)
        self.Bind(wx.EVT_MENU, self.on_new_database,            menu_new_database)
        self.Bind(wx.EVT_MENU, self.on_import_data,             menu_import_data)
        self.Bind(wx.EVT_MENU, self.on_open_database,           menu_open_database)
        self.Bind(wx.EVT_MENU, self.on_close_active_database,   menu_close_database)
        self.Bind(wx.EVT_MENU, self.on_save_active_database,    menu_save_database)
        self.Bind(wx.EVT_MENU, self.on_save_active_database_as, menu_save_database_as)
        self.Bind(wx.EVT_MENU, self.on_open_options,            menu_advanced)
        self.Bind(wx.EVT_MENU, self.on_exit,                    menu_exit)
        self.Bind(wx.EVT_MENU, self.on_check_update,            menu_update)
        self.Bind(wx.EVT_MENU, self.on_menu_homepage,           menu_homepage)
        self.Bind(wx.EVT_MENU, self.on_showhide_log,            menu_log)
        self.Bind(wx.EVT_MENU, self.on_toggle_console,          menu_console)
        self.Bind(wx.EVT_MENU, self.on_toggle_columneditor,     menu_editor)
        if self.trayicon.IsAvailable():
            self.Bind(wx.EVT_MENU, self.on_toggle_to_tray,      menu_to_tray)
            self.Bind(wx.EVT_MENU, self.on_toggle_trayicon,     menu_tray)
        self.Bind(wx.EVT_MENU, self.on_toggle_autoupdate_check,
                  menu_autoupdate_check)
        self.Bind(wx.EVT_MENU, self.on_toggle_allow_multi, menu_allow_multi)
        self.Bind(wx.EVT_MENU, self.on_about, menu_about)

        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["refresh"]), menu_view_refresh)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["folder"]),  menu_view_folder)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["locks"]),   menu_view_locks)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["changes"]), menu_view_changes)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["history"]), menu_view_history)

        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["save"]),        menu_edit_save)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["cancel"]),      menu_edit_cancel)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["drop schema"]), menu_edit_drop_schema)

        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["optimize"]),  menu_tools_optimize)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["reindex"]),   menu_tools_reindex)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["vacuum"]),    menu_tools_vacuum)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["integrity"]), menu_tools_integrity)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["fks"]),       menu_tools_fks)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["import"]),    menu_tools_import)

        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "tables"]),     menu_tools_export_tables)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "single"]),     menu_tools_export_spreadsheet)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "data"]),       menu_tools_export_data)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "structure"]),  menu_tools_export_structure)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "pragma"]),     menu_tools_export_pragma)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "schema"]),     menu_tools_export_schema)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "statistics"]), menu_tools_export_stats)
        self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["export", "dump"]),       menu_tools_export_dump)



    def populate_menu(self):
        """Updates program menu for currently selected tab."""
        page = self.notebook.GetSelection() and self.page_db_latest
        db, changes = (page.db, page.get_unsaved()) if page else (None, None)

        for x in self.menu_view.MenuItems:  x.Enable(bool(db))
        for x in self.menu_edit.MenuItems:  x.Enable(bool(db))
        for x in self.menu_tools.MenuItems: x.Enable(bool(db))
        self.menu_close_database.Enable(bool(page))
        self.menu_save_database.Enable(bool(page and (db.temporary or changes)))
        self.menu_save_database_as.Enable(bool(page))
        if not db: return

        self.MenuBar.Freeze()
        do_full = self.db_menustate.get(db.filename, {}).get("full")
        self.db_menustate.pop(db.filename, None)
        changes.pop("temporary", None)
        self.menu_view_changes.Enabled = bool(db.temporary or changes)
        self.menu_edit_save.Enabled = self.menu_edit_cancel.Enabled = bool(changes)
        self.menu_view_folder.Enabled = not db.temporary
        self.menu_edit_clone.Enabled    = any(db.schema.values())
        self.menu_edit_truncate.Enabled = bool(db.schema.get("table"))
        self.menu_edit_drop.Enabled     = any(db.schema.values())

        EDITMENUS  = {"table":   self.menu_edit_table,   "index": self.menu_edit_index,
                      "trigger": self.menu_edit_trigger, "view":  self.menu_edit_view}
        CLONEMENUS = {"table":   self.menu_edit_clone_table,  "view":  self.menu_edit_clone_view}
        DROPMENUS  = {"table":   self.menu_edit_drop_table,   "index": self.menu_edit_drop_index,
                      "trigger": self.menu_edit_drop_trigger, "view":  self.menu_edit_drop_view}
        TRUNCMENUS = {"table":   self.menu_edit_truncate}
        VIEWMENUS  = {"table":   self.menu_view_data_table,   "view":  self.menu_view_data_view}
        PAGESIZE   = 40
        for category in db.CATEGORIES if do_full else ():
            menu = EDITMENUS[category]
            for x in menu.SubMenu.MenuItems: menu.SubMenu.Delete(x)
            item_add = menu.SubMenu.Append(wx.ID_ANY, "Create &new %s" % category)
            args = ["create", category]
            self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), item_add)
            items = db.schema.get(category) or {}
            if items: menu.SubMenu.AppendSeparator()
            for name in items:
                if menu.SubMenu.MenuItemCount and not menu.SubMenu.MenuItemCount % PAGESIZE:
                    menu.SubMenu.Break()
                help = "Open schema editor for %s %s" % (category, fmt_entity(name))
                menuitem = menu.SubMenu.Append(wx.ID_ANY, util.ellipsize(util.unprint(name)), help)
                args = ["schema", category, name]
                self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), menuitem)

            menu = DROPMENUS[category]
            for x in menu.SubMenu.MenuItems: menu.SubMenu.Delete(x)
            item_all = menu.SubMenu.Append(wx.ID_ANY, "Drop all %s" % util.plural(category))
            menu.Enabled = bool(items)
            if items:
                args = ["drop", category]
                self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), item_all)
                if items: menu.SubMenu.AppendSeparator()
                for name in items:
                    if menu.SubMenu.MenuItemCount and not menu.SubMenu.MenuItemCount % PAGESIZE:
                        menu.SubMenu.Break()
                    help = "Drop %s %s" % (category, fmt_entity(name))
                    menuitem = menu.SubMenu.Append(wx.ID_ANY, util.ellipsize(util.unprint(name)), help)
                    args = ["drop", category, name]
                    self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), menuitem)

            if category in TRUNCMENUS:
                menu = TRUNCMENUS[category]
                for x in menu.SubMenu.MenuItems: menu.SubMenu.Delete(x)
                menu.Enabled = bool(items)
                item_all = menu.SubMenu.Append(wx.ID_ANY, "Truncate all %s" % util.plural(category),
                                               "Delete all rows from all tables")
                self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, ["truncate"]), item_all)
                if items: menu.SubMenu.AppendSeparator()
                for name, item in items.items():
                    if menu.SubMenu.MenuItemCount and not menu.SubMenu.MenuItemCount % PAGESIZE:
                        menu.SubMenu.Break()
                    help = "Delete all rows from %s %s" % (category, fmt_entity(name))
                    menuitem = menu.SubMenu.Append(wx.ID_ANY, util.ellipsize(util.unprint(name)), help)
                    menuitem.Enable(bool(item.get("count")))
                    args = ["truncate", name]
                    self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), menuitem)

            if category in CLONEMENUS:
                menu = CLONEMENUS[category]
                for x in menu.SubMenu.MenuItems: menu.SubMenu.Delete(x)
                menu.Enabled = bool(items)
                for name, item in items.items():
                    if menu.SubMenu.MenuItemCount and not menu.SubMenu.MenuItemCount % PAGESIZE:
                        menu.SubMenu.Break()
                    help = "Clone %s %s" % (category, fmt_entity(name))
                    menuitem = menu.SubMenu.Append(wx.ID_ANY, util.ellipsize(util.unprint(name)), help)
                    args = ["clone", category, name, "table" == category]
                    self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), menuitem)

            if category not in VIEWMENUS: continue # for category
            menu = VIEWMENUS[category]
            for x in menu.SubMenu.MenuItems: menu.SubMenu.Delete(x)
            menu.Enable(bool(items))
            for name in items:
                if menu.SubMenu.MenuItemCount and not menu.SubMenu.MenuItemCount % PAGESIZE:
                    menu.SubMenu.Break()
                help = "Open data grid for %s %s" % (category, fmt_entity(name))
                menuitem = menu.SubMenu.Append(wx.ID_ANY, util.ellipsize(util.unprint(name)), help)
                args = ["data", category, name]
                self.Bind(wx.EVT_MENU, functools.partial(self.on_menu_page, args), menuitem)
        self.MenuBar.Thaw()


    def on_menu_open(self, event):
        """Handler for opening main menu, repopulates menu if needed."""
        page = self.notebook.GetSelection() and self.page_db_latest
        db = page.db if page else None
        if not db or db.filename in self.db_menustate: self.populate_menu()


    def on_menu_page(self, args, event=None):
        """Handler for clicking a page-specific menu item, forwards to DatabasePage."""
        self.page_db_latest.handle_command(args[0], *args[1:])


    def update_check(self):
        """
        Checks for an updated program version if sufficient time
        from last check has passed, and opens a dialog for upgrading
        if new version available. Schedules a new check on due date.
        """
        if not self or not conf.UpdateCheckAutomatic: return
        interval = datetime.timedelta(days=conf.UpdateCheckInterval)
        due_date = datetime.datetime.now() - interval
        if not (conf.WindowMinimizedToTray or support.update_window) \
        and (not conf.LastUpdateCheck or conf.LastUpdateCheck < due_date.strftime("%Y%m%d")):
            callback = lambda resp: self.on_check_update_callback(resp, False)
            support.check_newest_version(callback)
        elif not support.update_window:
            try:
                dt = datetime.datetime.strptime(conf.LastUpdateCheck, "%Y%m%d")
                interval = (dt + interval) - datetime.datetime.now()
            except (TypeError, ValueError):
                pass
        # Schedule a check for due date, should the program run that long.
        millis = max(1, min(sys.maxsize, util.timedelta_seconds(interval) * 1000))
        wx.CallLater(millis, self.update_check)


    def on_toggle_allow_multi(self, event):
        """
        Handler for toggling allowing multiple instances, starts-stops the
        IPC server.
        """
        allow = conf.AllowMultipleInstances = event.IsChecked()
        util.run_once(conf.save)
        if allow:
            self.ipc_listener.stop()
            self.ipc_listener = None
        else:
            args = conf.IPCName, conf.IPCPort, self.on_ipc
            self.ipc_listener = workers.IPCListener(*args)
            self.ipc_listener.start()


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
        if conf.WindowMinimizedToTray:
            self.on_toggle_to_tray()


    def on_open_tray_menu(self, event):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()
        menu_recent = wx.Menu()
        menu_all = wx.Menu()

        def on_recent_file(event):
            if conf.WindowMinimizedToTray: self.on_toggle_to_tray()
            filename = history_file.GetHistoryFile(event.Id - wx.ID_FILE1)
            self.load_database_page(filename, clearselection=True)
        def open_item(filename, *_, **__):
            if conf.WindowMinimizedToTray: self.on_toggle_to_tray()
            self.load_database_page(filename, clearselection=True)

        history_file = wx.FileHistory(conf.MaxRecentFiles)
        history_file.UseMenu(menu_recent)
        # Reverse list, as FileHistory works like a stack
        [history_file.AddFileToHistory(f) for f in conf.RecentFiles[::-1]]
        history_file.UseMenu(menu_recent)

        label = ["Minimize to", "Restore from"][conf.WindowMinimizedToTray] + " &tray"
        item_new = wx.MenuItem(menu, -1, "&New database")
        item_toggle = wx.MenuItem(menu, -1, label)
        item_icon = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                text="Show &icon in notification area")
        item_console = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                   text="Show Python &console")
        item_editor = wx.MenuItem(menu, -1, kind=wx.ITEM_CHECK,
                                  text="Show value &editor")
        item_exit = wx.MenuItem(menu, -1, "E&xit %s" % conf.Title)

        boldfont = wx.Font(item_toggle.Font)
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
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, page.db.name), item)
            menu.Append(item)
        if openfiles: menu.AppendSeparator()

        allfiles = [(os.path.split(k)[-1], k) for k, v in self.db_datas.items()
                    if "name" in v]
        for i, (filename, path) in enumerate(sorted(allfiles)):
            label = "&%s %s" % ((i + 1), filename)
            item = wx.MenuItem(menu, -1, label)
            if len(allfiles) > 1 and (path == curfile if curfile
            else len(openfiles) == 1 and path in self.dbs):
                item.Font = boldfont
            menu_all.Append(item)
            menu.Bind(wx.EVT_MENU, functools.partial(open_item, path), item)
        if allfiles:
            menu.AppendSubMenu(menu_all, "All &files")

        item_recent = menu.AppendSubMenu(menu_recent, "&Recent files")
        menu.Enable(item_recent.Id, bool(conf.RecentFiles))
        menu.Append(item_new)
        menu.AppendSeparator()
        menu.Append(item_toggle)
        menu.Append(item_icon)
        menu.AppendSeparator()
        menu.Append(item_console)
        menu.Append(item_editor)
        menu.AppendSeparator()
        menu.Append(item_exit)
        item_icon.Check(True)
        item_console.Check(self.frame_console.Shown)
        item_editor.Check(bool(self.columndlg and self.columndlg.Shown))

        menu.Bind(wx.EVT_MENU_RANGE, on_recent_file, id=wx.ID_FILE1,
                  id2=wx.ID_FILE1 + conf.MaxRecentFiles)
        menu.Bind(wx.EVT_MENU, self.on_new_database,        item_new)
        menu.Bind(wx.EVT_MENU, self.on_toggle_to_tray,      item_toggle)
        menu.Bind(wx.EVT_MENU, self.on_toggle_trayicon,     item_icon)
        menu.Bind(wx.EVT_MENU, self.on_toggle_console,      item_console)
        menu.Bind(wx.EVT_MENU, self.on_toggle_columneditor, item_editor)
        menu.Bind(wx.EVT_MENU, self.on_exit,                item_exit)
        self.trayicon.PopupMenu(menu)


    def on_drop_files(self, filenames):
        """
        Handler for dropping files onto main program window, opens database pages
        if database files, opens import wizard if import files.
        ."""
        importfiles = [x for x in filenames
                       if os.path.splitext(x)[-1][1:].lower() in importexport.IMPORT_EXTS]
        if importfiles: self.on_import_data(filename=importfiles[0])
        else: self.load_database_pages(filenames, clearselection=True)


    def on_drop_folders(self, folders):
        """
        Handler for dropping folders onto main program window,
        starts importing databases.
        """
        t = util.plural("folder", folders) if len(folders) > 1 else folders[0]
        guibase.status("Detecting databases under %s.", t, log=True)
        self.button_folder.Label = "Stop &import from folder"
        for f in folders: self.worker_folder.work(f)


    def on_change_page(self, event=None):
        """
        Handler for changing a page in the main Notebook, remembers the visit.
        """
        if self.is_dragging_page: return
        if event: event.Skip() # Pass event along to next handler
        p = self.notebook.GetCurrentPage()
        if not self.pages_visited or self.pages_visited[-1] != p:
            self.pages_visited.append(p)
        self.Title, subtitle = conf.Title, ""
        if isinstance(p, DatabasePage): # Use parent/file.db or C:/file.db
            self.page_db_latest = p
            path, file = os.path.split(p.db.name)
            subtitle = os.path.join(os.path.split(path)[-1] or path, file)
            self.db_menustate[p.db.filename] = {"full": True}
        self.Title = " - ".join(filter(bool, (conf.Title, subtitle)))
        self.update_notebook_header()


    def on_dragdrop_page(self, event):
        """
        Handler for dragging notebook tabs, keeps main-tab first and log-tab last.
        """
        self.notebook.Freeze()
        self.is_dragging_page = True
        try:
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
            if self.notebook.GetCurrentPage() != cur_page:
                self.notebook.SetSelection(self.notebook.GetPageIndex(cur_page))
        finally:
            self.is_dragging_page = False
            self.notebook.Thaw()


    def on_toggle_to_tray(self, event=None):
        """Handler for toggling main window to tray and back."""
        if not self: return
        conf.WindowMinimizedToTray = not conf.WindowMinimizedToTray
        self.is_minimizing = True
        if conf.WindowMinimizedToTray:
            self.Hide()
            if not conf.TrayIconEnabled:
                conf.TrayIconEnabled = True
                self.trayicon.SetIcon(self.TRAY_ICON.Icon, conf.Title)
                self.menu_tray.Check(True)
            if self.menu_console.IsChecked(): self.frame_console.Hide()
        else:
            if conf.WindowPosition and not conf.WindowMaximized:
                self.Position = conf.WindowPosition
            self.Show()
            if self.menu_console.IsChecked():
                self.frame_console.Show(), self.frame_console.Iconize(False)
        wx.CallAfter(setattr, self, "is_minimizing", False)


    def on_size(self, event):
        """Handler for window size event, tweaks controls and saves size."""
        event.Skip()
        if self.is_minimizing: return
        if conf.WindowMaximized and not self.IsMaximized() and conf.WindowPosition:
            self.Position = conf.WindowPosition
        conf.WindowMaximized = self.IsMaximized()
        if not self.IsMaximized(): conf.WindowSize = self.Size[:]
        util.run_once(conf.save)
        # Right panel scroll
        wx.CallAfter(lambda: self and (self.list_db.RefreshRows(),
                                       self.panel_db_main.Parent.Layout()))


    def on_move(self, event):
        """Handler for window move event, saves position."""
        event.Skip()
        if self.is_minimizing: return
        if not self.IsIconized() and not self.IsMaximized() and not conf.WindowMaximized \
        and self.is_started and not self.is_minimizing:
            conf.WindowPosition = self.Position[:]
            util.run_once(conf.save)


    def on_ipc(self, data):
        """
        Handler for responding to an inter-process message from another
        program instance that was launched and then exited because of
        conf.AllowMultipleInstances. Raises the program window and loads
        given databases if any.
        """
        def after(data):
            if not self: return

            if conf.WindowMinimizedToTray: self.on_toggle_to_tray()
            else: self.Restore()
            self.Raise()
            data = data if isinstance(data, (list, set, tuple)) else list(filter(bool, [data]))
            if data: self.load_database_pages(data, clearselection=True)
        wx.CallAfter(after, data)


    def on_sys_colour_change(self, event):
        """Handler for system colour change, updates filesystem images."""
        event.Skip()
        self.adapt_colours()
        wx.CallAfter(self.load_fs_images) # Postpone to allow conf update


    def adapt_colours(self):
        """Adapts configuration colours to better fit current theme."""
        COLOURS = ["GridRowInsertedColour", "GridRowChangedColour",
                   "GridCellChangedColour"]
        frgb = tuple(ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT))[:3]
        brgb = tuple(ColourManager.GetColour(wx.SYS_COLOUR_WINDOW ))[:3]
        for n in COLOURS:
            rgb = tuple(wx.Colour(conf.Defaults.get(n)))[:3]
            delta = tuple(255 - x for x in rgb)
            direction = 1 if (sum(frgb) > sum(brgb)) else -1
            rgb2 = tuple(a + int(b * direction) for a, b in zip(brgb, delta))
            rgb2 = tuple(min(255, max(0, x)) for x in rgb2)
            setattr(conf, n, wx.Colour(rgb2).GetAsString(wx.C2S_HTML_SYNTAX))


    def load_fs_images(self):
        """Loads content to MemoryFS."""
        if not self: return
        abouticon = "%s.png" % conf.Title.lower() # Program icon shown in About window
        img = images.Icon48x48_32bit
        if abouticon in self.memoryfs["files"]:
            self.memoryfs["handler"].RemoveFile(abouticon)
        self.memoryfs["handler"].AddFile(abouticon, img.Image, wx.BITMAP_TYPE_PNG)
        self.memoryfs["files"][abouticon] = 1

        # Screenshots look better with colouring if system has off-white colour
        tint_colour = wx.Colour(conf.BgColour)
        tint_factor = [((4 * x) % 256) / 255. for x in tint_colour]
        # Images shown on the default search content page
        for name in ["HelpSearch", "HelpData", "HelpSchema", "HelpSQL",
                     "HelpPragma", "HelpInfo"]:
            embedded = getattr(images, name, None)
            if not embedded: continue # for name
            img = embedded.Image.AdjustChannels(*tint_factor)
            filename = "%s.png" % name
            if filename in self.memoryfs["files"]:
                self.memoryfs["handler"].RemoveFile(filename)
            self.memoryfs["handler"].AddFile(filename, img, wx.BITMAP_TYPE_PNG)
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
        util.run_once(conf.save)


    def on_database_page_event(self, event):
        """Handler for notification from DatabasePage, updates UI."""
        idx = self.notebook.GetPageIndex(event.source)
        ready, modified = (getattr(event, x, None) for x in ("ready", "modified"))
        rename, updated = (getattr(event, x, None) for x in ("rename", "updated"))

        if rename:
            self.dbs.pop(event.filename1, None)
            self.dbs[event.filename2] = event.source.db

            if event.temporary: self.db_datas.pop(event.filename1, None)
            self.update_database_list(event.filename2)
            if self.list_db.IsSelected(0): self.list_db.Select(0, False)
            for i in range(1, self.list_db.GetItemCount()):
                fn = self.list_db.GetItemText(i)
                self.list_db.Select(i, on=(fn == event.filename2))
            if event.filename2 in conf.RecentFiles: # Remove earlier position
                idx = conf.RecentFiles.index(event.filename2)
                try: self.history_file.RemoveFileFromHistory(idx)
                except Exception: pass
            self.history_file.AddFileToHistory(event.filename2)
            util.add_unique(conf.RecentFiles, event.filename2, -1,
                            conf.MaxRecentFiles)
            util.run_once(conf.save)
            if event.source == self.notebook.GetCurrentPage():
                self.on_change_page() # Update program title

        if modified is not None or updated:
            self.db_menustate.setdefault(event.source.db.filename, {})
            if updated: self.db_menustate[event.source.db.filename]["full"] = True

        if ready or rename: self.update_notebook_header()

        if (rename or modified is not None) and event.source.db.filename in self.db_datas:
            suffix = "*" if modified else ""
            title1 = self.db_datas[event.source.db.filename].get("title") \
                     or make_unique_page_title(event.source.db.name, self.notebook, front=True)
            self.db_datas[event.source.db.filename]["title"] = title1
            title2 = title1 + suffix
            if self.notebook.GetPageText(idx) != title2:
                self.notebook.SetPageText(idx, title2)


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
        elif event.KeyCode in [ord("F")] and event.CmdDown():
            self.edit_filter.SetFocus()
        elif self.list_db.GetFirstSelected() >= 0 and self.dbs_selected \
        and not event.AltDown() and event.KeyCode in controls.KEYS.ENTER:
            self.load_database_pages(self.dbs_selected)
        elif event.KeyCode in controls.KEYS.DELETE and self.dbs_selected:
            self.on_remove_database(None)


    def on_sort_list_db(self, event):
        """Handler for sorting dblist, saves sort state."""
        event.Skip()
        def save_sort_state():
            if not self: return
            conf.DBSort = self.list_db.GetSortState()
            util.run_once(conf.save)
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

            menu.Append(item_new)
            menu.Append(item_open)
            menu.Append(item_import)
            menu.Append(item_detect)
            menu.AppendSeparator()
            menu.Append(item_missing)
            menu.Append(item_clear)

            menu.Bind(wx.EVT_MENU, self.on_new_database,     item_new)
            menu.Bind(wx.EVT_MENU, self.on_open_database,    item_open)
            menu.Bind(wx.EVT_MENU, self.on_add_from_folder,  item_import)
            menu.Bind(wx.EVT_MENU, self.on_detect_databases, item_detect)
            menu.Bind(wx.EVT_MENU, self.on_remove_missing,   item_missing)
            menu.Bind(wx.EVT_MENU, self.on_clear_databases,  item_clear)

            # Needs callback, actions can modify list while mouse event ongoing
            return wx.CallAfter(self.list_db.PopupMenu, menu)


        def clipboard_copy(*a, **kw):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject("\n".join(files))
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
                guibase.status("Copied file path to clipboard.")
        def open_folder(*a, **kw):
            for f in files: util.select_file(f)

        name = os.path.split(files[0])[-1] if len(files) == 1 \
               else util.plural("file", files)

        menu = wx.Menu()
        item_name    = wx.MenuItem(menu, -1, name)
        item_copy    = wx.MenuItem(menu, -1, "&Copy file path")
        item_folder  = wx.MenuItem(menu, -1, "Show in &folder")

        boldfont = wx.Font(item_name.Font)
        boldfont.SetWeight(wx.FONTWEIGHT_BOLD)
        boldfont.SetFaceName(self.Font.FaceName)
        boldfont.SetPointSize(self.Font.PointSize)
        item_name.Font = boldfont

        item_open    = wx.MenuItem(menu, -1, "&Open")
        item_save    = wx.MenuItem(menu, -1, "&Save as")
        item_remove  = wx.MenuItem(menu, -1, "&Remove from list")
        item_missing = wx.MenuItem(menu, -1, "Remove &missing from list")
        item_delete  = wx.MenuItem(menu, -1, "Delete from disk")

        menu.Append(item_name)
        menu.AppendSeparator()
        menu.Append(item_copy)
        menu.Append(item_folder)
        menu.AppendSeparator()
        menu.Append(item_open)
        menu.Append(item_save)
        menu.Append(item_remove)
        menu.Append(item_missing)
        menu.Append(item_delete)

        menu.Bind(wx.EVT_MENU, clipboard_copy,                item_copy)
        menu.Bind(wx.EVT_MENU, open_folder,                   item_folder)
        menu.Bind(wx.EVT_MENU, self.on_open_current_database, item_open)
        menu.Bind(wx.EVT_MENU, self.on_save_database_as,      item_save)
        menu.Bind(wx.EVT_MENU, self.on_remove_database,       item_remove)
        menu.Bind(wx.EVT_MENU, self.on_delete_database,       item_delete)
        menu.Bind(wx.EVT_MENU, lambda e: self.on_remove_missing(event, selecteds),
                  item_missing)

        # Needs callback, actions can modify list while mouse event ongoing
        wx.CallAfter(self.list_db.PopupMenu, menu)


    def on_drag_list_db(self, event):
        """Handler for dragging items around in dblist, saves file order."""
        event.Skip()
        def save_list_order():
            conf.DBFiles = [self.list_db.GetItemText(i)
                            for i in range(1, self.list_db.GetItemCountFull())]
            util.run_once(conf.save)
        wx.CallAfter(save_list_order) # Allow list to update items


    def on_filter_list_db(self, event):
        """Handler for filtering dblist, applies search filter after timeout."""
        event.Skip()
        search = event.String.strip()
        if search == self.db_filter: return

        def do_filter(search):
            if not self: return
            self.db_filter_timer = None
            if search != self.db_filter: return
            self.list_db.SetFilter(search)
            self.update_database_list()

        if self.db_filter_timer: self.db_filter_timer.Stop()
        self.db_filter = search
        if search: self.db_filter_timer = wx.CallLater(200, do_filter, search)
        else: do_filter(search)


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
            guibase.status("New %s version %s available.", conf.Title, version)
            if wx.YES == controls.YesNoMessageBox(
                "Newer version (%s) available. You are currently on "
                "version %s.%s\nDownload and install %s %s?" %
                (version, conf.Version, "\n\n%s\n" % util.ellipsize(changes, MAX),
                 conf.Title, version),
                "Update information", wx.ICON_INFORMATION
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
            util.run_once(conf.save)
        support.update_window = None


    def populate_database_list(self):
        """
        Inserts all databases into the list, updates UI buttons.
        """
        if not self: return
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
                dy = (idx - self.list_db.GetCountPerPage() // 2) * lh
                self.list_db.ScrollList(0, dy)
                self.list_db.Update()

        self.button_missing.Show(bool(items))
        self.button_clear.Show(bool(items))
        self.panel_db_main.Layout()
        self.update_database_count()
        if selected_files: wx.CallLater(100, self.update_database_detail)


    def update_database_list(self, filenames=()):
        """
        Inserts the database into the list, if not there already, and updates
        UI buttons.

        @param   filename  possibly new filename, if any (single string or list)
        @return            True if was file was new or changed, False otherwise
        """
        if not self: return
        result, refresh_idxs = False, []
        # Insert into database lists, if not already there
        if isinstance(filenames, six.string_types): filenames = [filenames]
        for filename in filenames:
            filename = util.to_unicode(filename)
            if filename not in conf.DBFiles:
                conf.DBFiles.append(filename)
                util.run_once(conf.save)
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
                self.db_datas.setdefault(filename, defaultdict(lambda: None, name=filename))
                self.db_datas[filename].update(data)
                idx = self.list_db.FindItem(filename)
                if idx > 0: refresh_idxs.append(idx)
                result = True

        if self.button_missing.Shown != (self.list_db.GetItemCount() > 1):
            self.button_missing.Show(self.list_db.GetItemCount() > 1)
            self.button_clear.Show(self.list_db.GetItemCount() > 1)
            self.panel_db_main.Layout()
        self.update_database_count()
        for idx in refresh_idxs: self.list_db.RefreshRow(idx)
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
        if not self: return
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
                    and data.get("tables"):
                        # File does not seem changed: use cached values
                        self.label_tables.Value = data["tables"]
                    else:
                        data.update(size=sz, last_modified=dt)
                        idx = self.list_db.FindItem(filename)
                        if idx > 0: self.list_db.RefreshRow(idx)
                        wx.CallLater(10, self.update_database_stats, filename)
                else:
                    self.label_size.Value = "File does not exist."
                    self.label_size.ForegroundColour = conf.LabelErrorColour

        if size is not None: self.label_size.Value = util.format_bytes(size)

        for name in ["path", "size", "modified", "tables"]:
            getattr(self, "label_%s" % name).MinSize = (-1, -1)
        wx.CallLater(100, lambda: self and self.panel_db_detail.Layout())


    def on_clear_databases(self, event):
        """Handler for clicking to clear the database list."""
        count = self.list_db.GetItemCount() - 1
        total = len([v for v in self.db_datas.values() if "name" in v])
        t = "all" if count == total else "current"
        if (self.list_db.GetItemCount() > 1) and wx.YES != controls.YesNoMessageBox(
            "Are you sure you want to clear the list of %s databases?" % t,
            conf.Title, wx.ICON_INFORMATION, default=wx.NO
        ): return

        if count == total:
            self.list_db.Populate([])
            for lst in conf.DBFiles, conf.LastSelectedFiles: del lst[:]
            for dct in conf.LastActivePages, conf.LastSearchResults, \
                       conf.SchemaDiagrams,  conf.SQLWindowTexts: dct.clear()
            for k, v in (self.db_datas.items()): v.pop("name", None)
        else:
            files = [self.list_db.GetItemMappedData(i)["name"]
                     for i in range(1, self.list_db.GetItemCount())]
            for f in files:
                self.db_datas.get(f, {}).pop("name", None)
                self.clear_database_data(f)
            self.list_db.Freeze()
            try:
                for i in range(self.list_db.GetItemCount())[::-1]:
                    if self.list_db.GetItemText(i) in files:
                        self.list_db.DeleteItem(i)
            finally: self.list_db.Thaw()

        del conf.LastSelectedFiles[:]
        del self.dbs_selected[:]
        util.run_once(conf.save)
        self.update_database_list()


    def on_save_database_as(self, event=None):
        """Handler for clicking to save a copy of a database in the list."""
        filenames = list(filter(os.path.exists, self.dbs_selected))
        if not filenames:
            m = "None of the selected files" if len(self.dbs_selected) > 1 \
                else 'The file "%s" does not' % self.dbs_selected[0]
            return wx.MessageBox("%s exist on this computer." % m, conf.Title,
                                 wx.OK | wx.ICON_ERROR)

        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.DirDialog(self,
            message="Choose directory where to save databases",
            defaultPath=six.moves.getcwd(),
            style=wx.DD_DIR_MUST_EXIST | wx.RESIZE_BORDER
        ) if len(filenames) > 1 else wx.FileDialog(self,
            message="Save a copy..", wildcard=wildcard,
            defaultDir=os.path.split(filenames[0])[0],
            defaultFile=os.path.basename(filenames[0]),
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | 
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        path = controls.get_dialog_path(dialog)
        wx.YieldIfNeeded() # Allow dialog to disappear

        new_filenames = []
        for filename in filenames:
            _, basename = os.path.split(filename)
            filename2 = os.path.join(path, basename) if len(filenames) > 1 else path
            if filename == filename2:
                logger.error("Attempted to save %s as itself.", filename)
                wx.MessageBox("Cannot overwrite %s with itself." % filename,
                              conf.Title, wx.OK | wx.ICON_ERROR)
                continue # for filename
            try: shutil.copyfile(filename, filename2)
            except Exception as e:
                logger.exception("%r when trying to copy %s to %s.",
                                 e, basename, filename2)
                wx.MessageBox('Failed to copy "%s" to "%s":\n\n%s' %
                              (basename, filename2, util.format_exc(e)),
                              conf.Title, wx.OK | wx.ICON_ERROR)
            else:
                guibase.status("Saved a copy of %s as %s.", filename, filename2, log=True)
                self.update_database_list(filename2)
                new_filenames.append(filename2)

                for dct in conf.LastActivePages, conf.LastSearchResults, \
                           conf.SchemaDiagrams,  conf.SQLWindowTexts:
                    if filename in dct: dct[filename2] = copy.deepcopy(dct[filename])
                if filename in self.db_datas:
                    self.db_datas[filename2] = copy.deepcopy(self.db_datas[filename])
                    self.db_datas[filename2]["name"] = filename2

        if not new_filenames: return
        for i in range(1, self.list_db.GetItemCount()):
            self.list_db.Select(i, on=self.list_db.GetItemText(i) in new_filenames)


    def on_close_active_database(self, event=None):
        """Handler for clicking to close the active database."""
        page = self.notebook.GetSelection() and self.page_db_latest
        if isinstance(page, DatabasePage):
            self.notebook.DeletePage(self.notebook.GetPageIndex(page))


    def on_save_active_database(self, event=None):
        """
        Handler for clicking to save changes to the active database,
        commits unsaved changes.
        """
        page = self.notebook.GetSelection() and self.page_db_latest
        if isinstance(page, DatabasePage): page.save_database()


    def on_save_active_database_as(self, event=None):
        """
        Handler for clicking to save the active database under a new name,
        opens a save as dialog, copies file and commits unsaved changes.
        """
        page = self.notebook.GetSelection() and self.page_db_latest
        if isinstance(page, DatabasePage): page.save_database(rename=True)


    def on_remove_database(self, event=None):
        """Handler for clicking to remove an item from the database list."""
        if not self.dbs_selected: return

        msg = util.plural("file", self.dbs_selected, single="this")
        if wx.YES != controls.YesNoMessageBox(
            "Remove %s from database list?\n\n%s" % (msg, "\n".join(self.dbs_selected)),
            conf.Title, wx.ICON_INFORMATION, default=wx.NO
        ): return

        for filename in self.dbs_selected:
            self.clear_database_data(filename)
            self.db_datas.get(filename, {}).pop("name", None)
        self.list_db.Freeze()
        try:
            for i in range(self.list_db.GetItemCount())[::-1]:
                if self.list_db.GetItemText(i) in self.dbs_selected:
                    self.list_db.DeleteItem(i)
        finally: self.list_db.Thaw()
        del self.dbs_selected[:]
        self.list_db.Select(0)
        self.update_database_list()
        util.run_once(conf.save)


    def on_remove_missing(self, event, selecteds=None):
        """Handler to remove nonexistent files from the database list."""
        selecteds = selecteds or list(range(1, self.list_db.GetItemCount()))
        filter_func = lambda i: not os.path.exists(self.list_db.GetItemText(i))
        selecteds = list(filter(filter_func, selecteds))
        filenames = list(map(self.list_db.GetItemText, selecteds))
        for i in range(len(selecteds)):
            # - i, as item count is getting smaller one by one
            selected = selecteds[i] - i
            filename = self.list_db.GetItemText(selected)
            self.clear_database_data(filename, recent=True)
            self.db_datas.get(filename, {}).pop("name", None)
            self.list_db.DeleteItem(selected)
        self.update_database_list()
        if self.dbs_selected: self.update_database_detail()
        else: self.list_db.Select(0)

        if selecteds: util.run_once(conf.save)


    def on_delete_database(self, event=None):
        """Handler for clicking to delete a database from disk."""
        if not self.dbs_selected: return

        msg = util.plural("file", self.dbs_selected, single="this")
        if wx.YES != controls.YesNoMessageBox(
            "Delete %s from disk?\n\n%s" % (msg, "\n".join(self.dbs_selected)),
            conf.Title, wx.ICON_WARNING, default=wx.NO
        ): return

        unsaved_pages, ongoing_pages = {}, {}
        for page, db in self.db_pages.items():
            if db.filename in self.dbs_selected and page:
                if page.get_unsaved():
                    unsaved_pages[page] = db.filename
                if page.get_ongoing():
                    ongoing_pages[page] = db.filename
        if unsaved_pages:
            if wx.YES != controls.YesNoMessageBox(
                "There are unsaved changes in %s:\n\n%s\n\n"
                "Are you sure you want to discard them?" % (
                    util.plural("page", unsaved_pages, single="this"),
                    "\n".join(sorted(unsaved_pages.values()))
                ),
                conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return
        if ongoing_pages:
            if wx.YES != controls.YesNoMessageBox(
                "There are ongoing exports in %s:\n\n%s\n\n"
                "Are you sure you want to cancel them?" % (
                    util.plural(ongoing_pages, single="this"),
                    "\n".join(sorted(ongoing_pages.values()))
                ),
                conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return

        errors = []
        for filename in self.dbs_selected[:]:
            try:
                page = next((k for k, v in self.db_pages.items()
                             if v.filename == filename), None)
                if page:
                    page.on_close()
                    self.notebook.DeletePage(self.notebook.GetPageIndex(page))
                os.unlink(filename)

                self.clear_database_data(filename, recent=True)
                self.dbs.pop(filename, None)
                self.db_datas.get(filename, {}).pop("name", None)

                for i in range(self.list_db.GetItemCount())[::-1]:
                    if self.list_db.GetItemText(i) == filename:
                        self.list_db.DeleteItem(i)
                self.dbs_selected.remove(filename)
            except Exception as e:
                logger.exception("Error deleting %s.", filename)
                errors.append("%s: %s" % (filename, util.format_exc(e)))

        self.list_db.Select(0)
        self.update_database_list()
        util.run_once(conf.save)
        if errors:
            wx.MessageBox("Error removing %s:\n\n%s" % (
                          util.plural("file", errors, numbers=False),
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
        elif event and self.notebook.GetPageIndex(self.page_log) != self.notebook.GetSelection():
            self.notebook.SetSelection(self.notebook.GetPageCount() - 1)
            self.on_change_page(None)
            self.menu_log.Check(True)
        else:
            self.page_log.is_hidden = True
            self.notebook.RemovePage(self.notebook.GetPageIndex(self.page_log))
            self.menu_log.Check(False)


    def on_toggle_columneditor(self, event):
        """Handler for clicking to show/hide dummy column value editor."""
        if self.columndlg is None:
            cols = [{"name": "text",    "type": "TEXT"},
                    {"name": "float",   "type": "REAL"},
                    {"name": "integer", "type": "INTEGER"}]
            rowdata = {"text": "", "integer": 0, "float": 0.0}
            if six.PY2:
                cols.append({"name": "long",    "type": "BIGINT"})
                rowdata["long"] = long(0)

            dummydb = lambda: None
            dummydb.get_keys = lambda *a, **kw: ([], [])

            dummygridbase = lambda: None
            dummygridbase.category = "dummy"
            dummygridbase.columns = cols
            dummygridbase.db = dummydb
            dummygridbase.name = "dummy"
            dummygridbase.KEY_NEW = components.SQLiteGridBase.KEY_NEW
            dummygridbase.GetRowData = lambda *a, **kw: dict(rowdata)

            def onclose(event):
                event.Skip()
                if not isinstance(event, wx.ShowEvent) or not event.Show:
                    self.menu_editor.Check(False)

            kws = dict(title="Value editor", style=wx.CAPTION | wx.CLOSE_BOX | 
                       wx.MINIMIZE_BOX | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER | 
                       wx.DIALOG_NO_PARENT, row=0, col=0, rowdata=rowdata,
                       columnlabel="type")
            dlg = components.ColumnDialog(None, dummygridbase, **kws)
            dlg.SetIcons(images.get_appicons())
            dlg.Bind(wx.EVT_CLOSE, onclose)
            dlg.Bind(wx.EVT_SHOW,  onclose)
            dlg._button_reset.Show()
            dlg._label_meta.Hide()
            dlg.Size = 640, 390
            d = wx.Display(self)
            dlg.Position = [d.ClientArea[i] + a - b
                            for i, (a, b) in enumerate(zip(d.ClientArea[2:], dlg.Size))]
            self.columndlg = dlg
        self.columndlg.Show(not self.columndlg.Shown)
        self.menu_editor.Check(self.columndlg.Shown)


    def on_open_options(self, event):
        """
        Handler for opening advanced options, creates the property dialog
        and saves values.
        """
        dialog = controls.PropertyDialog(self, title="Advanced options")

        try: source = inspect.getsource(conf)
        except Exception:
            try:
                with open(os.path.join(conf.BinDirectory, "..", "conf.py")) as f:
                    source = f.read()
            except Exception: source = ""

        def get_field_doc(name, tree=ast.parse(source)):
            """Returns the docstring immediately before name assignment."""
            for i, node in enumerate(tree.body):
                if i and isinstance(node, ast.Assign) and node.targets[0].id == name:
                    prev = tree.body[i - 1]
                    if isinstance(prev, ast.Expr) \
                    and isinstance(prev.value, (ast.Str, ast.Constant)):  # Py2: Str, Py3: Constant
                        return prev.value.s.strip()
            return ""

        def typelist(mytype):
            def convert(v):
                v = ast.literal_eval(v) if isinstance(v, six.string_types) else v
                if not isinstance(v, (list, tuple)): v = tuple([v])
                if not v: raise ValueError("Empty collection")
                return tuple(map(mytype, v))
            convert.__name__ = "tuple(%s)" % mytype.__name__
            return convert

        for name in sorted(conf.OptionalFileDirectives):
            value, help = getattr(conf, name, None), get_field_doc(name)
            default = conf.Defaults.get(name)
            if value is None and default is None:
                continue # for name

            kind = type(value)
            if isinstance(value, (tuple, list)):
                kind = typelist(type(value[0]))
                default = kind(default)
            dialog.AddProperty(name, value, help, default, kind)
        dialog.Realize()

        if wx.ID_OK == dialog.ShowModal():
            for k, v in dialog.GetProperties():
                # Keep numbers in sane regions
                if isinstance(v, six.integer_types): v = max(1, min(sys.maxsize, v))
                setattr(conf, k, v)
            util.run_once(conf.save)
            self.MinSize = conf.MinWindowSize


    def on_open_database(self, event):
        """
        Handler for open database menu or button, displays a file dialog and
        loads the chosen database.
        """
        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.FileDialog(self, message="Open", wildcard=wildcard,
            style=wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE | wx.FD_OPEN | 
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK == dialog.ShowModal():
            self.load_database_pages(dialog.GetPaths(), clearselection=True)


    def on_import_data(self, event=None, filename=None):
        """Handler for import data menu or button, opens import wizard."""
        if not self.wizard_import:
            wizard = components.ImportWizard(self, title="Data import wizard",
                                             bitmap=images.WizardImport.Bitmap)
            wizard.SetIcons(self.GetIcons())
            self.wizard_import = wizard
            if filename: wx.CallAfter(lambda: self and wizard and wizard.OnDrop(filename))
            wizard.RunWizard()
            wizard.Destroy()
            self.wizard_import = None
        else: self.wizard_import.OnDrop(filename)


    def on_new_database(self, event):
        """
        Handler for new database menu or button, opens a temporary file database.
        """
        if conf.WindowMinimizedToTray: self.on_toggle_to_tray()
        self.load_database_page(None)


    def on_open_database_event(self, event):
        """
        Handler for OpenDatabaseEvent, updates db list and loads the event
        database.
        """
        self.load_database_pages([os.path.realpath(event.file)], clearselection=True)


    def on_recent_file(self, event):
        """Handler for clicking an entry in Recent Files menu."""
        filename = self.history_file.GetHistoryFile(event.Id - wx.ID_FILE1)
        self.update_database_list(filename)
        self.load_database_page(filename, clearselection=True)


    def on_detect_databases(self, event):
        """
        Handler for clicking to auto-detect databases, starts the
        detection in a background thread.
        """
        if self.worker_detection.is_working():
            guibase.status("")
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
            guibase.status("Detected %s.", util.plural(name, result["count"]), log=True)
        if result.get("done", False):
            self.button_detect.Label = "Detect databases"
            self.list_db.ResetColumnWidths()
            wx.Bell()


    def on_add_from_folder(self, event):
        """
        Handler for clicking to select folder where to search for databases,
        updates database list.
        """
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
                           result["folder"], log=True)
        if result.get("done"):
            self.button_folder.Label = "&Import from folder"
            self.list_db.ResetColumnWidths()
            wx.Bell()


    def on_open_current_database(self, event):
        """Handler for clicking to open selected files from database list."""
        self.load_database_pages(self.dbs_selected)


    def on_open_from_list_db(self, event):
        """Handler for clicking to open selected files from database list."""
        if event.GetIndex() > 0:
            self.load_database_page(self.list_db.GetItemText(event.GetIndex()))


    def update_database_stats(self, filename):
        """Opens the database and updates main page UI with database info."""
        if not self: return
        db = None
        try:
            db = self.dbs.get(filename) or database.Database(filename)
        except Exception as e:
            self.label_tables.Value = util.format_exc(e)
            self.label_tables.ForegroundColour = conf.LabelErrorColour
            logger.exception("Error opening %s.", filename)
            return
        try:
            tables = list(db.schema.get("table", {}).values())
            self.label_tables.Value = str(len(tables))
            if tables:
                s = ""
                for t in tables:
                    s += (", " if s else "") + fmt_entity(t["name"], force=False, limit=50)
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
        filename = self.list_db.GetItemText(event.GetIndex())
        if event.GetIndex() > 0 \
        and filename not in self.dbs_selected:
            self.dbs_selected.append(filename)
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

        filename = self.list_db.GetItemText(event.GetIndex())
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
        unsaved_pages, ongoing_pages = {}, {} # {DatabasePage: filename, }
        for page, db in self.db_pages.items():
            if not page: continue # for page, db
            if page.get_unsaved():
                unsaved_pages[page] = db.name
            if page.get_ongoing():
                ongoing_pages[page] = db.name

        if unsaved_pages:
            resp = wx.MessageBox(
                "There are unsaved changes in %s:\n\n%s\n\n"
                "Do you want to save the changes?" % (
                    util.plural("file", unsaved_pages, single="this"),
                    "\n".join(sorted(unsaved_pages.values()))
                ),
                conf.Title, wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION
            )
            if wx.CANCEL == resp: return
            for page in unsaved_pages if wx.YES == resp else ():
                if not page.save_database(): return

        if ongoing_pages:
            if wx.YES != controls.YesNoMessageBox(
                "There are ongoing exports in %s:\n\n%s\n\n"
                "Are you sure you want to cancel them?" % (
                    util.plural("file", ongoing_pages, single="this"),
                    "\n".join(sorted(ongoing_pages.values()))
                ),
                conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return

        for page, db in self.db_pages.items():
            if not page: continue # for page, db
            active_idx = page.notebook.Selection
            if active_idx and not db.temporary:
                conf.LastActivePages[db.filename] = active_idx
            elif page.db.filename in conf.LastActivePages:
                del conf.LastActivePages[page.db.filename]
            page.on_close()
            db.close()
        self.worker_detection.stop()
        self.worker_folder.stop()

        # Save cached parse results; memoize cache is {(sql, ..): (meta, error)}
        cache = util.memoize.get_cache(grammar.parse) or {}
        conf.ParseCache = {k[0]: v[0] for i, (k, v) in enumerate(cache.items())
                           if i < conf.MaxParseCache and len(k) == 1 and v[-1] is None}

        # Save last selected files in db lists, to reselect them on rerun
        conf.LastSelectedFiles[:] = self.dbs_selected[:]
        conf.WindowMaximized = self.IsMaximized()
        if not conf.WindowMinimizedToTray and not conf.WindowMaximized:
            conf.WindowPosition = self.Position[:]
        if not self.IsMaximized(): conf.WindowSize = self.Size[:]
        conf.save()
        self.trayicon.Destroy()
        wx.CallAfter(sys.exit) # Immediate exit fails if exiting from tray


    def on_close_page(self, event):
        """
        Handler for closing a page, asks the user about saving unsaved data,
        if any, removes page from main notebook.
        """
        if self.is_dragging_page: return
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

        unsaved = page.get_unsaved()
        if unsaved:
            if unsaved.pop("temporary", None) and not unsaved:
                msg = "%s has modifications.\n\n" % page.db
            else:
                info = ""
                if unsaved.get("pragma"): info = "PRAGMA settings"
                if unsaved.get("table"):
                    info += (", and " if info else "")
                    info += util.plural("table", unsaved["table"], numbers=False)
                    info += " " + ", ".join(map(fmt_entity, unsaved["table"]))
                if unsaved.get("schema"):
                    info += (", and " if info else "") + "schema changes"
                if unsaved.get("temporary"):
                    info += (", and " if info else "") + "temporary file"
                msg = "There are unsaved changes in this file:\n%s.\n\n%s\n\n" % (info, page.db)

            resp = wx.MessageBox(msg + "Do you want to save the changes?", conf.Title,
                                 wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION)
            if wx.CANCEL == resp: return event.Veto()
            if wx.YES == resp:
                if not page.save_database(): return event.Veto()

        ongoing = page.get_ongoing()
        if ongoing:
            infos = []
            for category in "table", "view":
                if category in ongoing:
                    info = ", ".join(sorted(ongoing[category], key=lambda x: x.lower()))
                    title = util.plural(category, ongoing[category], numbers=False)
                    info = "%s %s" % (title, info)
                    if len(ongoing) > 1:
                        info = "%s (%s)" % (util.plural(category, ongoing[category]), info)
                    infos.append(info)
            if "multi" in ongoing: infos.append(ongoing["multi"])
            if "sql" in ongoing:
                infos.append(util.plural("SQL query", ongoing["sql"]))

            if wx.YES != controls.YesNoMessageBox(
                "There are ongoing exports in this file:\n\n%s\n\n- %s\n\n"
                "Are you sure you want to cancel them?" % (page.db, "\n- ".join(infos)),
                conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return event.Veto()

        # Remove page from MainWindow data structures
        if page.notebook.Selection and not page.db.temporary:
            conf.LastActivePages[page.db.filename] = page.notebook.Selection
        elif page.db.filename in conf.LastActivePages:
            del conf.LastActivePages[page.db.filename]

        page.on_close()

        if page in self.db_pages:
            del self.db_pages[page]
        logger.info("Closed database tab for %s.", page.db)
        util.run_once(conf.save)

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
        self.pages_visited = [x for x in self.pages_visited if x != page]
        if self.page_db_latest == page:
            self.page_db_latest = next((i for i in self.pages_visited[::-1]
                                        if isinstance(i, DatabasePage)), None)
            CMDS = ["page = self.page_db_latest # Database tab",
                    "db = page.db if page else None # SQLite database wrapper"]
            for cmd in CMDS: self.TopLevelParent.run_console(cmd)
        self.SendSizeEvent() # Multiline wx.Notebooks need redrawing

        # Change notebook page to last visited
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
        util.run_once(conf.save)


    def load_database(self, filename, silent=False):
        """
        Tries to load the specified database, if not already open, and returns
        it. If filename is None, creates a temporary file database.

        @param   silent  if true, no error popups on failing to open the file
        """
        db = self.dbs.get(filename)
        if not db:
            if not filename or os.path.exists(filename):
                try:
                    db = database.Database(filename)
                except Exception:
                    logger.exception("Error opening %s.", filename)
                    is_accessible = False
                    if filename:
                        try:
                            with open(filename, "rb"): is_accessible = True
                        except Exception: pass
                    if filename and not is_accessible and not silent:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Some other process may be using the file."
                            % filename, conf.Title, wx.OK | wx.ICON_ERROR)
                    elif filename and not silent:
                        wx.MessageBox(
                            "Could not open %s.\n\n"
                            "Not a valid SQLite database?" % filename,
                            conf.Title, wx.OK | wx.ICON_ERROR)
                if db:
                    logger.info("Opened %s (%s).", db, util.format_bytes(db.filesize))
                    guibase.status("Reading database %s.", db)
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
                        util.run_once(conf.save)
            elif not silent:
                wx.MessageBox("Nonexistent file: %s." % filename,
                              conf.Title, wx.OK | wx.ICON_ERROR)
        return db


    def load_database_page(self, filename, clearselection=False):
        """
        Tries to load the specified database, if not already open, create a
        subpage for it, if not already created, and focuses the subpage.
        If filename is None, creates a temporary file database.

        @param   clearselection  clear previously selected files in database list
        @return                  database page instance
        """
        page, page0, db = None, None, self.dbs.get(filename)
        if db: page = page0 = next((x for x in self.db_pages if x and x.db == db), None)
        if not page:
            if not db: db = self.load_database(filename)
            if db:
                guibase.status("Opening database %s." % db)
                tab_title = make_unique_page_title(db.name, self.notebook, front=True)
                self.db_datas.setdefault(db.filename, defaultdict(lambda: None, name=db.filename))
                self.db_datas[db.filename]["title"] = tab_title
                page = DatabasePage(self.notebook, tab_title, db, self.memoryfs)
                if not page: return
                conf.DBsOpen[db.filename] = db
                self.db_pages[page] = db
                util.run_once(conf.save)
                if not page: return # User closed page before loading was complete
                self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS,
                          self.on_clear_searchall, page.edit_searchall)
        else:
            page.handle_command("refresh")
        if page:
            while not page0 and clearselection and self.list_db.GetSelectedItemCount():
                self.list_db.Select(self.list_db.GetFirstSelected(), False)
            if filename:
                self.list_db.Select(0, on=False) # Deselect home row
                for i in range(1, self.list_db.GetItemCount()):
                    if self.list_db.GetItemText(i) == filename:
                        self.list_db.Select(i)
                        break # for i
            for i in range(self.notebook.GetPageCount()):
                if self.notebook.GetPage(i) == page:
                    self.notebook.SetSelection(i)
                    self.update_notebook_header()
                    break # for i
            self.db_menustate[db.filename] = {"full": True}
        return page


    def load_database_pages(self, filenames, clearselection=False):
        """
        Tries to load the specified databases, if not already open, create
        subpages for them, if not already created, and focus the subpages.
        Skips files that are not SQLite databases, adds others to database list.

        @param   clearselection  clear previously selected files in database list
        """
        db_filenames, notdb_filenames = [], []
        for f in filenames:
            if database.is_sqlite_file(f, empty=True, ext=False): db_filenames.append(f)
            else:
                notdb_filenames.append(f)
                guibase.status("%s is not a valid SQLite database.", f, log=True)

        if db_filenames and clearselection:
            while self.list_db.GetSelectedItemCount():
                self.list_db.Select(self.list_db.GetFirstSelected(), False)

        if len(db_filenames) == 1:
            self.update_database_list(db_filenames)
            self.load_database_page(db_filenames[0])
        else:
            for f in db_filenames:
                if not self.load_database(f, silent=True): continue # for f
                self.update_database_list(f)
                self.load_database_page(f)
        if db_filenames: self.list_db.ResetColumnWidths()
        if notdb_filenames:
            t = "valid SQLite databases"
            if len(notdb_filenames) == 1: t = "a " + t[:-1]
            wx.MessageBox("Not %s:\n\n%s" % (t, "\n".join(notdb_filenames)),
                          conf.Title, wx.OK | wx.ICON_ERROR)


    def clear_database_data(self, filename, recent=False):
        """Clears database data from configuration."""
        lists = [conf.DBFiles, conf.LastSelectedFiles]
        if recent: lists.append(conf.RecentFiles)
        for lst in lists:
            if filename in lst: lst.remove(filename)
        for dct in conf.LastActivePages, conf.LastSearchResults, \
                   conf.SchemaDiagrams,  conf.SQLWindowTexts, self.dbs:
            dct.pop(filename, None)
        if not recent: return
        # Remove from recent file history
        idx = next((i for i in range(self.history_file.Count)
                    if self.history_file.GetHistoryFile(i) == filename), None)
        if idx is not None: self.history_file.RemoveFileFromHistory(idx)



class DatabasePage(wx.Panel):
    """
    A wx.Notebook page for managing a single database file, has its own
    Notebook with a number of pages for searching, browsing, SQL, information.
    """

    def __init__(self, parent_notebook, title, db, memoryfs):
        wx.Panel.__init__(self, parent_notebook)
        self.parent_notebook = parent_notebook

        self.pageorder = {} # {page: notebook index, }
        self.ready_to_close = False
        self.db = db
        self.db.register_consumer(self)
        self.flags      = {} # {various flags: bool}
        self.timers     = {} # {name: wx.Timer}
        self.statistics = {} # {?error: message, ?data: {..}}
        self.pages_closed = defaultdict(list) # {notebook: [{name, ..}, ]}
        self.pragma         = db.get_pragma_values() # {pragma_name: value}
        self.pragma_initial = copy.deepcopy(self.pragma)
        self.pragma_changes = {}    # {pragma_name: value}
        self.pragma_ctrls   = {}    # {pragma_name: wx control}
        self.pragma_items   = {}    # {pragma_name: [all wx components for directive]}
        self.pragma_edit = False    # Whether in PRAGMA edit mode
        self.pragma_fullsql = False # Whether show SQL for all PRAGMAs, changed or not
        self.pragma_filter = ""     # Current PRAGMA filter
        self.memoryfs = memoryfs
        parent_notebook.InsertPage(1, self, title)
        busy = controls.BusyPanel(self, 'Loading "%s".' % db.name)
        ColourManager.Manage(self, "BackgroundColour", "WidgetColour")
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)

        self.DropTarget = controls.FileDrop(on_files=self.on_drop_files)

        # Create search structures and threads
        self.Bind(EVT_SEARCH, self.on_searchall_result)
        self.workers_search = {} # {search ID: workers.SearchThread, }

        self.worker_analyzer = workers.AnalyzerThread(self.on_analyzer_result)
        self.worker_checksum = workers.ChecksumThread(self.on_checksum_result)

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_header.AddStretchSpacer()

        self.label_search = wx.StaticText(self, -1, "Search &in data:")
        self.label_search.ToolTip = "Search in all columns of all database tables and views"
        sizer_header.Add(self.label_search, border=5, flag=wx.RIGHT | wx.TOP)
        edit_search = self.edit_searchall = controls.TextCtrlAutoComplete(
            self, description=conf.SearchDescription,
            size=(300, -1), style=wx.TE_PROCESS_ENTER)
        edit_search.ToolTip = self.label_search.ToolTip.Tip
        self.Bind(wx.EVT_TEXT_ENTER, self.on_searchall, edit_search)
        tb = self.tb_search = wx.ToolBar(self, style=wx.TB_FLAT | wx.TB_NODIVIDER)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR,
                                       (16, 16))
        tb.SetToolBitmapSize(bmp.Size)
        tb.AddTool(wx.ID_FIND, "", bmp, shortHelp="Start search")
        tb.Realize()
        self.Bind(wx.EVT_TOOL, self.on_searchall, id=wx.ID_FIND)
        sizer_header.Add(edit_search, border=5, flag=wx.RIGHT)
        sizer_header.Add(tb, border=5, flag=wx.GROW)
        sizer.Add(sizer_header,
                  border=5, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.GROW)
        sizer.Layout() # To avoid searchbox moving around during page creation

        bookstyle = wx.lib.agw.fmresources.INB_LEFT
        if "posix" == os.name: # Hard to identify selected tab in Gtk
            bookstyle |= wx.lib.agw.fmresources.INB_BOLD_TAB_SELECTION
        notebook = self.notebook = wx.lib.agw.labelbook.FlatImageBook(
            self, agwStyle=bookstyle, style=wx.BORDER_STATIC)

        self.TopLevelParent.page_db_latest = self
        self.TopLevelParent.run_console(
            "page = self.page_db_latest # Database tab")
        self.TopLevelParent.run_console("db = page.db # SQLite database wrapper")

        self.create_page_search(notebook)
        self.create_page_data(notebook)
        self.create_page_schema(notebook)
        self.create_page_diagram(notebook)
        self.create_page_sql(notebook)
        self.create_page_pragma(notebook)
        self.create_page_info(notebook)

        IMAGES = [images.PageSearch,  images.PageData, images.PageSchema,
                  images.PageDiagram, images.PageSQL,  images.PagePragma,
                  images.PageInfo]
        il = wx.ImageList(32, 32)
        idxs = [il.Add(x.Bitmap) for x in IMAGES]
        notebook.AssignImageList(il)
        for i, idx in enumerate(idxs): notebook.SetPageImage(i, idx)

        sizer.Add(notebook, proportion=1, border=5, flag=wx.GROW | wx.ALL)

        self.dialog_savefile = wx.FileDialog(
            self, defaultDir=six.moves.getcwd(), wildcard=importexport.EXPORT_WILDCARD,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR | wx.RESIZE_BORDER)
        # Need separate dialog w/o overwrite prompt, cannot swap style in Linux
        self.dialog_savefile_ow = wx.FileDialog(
            self, defaultDir=six.moves.getcwd(), wildcard=importexport.EXPORT_WILDCARD,
            message="Choose directory where to save files",
            style=wx.FD_SAVE | wx.FD_CHANGE_DIR | wx.RESIZE_BORDER)

        self.Layout()
        # Hack to get diagram-page diagram lay itself out
        notebook.SetSelection(self.pageorder[self.page_diagram])
        # Hack to get info-page multiline TextCtrls to layout without quirks.
        notebook.SetSelection(self.pageorder[self.page_info])
        # Hack to get SQL window size to layout without quirks.
        notebook.SetSelection(self.pageorder[self.page_sql])
        for i in range(1, self.notebook_sql.GetPageCount() - 1):
            self.notebook_sql.SetSelection(i)
        self.notebook_sql.SetSelection(0)
        firstpage = self.page_schema if db.temporary else self.page_data
        notebook.SetSelection(self.pageorder[firstpage])
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_page, notebook)
        # Restore last active page
        if db.filename in conf.LastActivePages \
        and conf.LastActivePages[db.filename] != notebook.Selection:
            notebook.SetSelection(conf.LastActivePages[db.filename])

        try: self.load_data()
        finally: busy.Close()
        if not self: return
        wx_accel.accelerate(self)
        wx.CallAfter(lambda: self and (edit_search.SetFocus(), edit_search.SelectAll()))


    def create_page_search(self, notebook):
        """Creates a page for searching the database."""
        page = self.page_search = wx.Panel(notebook)
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
            wx.ToolBar(page, style=wx.TB_FLAT | wx.TB_NODIVIDER | wx.TB_HORZ_TEXT)
        tb.SetToolBitmapSize((24, 24))
        tb.AddRadioTool(wx.ID_STATIC, "Data", bitmap1=images.ToolbarData.Bitmap,
            shortHelp="Search in all columns of all database tables and views")
        tb.AddRadioTool(wx.ID_INDEX, "Meta", bitmap1=images.ToolbarTitle.Bitmap,
            shortHelp="Search in database CREATE SQL")
        tb.AddSeparator()
        tb.AddCheckTool(wx.ID_NEW, "Tabs", images.ToolbarTabs.Bitmap,
            shortHelp="New tab for each search  (Alt-N)", longHelp="")
        tb.AddCheckTool(wx.ID_CONVERT, "", images.ToolbarCase.Bitmap,
            shortHelp="Case-sensitive search", longHelp="")
        tb.AddTool(wx.ID_STOP, "", images.ToolbarStopped.Bitmap,
            shortHelp="Stop current search, if any")
        tb.Realize()
        tb.ToggleTool(wx.ID_INDEX,   conf.SearchInMeta)
        tb.ToggleTool(wx.ID_STATIC,  conf.SearchInData)
        tb.ToggleTool(wx.ID_NEW,     conf.SearchUseNewTab)
        tb.ToggleTool(wx.ID_CONVERT, conf.SearchCaseSensitive)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_INDEX)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_STATIC)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_NEW)
        self.Bind(wx.EVT_TOOL, self.on_searchall_toggle_toolbar, id=wx.ID_CONVERT)
        self.Bind(wx.EVT_TOOL, self.on_searchall_stop, id=wx.ID_STOP)

        self.label_search.Label = "Search &in data:"
        if conf.SearchInMeta:
            self.label_search.Label = "Search &in metadata:"
            self.label_search.ToolTip = "Search in database CREATE SQL"

        nb = self.notebook_search = controls.TabbedHtmlWindow(page)
        ColourManager.Manage(nb, "TabAreaColour", "WidgetColour")
        nb.Font.PixelSize = (0, 8)
        nb.SetCustomPage(step.Template(templates.SEARCH_WELCOME_HTML).expand())
        label_html.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                        self.on_click_html_link)
        self.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.on_click_html_link, nb.GetHtmlWindow())
        nb.GetHtmlWindow().Bind(wx.EVT_RIGHT_UP, self.on_rightclick_searchall)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_searchall_tab, nb)
        nb.Bind(controls.EVT_TAB_LEFT_DCLICK, self.on_dclick_searchall_tab)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                  self.on_close_search_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CONTEXT_MENU,
                  self.on_notebook_menu, nb)
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_notebook_menu, nb.GetTabArea())
        self.register_notebook_hotkeys(nb)

        sizer_top.Add(label_html, proportion=1, flag=wx.GROW)
        sizer_top.Add(tb, border=5, flag=wx.TOP | wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(sizer_top, border=5, flag=wx.TOP | wx.RIGHT | wx.GROW)
        sizer.Add(nb, border=5, proportion=1,
                  flag=wx.GROW | wx.LEFT | wx.RIGHT | wx.BOTTOM)
        wx.CallAfter(lambda: self and label_html.Show())


    def create_page_data(self, notebook):
        """Creates a page for listing and browsing tables and views."""
        page = self.page_data = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Data")

        self.data_pages = defaultdict(util.CaselessDict) # {category: {name: DataObjectPage}}

        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = self.splitter_data = wx.SplitterWindow(
            page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(100)

        panel_export = self.panel_data_export = components.ExportProgressPanel(page)
        panel_export.Hide()

        panel1 = wx.Panel(splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_topleft = wx.BoxSizer(wx.HORIZONTAL)
        gauge = self.gauge_data = wx.Gauge(panel1)
        gauge.Hide()
        button_refresh = self.button_refresh_data = \
            wx.Button(panel1, label="Refresh")
        button_refresh.Disable()
        sizer_topleft.Add(gauge, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_topleft.AddStretchSpacer()
        sizer_topleft.Add(button_refresh)

        tree = self.tree_data = controls.TreeListCtrl(
            panel1, agwStyle=wx.TR_DEFAULT_STYLE | wx.TR_FULL_ROW_HIGHLIGHT
        )
        ColourManager.Manage(tree, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(tree, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
        isize = (16, 16)
        il = wx.ImageList(*isize)
        # Add placeholder image, empty ImageList throws error on Linux
        il.Add(wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR, isize))
        tree.AssignImageList(il) # Same height rows as tree_schema

        tree.AddColumn("Object")
        tree.AddColumn("Info")
        tree.AddRoot("Loading data..")
        tree.SetMainColumn(0)
        tree.SetColumnAlignment(1, wx.ALIGN_RIGHT)
        tree.SetColumnEditable(0, True)

        self.Bind(wx.EVT_BUTTON, self.on_refresh_tree_data, button_refresh)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED,   self.on_change_tree_data)
        tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_rclick_tree_data)
        tree.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.on_editstart_tree)
        tree.Bind(wx.EVT_TREE_END_LABEL_EDIT,   self.on_editend_tree)
        tree.Bind(wx.EVT_CONTEXT_MENU,          self.on_rclick_tree_data)
        tree.Bind(wx.EVT_SIZE,                  self.on_size_tree)
        tree.Bind(wx.EVT_CHAR_HOOK,             self.on_key_tree)

        sizer1.Add(sizer_topleft, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer1.Add(tree, proportion=1,
                   border=5, flag=wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM)

        panel2 = wx.Panel(splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_data = self.make_page_notebook(panel2)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        sizer2.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        sizer.Add(panel_export, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 400)

        self.Bind(components.EVT_DATA_PAGE, self.on_data_page_event)
        self.Bind(components.EVT_IMPORT,    self.on_import_event)
        self.Bind(components.EVT_PROGRESS,  self.on_close_data_export)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                  self.on_close_data_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CONTEXT_MENU,
                  self.on_notebook_menu, nb)
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_notebook_menu, nb.GetTabArea())
        self.register_notebook_hotkeys(nb)


    def create_page_schema(self, notebook):
        """Creates a page for browsing and modifying schema."""
        page = self.page_schema = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Schema")

        self.schema_pages = defaultdict(util.CaselessDict) # {category: {name: SchemaObjectPage}}

        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = self.splitter_schema = wx.SplitterWindow(
            page, style=wx.BORDER_NONE
        )
        splitter.SetMinimumPaneSize(100)

        panel1 = wx.Panel(splitter)
        gauge = self.gauge_schema = wx.Gauge(panel1)
        button_refresh = self.button_refresh_schema = \
            wx.Button(panel1, label="Refresh")
        button_refresh.Disable()
        button_new = wx.Button(panel1, label="Create ne&w ..")

        tree = self.tree_schema = controls.TreeListCtrl(
            panel1, agwStyle=wx.TR_DEFAULT_STYLE | wx.TR_FULL_ROW_HIGHLIGHT
        )
        ColourManager.Manage(tree, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(tree, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)

        gauge.Hide()
        isize = (16, 16)
        il = wx.ImageList(*isize)
        self.tree_schema_images = {
            "table":    il.Add(wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW,     wx.ART_TOOLBAR, isize)),
            "index":    il.Add(wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE,     wx.ART_TOOLBAR, isize)),
            "trigger":  il.Add(images.TreeTrigger.Bitmap),
            "view":     il.Add(wx.ArtProvider.GetBitmap(wx.ART_HELP_PAGE,       wx.ART_TOOLBAR, isize)),
            "columns":  il.Add(wx.ArtProvider.GetBitmap(wx.ART_FOLDER,          wx.ART_TOOLBAR, isize)),
        }
        tree.AssignImageList(il)

        tree.AddColumn("Object")
        tree.AddColumn("Info")
        tree.AddRoot("Loading schema..")
        tree.SetMainColumn(0)
        tree.SetColumnAlignment(1, wx.ALIGN_RIGHT)
        tree.SetColumnEditable(0, True)

        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_topleft = wx.BoxSizer(wx.HORIZONTAL)
        sizer_topleft.Add(gauge, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_topleft.AddStretchSpacer()
        sizer_topleft.Add(button_refresh)
        sizer_topleft.Add(button_new, border=5, flag=wx.LEFT)

        sizer1.Add(sizer_topleft, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer1.Add(tree, proportion=1,
                   border=5, flag=wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM)

        panel2 = wx.Panel(splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_schema = self.make_page_notebook(panel2)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        sizer2.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 400)

        self.Bind(wx.EVT_BUTTON, self.on_refresh_tree_schema, button_refresh)
        self.Bind(wx.EVT_BUTTON, self.on_schema_create,  button_new)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED,   self.on_change_tree_schema)
        tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_rclick_tree_schema)
        tree.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.on_editstart_tree)
        tree.Bind(wx.EVT_TREE_END_LABEL_EDIT,   self.on_editend_tree)
        tree.Bind(wx.EVT_CONTEXT_MENU,          self.on_rclick_tree_schema)
        tree.Bind(wx.EVT_SIZE,                  self.on_size_tree)
        tree.Bind(wx.EVT_CHAR_HOOK,             self.on_key_tree)
        self.Bind(components.EVT_SCHEMA_PAGE,   self.on_schema_page_event)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                  self.on_close_schema_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CONTEXT_MENU,
                  self.on_notebook_menu, nb)
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_notebook_menu, nb.GetTabArea())
        self.register_notebook_hotkeys(nb)


    def create_page_diagram(self, notebook):
        """Creates a page for schema visual diagram."""
        page = self.page_diagram = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Diagram")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_top    = wx.BoxSizer(wx.HORIZONTAL)
        sizer_middle = wx.BoxSizer(wx.HORIZONTAL)
        sizer_bottom = wx.BoxSizer(wx.HORIZONTAL)
        WIDTH_FACTOR = controls.COMBO_WIDTH_FACTOR

        tb = self.tb_diagram = wx.ToolBar(page, style=wx.TB_FLAT | wx.TB_NODIVIDER | wx.TB_HORZ_TEXT)
        combo_zoom = self.combo_diagram_zoom = wx.ComboBox(tb, size=(60 * WIDTH_FACTOR, -1), style=wx.CB_DROPDOWN)
        statusgauge = self.diagram_gauge  = wx.Gauge(page)
        button_export = self.button_diagram_export = wx.Button(page, label="Export &diagram")
        button_action = self.button_diagram_action = wx.Button(page, label="Other &actions ..")
        diagram = self.diagram = components.SchemaDiagram(page, self.db)
        cb_rels  = self.cb_diagram_rels   = wx.CheckBox(page, label="Foreign &relations")
        cb_lbls  = self.cb_diagram_labels = wx.CheckBox(page, label="Foreign &labels")
        cb_stats = self.cb_diagram_stats  = wx.CheckBox(page, label="&Statistics")
        label_find = self.label_diagram_find = wx.StaticText(page, label="&Quickfind:")
        combo_find = self.combo_diagram_find = wx.ComboBox(page, size=(100 * WIDTH_FACTOR, -1), style=wx.CB_DROPDOWN)

        level = diagram.ZOOM_MAX
        while level >= diagram.ZOOM_MIN:
            if level == diagram.ZOOM_MIN or not (100 * level) % 1:
                combo_zoom.Append("%s%%" % util.round_float(100 * level, 2))
                combo_zoom.SetClientData(combo_zoom.Count - 1, level)
            level -= diagram.ZOOM_STEP
        combo_zoom.SetValue("%s%%" % util.round_float(100 * diagram.ZOOM_DEFAULT, 2))
        combo_zoom.ToolTip = "Zoom"
        bmp1 = images.ToolbarTick.Bitmap
        bmp2 = images.ToolbarZoomIn.Bitmap
        bmp3 = images.ToolbarZoomOut.Bitmap
        bmp4 = images.ToolbarZoom100.Bitmap
        bmp5 = images.ToolbarZoomFit.Bitmap
        bmp6 = images.ToolbarLayoutGrid.Bitmap
        bmp7 = images.ToolbarLayoutGraph.Bitmap
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddCheckTool(wx.ID_APPLY, "Enable", bmp1, shortHelp="Enable diagram")
        tb.AddSeparator()
        tb.AddTool(wx.ID_ZOOM_IN,  "", bmp2, shortHelp="Zoom in one step  (+)")
        tb.AddTool(wx.ID_ZOOM_OUT, "", bmp3, shortHelp="Zoom out one step  (-)")
        tb.AddSeparator()
        tb.AddTool(wx.ID_ZOOM_100, "", bmp4, shortHelp="Reset zoom  (*)")
        tb.AddTool(wx.ID_ZOOM_FIT, "", bmp5, shortHelp="Zoom to fit")
        tb.AddControl(combo_zoom)
        tb.AddSeparator()
        tb.AddCheckTool(wx.ID_STATIC,  "", bmp6, shortHelp="Grid layout (click for options)")
        tb.AddCheckTool(wx.ID_NETWORK, "", bmp7, shortHelp="Graph layout")
        tb.EnableTool(wx.ID_ZOOM_100, False)
        tb.ToggleTool(wx.ID_APPLY,    True)
        tb.ToggleTool(wx.ID_STATIC,   True)
        tb.Realize()
        diagram.DatabasePage = self
        cb_rels.Enabled = cb_lbls.Enabled = cb_stats.Enabled = False
        cb_rels.Value = True
        cb_lbls.Value = True
        cb_rels.ToolTip  = "Show foreign relations between tables"
        cb_lbls.ToolTip  = "Show labels on foreign relations between tables"
        cb_stats.ToolTip = "Show table size information"
        label_find.ToolTip = "Select schema items as you type (* is wildcard)"
        combo_find.ToolTip = label_find.ToolTip.Tip
        statusgauge.Hide()

        sizer_top.Add(tb, flag=wx.ALIGN_BOTTOM)
        sizer_top.AddStretchSpacer()
        sizer_top.Add(statusgauge,   border=15, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        sizer_top.Add(button_export, border=5,  flag=wx.RIGHT | wx.BOTTOM)
        sizer_top.Add(button_action, border=5,  flag=wx.RIGHT | wx.BOTTOM)
        sizer_middle.Add(diagram,     proportion=1, flag=wx.GROW)
        sizer_bottom.Add(cb_rels,     border=5, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL)
        sizer_bottom.Add(cb_lbls,     border=5, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL)
        sizer_bottom.Add(cb_stats,    border=5, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL)
        sizer_bottom.AddStretchSpacer()
        sizer_bottom.Add(label_find,  border=5, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL)
        sizer_bottom.Add(combo_find,  border=5, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(sizer_top,    border=5, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)
        sizer.Add(sizer_middle, border=5, flag=wx.LEFT | wx.RIGHT | wx.GROW, proportion=1)
        sizer.Add(sizer_bottom, border=5, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)

        tb.Bind(wx.EVT_TOOL, self.on_diagram_toggle,   id=wx.ID_APPLY)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_diagram_zoom(+1),  id=wx.ID_ZOOM_IN)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_diagram_zoom(-1),  id=wx.ID_ZOOM_OUT)
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_diagram_zoom(0),   id=wx.ID_ZOOM_100)
        tb.Bind(wx.EVT_TOOL, self.on_diagram_zoom_fit, id=wx.ID_ZOOM_FIT)
        tb.Bind(wx.EVT_TOOL, self.on_diagram_grid,     id=wx.ID_STATIC)
        tb.Bind(wx.EVT_TOOL, self.on_diagram_graph,    id=wx.ID_NETWORK)

        self.Bind(wx.EVT_COMBOBOX,  self.on_diagram_zoom_combo, combo_zoom)
        self.Bind(wx.EVT_TEXT,      self.on_diagram_zoom_combo, combo_zoom)
        self.Bind(wx.EVT_CHECKBOX,  self.on_diagram_relations,  cb_rels)
        self.Bind(wx.EVT_CHECKBOX,  self.on_diagram_labels,     cb_lbls)
        self.Bind(wx.EVT_CHECKBOX,  self.on_diagram_stats,      cb_stats)
        self.Bind(wx.EVT_BUTTON,    self.on_diagram_export,     button_export)
        self.Bind(wx.EVT_BUTTON,    self.on_diagram_action,     button_action)
        self.Bind(wx.EVT_COMBOBOX,  self.on_diagram_find,       combo_find)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_diagram_find_char,  combo_find)


    def create_page_sql(self, notebook):
        """Creates a page for executing arbitrary SQL."""
        page = self.page_sql = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "SQL")

        self.sql_pages = defaultdict(dict) # {name: SQLPage}
        self.sql_page_counter = 0

        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)

        nb = self.notebook_sql = self.make_page_notebook(page)
        ColourManager.Manage(nb, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(nb, "TabAreaColour",   wx.SYS_COLOUR_BTNFACE)
        try: nb._pages.GetSingleLineBorderColour = nb.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        for name, text in conf.SQLWindowTexts.get(self.db.filename, [])[::-1]:
            self.add_sql_page(name, text)
        if self.sql_pages:
            self.sql_page_counter = max(
                int(re.sub(r"[^\d]", "", x) or 0) for x in self.sql_pages
            ) or len(self.sql_pages)
        else: self.add_sql_page()
        nb.AddPage(page=wx.Panel(page), text="+")

        sizer.Add(nb, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_change_sql_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                  self.on_close_sql_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_DROPPED,
                  self.on_dragdrop_sql_page, nb)
        self.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CONTEXT_MENU,
                  self.on_notebook_menu, nb)
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_notebook_menu, nb.GetTabArea())
        nb.Bind(wx.EVT_CHAR_HOOK, self.on_key_sql_page)
        self.register_notebook_hotkeys(nb)


    def create_page_pragma(self, notebook):
        """Creates a page for database PRAGMA settings."""
        page = self.page_pragma = wx.Panel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Pragma")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)

        splitter = self.splitter_pragma = wx.SplitterWindow(page, style=wx.BORDER_NONE)
        panel_wrapper = self.panel_pragma_wrapper = wx.ScrolledWindow(splitter)
        panel_pragma = wx.Panel(panel_wrapper)
        panel_sql = self.panel_pragma_sql = wx.Panel(splitter)
        sizer_wrapper = panel_wrapper.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_pragma = panel_pragma.Sizer = wx.FlexGridSizer(cols=4, vgap=4, hgap=10)
        sizer_sql = panel_sql.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_sql_header = wx.BoxSizer(wx.HORIZONTAL)
        sizer_footer = wx.BoxSizer(wx.HORIZONTAL)
        splitter.SetMinimumPaneSize(20)
        panel_wrapper.SetScrollRate(0, 20)

        label_header = wx.StaticText(page, label="Database PRAGMA settings")
        label_header.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                    wx.FONTWEIGHT_BOLD, faceName=self.Font.FaceName)
        edit_filter = self.edit_pragma_filter = controls.HintedTextCtrl(page, "Filter list",
                                                                        style=wx.TE_PROCESS_ENTER)
        edit_filter.ToolTip = "Filter PRAGMA directive list (%s-F)" % controls.KEYS.NAME_CTRL

        def on_help(ctrl, text, event):
            """Handler for clicking help bitmap, shows text popup."""
            wx.TipWindow(ctrl, text, maxLength=300)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_QUESTION, wx.ART_TOOLBAR, (16, 16))
        cursor_pointer = wx.Cursor(wx.CURSOR_HAND)
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
                                   value="\n".join(util.to_unicode(x) for x in value or ()))
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
                choices = [util.to_unicode(v) for k, v in items]
                ctrl = wx.Choice(panel_pragma, name=ctrl_name, choices=choices)
                ctrl.Selection = [k for k, v in items].index(value)
                ctrl.Bind(wx.EVT_CHOICE, self.on_pragma_change)
            elif int == opts["type"]:
                ctrl = wx.SpinCtrl(panel_pragma, name=ctrl_name)
                ctrl.SetRange(opts.get("min", -sys.maxsize), opts.get("max", sys.maxsize))
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
            for c in label, ctrl, label_text: c.ToolTip = description
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

        check_sql = self.check_pragma_sql = \
            wx.CheckBox(panel_sql, label="See change S&QL")
        check_sql.ToolTip = "See SQL statements for PRAGMA changes"
        check_sql.Value = True
        check_fullsql = self.check_pragma_fullsql = \
            wx.CheckBox(panel_sql, label="See f&ull SQL")
        check_fullsql.ToolTip = "See SQL statements for setting all current PRAGMA values"
        check_fullsql.Hide()

        stc = self.stc_pragma = controls.SQLiteTextCtrl(panel_sql, style=wx.BORDER_STATIC)
        stc.SetReadOnly(True)
        tb = self.tb_pragma = wx.ToolBar(panel_sql, style=wx.TB_FLAT | wx.TB_NODIVIDER)
        bmp1 = wx.ArtProvider.GetBitmap(wx.ART_COPY,      wx.ART_TOOLBAR, (16, 16))
        bmp2 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR, (16, 16))
        tb.SetToolBitmapSize(bmp1.Size)
        tb.AddTool(wx.ID_COPY, "", bmp1, shortHelp="Copy pragma SQL to clipboard")
        tb.AddTool(wx.ID_SAVE, "", bmp2, shortHelp="Save pragma SQL to file")
        tb.Realize()
        tb.Bind(wx.EVT_TOOL, lambda e: self.on_copy_sql(self.stc_pragma), id=wx.ID_COPY)
        tb.Bind(wx.EVT_TOOL, lambda e: self.save_sql(self.stc_pragma.Text, "PRAGMA"), id=wx.ID_SAVE)

        button_edit = self.button_pragma_edit = \
            wx.Button(page, label="Edit")
        button_refresh = self.button_pragma_refresh = \
            wx.Button(page, label="Refresh")
        button_cancel = self.button_pragma_cancel = \
            wx.Button(page, label="Cancel")

        button_edit.ToolTip = "Change PRAGMA values"
        button_refresh.ToolTip = "Reload PRAGMA values from database"
        button_cancel.ToolTip = "Cancel PRAGMA changes"
        button_cancel.Enabled = False

        self.Bind(wx.EVT_BUTTON,     self.on_pragma_edit,    button_edit)
        self.Bind(wx.EVT_BUTTON,     self.on_pragma_refresh, button_refresh)
        self.Bind(wx.EVT_BUTTON,     self.on_pragma_cancel,  button_cancel)
        self.Bind(wx.EVT_CHECKBOX,   self.on_pragma_sql,     check_sql)
        self.Bind(wx.EVT_CHECKBOX,   self.on_pragma_fullsql, check_fullsql)
        page.Bind(wx.EVT_CHAR_HOOK,  self.on_pragma_key)
        edit_filter.Bind(wx.EVT_TEXT_ENTER, self.on_pragma_filter)

        sizer_header.Add(edit_filter.Size[0], 0)
        sizer_header.AddStretchSpacer()
        sizer_header.Add(label_header)
        sizer_header.AddStretchSpacer()
        sizer_header.Add(edit_filter, border=16, flag=wx.RIGHT)

        sizer_wrapper.Add(panel_pragma, proportion=1, border=20, flag=wx.TOP | wx.GROW)

        sizer_sql_header.Add(check_sql, border=5, flag=wx.TOP | wx.ALIGN_CENTER_VERTICAL)
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
        sizer.Add(splitter, proportion=1, border=5, flag=wx.LEFT | wx.GROW)
        sizer.Add(sizer_footer, border=10, flag=wx.BOTTOM | wx.TOP | wx.GROW)

        splitter.SplitHorizontally(panel_wrapper, panel_sql, page.Size[1] - 150)
        splitter.Unsplit()
        ColourManager.Manage(panel_wrapper, "BackgroundColour", "BgColour")


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
        panel1c = wx.Panel(panel1)
        ColourManager.Manage(panel1c, "BackgroundColour", "BgColour")
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_file = panel1c.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_info = wx.GridBagSizer(vgap=3, hgap=10)
        label_file = wx.StaticText(panel1, label="Database information")
        label_file.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                  wx.FONTWEIGHT_BOLD, faceName=self.Font.FaceName)

        names = ["edit_info_path", "edit_info_size", "edit_info_created",
                 "edit_info_modified", "edit_info_sha1", "edit_info_md5", ]
        labels = ["Full path", "File size", "Created", "Last modified",
                  "SHA-1 checksum", "MD5 checksum",  ]
        for i, (name, label) in enumerate(zip(names, labels)):
            labeltext = wx.StaticText(panel1c, label="%s:" % label,
                                      name=name+"_label")
            ColourManager.Manage(labeltext, "ForegroundColour", "DisabledColour")
            valuetext = wx.TextCtrl(panel1c, value="Analyzing..", name=name,
                style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH | wx.TE_NO_VSCROLL)
            valuetext.MinSize = (-1, 35)
            valuetext.SetEditable(False)
            sizer_info.Add(labeltext, pos=(i, 0), border=5, flag=wx.LEFT | wx.TOP)
            sizer_info.Add(valuetext, pos=(i, 1), span=(1, 1 if "checksum" in label else 2),
                           border=5, flag=wx.TOP | wx.GROW)
            setattr(self, name, valuetext)
        button_checksum_stop = self.button_checksum_stop = wx.Button(panel1c, label="Stop")
        button_checksum_stop.ToolTip = "Stop checksum calculation"
        sizer_info.Add(button_checksum_stop, pos=(len(names) - 2, 2), span=(2, 1),
                       border=10, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL)
        self.edit_info_path.Value = "<temporary file>" if self.db.temporary \
                                    else self.db.filename

        self.Bind(wx.EVT_BUTTON, self.on_checksum_stop, button_checksum_stop)

        button_fks      = self.button_check_fks       = wx.Button(panel1c, label="Check foreign keys")
        button_check    = self.button_check_integrity = wx.Button(panel1c, label="Check for corruption")
        button_optimize = self.button_optimize        = wx.Button(panel1c, label="Optimize")

        button_vacuum      = self.button_vacuum       = wx.Button(panel1c, label="Vacuum")
        button_open_folder = self.button_open_folder  = wx.Button(panel1c, label="Show in folder")
        button_refresh     = self.button_refresh_info = wx.Button(panel1c, label="Refresh")
        button_fks.Enabled = button_check.Enabled = button_optimize.Enabled = False
        button_vacuum.Enabled = button_open_folder.Enabled = button_refresh.Enabled = False
        button_fks.ToolTip         = "Check for foreign key violations"
        button_check.ToolTip       = "Check database integrity for " \
                                     "corruption and recovery"
        button_optimize.ToolTip    = "Attempt to optimize the database, " \
                                     "running ANALYZE on tables"
        button_vacuum.ToolTip      = "Rebuild the database file, repacking " \
                                     "it into a minimal amount of disk space"
        button_open_folder.ToolTip = "Open database file directory"
        button_refresh.ToolTip =     "Refresh file information"

        sizer_buttons = wx.FlexGridSizer(cols=5, vgap=5, hgap=0)
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
        self.Bind(wx.EVT_BUTTON, lambda e: util.select_file(self.db.filename),
                  button_open_folder)
        self.Bind(wx.EVT_BUTTON, lambda e: self.update_info_panel(reload=True),
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
        bmp2 = images.ToolbarStopped.Bitmap
        bmp3 = wx.ArtProvider.GetBitmap(wx.ART_COPY, wx.ART_TOOLBAR,
                                        (16, 16))
        bmp4 = wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR,
                                        (16, 16))
        bmp5 = images.ToolbarNumbered.Bitmap
        bmp6 = images.ToolbarWordWrap.Bitmap
        tb_stats = self.tb_stats = wx.ToolBar(panel_stats,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        tb_stats.SetToolBitmapSize(bmp1.Size)
        tb_stats.AddTool(wx.ID_REFRESH, "", bmp1, shortHelp="Refresh statistics")
        tb_stats.AddTool(wx.ID_STOP,    "", bmp2, shortHelp="Stop statistics analysis")
        tb_stats.AddSeparator()
        tb_stats.AddTool(wx.ID_COPY,    "", bmp3, shortHelp="Copy statistics to clipboard as text")
        tb_stats.AddTool(wx.ID_SAVE,    "", bmp4, shortHelp="Save statistics to file")
        tb_stats.Realize()
        tb_stats.Bind(wx.EVT_TOOL, self.on_update_statistics, id=wx.ID_REFRESH)
        tb_stats.Bind(wx.EVT_TOOL, self.on_stop_statistics,   id=wx.ID_STOP)
        tb_stats.Bind(wx.EVT_TOOL, self.on_copy_statistics,   id=wx.ID_COPY)
        tb_stats.Bind(wx.EVT_TOOL, self.on_save_statistics,   id=wx.ID_SAVE)

        html_stats = self.html_stats = wx.html.HtmlWindow(panel_stats)

        tb_sql = self.tb_sql = wx.ToolBar(panel_schema,
                                      style=wx.TB_FLAT | wx.TB_NODIVIDER)
        tb_sql.SetToolBitmapSize(bmp1.Size)
        tb_sql.AddTool(wx.ID_REFRESH, "", bmp1, shortHelp="Refresh schema SQL")
        tb_sql.AddSeparator()
        tb_sql.AddTool(wx.ID_INDENT,  "", bmp5, shortHelp="Show line numbers", kind=wx.ITEM_CHECK)
        tb_sql.AddTool(wx.ID_STATIC,  "", bmp6, shortHelp="Word-wrap",         kind=wx.ITEM_CHECK)
        tb_sql.AddSeparator()
        tb_sql.AddTool(wx.ID_COPY,    "", bmp3, shortHelp="Copy schema SQL to clipboard")
        tb_sql.AddTool(wx.ID_SAVE,    "", bmp4, shortHelp="Save schema SQL to file")
        tb_sql.Realize()
        tb_sql.ToggleTool(wx.ID_INDENT, conf.SchemaLineNumbered)
        tb_sql.ToggleTool(wx.ID_STATIC, conf.SchemaWordWrap)
        tb_sql.EnableTool(wx.ID_COPY,   False)
        tb_sql.EnableTool(wx.ID_SAVE,   False)
        tb_sql.Bind(wx.EVT_TOOL, self.on_update_stc_schema, id=wx.ID_REFRESH)
        tb_sql.Bind(wx.EVT_TOOL, self.on_toggle_numbers_stc_schema, id=wx.ID_INDENT)
        tb_sql.Bind(wx.EVT_TOOL, self.on_toggle_wrap_stc_schema,    id=wx.ID_STATIC)
        tb_sql.Bind(wx.EVT_TOOL, lambda e: self.on_copy_sql(self.stc_schema), id=wx.ID_COPY)
        tb_sql.Bind(wx.EVT_TOOL, lambda e: self.save_sql(self.stc_schema.Text), id=wx.ID_SAVE)

        stc = self.stc_schema = controls.SQLiteTextCtrl(panel_schema, style=wx.BORDER_STATIC)
        stc.SetMarginCount(1)
        stc.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
        stc.SetMarginCursor(0, wx.stc.STC_CURSORARROW)
        stc.SetMarginWidth(0, 25 if conf.SchemaLineNumbered else 0)
        stc.SetText("Parsing..")
        stc.SetReadOnly(True)
        stc.SetWrapMode(wx.stc.STC_WRAP_WORD if conf.SchemaWordWrap else wx.stc.STC_WRAP_NONE)

        panel_stats.Sizer.Add(tb_stats, border=5, flag=wx.ALL)
        panel_stats.Sizer.Add(html_stats, proportion=1, flag=wx.GROW)

        panel_schema.Sizer.Add(tb_sql, border=5, flag=wx.ALL)
        panel_schema.Sizer.Add(stc, proportion=1, flag=wx.GROW)

        nb.AddPage(panel_stats,  "Statistics")
        nb.AddPage(panel_schema, "Schema")
        sizer2.Add(nb, proportion=1, flag=wx.GROW)

        sizer.Add(splitter, border=5, proportion=1, flag=wx.ALL | wx.GROW)
        splitter.SplitVertically(panel1, panel2, self.Size[0] // 2 - 60)

        self.populate_statistics()


    def handle_command(self, cmd, *args):
        """Handles a command, like "drop", ["table", name]."""

        def format_changes(temp=False):
            """Returns unsaved changes as readable text."""
            info, changes = "", self.get_unsaved()
            if changes.get("table"):
                info += "Unsaved data in tables:\n- "
                info += "\n- ".join(fmt_entity(x, force=False) for x in changes["table"])
            if changes.get("schema"):
                info += "%sUnsaved schema changes:\n- " % ("\n\n" if info else "")
                names = {}
                for x in changes["schema"]:
                    names.setdefault(x.Category, []).append(x.Name)
                info += "\n- ".join("%s %s" % (c, fmt_entity(n, force=False))
                        for c in self.db.CATEGORIES for n in names.get(c, ()))
            if changes.get("pragma"):
                info += "%sPRAGMA settings" % ("\n\n" if info else "")
            if temp and self.db.temporary:
                info += "%s%s is a temporary file." % ("\n\n" if info else "", self.db)
            return info

        def clipboard_copy(text, *_, **__):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text() if callable(text) else text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()


        if "data" == cmd:
            self.notebook.SetSelection(self.pageorder[self.page_data])
            names = args[1:]
            for name in names:
                category = next((c for c, xx in self.db.schema.items() if name in xx), None)
                page = self.data_pages[category].get(name) or \
                       self.add_data_page(self.db.get_category(category, name))
                self.notebook_data.SetSelection(self.notebook_data.GetPageIndex(page))
        elif "create" == cmd:
            self.notebook.SetSelection(self.pageorder[self.page_schema])
            category = args[0]
            sourcecat, sourcename = (list(args[1:]) + [None, None])[:2]
            meta = args[3] if len(args) > 3 else {}
            newdata = {"type": category,
                       "meta": {"__type__": "CREATE %s" % category.upper()}}
            if category in ("index", "trigger"):
                if "table" == sourcecat:
                    newdata["meta"]["table"] = sourcename
                elif "trigger" == category and "view" == sourcecat:
                    newdata["meta"]["table"] = sourcename
                    newdata["meta"]["upon"] = grammar.SQL.INSTEAD_OF
            if meta: newdata["meta"].update(meta)
            self.add_schema_page(newdata)
        elif "schema" == cmd:
            self.notebook.SetSelection(self.pageorder[self.page_schema])
            names = args[1:]
            for name in names:
                category = next((c for c, xx in self.db.schema.items() if name in xx), None)
                page = self.schema_pages[category].get(name) or \
                       self.add_schema_page(self.db.get_category(category, name))
                self.notebook_schema.SetSelection(self.notebook_schema.GetPageIndex(page))
        elif "drop schema" == cmd:
            CATEGORY_ORDER = ["table", "view", "index", "trigger"]

            categories = {c: list(vv) for c, vv in self.db.schema.items() if vv}
            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to drop everything in the database?",
                conf.Title, wx.ICON_WARNING, default=wx.NO
            ): return

            if wx.YES != controls.YesNoMessageBox(
                "Are you REALLY sure you want to drop everything in the database?\n\n"
                "This will delete: %s." % util.join(", ", 
                    (util.plural(c, categories[c]) for c in CATEGORY_ORDER if c in categories)
                ), conf.Title, wx.ICON_WARNING, default=wx.NO
            ): return

            datapages = sum((list(d.values()) for d in self.data_pages.values()), [])
            locks = self.db.get_locks(skip=datapages)
            if locks:
                wx.MessageBox("Cannot drop schema, database has locks:\n\n- %s." % "\n- ".join(locks),
                              conf.Title)
                return
            if any(p.IsExporting() for p in self.sql_pages.values()):
                wx.MessageBox("Cannot drop schema, SQL query export in progress.",
                              conf.Title)
                return

            pages = []
            for category, names in categories.items():
                for pagedict in (self.data_pages, self.schema_pages):
                    pages.extend(pagedict[category][n] for n in names
                                 if n in pagedict.get(category, {}))
            for page in pages: page.Close(force=True)
            for page in self.sql_pages.values(): page.CloseGrid()

            deleteds = []
            try:
                for category, names in ((c, categories.get(c)) for c in CATEGORY_ORDER):
                    for name in names or ():
                        self.db.executeaction("DROP %s IF EXISTS %s" % (category.upper(),
                                              grammar.quote(name)), name="DROP")
                        deleteds += [name]
            finally:
                if deleteds:
                    try: self.db.executeaction("VACUUM", name="DROP")
                    except Exception:
                        logger.exception("Error running VACUUM after dropping schema.")
                    def after():
                        if not self: return
                        self.reload_schema()
                        self.update_page_header(updated=True)
                    wx.CallAfter(after)

        elif "drop" == cmd:
            category = args[0]
            names = args[1] if len(args) > 1 else list(self.db.schema[category])

            lock = self.db.get_lock(category=None)
            if lock: return wx.MessageBox("%s, cannot drop." % lock,
                                          conf.Title, wx.OK | wx.ICON_WARNING)

            CATEGORY_ORDER = ["table", "view", "index", "trigger"]
            categories = {category: names} if category else \
                         OrderedDict((c, [n for n in names if n in d])
                                     for c in CATEGORY_ORDER
                                     for d in [self.db.schema.get(c, {})]
                                     if set(names) & set(d))
            extra = "\n\nAll data, and any associated indexes and triggers will be lost." \
                    if "table" in categories else ""
            itemtext = ", and ".join("%s %s" % (
                util.plural(c, nn, numbers=False), ", ".join(map(fmt_entity, nn))
            ) for c, nn in categories.items())
            if len(names) == 1:
                itemtext = "the %s %s" % (next(iter(categories)), fmt_entity(names[0]))

            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to drop %s?%s" % (itemtext, extra),
                conf.Title, wx.ICON_WARNING, default=wx.NO
            ): return

            items = self.db.get_category("table", categories["table"]).values() \
                    if "table" in categories else ()
            if any(x.get("count") for x in items):
                if wx.YES != controls.YesNoMessageBox(
                    "Are you REALLY sure you want to drop the %s?\n\n"
                    "%s currently %s %s." % (
                        util.plural("table", categories["table"]),
                        "They" if len(categories["table"]) > 1 else "It",
                        "contain" if len(categories["table"]) > 1 else "contains",
                        util.count(items, "row")
                    ), conf.Title, wx.ICON_WARNING, default=wx.NO
                ): return

            datapages = sum(([p for n, p in d.items() if n in categories.get(c, {})]
                             for c, d in self.data_pages.items()), [])
            deleteds, notdeleteds = {}, OrderedDict()
            try:
                for category, names in categories.items():
                    for name in names:
                        lock = self.db.get_lock(category, name, skip=datapages)
                        if lock:
                            notdeleteds.setdefault(category, {})[name] = lock
                            continue # for name

                        for pagedict in (self.data_pages, self.schema_pages):
                            page = pagedict.get(category, {}).get(name)
                            if page: page.Close(force=True)

                        for subcategory, subdict in self.db.get_related(
                            category, name, own=True, clone=False
                        ).items() if category in ("table", "view") else ():
                            for subname in subdict: # Close child index/trigger pages
                                page = self.schema_pages.get(subcategory, {}).get(subname)
                                if page: page.Close(force=True)

                        try:
                            self.db.executeaction("DROP %s IF EXISTS %s" % (category.upper(),
                                                  grammar.quote(name)), name="DROP")
                            deleteds.setdefault(category, []).append(name)
                        except Exception as e:
                            logger.exception("Error dropping %s %s.", category,
                                             fmt_entity(name, limit=0))
                            notdeleteds.setdefault(category, {})[name] = util.format_exc(e)
            finally:
                def after_err():
                    if not self: return
                    wx.MessageBox("Failed to drop %s:\n\n- %s" % (
                        util.join(", ", (util.plural(c, nn) for c, nn in notdeleteds.items())),
                        "\n- ".join("%s %s: %s" % (c, fmt_entity(n), v)
                                    for c, d in notdeleteds.items() for n, v in d.items())
                    ), conf.Title, wx.ICON_WARNING | wx.OK)
                    
                if notdeleteds: wx.CallAfter(after_err) if deleteds else after_err()
                if deleteds:
                    guibase.status("Dropped %s." % util.join(", ", (
                        util.plural(c, deleteds[c]) for c in CATEGORY_ORDER if c in deleteds
                    )), log=True)
                    def after():
                        if not self: return
                        self.reload_schema()
                        self.update_page_header(updated=True)
                    wx.CallAfter(after)

        elif "drop column" == cmd:
            category, (name, column) = "table", args[:2]
            qname, qcolumn = (fmt_entity(n, force=True) for n in (name, column))
            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to drop %s %s column %s?" % 
                (category, qname, qcolumn), conf.Title, wx.ICON_WARNING, default=wx.NO
            ): return

            deps = self.db.get_column_dependents(category, name, column)
            if deps:
                wx.MessageBox("Cannot drop %s %s column %s, in use in:\n\n- %s" %
                    (category, qname, qcolumn, "\n- ".join("%s: %s" % (
                        util.plural(c, nn, numbers=False), util.join(", ", map(fmt_entity, nn))
                    ) for c, nn in deps.items())), conf.Title, wx.ICON_WARNING
                )
                return

            datapage = self.data_pages.get(category, {}).get(name)
            lock = self.db.get_lock(category, name, skip=list(filter(bool, [datapage])))
            if lock:
                wx.MessageBox(
                    "Cannot drop %s %s column %s.\n\n" % 
                    (category, qname, qcolumn, lock), conf.Title, wx.ICON_WARNING
                )
                return

            schemapage = self.schema_pages.get(category, {}).get(name)
            if datapage and datapage.IsChanged():
                res = wx.MessageBox(
                    "There are unsaved changes to %s %s data.\n\n"
                    "Commit changes before column drop?" % (category, qname),
                    conf.Title, wx.ICON_WARNING | wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT
                )
                if res == wx.CANCEL: return
                elif res == wx.YES:
                    if not datapage.Save(): return
                else: datapage.Rollback(force=True)
            if datapage: datapage.CloseCursor()
            if schemapage and schemapage.IsChanged():
                if wx.CANCEL == wx.MessageBox(
                    "There are unsaved changes to %s %s schema.\n\n"
                    "Discard changes before column drop?" % (category, qname),
                    conf.Title, wx.ICON_WARNING | wx.OK | wx.CANCEL | wx.CANCEL_DEFAULT
                ): return
            if schemapage: schemapage.SetReadOnly()

            self.toggle_cursors(category, name, close=True)
            extradrops = self.db.drop_column(name, column)
            def after():
                if not self: return
                self.reload_schema()
                self.toggle_cursors(category, name)
            wx.CallAfter(after) if extradrops else after()
            for c, d in extradrops.items():
                for n in d:
                    schemapage = self.schema_pages.get(c, {}).get(n)
                    if schemapage: schemapage.Close(force=True)
            if extradrops:
                wx.MessageBox("Also dropped column %s dependents:\n\n- %s\n\n%s" % 
                              (qname, "\n- ".join("%s %s" % (
                                  (util.plural(c, d, numbers=False),
                                   ", ".join(map(fmt_entity, d)))
                               ) for c, d in extradrops.items()),
                               "\n\n".join(x["sql"] for c, d in extradrops.items()
                                           for x in d.values())
                              ), conf.Title)

        elif "truncate" == cmd:
            self.on_truncate(args) if args else self.on_truncate_all()
        elif "reindex" == cmd:
            if not self.db.schema.get("index"):
                return wx.MessageBox("No indexes to re-create.", conf.Title,
                                     wx.ICON_INFORMATION)

            category = (list(args) + [None])[0]
            names = args[1:]

            targets = indexes = list(self.db.schema["index"])
            if names and "table" == category:
                targets = names
                indexes = [n for name in names for k, m in self.db.get_related(category, name, own=True).items()
                           if "index" == k for n in m]
                names = [n for n in names if any("index" == k for k in self.db.get_related(category, n, own=True))]
                label = "%s on %s %s" % (util.plural("index", indexes, single="the"),
                                         util.plural("table", names, numbers=False),
                                         util.join(", ", map(fmt_entity, names)))
                lock = any(self.db.get_lock(category, n) for n in names)
            elif names:
                targets = indexes = names
                label = "%s %s" % (util.plural("index", names, numbers=False, single="the"),
                                   util.join(", ", map(fmt_entity, names)))
                lock = any(self.db.get_lock("table", self.db.schema["index"][name]["tbl_name"])
                           for name in names)
            elif "table" == category:
                targets = list(self.db.schema["table"])
                label = "indexes on all tables"
                lock = self.db.get_lock("table")
            else:
                label = "all indexes"
                lock = self.db.get_lock("table")
            if not indexes: return wx.MessageBox("No indexes to re-create.",
                                                 conf.Title, wx.ICON_INFORMATION)
                
            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to re-create %s?" % label,
                conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return

            if lock: return wx.MessageBox("%s, cannot reindex." % lock,
                                          conf.Title, wx.OK | wx.ICON_WARNING)

            sql = "REINDEX" if not names else \
                  "\n\n".join("REINDEX main.%s;" % grammar.quote(x) for x in targets)
            busy = controls.BusyPanel(self, "Re-creating %s.." % label)
            try:
                logger.info("Running REINDEX on %s in %s.", label, self.db)
                self.db.executescript(sql, name="REINDEX")
                busy.Close()
                self.update_info_panel()
                self.on_update_statistics()
                wx.MessageBox("Re-created %s." % util.plural("index", indexes),
                              conf.Title, wx.ICON_INFORMATION)
            finally: busy.Close()
        elif "rename" == cmd:
            category, name, name2 = (list(args) + [None])[:3]
            if name not in self.db.schema.get(category) or {}: return
            if not name2:
                dlg = wx.TextEntryDialog(self, 
                    'Rename %s %s to:' % (category, fmt_entity(name)),
                    conf.Title, value=name, style=wx.OK | wx.CANCEL
                )
                dlg.CenterOnParent()
                if wx.ID_OK != dlg.ShowModal(): return

                name2 = dlg.GetValue().strip()
                if not name2 or name2 == name: return

            duplicate = next((vv.get(name2) for vv in self.db.schema.values()), None) \
                        if not util.lceq(name, name2) else None
            if duplicate:
                wx.MessageBox(
                    "Cannot rename %s: there already exists %s named %s." %
                    (category, util.articled(duplicate["type"]),
                     fmt_entity(duplicate["name"])),
                    conf.Title, wx.ICON_WARNING | wx.OK
                )
                return

            pages = [pp.get(category, {}).get(name)
                     for pp in (self.data_pages, self.schema_pages)]
            for page in pages:
                if isinstance(page, components.DataObjectPage):
                    if page.IsChanged():
                        res = wx.MessageBox(
                            "There are unsaved changes to table %s data.\n\n"
                            "Commit changes before rename?" % fmt_entity(name),
                            conf.Title, wx.ICON_WARNING | wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT
                        )
                        if res == wx.CANCEL: return
                        elif res == wx.YES:
                            if not page.Save(): return
                        else: page.Rollback(force=True)
                    page.CloseCursor()
                if isinstance(page, components.SchemaObjectPage):
                    if page.IsChanged():
                        if wx.CANCEL == wx.MessageBox(
                            "There are unsaved changes to %s %s schema.\n\n"
                            "Discard changes before rename?" % (category, fmt_entity(name)),
                            conf.Title, wx.ICON_WARNING | wx.OK | wx.CANCEL | wx.CANCEL_DEFAULT
                        ): return
                    page.SetReadOnly()

            self.toggle_cursors(category, name, close=True)
            self.db.rename_item(category, name, name2)
            self.reload_schema()

            # Update name of the item's data/schema pages
            for page, pagemap, nb in zip(pages, [self.data_pages, self.schema_pages],
                                         [self.notebook_data, self.notebook_schema]):
                for myitem in self.pages_closed.get(nb, []):
                    if myitem["name"] == name: myitem["name"] = name2
                    break # for myitem
                if not page: continue # for page, pagemap, nb

                pagemap[category].pop(name)
                title = "%s %s" % (category.capitalize(), grammar.quote(name2))
                title = make_unique_page_title(title, nb, skip=nb.GetPageIndex(page))
                nb.SetPageText(nb.GetPageIndex(page), title)
                pagemap[category][name2] = page
                if isinstance(page, components.SchemaObjectPage):
                    page.Reload(item=self.db.get_category(category, name2))
            self.toggle_cursors(category, name2)
            return True

        elif "rename column" == cmd:
            table, name, name2 = (list(args) + [None])[:3]
            item = self.db.get_category("table", table)
            if not item: return
            if not name2:
                dlg = wx.TextEntryDialog(self, 
                    "Rename column %s.%s to:"
                    % (fmt_entity(table, force=False), fmt_entity(name, force=False)),
                    conf.Title, value=name, style=wx.OK | wx.CANCEL
                )
                dlg.CenterOnParent()
                if wx.ID_OK != dlg.ShowModal(): return

                name2 = dlg.GetValue().strip()
                if not name2 or name2 == name: return

            duplicate = next((v for v in item["columns"] if util.lceq(name2, v["name"])), None) \
                        if not util.lceq(name, name2) else None
            if duplicate:
                wx.MessageBox(
                    "Cannot rename column: table %s already has a column named %s." %
                    (fmt_entity(table), fmt_entity(duplicate["name"])),
                    conf.Title, wx.ICON_WARNING | wx.OK
                )
                return

            pages = [pp.get("table", {}).get(table)
                     for pp in (self.data_pages, self.schema_pages)]
            for page in pages:
                if isinstance(page, components.DataObjectPage):
                    if page.IsChanged():
                        res = wx.MessageBox(
                            "There are unsaved changes to table %s data.\n\n"
                            "Commit changes before column rename?" % fmt_entity(table),
                            conf.Title, wx.ICON_WARNING | wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT
                        )
                        if res == wx.CANCEL: return
                        elif res == wx.YES:
                            if not page.Save(): return
                        else: page.Rollback(force=True)
                    page.CloseCursor()
                if isinstance(page, components.SchemaObjectPage):
                    if page.IsChanged():
                        if wx.CANCEL == wx.MessageBox(
                            "There are unsaved changes to table %s schema.\n\n"
                            "Discard changes before column rename?" % fmt_entity(table),
                            conf.Title, wx.ICON_WARNING | wx.OK | wx.CANCEL | wx.CANCEL_DEFAULT
                        ): return
                    page.SetReadOnly()

            self.toggle_cursors("table", name, close=True)
            self.db.rename_column(table, name, name2)
            self.reload_schema()
            self.toggle_cursors("table", table)
            return True

        elif "clone" == cmd:
            (category, name), with_data = args[:2], (list(args) + [False])[2]
            item = self.db.schema[category][name]

            allnames = sum(map(list, self.db.schema.values()), [])
            name2 = util.make_unique(name, allnames)
            dlg = wx.TextEntryDialog(self, "Clone %s%s %s as:"
                % (category, fmt_entity(name), "" if with_data else " structure"),
                conf.Title, value=name2, style=wx.OK | wx.CANCEL
            )
            dlg.CenterOnParent()
            if wx.ID_OK != dlg.ShowModal(): return

            name2 = dlg.GetValue().strip()
            if not name2 or name2.lower() == name.lower(): return

            qname, qname2 = (grammar.quote(n, force=True) for n in (name, name2))
            sname, sname2 = fmt_entity(name), fmt_entity(name2)

            duplicate = next((vv.get(name2) for vv in self.db.schema.values()), None)
            if duplicate:
                wx.MessageBox(
                    "Cannot clone %s as %s:\n\nthere already exists %s named %s."
                    % (category, sname2, util.articled(duplicate["type"]),
                       fmt_entity(duplicate["name"])),
                    conf.Title, wx.ICON_WARNING | wx.OK
                )
                return

            busy = controls.BusyPanel(self, "Cloning %s.." % category)
            try:
                allnames.append(name2)
                renames = {category: {name: name2}}
                rels = self.db.get_related(category, name, own=True)

                create_sql = grammar.transform(item["sql"], renames=renames)[0]
                rel_sqls = []
                for relitem in (x for xx in rels.values() for x in xx.values()):
                    relname2 = util.make_unique(relitem["name"], allnames)
                    allnames.append(relname2)
                    renames.setdefault(relitem["type"], {})[relitem["name"]] = relname2
                    rel_sql2, err = grammar.transform(relitem["sql"], renames=renames)
                    if not err: rel_sqls.append(rel_sql2)
                errors = []
                guibase.status("Cloning %s %s as %s." % (category, sname, sname2), log=True)
                try:
                    self.db.executescript(create_sql, name="CLONE")
                except Exception as e:
                    logger.exception("Error cloning %s %s as %s.", category, qname, create_sql)
                    msg = "Error cloning %s %s as\n\n%s." % (category, sname, create_sql)
                    guibase.status(msg)
                    error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
                    wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
                    return

                try:
                    if "table" == category and with_data:
                        insert_sql = "INSERT INTO %s SELECT * FROM %s" \
                                     % (grammar.quote(name2), grammar.quote(name))
                        logger.info("Copying data from %s %s to %s.", category, qname, qname2)
                        self.db.executescript(insert_sql, name="CLONE")
                except Exception as e:
                    logger.exception("Error copying %s %s data to %s.",
                                     category, qname, qname2)
                    msg = "Error copying %s %s data to %s." % (category, sname, sname2)
                    guibase.status(msg)
                    errors.append(msg[:-1] + (":\n\n%s" % util.format_exc(e)))

                rellabel = " and ".join(util.plural(k, v, numbers=False)
                                        for k, v in rels.items())
                try:
                    if rel_sqls:
                        logger.info("Cloning %s of %s %s for %s.",
                                    rellabel, category, qname, qname2)
                        self.db.executescript("\n\n".join(rel_sqls), name="CLONE")
                except Exception as e:
                    logger.exception("Error cloning %s %s %s for %s.",
                                     category, qname, rellabel, qname2)
                    msg = "Error cloning %s %s %s for %s." \
                          % (category, sname, rellabel, sname2)
                    guibase.status(msg)
                    errors.append(msg[:-1] + (":\n\n%s" % util.format_exc(e)))

                busy.Close()
                self.reload_schema(count=True)
                guibase.status("Cloned %s %s as %s." % (category, sname, sname2), log=True)
                if errors: wx.MessageBox("Errors were encountered during cloning:\n\n%s"
                                         % "\n\n".join(errors), conf.Title,
                                         wx.OK | wx.ICON_WARNING)
            finally:
                busy.Close()

        elif "refresh" == cmd:
            self.reload_schema(count=True)
        elif "locks" == cmd:
            locks = self.db.get_locks()
            wx.MessageBox(("Current database locks:\n\n- %s." % "\n- ".join(locks))
                          if locks else "Database is currently unlocked.", conf.Title)
        elif "changes" == cmd:
            wx.MessageBox("Current unsaved changes:\n\n%s" %
                          format_changes(temp=True), conf.Title)
        elif "history" == cmd:
            components.HistoryDialog(self, self.db).ShowModal()
        elif "folder" == cmd:
            util.select_file(self.db.filename)
        elif "save" == cmd:
            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to save the following changes:\n\n%s" %
                format_changes(), conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return

            self.save_database()
        elif "cancel" == cmd:
            if wx.YES != controls.YesNoMessageBox(
                "Are you sure you want to cancel the following changes:\n\n%s" %
                format_changes(), conf.Title, wx.ICON_INFORMATION, default=wx.NO
            ): return

            self.on_pragma_cancel()
            for p in (y for x in self.data_pages.values() for y in x.values()):
                if p.IsChanged(): p.Reload(force=True)
            for p in (y for x in self.schema_pages.values() for y in x.values()):
                if p.IsChanged(): p.Reload(force=True)
        elif "optimize" == cmd:
            self.on_optimize()
        elif "vacuum" == cmd:
            self.on_vacuum()
        elif "integrity" == cmd:
            self.on_check_integrity()
        elif "fks" == cmd:
            self.on_check_fks()
        elif "import" == cmd:
            components.ImportDialog(self, self.db).ShowModal()
        elif "copy" == cmd:
            target = args[0]
            if "related" == target:

                sqls = defaultdict(OrderedDict) # {category: {name: sql}}

                def collect(relateds):
                    for category, item in ((c, v) for c, vv in relateds.items() for v in vv.values()):
                        sqls[category][item["name"]] = item["sql"]
                        if category not in ("table", "view"): continue # for category, item
                        subrelateds = self.db.get_related("table", item["name"], own=True)
                        for subcategory, subitemmap in subrelateds.items():
                            for subitem in subitemmap.values():
                                sqls[subcategory][subitem["name"]] = subitem["sql"]

                names = args[2:]
                for name in names:
                    category = next(c for c, xx in self.db.schema.items() if name in xx)
                    sqls[category][name] = self.db.get_sql(category, name)
                    collect(self.db.get_related(category, name, own=True))
                    collect(self.db.get_related(category, name))
                clipboard_copy("\n\n".join(x.rstrip(";") + ";" for c in sqls for x in sqls[c].values()) + "\n\n")
                guibase.status("Copied SQL to clipboard.")

        elif "export" == cmd:
            arg = args[0]
            if arg in ("tables", "single", "data", "structure") \
            and not self.db.schema["table"]: return wx.MessageBox(
                "No tables to save.", conf.Title, wx.ICON_NONE
            )
            if arg in ("tables", "single", "dump") \
            and self.panel_data_export.IsRunning(): return wx.MessageBox(
                "A global export is already underway.", conf.Title, wx.ICON_NONE
            )

            if "tables" == arg:
                self.notebook.SetSelection(self.pageorder[self.page_data])
                self.on_export_data_file("table", list(self.db.schema["table"]))
            elif "single" == arg:
                self.notebook.SetSelection(self.pageorder[self.page_data])
                self.on_export_singlefile("table")
            elif "data" == arg:
                self.on_export_to_db("table", category=list(self.db.schema["table"]))
            elif "structure" == arg:
                self.on_export_to_db("table", category=list(self.db.schema["table"]), data=False)
            elif "pragma" == arg:
                template = step.Template(templates.PRAGMA_SQL, strip=False)
                sql = template.expand(pragma=self.pragma)
                self.save_sql(sql, "PRAGMA")
            elif "schema" == arg:
                if any(self.db.schema.values()): return self.save_sql(self.stc_schema.Text)

                wx.MessageBox("No schema to save.", conf.Title, wx.ICON_NONE)
            elif "statistics" == arg:
                if any(self.db.schema.values()): return self.on_save_statistics()
                wx.MessageBox("No statistics to save, database is empty.", conf.Title, wx.ICON_NONE)
            elif "dump" == arg:
                self.notebook.SetSelection(self.pageorder[self.page_data])
                self.on_dump()


    def on_sys_colour_change(self, event):
        """Handler for system colour change, refreshes content."""
        event.Skip()
        def dorefresh():
            if not self: return
            self.label_html.SetPage(step.Template(templates.SEARCH_HELP_SHORT_HTML).expand())
            self.label_html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNFACE)
            self.label_html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
            default = step.Template(templates.SEARCH_WELCOME_HTML).expand()
            self.notebook_search.SetCustomPage(default)
            self.populate_statistics()
            self.load_tree_data()
            self.load_tree_schema()
        wx.CallAfter(dorefresh) # Postpone to allow conf update


    def on_drop_files(self, filenames):
        """
        Handler for dropping files onto database page, opens import dialog
        for spreadsheets, forwards database files to parent to open.
        """
        dbfiles = [x for x in filenames
                   if os.path.splitext(x)[-1].lower() in conf.DBExtensions]
        importfiles = [x for x in filenames
                       if os.path.splitext(x)[-1][1:].lower() in importexport.IMPORT_EXTS]
        for dbfile in dbfiles:
            wx.PostEvent(self, OpenDatabaseEvent(self.Id, file=dbfile))
        if importfiles:
            dlg = components.ImportDialog(self, self.db)
            wx.CallAfter(lambda: dlg and dlg._OnFile(filename=importfiles[0]))
            dlg.ShowModal()


    def make_page_notebook(self, parent):
        """Returns wx.lib.agw.flatnotebook.FlatNotebook for a subpage."""
        agwStyle = (wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST |
                    wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                    wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                    wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                    wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                    wx.lib.agw.flatnotebook.FNB_X_ON_TAB |
                    wx.lib.agw.flatnotebook.FNB_VC8)
        if "linux" in sys.platform and wx.VERSION[:3] == (4, 1, 1):
            # wxPython 4.1.1 on Linux crashes with FNB_VC8
            agwStyle ^= wx.lib.agw.flatnotebook.FNB_VC8
        return wx.lib.agw.flatnotebook.FlatNotebook(parent, size=(-1, 27), agwStyle=agwStyle)


    def register_notebook_hotkeys(self, notebook):
        """Register Ctrl-W close and Ctrl-Shift-T reopen handler to notebook pages."""
        def on_close_hotkey(event=None):
            if not notebook: return
            if notebook is self.notebook_sql: # Close SQL grid first
                page = notebook.GetPage(notebook.GetSelection())
                if page.HasGrid(): return page.CloseGrid()
            notebook.DeletePage(notebook.GetSelection())
        def on_reopen_hotkey(event=None):
            if not notebook: return
            self.reopen_page(notebook, -1)

        id_close, id_reopen = wx.NewIdRef().Id, wx.NewIdRef().Id
        accelerators = [(wx.ACCEL_CMD,                  ord("W"), id_close),
                        (wx.ACCEL_CMD | wx.ACCEL_SHIFT, ord("T"), id_reopen)]
        notebook.Bind(wx.EVT_MENU, on_close_hotkey,  id=id_close)
        notebook.Bind(wx.EVT_MENU, on_reopen_hotkey, id=id_reopen)
        notebook.SetAcceleratorTable(wx.AcceleratorTable(accelerators))


    def on_change_page(self, event):
        """
        Handler for changing a page in the main Notebook, focuses content.
        """
        event.Skip()
        self.notebook.GetCurrentPage().SetFocus()


    def on_toggle_numbers_stc_schema(self, event):
        """Handler for toggling line numbers in schema STC, saves configuration."""
        conf.SchemaLineNumbered = event.IsChecked()
        w = 0
        if conf.SchemaLineNumbered:
            w = max(25, 5 + 10 * int(math.log(self.stc_schema.LineCount, 10)))
        self.stc_schema.SetMarginWidth(0, w)
        util.run_once(conf.save)


    def on_toggle_wrap_stc_schema(self, event):
        """Handler for toggling word-wrap in schema STC, saves configuration."""
        conf.SchemaWordWrap = event.IsChecked()
        mode = wx.stc.STC_WRAP_WORD if conf.SchemaWordWrap else wx.stc.STC_WRAP_NONE
        self.stc_schema.SetWrapMode(mode)
        util.run_once(conf.save)


    def on_update_stc_schema(self, event=None):
        """Handler for clicking to refresh database schema SQL."""
        scrollpos = self.stc_schema.GetScrollPos(wx.VERTICAL)

        self.stc_schema.SetReadOnly(False)
        self.stc_schema.SetText("Parsing..")
        self.stc_schema.SetReadOnly(True)
        self.tb_sql.EnableTool(wx.ID_COPY, False)
        self.tb_sql.EnableTool(wx.ID_SAVE, False)

        if event: self.db.populate_schema(parse=True)
        sql = self.db.get_sql()
        self.stc_schema.SetReadOnly(False)
        self.stc_schema.SetText(sql + ("\n" if sql else ""))
        self.stc_schema.SetReadOnly(True)
        self.stc_schema.ScrollToLine(scrollpos)
        self.tb_sql.EnableTool(wx.ID_COPY, bool(sql))
        self.tb_sql.EnableTool(wx.ID_SAVE, bool(sql))


    def on_update_statistics(self, event=None):
        """
        Handler for refreshing database statistics, sets loading-content
        and tasks worker.
        """
        if not event and not conf.RunStatistics: return

        self.statistics = {}
        self.worker_analyzer.work(self.db.filename)
        self.db.lock(None, None, self.db, label="statistics analysis")
        wx.CallAfter(self.populate_statistics)


    def on_copy_statistics(self, event=None):
        """Handler for copying database statistics to clipboard."""
        if wx.TheClipboard.Open():
            template = step.Template(templates.DATA_STATISTICS_TXT, strip=False)
            content = template.expand(db=self.db, stats=self.statistics.get("data", {}))
            d = wx.TextDataObject(content)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied database statistics to clipboard.")


    def on_save_statistics(self, event=None):
        """
        Handler for saving database statistics to file, pops open file dialog
        and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.name))[0]
        filename = filename.rstrip() + " statistics"
        dialog = wx.FileDialog(
            self, message="Save statistics as", defaultFile=filename,
            wildcard="HTML file (*.html)|*.html|SQL file (*.sql)|*.sql|"
                     "Text file (*.txt)|*.txt",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | 
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = controls.get_dialog_path(dialog)
        extname = os.path.splitext(filename)[-1].lstrip(".")

        busy = controls.BusyPanel(self, "Exporting statistics.")
        try:
            data, diagram = self.statistics.get("data") or {}, None
            if "HTML" == extname.upper():
                args = dict(selections=False, statistics=True,
                            show_lines=True, show_labels=True)
                bmp = self.diagram.MakeBitmap(zoom=1, defaultcolours=True, **args)
                svg = self.diagram.MakeTemplate("SVG", title="", embed=True, **args)
                diagram = {"bmp": bmp, "svg": svg}
            importexport.export_stats(filename, self.db, data, diagram)
            guibase.status('Exported to "%s".', filename, log=True)
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving statistics %s to %s." % (extname.upper(), filename)
            logger.exception(msg); guibase.status(msg)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally: busy.Close()


    def on_stop_statistics(self, event=None):
        """Stops current analyzer work."""
        if not self.worker_analyzer.is_working(): return

        self.worker_analyzer.stop_work()
        self.db.unlock(None, None, self.db)
        self.html_stats.SetPage("")
        self.html_stats.BackgroundColour = conf.BgColour
        self.tb_stats.EnableTool(wx.ID_REFRESH, True)
        self.tb_stats.SetToolNormalBitmap(wx.ID_STOP, images.ToolbarStopped.Bitmap)


    def on_analyzer_result(self, result):
        """
        Handler for getting results from analyzer thread, populates statistics.
        """
        if not self: return
        self.statistics = result
        self.db.unlock(None, None, self.db)
        if "data" in result: self.db.set_sizes(result["data"])

        def after():
            if not self: return
            if result:
                if "error" not in result:
                    guibase.status("Statistics analysis complete.")
                    self.diagram.UpdateStatistics(redraw=False)
                    if self.diagram.ShowStatistics: self.diagram.Redraw(remake=True)
                self.cb_diagram_stats.Enable(self.diagram.Enabled)
                self.populate_statistics()
                self.update_page_header(updated="error" not in result)
        wx.CallAfter(after)


    def on_checksum_result(self, result):
        """
        Handler for getting results from checksum thread, populates information.
        """
        def after():
            if not self: return
            # Gtk tends to crash if not clearing these before setting longer value
            self.edit_info_sha1.Value = ""
            self.edit_info_md5.Value  = ""
            if "error" in result:
                self.edit_info_sha1.Value = result["error"]
                self.edit_info_md5.Value  = result["error"]
            else:
                self.edit_info_sha1.Value = result["sha1"]
                self.edit_info_md5.Value  = result["md5"]
            self.edit_info_sha1.MinSize = (-1, -1)
            self.edit_info_md5.MinSize  = (-1, -1)
            self.button_checksum_stop.Hide()
            self.edit_info_md5.ContainingSizer.Layout()
        wx.CallAfter(after)


    def populate_statistics(self):
        """Populates statistics HTML window."""
        if not self: return
        previous_scrollpos = getattr(self.html_stats, "_last_scroll_pos", None)
        ns = dict(self.statistics, running=self.worker_analyzer.is_working())
        html = step.Template(templates.STATISTICS_HTML, escape=True).expand(ns)
        self.html_stats.Freeze()
        try:
            self.html_stats.SetPage(html)
            self.html_stats.BackgroundColour = conf.BgColour
            if previous_scrollpos:
                self.html_stats.Scroll(*previous_scrollpos)
        finally: self.html_stats.Thaw()
        self.tb_stats.EnableTool(wx.ID_REFRESH, not self.worker_analyzer.is_working())
        bmp = images.ToolbarStop.Bitmap if self.worker_analyzer.is_working() \
              else images.ToolbarStopped.Bitmap
        self.tb_stats.SetToolNormalBitmap(wx.ID_STOP, bmp)


    def update_diagram_controls(self):
        """Updates diagram toolbar and other controls with diagram state."""
        self.tb_diagram.EnableTool(wx.ID_ZOOM_IN,  self.diagram.Enabled and self.diagram.Zoom < self.diagram.ZOOM_MAX)
        self.tb_diagram.EnableTool(wx.ID_ZOOM_OUT, self.diagram.Enabled and self.diagram.Zoom > self.diagram.ZOOM_MIN)
        self.tb_diagram.EnableTool(wx.ID_ZOOM_100, self.diagram.Enabled and self.diagram.Zoom != self.diagram.ZOOM_DEFAULT)
        self.combo_diagram_zoom.Value = "%s%%" % util.round_float(100 * self.diagram.Zoom, 2)
        self.tb_diagram.ToggleTool(wx.ID_APPLY,   self.diagram.Enabled)
        self.tb_diagram.ToggleTool(wx.ID_STATIC,  self.diagram.LAYOUT_GRID  == self.diagram.Layout)
        self.tb_diagram.ToggleTool(wx.ID_NETWORK, self.diagram.LAYOUT_GRAPH == self.diagram.Layout)
        self.cb_diagram_rels  .Value = self.diagram.ShowLines
        self.cb_diagram_labels.Value = self.diagram.ShowLineLabels
        self.cb_diagram_stats .Value = self.diagram.ShowStatistics

        for myid in wx.ID_ZOOM_FIT, wx.ID_STATIC, wx.ID_NETWORK:
            self.tb_diagram.EnableTool(myid, self.diagram.Enabled)

        schema_parsed = any(v.get("__parsed__") for vv in self.db.schema.values() for v in vv.values())
        self.combo_diagram_zoom.Enable(self.diagram.Enabled)
        self.cb_diagram_rels  .Enable(self.diagram.Enabled and schema_parsed)
        self.cb_diagram_labels.Enable(self.diagram.Enabled and schema_parsed)
        self.cb_diagram_stats .Enable(self.diagram.Enabled and "data" in self.statistics)
        self.label_diagram_find.Enable(self.diagram.Enabled)
        self.combo_diagram_find.Enable(self.diagram.Enabled)
        self.button_diagram_export.Enable(self.diagram.Enabled)
        self.button_diagram_action.Enable(self.diagram.Enabled)


    def on_diagram_event(self, event=None):
        """Handler for SchemaDiagramEvent, updates toolbar state and saves conf."""
        if getattr(event, "progress", False):
            VARS = "done", "index", "count"
            done, index, count = (getattr(event, k, None) for k in VARS)
            if done:
                self.diagram_gauge.Hide()
            else:
                if not self.diagram_gauge.Shown:
                    self.diagram_gauge.Show()
                    self.diagram_gauge.ContainingSizer.Layout()
                v = self.diagram_gauge.Value = 100 * index // count
                self.diagram_gauge.ToolTip = "Generating.. %s%% (%s of %s)" % (v, index + 1, count)
            return

        self.update_diagram_controls()
        if not self.db.temporary:
            conf.SchemaDiagrams[self.db.filename] = self.diagram.GetOptions()
            util.run_once(conf.save)


    def on_diagram_toggle(self, event=None):
        """Handler for toggling diagram on/off."""
        self.diagram.Enable(event.IsChecked())
        if event.IsChecked(): self.diagram.Populate()
        conf.SchemaDiagramEnabled = event.IsChecked()
        util.run_once(conf.save)


    def on_diagram_stats(self, event):
        """Handler for toggling statistics checkbox, shows or hides stats on diagram."""
        self.diagram.ShowStatistics = self.cb_diagram_stats.Value


    def on_diagram_relations(self, event):
        """Handler for toggling foreign relations checkbox, shows or hides diagram lines."""
        self.diagram.ShowLines = self.cb_diagram_rels.Value
        self.cb_diagram_labels.Enable(self.cb_diagram_rels.Value)


    def on_diagram_labels(self, event):
        """Handler for toggling foreign labels checkbox, shows or hides diagram line labels."""
        self.diagram.ShowLineLabels = self.cb_diagram_labels.Value


    def on_diagram_export(self, event):
        """Handler for exporting diagram, opens file dialog."""
        self.diagram.SaveFile()


    def on_diagram_action(self, event):
        """Handler for other diagram actions, opens popup menu."""
        menu = wx.Menu()

        def on_export(event=None):
            CHOICES, LEVELS, index, level = [], [], -1, self.diagram.ZOOM_MAX
            while level >= self.diagram.ZOOM_MIN:
                CHOICES.append("%s%%" % util.round_float(100 * level, 2))
                LEVELS.append(level)
                if level == self.diagram.Zoom: index = len(CHOICES) - 1
                level -= self.diagram.ZOOM_STEP
            dlg = wx.SingleChoiceDialog(self, "", "Select zoom", CHOICES)
            dlg.SetSelection(index)
            res, sel = dlg.ShowModal(), dlg.GetSelection()
            dlg.Destroy()
            if wx.ID_OK != res: return
            self.diagram.SaveFile(zoom=LEVELS[sel])
        def cmd(*args):
            return lambda e: self.handle_command(*args)

        menu = wx.Menu()
        item_export = wx.MenuItem(menu, -1, "Export &zoomed bitmap")
        menu.Append(item_export)
        menu.Bind(wx.EVT_MENU, on_export, item_export)

        submenu, keys = wx.Menu(), []
        menu.AppendSubMenu(submenu, text="Create &new ..")
        for category in database.Database.CATEGORIES:
            key = next((x for x in category if x not in keys), category[0])
            keys.append(key)
            it = wx.MenuItem(submenu, -1, "New " + category.replace(key, "&" + key, 1))
            submenu.Append(it)
            menu.Bind(wx.EVT_MENU, cmd("create", category), it)

        event.EventObject.PopupMenu(menu, tuple(event.EventObject.Size))


    def on_diagram_zoom(self, direction=0, event=None):
        """Handler for zooming diagram in or out or to 100%."""
        if direction: self.diagram.Zoom += self.diagram.ZOOM_STEP * direction
        else: self.diagram.Zoom = self.diagram.ZOOM_DEFAULT


    def on_diagram_zoom_combo(self, event):
        """Handler for zoom step change in combobox."""
        if event.ClientData: self.diagram.Zoom = event.ClientData


    def on_diagram_find(self, event=None):
        """Handler for change in diagram quickfind, selects schema items."""
        if not self or not self.combo_diagram_find.Enabled: return
        if "diagram_find" in self.timers: self.timers.pop("diagram_find").Stop()
        names, text = [], self.combo_diagram_find.Value.strip().lower()
        if event and event.ClientData: names.append(event.ClientData)
        elif text:
            pattern = "".join((".*" if i or not x else "") + re.escape(x)
                              for i, x in enumerate(text.split("*")))
            rgx = re.compile("^" + pattern, re.I | re.U)
            combo = self.combo_diagram_find
            for name in map(combo.GetClientData, range(combo.Count)):
                if rgx.match(name): names.append(name)
        self.diagram.SetSelection(*names)
        if self.diagram.Selection \
        and not any(self.diagram.IsVisible(x) for x in self.diagram.Selection):
            self.diagram.EnsureVisible(self.diagram.Selection[0])


    def on_diagram_find_char(self, event):
        """
        Handler for keypress in diagram quickfind, clears diagram if Escape,
        scrolls viewport to selected item start if Enter.
        """
        event.Skip()
        had_timer = "diagram_find" in self.timers
        if had_timer: self.timers.pop("diagram_find").Stop()
        if event.KeyCode in controls.KEYS.ESCAPE:
            text = event.EventObject.Value
            event.EventObject.Value = ""
            self.diagram.SetSelection()
            if not text: self.diagram.Scroll(0, 0)
        elif event.KeyCode in controls.KEYS.ENTER:
            if had_timer: self.on_diagram_find() # Apply pending search
            if self.diagram.Selection:
                self.diagram.EnsureVisible(self.diagram.Selection[0], force=True)
        else: # Launch delayed timer to not apply search on every keypress
            self.timers["diagram_find"] = wx.CallLater(500, self.on_diagram_find)


    def on_diagram_zoom_fit(self, event=None):
        """Handler for zooming diagram to fit."""
        self.diagram.ZoomToFit()


    def on_diagram_grid(self, event=None):
        """Handler for choosing diagram grid layout, opens options menu."""

        was_grid = not self.tb_diagram.GetToolState(wx.ID_STATIC)
        self.tb_diagram.ToggleTool(wx.ID_NETWORK, False)
        self.tb_diagram.ToggleTool(wx.ID_STATIC,  True)
        if not was_grid: return self.diagram.SetLayout(self.diagram.LAYOUT_GRID)


        def set_option(**kws):
            self.diagram.SetLayout(self.diagram.LAYOUT_GRID, kws)

        menu = wx.Menu()
        item_vertical   = wx.MenuItem(menu, -1, "Items in &columns",   kind=wx.ITEM_CHECK)
        item_horizontal = wx.MenuItem(menu, -1, "Items in &rows", kind=wx.ITEM_CHECK)

        submenu = wx.Menu()
        item_name    = wx.MenuItem(submenu, -1, "&name",          kind=wx.ITEM_CHECK)
        item_columns = wx.MenuItem(submenu, -1, "&column count",  kind=wx.ITEM_CHECK)
        item_rows    = wx.MenuItem(submenu, -1, "&row count",     kind=wx.ITEM_CHECK)
        item_bytes   = wx.MenuItem(submenu, -1, "&byte count",    kind=wx.ITEM_CHECK)
        item_reverse = wx.MenuItem(submenu, -1, "&Descending order", kind=wx.ITEM_CHECK)


        menu.Append(item_vertical)
        menu.Append(item_horizontal)
        menu.AppendSeparator()
        menu.AppendSubMenu(submenu, text="&Order by ..")
        submenu.Append(item_name)
        submenu.Append(item_columns)
        submenu.Append(item_rows)
        submenu.Append(item_bytes)
        submenu.AppendSeparator()
        submenu.Append(item_reverse)

        opts = self.diagram.GetLayoutOptions(self.diagram.LAYOUT_GRID)
        item_vertical.Check  (bool(opts.get("vertical")))
        item_horizontal.Check(not opts.get("vertical"))
        item_name.Check   (opts.get("order") == "name")
        item_columns.Check(opts.get("order") == "columns")
        item_rows.Check   (opts.get("order") == "rows")
        item_bytes.Check  (opts.get("order") == "bytes")
        item_rows.Enable  (any(x.get("count") for x in self.db.schema.get("table", {}).values()))
        item_bytes.Enable (bool(self.statistics.get("data")))
        item_reverse.Check(bool(opts.get("reverse")))

        menu.Bind(wx.EVT_MENU, lambda e: set_option(vertical=True),   item_vertical)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(vertical=False),  item_horizontal)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(order="name"),    item_name)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(order="columns"), item_columns)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(order="rows"),    item_rows)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(order="bytes"),   item_bytes)
        menu.Bind(wx.EVT_MENU, lambda e: set_option(reverse=e.IsChecked()), item_reverse)

        rect = controls.get_tool_rect(self.tb_diagram, wx.ID_STATIC)
        self.diagram.PopupMenu(menu, rect.Right + 2, -rect.Height - 2)


    def on_diagram_graph(self, event):
        """Handler for choosing diagram graph layout, toggles grid layout off."""
        self.diagram.SetLayout(self.diagram.LAYOUT_GRAPH)
        self.tb_diagram.ToggleTool(wx.ID_NETWORK, True)
        self.tb_diagram.ToggleTool(wx.ID_STATIC,  False)


    def on_pragma_change(self, event):
        """Handler for changing a PRAGMA value."""
        if not self.pragma_edit: return
        ctrl = event.EventObject

        name = ctrl.Name.replace("pragma_", "", 1)
        if isinstance(ctrl, wx.Choice):
            vals = database.Database.PRAGMA[name]["values"]
            value = ctrl.GetString(ctrl.Selection)
            value = next(k for k, v in vals.items() if util.to_unicode(v) == value)
        else:
            value = ctrl.Value
            if isinstance(ctrl, wx.CheckBox) and ctrl.Is3State():
                FLAGS = {wx.CHK_CHECKED: True, wx.CHK_UNCHECKED: False,
                         wx.CHK_UNDETERMINED: None}
                value = FLAGS[ctrl.Get3StateValue()]

        if (value == self.pragma.get(name)
        or not value and bool(value) == bool(self.pragma.get(name))
        and isinstance(database.Database.PRAGMA[name]["type"], six.string_types)):
            self.pragma_changes.pop(name, None)
        else: self.pragma_changes[name] = value

        self.populate_pragma_sql()


    def populate_pragma_sql(self):
        """Populates PRAGMA SQL STC with PRAGMA values-"""
        scrollpos = self.stc_pragma.GetScrollPos(wx.VERTICAL)
        self.stc_pragma.Freeze()
        try:
            values = dict(self.pragma_changes)
            if self.pragma_fullsql: values = dict(self.pragma, **values)

            template = step.Template(templates.PRAGMA_SQL, strip=False)
            sql = template.expand(pragma=values)
            self.stc_pragma.SetReadOnly(False)
            self.stc_pragma.Text = sql
            self.stc_pragma.SetReadOnly(True)
            self.stc_pragma.ScrollToLine(scrollpos)
        finally: self.stc_pragma.Thaw()
        self.update_page_header()


    def on_pragma_sql(self, event=None):
        """Handler for toggling PRAGMA change SQL visible."""
        self.stc_pragma.Shown = self.check_pragma_sql.Value
        self.check_pragma_fullsql.Shown = self.check_pragma_sql.Value
        self.tb_pragma.Shown = self.check_pragma_sql.Value
        self.splitter_pragma.SashPosition = self.page_pragma.Size[1] - (200 if self.stc_pragma.Shown else 20)
        self.splitter_pragma.SashInvisible = not self.stc_pragma.Shown
        self.panel_pragma_sql.Layout()
        self.page_pragma.Layout()


    def on_pragma_fullsql(self, event=None):
        """Handler for toggling full PRAGMA SQL."""
        self.pragma_fullsql = self.check_pragma_fullsql.Value
        self.panel_pragma_sql.Layout()
        self.populate_pragma_sql()


    def on_pragma_filter(self, event):
        """Handler for filtering PRAGMA list, shows/hides components."""
        search = event.String.strip()
        if search == self.pragma_filter: return

        patterns = list(map(re.escape, search.split()))
        values = dict(self.pragma, **self.pragma_changes)
        show_deprecated = False
        self.page_pragma.Freeze()
        try:
            for name, opts in database.Database.PRAGMA.items():
                texts = [name, opts["label"], opts["short"],
                         self.pragma_ctrls[name].ToolTip.Tip]
                for kv in opts.get("values", {}).items():
                    texts.extend(map(util.to_unicode, kv))
                if name in values: texts.append(util.to_unicode(values[name]))
                show = all(any(re.search(p, x, re.I | re.U) for x in texts)
                           for p in patterns)
                if opts.get("deprecated"): show_deprecated |= show
                if self.pragma_ctrls[name].Shown == show: continue # for name
                [x.Show(show) for x in self.pragma_items[name]]
            if show_deprecated != self.label_deprecated.Shown:
                self.label_deprecated.Show(show_deprecated)
            self.pragma_filter = search
            self.panel_pragma_wrapper.SendSizeEvent()
        finally: self.page_pragma.Thaw()


    def on_pragma_key(self, event):
        """
        Handler for pressing a key in pragma page, focuses filter on Ctrl-F.
        """
        if event.CmdDown() and event.KeyCode in [ord("F")]:
            self.edit_pragma_filter.SetFocus()
        else: event.Skip()


    def on_pragma_save(self, event=None):
        """Handler for clicking to save PRAGMA changes."""
        result = True

        template = step.Template(templates.PRAGMA_SQL, strip=False)
        sql = template.expand(pragma=self.pragma_changes)
        if sql and wx.YES != controls.YesNoMessageBox(
            "Save PRAGMA changes?\n\n%s" % sql, conf.Title,
            wx.ICON_INFORMATION, default=wx.NO
        ): return

        lock = self.db.get_lock(category=None)
        if lock: return wx.MessageBox("%s, cannot save." % lock,
                                      conf.Title, wx.OK | wx.ICON_WARNING)

        try:
            self.db.executescript(sql, name="PRAGMA")
        except Exception as e:
            result = False
            msg = "Error saving PRAGMA:\n\n%s" % util.format_exc(e)
            logger.exception(msg)
            guibase.status(msg)
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
        self.splitter_pragma.SplitHorizontally(*list(self.splitter_pragma.Children) + [self.page_pragma.Size[1] - 200])
        if self.check_pragma_sql.Value:
            self.stc_pragma.Shown = True
            self.check_pragma_fullsql.Shown = True
            self.tb_pragma.Shown = True
        else:
            self.splitter_pragma.SashPosition = self.page_pragma.Size[1] - 20
            self.splitter_pragma.SashInvisible = False
        for name, opts in database.Database.PRAGMA.items():
            ctrl = self.pragma_ctrls[name]
            writable = opts.get("write")
            if callable(writable): writable = writable(self.db)
            if writable is not False and "table" != opts["type"]:
                ctrl.Enable()
        self.panel_pragma_sql.Layout()
        self.page_pragma.Layout()


    def on_pragma_refresh(self, event=None, reload=False):
        """Handler for clicking to refresh PRAGMA settings."""
        if not self: return
        editmode = self.pragma_edit
        if event or reload:
            try: self.pragma.update(self.db.get_pragma_values())
            except Exception:
                if not reload: raise
                logger.exception("Error refreshing PRAGMA values.")
        self.pragma_edit = False # Ignore change events in edit handler
        for name, opts in database.Database.PRAGMA.items():
            ctrl = self.pragma_ctrls[name]
            value = self.pragma_changes[name] if name in self.pragma_changes \
                    else self.pragma.get(name)
            if "table" == opts["type"]:
                ctrl.Value = "\n".join(util.to_unicode(x) for x in value or ())
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
        self.populate_pragma_sql()
        self.pragma_edit = editmode
        self.update_page_header()


    def on_pragma_cancel(self, event=None):
        """Handler for clicking to cancel PRAGMA changes."""
        if event and self.pragma_changes and wx.YES != controls.YesNoMessageBox(
            "You have unsaved changes, are you sure you want to discard them?",
            conf.Title, wx.ICON_INFORMATION, default=wx.NO
        ): return

        self.pragma_edit = False
        self.button_pragma_edit.Label = "Edit"
        self.button_pragma_cancel.Disable()
        self.pragma_changes.clear()
        self.on_pragma_refresh()
        self.splitter_pragma.Unsplit()
        for name, opts in database.Database.PRAGMA.items():
            if "table" != opts["type"]: self.pragma_ctrls[name].Disable()
        self.page_pragma.Layout()
        self.update_page_header()
        wx.CallLater(1, self.on_pragma_refresh, reload=True)


    def on_check_fks(self, event=None):
        """
        Handler for checking foreign key violations, pops open dialog with
        violation results.
        """
        msg = "Checking foreign keys of %s." % self.db.filename
        guibase.status(msg, log=True)
        rows = self.db.execute("PRAGMA foreign_key_check").fetchall()
        guibase.status("")
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
                            "SELECT %s FROM %s WHERE %s IN (%s)" %
                            (grammar.quote(fk), grammar.quote(table),
                             self.db.get_rowid(table), ", ".join(map(str, rowids)))
                        ).fetchall()]
                        if vals: line += "\nKeys: (%s)" % ", ".join(map(six.text_type, sorted(vals)))
                    lines.append(line)

        msg = "Detected %s in %s:\n\n%s" % (
              util.plural("foreign key violation", rows), util.plural("table", data), "\n\n".join(lines))
        wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)


    def on_optimize(self, event=None):
        """
        Handler for running optimize on database.
        """
        msg = "Running optimize on %s." % self.db.filename
        guibase.status(msg, log=True)
        self.db.executeaction("PRAGMA optimize", name="PRAGMA")
        guibase.status("")
        self.update_info_panel()
        self.on_update_statistics()
        wx.MessageBox("Optimize complete.", conf.Title, wx.OK | wx.ICON_INFORMATION)


    def on_check_integrity(self, event=None):
        """
        Handler for checking database integrity, offers to save a fixed
        database if corruption detected.
        """
        msg = "Checking integrity of %s." % self.db.filename
        guibase.status(msg, log=True)
        busy = controls.BusyPanel(self, msg)
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
            msg = "A number of errors were found in %s:\n\n- %s\n\n" \
                  "Recover as much as possible to a new database?" % \
                  (self.db, util.ellipsize(err, 500))
            if wx.YES != wx.MessageBox(msg, conf.Title,
                                       wx.YES | wx.NO | wx.ICON_WARNING): return

            directory, filename = os.path.split(self.db.filename)
            base = os.path.splitext(filename)[0]

            dlg = wx.FileDialog(self, message="Save recovered data as",
                defaultDir=directory, defaultFile="%s (recovered)" % base,
                wildcard="SQLite database (*.db)|*.db",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | 
                      wx.FD_CHANGE_DIR | wx.RESIZE_BORDER)
            if wx.ID_OK != dlg.ShowModal(): return

            newfile = controls.get_dialog_path(dlg)
            if os.path.abspath(newfile) == os.path.abspath(self.db.filename):
                wx.MessageBox("Cannot recover data from %s to itself."
                              % self.db, conf.Title, wx.ICON_ERROR)
                return

            guibase.status("Recovering data from %s to %s.",
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
            guibase.status("Recovery to %s complete." % newfile)
            wx.PostEvent(self, OpenDatabaseEvent(self.Id, file=newfile))
            wx.MessageBox("Recovery to %s complete.%s" %
                          (newfile, util.ellipsize(err, 500)), conf.Title,
                          wx.ICON_INFORMATION)


    def on_vacuum(self, event=None):
        """
        Handler for vacuuming the database.
        """
        lock = self.db.get_lock()
        if lock: return wx.MessageBox("%s, cannot vacuum." % lock,
                                      conf.Title, wx.OK | wx.ICON_INFORMATION)

        pages = []
        for page in (v for vv in self.data_pages.values() for v in vv.values()):
            if page.IsOpen(): pages.append(page); page.CloseCursor()

        size1 = self.db.filesize
        msg = "Vacuuming %s." % self.db.name
        guibase.status(msg, log=True)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        errors = []
        try:
            self.db.executeaction("VACUUM", name="VACUUM")
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        guibase.status("")
        for page in pages: page.Reload(force=True)
        if errors:
            err = "\n- ".join(errors)
            logger.info("Error running vacuum on %s: %s", self.db, err)
            wx.MessageBox(util.ellipsize(err, 500), conf.Title, wx.OK | wx.ICON_ERROR)
        else:
            self.update_info_panel()
            self.on_update_statistics()
            wx.MessageBox("VACUUM complete.\n\nSize before: %s.\nSize after:    %s." %
                tuple(util.format_bytes(x, max_units=False) for x in (size1, self.db.filesize)),
                conf.Title, wx.OK | wx.ICON_INFORMATION)


    def on_close(self):
        """
        Stops worker threads, saves page last configuration
        like search text and results.
        """

        for worker in self.workers_search.values(): worker.stop()
        self.worker_analyzer.stop()
        self.worker_checksum.stop()
        self.panel_data_export.Stop()
        for p in (p for x in self.data_pages.values() for p in x.values()):
            p.Close(force=True)
        for p in (p for x in self.schema_pages.values() for p in x.values()):
            p.Close(force=True)
        sql_order = [self.notebook_sql.GetPageText(i)
                     for i in range(self.notebook_sql.GetPageCount() - 1)]
        for p in self.sql_pages.values():
            p.Close(force=True)
        try: self.db.connection.interrupt()
        except Exception: pass
        self.db.clear_locks()

        if self.db.temporary: return

        # Save search box state
        if conf.SearchHistory[-1:] == [""]: # Clear empty search flag
            conf.SearchHistory = conf.SearchHistory[:-1]
        util.add_unique(conf.SearchHistory, self.edit_searchall.Value,
                        1, conf.MaxSearchHistory)

        # Save last search results HTML
        nb = self.notebook_search
        search_data = next((nb.GetPage(i) for i in range(nb.GetPageCount())
                            if ((nb.GetPage(i) or {}).get("info") or {}).get("done")), None)
        if search_data:
            info = {}
            if search_data.get("info"):
                info.update({x: search_data["info"].get(x)
                            for x in ("map", "text", "source", "case")})
            data = {"content": search_data["content"],
                    "id": search_data["id"], "info": info,
                    "title": search_data["title"], }
            conf.LastSearchResults[self.db.filename] = data
        elif self.db.filename in conf.LastSearchResults:
            del conf.LastSearchResults[self.db.filename]

        # Save page SQL windows content, if changed from previous value
        sqls = [(k, self.sql_pages[k].Text) for k in sql_order
                if self.sql_pages[k].Text.strip()]
        if sqls != conf.SQLWindowTexts.get(self.db.filename):
            if sqls: conf.SQLWindowTexts[self.db.filename] = sqls
            else: conf.SQLWindowTexts.pop(self.db.filename, None)

        # Save schema diagram state
        if not self.db.temporary:
            conf.SchemaDiagrams[self.db.filename] = self.diagram.GetOptions()
        self.diagram.Disable() # Stop diagram workers


    def update_info_panel(self, reload=False):
        """
        Updates the Information page panel with current data.

        @param   reload  whether to reload checksums
        """
        self.db.update_fileinfo()
        for name in ["edit_info_size", "edit_info_created", "edit_info_modified"]:
            getattr(self, name).Value = ""

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

        if self.db.filesize and not self.worker_checksum.is_working() \
        and (conf.RunChecksums or reload):
            self.edit_info_sha1.Value = "Analyzing.."
            self.edit_info_md5.Value  = "Analyzing.."
            self.button_checksum_stop.Show()
            self.worker_checksum.work(self.db.filename)
        elif not self.worker_checksum.is_working():
            self.edit_info_sha1.Value = ""
            self.edit_info_md5.Value  = ""
            self.button_checksum_stop.Hide()

        for name in ["edit_info_size", "edit_info_created", "edit_info_modified",
                     "edit_info_path", "edit_info_sha1", "edit_info_md5"]:
            getattr(self, name).MinSize = (-1, -1)
        self.edit_info_path.ContainingSizer.Layout()

        self.button_vacuum.Enabled = self.button_check_fks.Enabled = True
        self.button_optimize.Enabled = self.button_check_integrity.Enabled = True
        self.button_refresh_info.Enabled = True
        self.button_open_folder.Enabled = not self.db.temporary


    def on_checksum_stop(self, event=None):
        """Stops current checksum analysis."""
        self.worker_checksum.stop_work()
        self.on_checksum_result({"sha1": "Cancelled", "md5": "Cancelled"})


    def on_refresh_tree_data(self, event):
        """Refreshes the data tree."""
        self.load_tree_data(refresh=True)


    def on_rightclick_searchall(self, event):
        """
        Handler for right-clicking in HtmlWindow, sets up a temporary flag for
        HTML link click handler to check, in order to display a context menu.
        """
        event.Skip()
        self.notebook_search.is_rightclick = True
        def reset():
            if not self: return
            if self.notebook_search.is_rightclick: # Flag still up: show menu
                def on_copy(event):
                    if wx.TheClipboard.Open():
                        text = self.notebook_search.SelectionToText()
                        d = wx.TextDataObject(text)
                        wx.TheClipboard.SetData(d), wx.TheClipboard.Close()

                def on_selectall(event):
                    self.notebook_search.SelectAll()
                self.notebook_search.is_rightclick = False
                menu = wx.Menu()
                item_selection = wx.MenuItem(menu, -1, "&Copy selection")
                item_selectall = wx.MenuItem(menu, -1, "&Select all")
                menu.Append(item_selection)
                menu.AppendSeparator()
                menu.Append(item_selectall)
                item_selection.Enable(bool(self.notebook_search.SelectionToText()))
                menu.Bind(wx.EVT_MENU, on_copy,      item_selection)
                menu.Bind(wx.EVT_MENU, on_selectall, item_selectall)
                self.notebook_search.PopupMenu(menu)
        wx.CallAfter(reset)


    def on_click_html_link(self, event):
        """
        Handler for clicking a link in HtmlWindow, opens the link inside
        program or in default browser, opens a popupmenu if right click.
        """
        href = event.GetLinkInfo().Href
        link_data, tab_data = None, None
        if event.EventObject != self.label_html:
            tab_data = self.notebook_search.GetPage(self.notebook_search.Selection)
        if tab_data and tab_data.get("info"):
            link_data = tab_data["info"]["map"].get(href, {})

        # Workaround for no separate wx.html.HtmlWindow link right click event
        if getattr(self.notebook_search, "is_rightclick", False):
            # Open a pop-up menu with options to copy or select text
            self.notebook_search.is_rightclick = False
            def clipboardize(text):
                if wx.TheClipboard.Open():
                    d = wx.TextDataObject(text)
                    wx.TheClipboard.SetData(d), wx.TheClipboard.Close()

            menutitle = "C&opy link location"
            if href.startswith("file://"):
                href = urllib.request.url2pathname(href[5:])
                if any(href.startswith(x) for x in ["\\\\\\", "///"]):
                    href = href[3:] # Strip redundant filelink slashes
                if isinstance(href, six.text_type):
                    # Workaround for wx.html.HtmlWindow double encoding
                    href = href.encode("latin1", errors="xmlcharrefreplace"
                           ).decode("utf-8")
                menutitle = "C&opy file location"
            elif href.startswith("mailto:"):
                href = href[7:]
                menutitle = "C&opy e-mail address"
            def handler(e):
                clipboardize(href)

            def on_copyselection(event):
                clipboardize(self.notebook_search.SelectionToText())
            def on_selectall(event):
                self.notebook_search.SelectAll()
            menu = wx.Menu()
            item_selection = wx.MenuItem(menu, -1, "&Copy selection")
            item_copy = wx.MenuItem(menu, -1, menutitle)
            item_selectall = wx.MenuItem(menu, -1, "&Select all")
            menu.Append(item_selection)
            menu.Append(item_copy)
            menu.Append(item_selectall)
            item_selection.Enable(bool(self.notebook_search.SelectionToText()))
            menu.Bind(wx.EVT_MENU, on_copyselection, item_selection)
            menu.Bind(wx.EVT_MENU, handler,          item_copy)
            menu.Bind(wx.EVT_MENU, on_selectall,     item_selectall)
            self.notebook_search.PopupMenu(menu)
        elif href.startswith("file://"):
            # Open the link, or file, or program internal link to table
            filename = path = urllib.request.url2pathname(href[5:])
            if any(path.startswith(x) for x in ["\\\\\\", "///"]):
                filename = href = path[3:]
            if path and os.path.exists(path):
                util.start_file(path)
            else:
                e = 'The file "%s" cannot be found on this computer.' % \
                    filename
                wx.MessageBox(e, conf.Title, wx.OK | wx.ICON_WARNING)
        elif link_data:
            # Go to specific data/schema page object
            category, row = link_data.get("category"), link_data.get("row")
            item = self.db.schema.get(category, {}).get(link_data["name"])
            if not item: return

            tree, page = self.tree_data, self.page_data
            match = dict(type=category, name=item["name"])
            if "schema" == link_data.get("page"):
                tree, page = self.tree_schema, self.page_schema
                match.update(level=category)
            if tree.FindAndActivateItem(match):
                self.notebook.SetSelection(self.pageorder[page])
                wx.YieldIfNeeded()
                if row: # Scroll to matching row
                    p = self.data_pages[category].get(item["name"])
                    if p: p.ScrollToRow(row)
        elif href.startswith("page:"):
            # Go to database subpage
            page = href[5:]
            if "#help" == page:
                nb = self.notebook_search
                if nb.GetPage(id=0):
                    nb.SetSelection(id=0)
                else:
                    h = step.Template(templates.SEARCH_HELP_LONG_HTML).expand()
                    nb.InsertPage(nb.GetTabCount(), h, "Search help", 0)
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
        if wx.ID_INDEX == event.Id:
            conf.SearchInMeta = True
            conf.SearchInData = False
            self.label_search.Label = "Search &in metadata:"
            self.label_search.ToolTip = "Search in database CREATE SQL"
            self.edit_searchall.ToolTip = self.label_search.ToolTip.Tip
        elif wx.ID_STATIC == event.Id:
            conf.SearchInData = True
            conf.SearchInMeta = False
            self.label_search.Label = "Search &in data:"
            self.label_search.ToolTip = "Search in all columns of all database tables and views"
            self.edit_searchall.ToolTip = self.label_search.ToolTip.Tip
        self.label_search.ContainingSizer.Layout()
        if wx.ID_NEW == event.Id:
            conf.SearchUseNewTab = event.EventObject.GetToolState(event.Id)
        elif wx.ID_CONVERT == event.Id:
            conf.SearchCaseSensitive = event.EventObject.GetToolState(event.Id)
        elif not event.EventObject.GetToolState(event.Id):
            # All others are radio tools and state might be toggled off by
            # shortkey key adapter
            event.EventObject.ToggleTool(event.Id, True)


    def on_searchall_stop(self, event):
        """
        Handler for clicking to stop a search, signals the search thread to
        close.
        """
        nb = self.notebook_search
        for tab_data in map(nb.GetPage, range(nb.GetPageCount())):
            if not tab_data or tab_data["id"] not in self.workers_search:
                continue # for tab_data
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
            self.workers_search[tab_data["id"]].stop(drop=False)
            del self.workers_search[tab_data["id"]]
            break # for tab_data


    def on_change_searchall_tab(self, event):
        """Handler for changing a tab in search window, updates stop button."""
        tab_data = self.notebook_search.GetPage(self.notebook_search.Selection)
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
        if not event.Data: return

        text, source = event.Data["info"]["text"], event.Data["info"]["source"]
        myid = wx.ID_INDEX if "meta" == source else wx.ID_STATIC
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_TOOL_CLICKED, myid)
        evt.SetEventObject(self.tb_search_settings)
        wx.PostEvent(self, evt)
        self.edit_searchall.Value = text
        self.edit_searchall.SetFocus()
        self.edit_searchall.SelectAll()


    def on_searchall_result(self, event):
        """
        Handler for getting results from search thread, adds the results to
        the search window.
        """
        result = event.result
        search_id, search_done = result.get("search", {}).get("id"), False
        tab_data = self.notebook_search.GetPage(id=search_id)
        if tab_data:
            tab_data["info"]["map"].update(result.get("map", {}))
            tab_data["info"]["partial_html"] += result.get("output", "")
            html = tab_data["info"]["partial_html"]
            if "done" in result:
                search_done = tab_data["info"]["done"] = True
            else:
                html += "</table></font>"
            text = tab_data["info"]["text"]
            title = "%s (%s)" % (util.ellipsize(text, conf.MaxTabTitleLength),
                                 result.get("count", 0))
            self.notebook_search.SetPageData(search_id, title, html,
                                             tab_data["info"])
        if search_done:
            guibase.status('Finished searching for "%s" in %s.',
                           result["search"]["text"], self.db)
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


    def on_searchall(self, event=None, text=None, source=None):
        """
        Handler for clicking to global search the database.
        """
        has_focus = self.edit_searchall.HasFocus()
        text = text or self.edit_searchall.Value.strip()
        if text:
            guibase.status('Searching for "%s" in %s.',
                           text, self.db)
            nb = self.notebook_search
            data = {"id": wx.NewIdRef().Id, "db": self.db, "text": text,
                    "map": {}, "width": nb.Size.width * 5//9, "partial_html": "",
                    "case": conf.SearchCaseSensitive}
            if "meta" == source or conf.SearchInMeta:
                data["source"] = "meta"
                fromtext = "database metadata"
            elif "data" == source or conf.SearchInData:
                data["source"] = "data"
                fromtext = "database data"
            # Partially assembled HTML for current results
            template = step.Template(templates.SEARCH_HEADER_HTML, escape=True)
            data["partial_html"] = template.expand(locals())

            worker = workers.SearchThread(self.on_searchall_callback)
            self.workers_search[data["id"]] = worker
            worker.work(data)
            bmp = images.ToolbarStop.Bitmap
            self.tb_search_settings.SetToolNormalBitmap(wx.ID_STOP, bmp)

            title = util.ellipsize(text, conf.MaxTabTitleLength)
            content = data["partial_html"] + "</table></font>"
            if conf.SearchUseNewTab or not nb.GetTabCount():
                nb.InsertPage(0, content, title, data["id"], data)
            else:
                # Set new ID for the existing reused tab
                page = self.notebook_search.GetPage(self.notebook_search.Selection)
                nb.SetPageData(page["id"], title,
                               content, data, data["id"])

            self.notebook.SetSelection(self.pageorder[self.page_search])
            util.add_unique(conf.SearchHistory, text, 1, conf.MaxSearchHistory)
            self.edit_searchall.SetChoices(conf.SearchHistory)
            if has_focus: self.edit_searchall.SetFocus()
            util.run_once(conf.save)


    def on_close_search_page(self, event):
        """Handler for closing a search page, stops its ongoing search if any."""
        tab_data = self.notebook_search.GetPage(event.GetSelection())
        if tab_data and tab_data.get("info"):
            item = {"name": tab_data["info"]["text"], "type": tab_data["info"]["source"]}
            self.pages_closed[self.notebook_search].append(item)
        if tab_data and tab_data["id"] == tab_data["id"]:
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
        if tab_data and tab_data["id"] in self.workers_search:
            self.workers_search[tab_data["id"]].stop()
            del self.workers_search[tab_data["id"]]


    def on_copy_sql(self, stc, event=None):
        """Handler for copying SQL to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(stc.Text)
            wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
            guibase.status("Copied SQL to clipboard.")


    def save_sql(self, sql, title=None):
        """
        Handler for saving SQL to file, opens file dialog and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.name))[0]
        if title: filename += " " + title
        dialog = wx.FileDialog(
            self, message="Save SQL as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | 
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = controls.get_dialog_path(dialog)
        try:
            title = "PRAGMA settings." if "PRAGMA" == title else \
                    "Database %s." % (title or "schema")
            importexport.export_sql(filename, self.db, sql, title)
            guibase.status('Exported to "%s".', filename, log=True)
            util.start_file(filename)
        except Exception as e:
            msg = "Error saving SQL to %s." % filename
            logger.exception(msg); guibase.status(msg)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)


    def reopen_page(self, notebook, index, *_, **__):
        """Reopens a page in the notebook."""
        pp = self.pages_closed.get(notebook, [])
        if not pp: return

        if notebook is self.notebook_sql:
            title, text = pp[index]["name"], pp[index]["text"]
            t, p = next(iter(self.sql_pages.items()), (None, None))
            if p and "SQL" == t and not p.Text and not p.CanUndoRedo():
                # Reuse empty default tab
                p.Text = text
                self.sql_pages[title] = self.sql_pages.pop(t)
                self.notebook_sql.SetPageText(0, title)
            else: self.add_sql_page(title, text)
            del pp[index]
        elif notebook is self.notebook_search:
            text, source = pp[index]["name"], pp[index]["type"]
            self.on_searchall(text=text, source=source)
            del pp[index]
        else:
            category, name = pp[index]["type"], pp[index]["name"]
            f = self.add_data_page if notebook is self.notebook_data \
                else self.add_schema_page
            f(self.db.get_category(category, name))


    def on_notebook_menu(self, event):
        """Handler for right-clicking a notebook header, opens menu."""
        nbs = (self.notebook_search, self.notebook_data, self.notebook_schema,
               self.notebook_sql)
        has_page = not isinstance(event, wx.ContextMenuEvent)
        nb = event.EventObject
        while nb and nb not in nbs: nb = nb.Parent
        page = nb.GetPage(event.GetSelection()) if has_page else None

        if page and nb is self.notebook_sql and "+" == nb.GetPageText(event.GetSelection()):
            page = None

        def fmtname(item, cap=False):
            vv = tuple(item.get(x) for x in ("type", "name"))
            if nb is self.notebook_search: t = "%s search: %s" % vv
            else: t = "%s %s" % (vv[0], fmt_entity(vv[1])) if all(vv) else vv[-1]
            return "%s%s" % (t[0].capitalize(), t[1:]) if cap else t

        def on_take(event=None):
            text, source, case = (page["info"].get(x) for x in ["text", "source", "case"])
            myid = wx.ID_INDEX if "meta" == source else wx.ID_STATIC
            evt = wx.CommandEvent(wx.wxEVT_COMMAND_TOOL_CLICKED, myid)
            evt.SetEventObject(self.tb_search_settings)
            wx.PostEvent(self, evt)
            if bool(case) != conf.SearchCaseSensitive:
                conf.SearchCaseSensitive = bool(case)
                self.tb_search_settings.ToggleTool(wx.ID_CONVERT, bool(case))
            self.edit_searchall.Value = text
            self.edit_searchall.SetFocus()
            self.edit_searchall.SelectAll()

        menu, hmenu = wx.Menu(), wx.Menu()
        item_close = item_save = item_last = item_take = None

        pp = self.pages_closed.get(nb, [])
        if nb in (self.notebook_data, self.notebook_schema): # Remove stale items
            for i, item in list(enumerate(pp))[::-1]:
                if item["name"] not in self.db.schema[item["type"]]: del pp[i]

        if page:
            item_close = wx.MenuItem(menu, -1, "&Close\t%s-W" % controls.KEYS.NAME_CTRL)
            if isinstance(page, (components.DataObjectPage, components.SchemaObjectPage)):
                item_save = wx.MenuItem(menu, -1, "&Save")

        if nb is self.notebook_search and page and page.get("info"):
            item_take = wx.MenuItem(menu, -1, "&Take search query")

        if pp:
            item_last = wx.MenuItem(menu, -1, "Re&open %s\t%s-Shift-T" % (fmtname(pp[-1]), controls.KEYS.NAME_CTRL))
            for i, item in list(enumerate(pp))[::-1]:
                item_open = wx.MenuItem(hmenu, -1, fmtname(item, cap=True))
                hmenu.Append(item_open)
                menu.Bind(wx.EVT_MENU, functools.partial(self.reopen_page, nb, i), item_open)

        if item_close: menu.Append(item_close)
        if item_save:  menu.Append(item_save)
        if item_take:  menu.Append(item_take)

        if hmenu.MenuItemCount:
            if menu.MenuItemCount: menu.AppendSeparator()
            menu.Append(item_last)
            menu.AppendSubMenu(hmenu, "&Recent pages")

        if page:
            menu.Bind(wx.EVT_MENU, lambda e: nb.DeletePage(nb.GetPageIndex(page)), item_close)
            if isinstance(page, (components.DataObjectPage, components.SchemaObjectPage)):
                if not page.IsChanged() if isinstance(page, components.DataObjectPage) \
                else page.ReadOnly: item_save.Enable(False)
                menu.Bind(wx.EVT_MENU, lambda e: page.Save(), item_save)

        if nb is self.notebook_search and page and page.get("info"):
            menu.Bind(wx.EVT_MENU, on_take, item_take)

        if pp:
            menu.Bind(wx.EVT_MENU, functools.partial(self.reopen_page, nb, -1), item_last)

        if menu.MenuItemCount: nb.PopupMenu(menu)


    def on_dump(self, event=None):
        """
        Handler for saving database dump to file, opens file dialog and saves content.
        """
        filename = os.path.splitext(os.path.basename(self.db.name))[0]
        filename += " dump"
        dialog = wx.FileDialog(
            self, message="Save database dump as", defaultFile=filename,
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | 
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = controls.get_dialog_path(dialog)
        args = {"filename": filename, "db": self.db}
        opts = {"filename": filename, "multi": True,
                "name":     "database dump",
                "callable": functools.partial(importexport.export_dump, **args),
                "subtotals": {t: {
                    "total": topts.get("count"),
                    "is_total_estimated": topts.get("is_count_estimated")
                } for t, topts in self.db.schema["table"].items()}}
        opts["total"] = sum(x["total"] or 0 for x in opts["subtotals"].values())
        if any(x["is_total_estimated"] for x in opts["subtotals"].values()):
            opts["is_total_estimated"] = True

        self.Freeze()
        try:
            self.splitter_data.Hide()
            self.panel_data_export.Show()
            self.panel_data_export.Run(opts)
            self.Layout()
        except Exception as e:
            msg = "Error saving database dump to %s." % filename
            logger.exception(msg); guibase.status(msg)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally: self.Thaw()


    def on_export_singlefile(self, category, event=None):
        """
        Handler for saving database category item data to file,
        opens file dialog, saves content.
        """
        title = os.path.splitext(os.path.basename(self.db.name))[0]
        title += " %s" % util.plural(category)
        dialog = wx.FileDialog(
            self, message="Save %s as" % util.plural(category),
            defaultFile=title,
            wildcard="|".join(filter(bool, (importexport.XLSX_WILDCARD, "All files|*.*"))),
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE |
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return

        filename = controls.get_dialog_path(dialog)
        args = {"filename": filename, "db": self.db, "title": title,
                "category": category}
        opts = {"filename": filename, "multi": True, "category": category,
                "name": "all %s to single spreadsheet" % util.plural(category),
                "callable": functools.partial(importexport.export_data_multiple, **args)}
        if "table" == category:
            opts["subtotals"] = {t: {
                    "total": topts.get("count"),
                    "is_total_estimated": topts.get("is_count_estimated")
                } for t, topts in self.db.schema[category].items()}
            opts["total"] = sum(x["total"] or 0 for x in opts["subtotals"].values())
            if any(x["is_total_estimated"] for x in opts["subtotals"].values()):
                opts["is_total_estimated"] = True

        self.Freeze()
        try:
            self.splitter_data.Hide()
            self.panel_data_export.Show()
            self.panel_data_export.Run(opts)
            self.Layout()
        except Exception as e:
            msg = "Error saving %s to %s." % (util.plural(category), filename)
            logger.exception(msg); guibase.status(msg)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally: self.Thaw()


    def get_ongoing(self):
        """
        Returns whether page has ongoing exports,
        as {?"table": [], ?"view": [], ?"sql": [], ?multi: ""}.
        """
        result = {}
        for opts in self.panel_data_export.GetIncomplete():
            if opts.get("multi"): result["multi"] = opts["name"]
            else: result.setdefault(opts["category"], []).append(opts["name"])
        for category in self.data_pages:
            for p in self.data_pages[category].values():
                if p.IsExporting():
                    result.setdefault(category, []).append(p.Name)
        for p in self.sql_pages.values():
            if p.IsExporting():
                result.setdefault("sql", []).append(p.SQL)
        return result


    def get_unsaved(self):
        """
        Returns whether page has unsaved changes,
        as {?"pragma": [pragma_name, ], ?"table": [table, ],
            ?"schema": True, ?"temporary"? True}.
        Temporary-flag is populated only if there are no pending changes
        but database is not pristine.
        """
        result = {}
        if not hasattr(self, "data_pages"): # Closed before fully created
            return result

        if self.pragma_changes: result["pragma"] = list(self.pragma_changes)
        grids = self.get_unsaved_grids()
        if grids: result["table"] = [x.Name for x in grids]
        schemas = self.get_unsaved_schemas()
        if schemas: result["schema"] = schemas
        if not result and self.db.temporary and self.pragma_initial != self.pragma:
            result["temporary"] = True
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
                style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE |
                      wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
            )
            if wx.ID_OK != dialog.ShowModal(): return

            filename2 = controls.get_dialog_path(dialog)
            if filename1 != filename2 and filename2 in conf.DBsOpen: return wx.MessageBox(
                "%s is already open in %s." % (filename2, conf.Title),
                conf.Title, wx.OK | wx.ICON_WARNING
            )
        rename = (filename1 != filename2)

        if rename:
            # Use a tertiary file in case something fails
            fh, tempname = tempfile.mkstemp(".db")
            os.close(fh)

        try:
            if rename:
                shutil.copy(filename1, tempname)
                self.db.reopen(tempname)
        except Exception as e:
            logger.exception("Error saving %s as %s.", self.db, filename2)
            self.db.reopen(filename1)
            self.reload_grids(restore=True)
            try: os.unlink(tempname)
            except Exception: pass
            wx.MessageBox("Error saving %s as %s:\n\n%s" %
                          (filename1, filename2, util.format_exc(e)),
                          conf.Title, wx.OK | wx.ICON_ERROR)
            return

        success, error = True, None
        self.flags["save_underway"] = True
        schemas_saved = {} # {category: {key: page}}
        try:
            for dct in self.data_pages, self.schema_pages:
                for category, key, page in ((c, k, p) for c, m in dct.items()
                                            for k, p in m.items()):
                    if not page.IsChanged(): continue # for category, ..
                    success = page.Save(backup=True)
                    if not success: break # for category
                    if isinstance(page, components.SchemaObjectPage):
                        schemas_saved.setdefault(category, {})[key] = page
                if not success: break # for group

            if success and self.pragma_changes:
                success = self.on_pragma_save()
        except Exception as e:
            logger.exception("Error saving changes in %s.", self.db)
            error = "Error saving changes:\n\n%s" % util.format_exc(e)
            try: self.db.execute("ROLLBACK")
            except Exception: pass
        self.flags.pop("save_underway", None)

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
            self.reload_schema(count=True)
            if success: self.reload_grids()

        if not success and rename:
            for category, key, page in ((c, k, p) for c, m in schemas_saved.items()
                                        for k, p in m.items()):
                # Restore schema page under original key if was new object
                self.schema_pages[category][key] = self.schema_pages[category].pop(page.Name)
                page.RestoreBackup()

            self.reload_grids(restore=True)

        try: tempname and os.unlink(tempname)
        except Exception: pass

        if not success:
            if error: wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
            return

        self.db.name, self.db.temporary = filename2, False
        if rename:
            evt = DatabasePageEvent(self.Id, source=self, rename=True, temporary=is_temporary,
                                    filename1=filename1, filename2=filename2)
            wx.PostEvent(self, evt)
            self.load_data()
        return True


    def reload_grids(self, restore=False):
        """
        Reloads all grids in data and SQL tabs,
        optionally restoring last saved changes.
        """
        for p in self.data_pages["table"].values(): p.Reload(restore=restore)
        for p in self.sql_pages.values(): p.Reload()


    def update_page_header(self, **kwargs):
        """Mark database as changed/pristine in the parent notebook tabs."""
        evt = DatabasePageEvent(self.Id, source=self, modified=self.get_unsaved(), **kwargs)
        wx.PostEvent(self, evt)


    def add_data_page(self, data):
        """Opens and returns a data object page for specified object data."""
        title = "%s %s" % (data["type"].capitalize(), fmt_entity(data["name"], force=False))
        title = make_unique_page_title(title, self.notebook_data)
        self.notebook_data.Freeze()
        try:
            p = components.DataObjectPage(self.notebook_data, self.db, data)
            self.data_pages[data["type"]][data["name"]] = p
            self.notebook_data.InsertPage(0, page=p, text=title, select=True)
            for i, item in enumerate(self.pages_closed.get(self.notebook_data, [])):
                if item["type"] == data["type"] and item["name"] == data["name"]:
                    del self.pages_closed[self.notebook_data][i]
                    break # for i, item
        finally: self.notebook_data.Thaw()
        self.TopLevelParent.run_console(
            "datapage = page.notebook_data.GetPage(0) # Data object subtab")
        return p


    def add_sql_page(self, name="", text=""):
        """Opens and returns an SQL page with specified text."""
        if not name or name in self.sql_pages:
            name = "SQL"
            if not self.sql_pages: self.sql_page_counter = 1
            while name in self.sql_pages:
                self.sql_page_counter += 1
                name += " (%s)" % self.sql_page_counter
        p = components.SQLPage(self.notebook_sql, self.db)
        p.Text = text
        self.sql_pages[name] = p
        self.notebook_sql.InsertPage(0, page=p, text=name, select=True)
        self.TopLevelParent.run_console(
            "sqlpage = page.notebook_sql.GetPage(0) # SQL window subtab")
        return p


    def on_refresh_tree_schema(self, event=None):
        """Refreshes database schema tree and panel."""
        self.load_tree_schema(refresh=True)


    def toggle_cursors(self, category, name, close=False):
        """Closes or reopens grid cursors using specified table or view."""
        if not name: return            
        relateds = {category: set([name])}
        for c, m in self.db.get_related(category, name, data=True).items():
            if c in ("table", "view") and not ("table" == category == c):
                relateds.setdefault(c, set()).update(m)

        for c, n, page in ((c, n, p) for c, nn in relateds.items()
                     for n, p in self.data_pages.get(c, {}).items() if n in nn):
            if close: page.CloseCursor()
            else: page.Reload(force=True, item=self.db.get_category(c, n))


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
            it = wx.MenuItem(menu, -1, "New " + category.replace(key, "&" + key, 1))
            menu.Append(it)
            menu.Bind(wx.EVT_MENU, functools.partial(create_object, category), it)
        event.EventObject.PopupMenu(menu, tuple(event.EventObject.Size))


    def add_schema_page(self, data):
        """Opens and returns schema object page for specified object data."""
        if "name" in data:
            title = "%s %s" % (data["type"].capitalize(), fmt_entity(data["name"], force=False))
            busy = controls.BusyPanel(self.notebook_schema, "Opening %s %s." %
                                      (data["type"], fmt_entity(data["name"])))
        else:
            title, busy = "* New %s *" % data["type"], None
        title = make_unique_page_title(title, self.notebook_schema)
        self.notebook_schema.Freeze()
        try:
            p = components.SchemaObjectPage(self.notebook_schema, self.db, data)
            self.schema_pages[data["type"]][data.get("name") or str(id(p))] = p
            self.notebook_schema.InsertPage(0, page=p, text=title, select=True)
            for i, item in enumerate(self.pages_closed.get(self.notebook_schema, [])):
                if item["type"] == data["type"] and item["name"] == data.get("name"):
                    del self.pages_closed[self.notebook_schema][i]
                    break # for i, item
        finally:
            self.notebook_schema.Thaw()
            if busy: busy.Close()
        self.TopLevelParent.run_console(
            "schemapage = page.notebook_schema.GetPage(0) # Schema object subtab")
        return p


    def on_close_schema_page(self, event):
        """Handler for closing a schema object page."""
        page = self.notebook_schema.GetPage(event.GetSelection())
        if not page.Close(): return event.Veto()

        for c, k, p in ((c, k, p) for c, m in self.schema_pages.items() for k, p in m.items()):
            if p is page:
                if p.Name in self.db.schema[c]:
                    self.pages_closed[self.notebook_schema].append({"name": p.Name, "type": c})
                self.schema_pages[c].pop(k)
                break # for c, k, p
        self.update_page_header()


    def on_schema_page_event(self, event):
        """Handler for a message from SchemaObjectPage."""
        idx = self.notebook_schema.GetPageIndex(event.source)
        VARS = ("close", "modified", "updated", "reindex", "export", "data",
                "truncate", "drop", "close_grids", "reload_grids")
        close, modified, updated, reindex, export, data, truncate, drop, \
        close_grids, reload_grids = (getattr(event, x, None) for x in VARS)
        category, name = (event.item.get(x) for x in ("type", "name"))
        name0 = None
        if close and idx >= 0:
            self.notebook_schema.DeletePage(idx)
        if export:
            self.on_export_to_db(category=category, names=[name], data=data)
        if reindex:
            self.handle_command("reindex", category, name)
        if truncate:
            self.on_truncate(name)
        if drop:
            self.handle_command("drop", category, [name])
        if close_grids:
            self.toggle_cursors(category, name, close=True)
        if reload_grids:
            self.toggle_cursors(category, name)
        if (modified is not None or updated is not None) and event.source:
            if name:
                title = "%s %s" % (category.capitalize(), fmt_entity(name, force=False))
                title = make_unique_page_title(title, self.notebook_schema, skip=idx)
                if event.source.IsChanged(): title += "*"
                if self.notebook_schema.GetPageText(idx) != title:
                    self.notebook_schema.SetPageText(idx, title)
            if not self.flags.get("save_underway"): self.update_page_header(updated=updated)
        if updated:
            self.load_tree_schema()
            self.diagram.Populate()
            self.populate_diagram_finder()
            for n, p in self.schema_pages[category].items():
                if p is event.source and name != n:
                    name0 = n
                    self.schema_pages[category].pop(n)
                    self.schema_pages[category][name] = p
                    for item in self.pages_closed.get(self.notebook_data, []):
                        if item["name"] == n: item["name"] = name
                        break # for item
                    break # for n, p
        if updated and not self.flags.get("save_underway"):
            self.on_pragma_refresh(reload=True)
            self.update_autocomp()
            self.load_tree_data()
            datapage = self.data_pages.get(category, {}).get(name0 or name)
            if datapage:
                if name in self.db.schema[category]:
                    if not datapage.IsChanged():
                        datapage.Reload(item=self.db.get_category(category, name))
                else: datapage.Close(force=True)


    def on_change_sql_page(self, event):
        """Handler for SQL notebook tab change, adds new window if adder-tab."""
        if "+" == self.notebook_sql.GetPageText(self.notebook_sql.GetSelection()):
            self.notebook_sql.Freeze() # Avoid flicker from changing tab
            try:
                self.add_sql_page()
                self.update_autocomp()
            finally: wx.CallAfter(lambda: self and self.notebook_sql.Thaw())


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


    def on_key_sql_page(self, event):
        """
        Handler for keypress in SQL notebook,
        skips adder-tab on Ctrl+PageUp|PageDown|Tab navigation.
        """
        if not event.CmdDown() or event.AltDown() \
        or event.KeyCode not in controls.KEYS.TAB + controls.KEYS.PAGING \
        or event.ShiftDown() and event.KeyCode in controls.KEYS.PAGING:
            if not event.CmdDown() \
            or event.KeyCode not in controls.KEYS.PAGING + controls.KEYS.TAB:
                event.Skip()
            return

        nb = self.notebook_sql
        direction = -1 if event.KeyCode in controls.KEYS.PAGEUP else 1
        if event.ShiftDown() and event.KeyCode in controls.KEYS.TAB:
            direction = -1
        cur, count = nb.GetSelection(), nb.GetPageCount()
        index2 = cur + direction
        if index2 < 0: index2 = count - 1
        if "+" != nb.GetPageText(index2):
            event.Skip()
        elif count > 2:
            # Skip adder-tab and select next tab
            nb.SetSelection(0 if cur else count - 2)


    def on_close_sql_page(self, event):
        """Handler for closing an SQL page."""
        if "+" == self.notebook_sql.GetPageText(event.GetSelection()):
            if not getattr(self, "_ignore_adder_close", False): event.Veto()
            return
        page = self.notebook_sql.GetPage(event.GetSelection())
        if not page.Close(): return event.Veto()

        self.notebook_sql.Freeze() # Avoid flicker when closing last
        try:
            for k, p in self.sql_pages.items():
                if p is page:
                    if p.Text.strip():
                        self.pages_closed[self.notebook_sql].append({"name": k, "text": p.Text})
                    self.sql_pages.pop(k)
                    break # for k, p
        finally: wx.CallAfter(lambda: self and self.notebook_sql.Thaw())


    def on_close_data_page(self, event):
        """Handler for closing data object page."""
        page = self.notebook_data.GetPage(event.GetSelection())
        if not page.Close(): return event.Veto()

        for c, k, p in ((c, k, p) for c, m in self.data_pages.items() for k, p in m.items()):
            if p is page:
                self.pages_closed[self.notebook_data].append({"name": k, "type": c})
                self.data_pages[c].pop(k)
                break # for c, k, p
        self.update_page_header()


    def on_data_page_event(self, event):
        """Handler for a message from DataObjectPage."""
        if getattr(event, "export_db", False):
            return self.on_export_to_db(category="table", names=event.names, selects=event.selects)

        VARS = ("close", "modified", "updated", "open", "remove", "drop",
                "reindex", "table", "row", "rows")
        idx = self.notebook_data.GetPageIndex(event.source)
        close, modified, updated, open, remove, drop, reindex, table, row, rows = \
            (getattr(event, x, None) for x in VARS)
        category, name = (event.item.get(x) for x in ("type", "name"))
        if close and idx >= 0:
            self.notebook_data.DeletePage(idx)
        if drop:
            self.handle_command("drop", category, [name])
        if reindex:
            self.handle_command("reindex", category, name)
        if (modified is not None or updated is not None) and event.source:
            if name:
                title = "%s %s" % (category.capitalize(), fmt_entity(name, force=False))
                title = make_unique_page_title(title, self.notebook_data, skip=idx)
                if event.source.IsChanged(): title += "*"
                if self.notebook_data.GetPageText(idx) != title:
                    self.notebook_data.SetPageText(idx, title)
            if not self.flags.get("save_underway"): self.update_page_header()
        if updated and not self.flags.get("save_underway"):
            self.db.populate_schema(count=True, category=category, name=table or name)
            self.load_tree_data()
        if open:
            page = self.data_pages["table"].get(table) or \
                   self.add_data_page(self.db.get_category("table", table))
            self.notebook_data.SetSelection(self.notebook_data.GetPageIndex(page))
            if row: page.ScrollToRow(row, full=True)
        if remove:
            self.db.populate_schema(count=True)
            self.load_tree_data()
            if table in self.data_pages["table"]:
                self.data_pages["table"][table].DropRows(rows)


    def on_close_data_export(self, event=None):
        """Hides export panel."""
        self.Freeze()
        try:
            self.splitter_data.Show()
            self.panel_data_export.Hide()
            self.Layout()
        finally: self.Thaw()


    def on_export_data_file(self, category, item, event=None):
        """
        Handler for exporting one or more tables/views to file, opens file dialog
        and performs export.
        """
        items = [item] if isinstance(item, six.string_types) else item

        exporting = [x for x in items if category in self.data_pages
                     and x in self.data_pages[category]
                     and self.data_pages[category][x].IsExporting()]
        if exporting:
            return wx.MessageBox("Export is already underway for %s." % util.join(", ", exporting),
                                 conf.Title, wx.OK | wx.ICON_INFORMATION)

        if len(items) == 1:
            dialog = self.dialog_savefile
            filename = "%s %s" % (category.capitalize(), items[0])
            dialog.Filename = util.safe_filename(filename)
            dialog.Message = "Save %s as" % category
        else:
            dialog = self.dialog_savefile_ow
            dialog.Filename = "Filename will be ignored"
        if conf.LastExportType in importexport.EXPORT_EXTS:
            dialog.SetFilterIndex(importexport.EXPORT_EXTS.index(conf.LastExportType))
        if wx.ID_OK != dialog.ShowModal(): return

        wx.YieldIfNeeded() # Allow dialog to disappear
        extname = importexport.EXPORT_EXTS[dialog.FilterIndex]
        conf.LastExportType = extname
        path = controls.get_dialog_path(dialog)
        filenames = [path]
        if len(items) > 1:
            path, _ = os.path.split(path)
            filenames, names_unique = [], []
            for t in items:
                name = util.safe_filename("%s %s" % (category.capitalize(), t))
                name = util.make_unique(name, names_unique, suffix=" (%s)")
                filenames.append(os.path.join(path, name + "." + extname))
                names_unique.append(name)

            existing = next((x for x in filenames if os.path.exists(x)), None)
            if existing and wx.YES != wx.MessageBox(
                "Some files already exist, like %s.\n"
                "Do you want to replace them?" % os.path.basename(existing),
                conf.Title, wx.YES | wx.NO | wx.ICON_WARNING
            ): return

        exports = []

        for name, filename in zip(items, filenames):
            if not filename.lower().endswith(".%s" % extname):
                filename += ".%s" % extname
            data = self.db.get_category(category, name)
            sql = "SELECT * FROM %s" % grammar.quote(name)
            make_iterable = functools.partial(self.db.execute, sql)
            args = {"make_iterable": make_iterable, "filename": filename,
                    "title": "%s %s" % (category.capitalize(),
                                        grammar.quote(name, force=True)),
                    "db": self.db, "columns": data["columns"],
                    "category": category, "name": name}
            exports.append({
                "filename": filename, "category": category,
                "name": "all %s to file" % util.plural(category),
                "callable": functools.partial(importexport.export_data, **args),
                "total": data.get("count"),
                "is_total_estimated": data.get("is_count_estimated")
            })

        if isinstance(item, six.string_types): # Chose one specific table to export
            page = self.data_pages[category].get(item) or \
                   self.add_data_page(self.db.get_category(category, item))
            page.Export(exports)
            return

        self.Freeze()
        try:
            self.splitter_data.Hide()
            self.panel_data_export.Show()
            self.panel_data_export.Run(exports)
            self.Layout()
        finally: self.Thaw()


    def on_export_to_db(self, event=None, category=None, names=(), data=True, selects=None):
        """
        Handler for exporting one or more tables or views to another database,
        opens file dialog and performs direct copy.
        By default copies both structure and data.

        @param   category  category to export if not both tables and views
        @param   names     name or names to export if not all in category
        @param   data      whether to export data
        @param   selects   {table name: SELECT SQL if not using default}
        """
        if data and self.panel_data_export.IsRunning(): return wx.MessageBox(
            "A global export is already underway.", conf.Title, wx.ICON_NONE
        )

        names = [names] if isinstance(names, six.string_types) else names or []
        if not names and category: names = list(self.db.schema[category])
        elif not names: names = sum((list(self.db.schema.get(x) or [])
                                     for x in ("table", "view")), [])
        if not names: return

        exts = ";".join("*" + x for x in conf.DBExtensions)
        wildcard = "SQLite database (%s)|%s|All files|*.*" % (exts, exts)
        dialog = wx.FileDialog(
            self, message="Select existing or new database to export to",
            wildcard=wildcard, style=wx.FD_SAVE | wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return
        wx.YieldIfNeeded() # Allow dialog to disappear

        filename2 = controls.get_dialog_path(dialog)
        is_samefile = util.lceq(self.db.filename, filename2)
        file_exists = is_samefile or os.path.isfile(filename2)

        renames = defaultdict(util.CaselessDict) # {category: {name1: name2}}
        eschema = defaultdict(util.CaselessDict) # {category: {name: True}}
        mynames, requireds = names[:], defaultdict(dict) # {name: {name2: category}}
        names1_all = util.CaselessDict({x: True for xx in self.db.schema.values() for x in xx})
        names2_all = util.CaselessDict()
        if not file_exists:
            for name in names:
                category = "table" if name in self.db.schema.get("table", ()) else "view"
                eschema[category][name] = True
        else:
            if is_samefile:
                schema2 = {c: {k: True} for c, kk in self.db.schema.items() for k in kk}
            else:
                # Check for name conflicts with existing items and ask user choice
                schemaname2 = None
                try:
                    schemas = [x["name"] for x in
                               self.db.execute("PRAGMA database_list").fetchall()]
                    schemaname2 = util.make_unique("main", schemas, suffix="%s")
                    self.db.execute("ATTACH DATABASE ? AS %s" % schemaname2, [filename2])

                    schema2 = defaultdict(util.CaselessDict) # {category: {name: True}}
                    for x in self.db.execute(
                        "SELECT type, name FROM %s.sqlite_master WHERE sql != '' "
                        "AND name NOT LIKE 'sqlite_%%'" % schemaname2
                    ).fetchall(): schema2[x["type"]][x["name"]] = True
                    names2_all.update({x: True for xx in schema2.values() for x in xx})
                except Exception as e:
                    msg = "Failed to read database %s." % filename2
                    logger.exception(msg); guibase.status(msg)
                    error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
                    return wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
                finally:
                    try: self.db.execute("DETACH DATABASE %s" % schemaname2)
                    except Exception: pass

        def add_requireds(name):
            """Adds tables and views that the specified item depends on."""
            category = "table" if name in self.db.schema.get("table", ()) else "view"
            items = [self.db.schema[category][name]]
            items.extend(self.db.get_related(category, name, own=True).get("trigger", {}).values())
            for item in items:
                # Foreign tables and tables/views used in triggers for table,
                # tables/views used in view body and view triggers for view.
                for name2 in util.getval(item, "meta", "__tables__"):
                    if util.lceq(name, name2): continue # for name2
                    if name2 not in self.db.schema[category]:
                        guibase.status("Warning: no item named %s in database to export.",
                                       grammar.quote(name2, force=True), log=True)
                        continue # for item
                    category2 = "table" if name2 in self.db.schema.get("table", ()) else "view"
                    requireds[name][name2] = category2
                    if name2 not in mynames and name2 not in eschema.get(category2, ()) \
                    and self.db.is_valid_name(name2): # Skip sqlite_* specials
                        mynames.append(name2)


        def fmt_schema_items(dct):
            """Returns schema information string as "tables A, B and views C, D"."""
            return " and ".join(
                "%s %s" % (util.plural(c, vv, numbers=False),
                           ", ".join(map(fmt_entity, sorted(vv, key=lambda x: x.lower()))))
                for c, vv in sorted(dct.items())
            )


        def fmt_dependents(name):
            """Returns information string with items that require name."""
            rels = {} # {category: [name, ]}
            for name0, kv in requireds.items():
                if name in kv: rels.setdefault(kv[name], []).append(name0)
            return fmt_schema_items(rels)


        entrymsg = ("Name conflict on exporting %(category)s %(name)s as %(name2)s%(depend)s.\n"
                    "Database %(filename2)s %(entryheader)s "
                    "%(category2)s named %(name2)s.\n\nYou can:\n"
                    "- keep same name to overwrite %(category2)s %(name2)s,\n"
                    "- enter another name to export %(category)s %(name2)s as,\n"
                    "- or set blank to skip %(category)s %(name)s.")
        while mynames:
            name = mynames.pop(0)
            category = "table" if name in self.db.schema.get("table", ()) else "view"
            if name not in names2_all:
                add_requireds(name)
                names2_all[name] = True
                eschema[category][name] = True
                continue # while mynames

            name2 = name2_prev = name
            entryheader = "already contains a"
            depend = "" if name in names else " (required by %s)" % fmt_dependents(name)
            while name2:
                category2 = next(c for c, xx in schema2.items() if name2 in xx)
                entrydialog = wx.TextEntryDialog(self, entrymsg % {
                    "category":  category, "category2": category2,
                    "depend": depend,
                    "name":      fmt_entity(name),
                    "name2":     fmt_entity(name2),
                    "filename2": filename2, "entryheader": entryheader
                }, conf.Title, name2)
                if wx.ID_OK != entrydialog.ShowModal(): return

                value = entrydialog.GetValue().strip()
                if value and not self.db.is_valid_name(table=value):
                    msg = "%s is not a valid %s name." % (grammar.quote(value, force=True), category)
                    wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                    continue # while name2

                name2 = name2_prev = value
                if not name2 \
                or util.lceq(name, name2) and util.lceq(name, name2_prev): break # while name2

                if not util.lceq(name2, name2_prev) and name2 in names2_all:
                    # User entered another table existing in db2
                    entryheader = "already contains a"
                    continue # while name2
                if not util.lceq(name2, name2_prev) \
                and (any(name2 in xx for xx in eschema.values())
                or any(util.lceq(name2, x) for xx in renames.values() for x in xx.values())):
                    # User entered a duplicate rename
                    entryheader = "will contain another"
                    continue # while name2
                break # while name2

            if is_samefile and name2 in names1_all: # Needs rename if same file
                continue # while mynames
            if name2:
                eschema[category][name] = True
                if name != name2: renames[category][name] = name2
                add_requireds(name)

        deps, reqs = {}, {} # {category: set(name, )}
        for c, name in ((c, n) for c, nn in eschema.items() for n in nn):
            for name0, kv in requireds.items():
                if name in kv and not util.getval(eschema, kv[name], name):
                    deps.setdefault(c, set()).add(name0)
                    reqs.setdefault(kv[name], set()).add(name)
        if deps:
            return wx.MessageBox("Export cancelled: %s %s required for %s.", 
                fmt_schema_items(reqs),
                "are" if len(reqs) > 1 or any(len(x) > 1 for x in reqs.values()) else "is",
                fmt_schema_items(deps),
                conf.Title, wx.OK | wx.ICON_WARNING
            )

        if not eschema: return
        schema = {c: list(xx) for c, xx in eschema.items()}

        args = {"db": self.db, "filename": filename2, "schema": schema,
                "renames": renames, "data": data, "selects": selects}


        def on_complete(result):
            """Callback function for ExportProgressPanel."""
            successes, errors = {}, []
            for k, v in result["subtasks"].items():
                category = next(c for c, v in self.db.schema.items() if k in v)
                if v.get("error"): errors.append("%s %s: %s" % 
                    (category, fmt_entity(k), v["error"]))
                if v.get("result"): successes.setdefault(category, []).append(k)

            errors.sort(key=lambda x: x.lower())
            if result.get("error"): errors.append(result["error"])

            if errors:
                msg = "Export to %s done, with following errors"
                if not result["result"]: msg = "Failed to export to %s"
                msg = (msg + ":\n\n- %s") % (filename2, "\n- ".join(errors))
                wx.CallLater(500, wx.MessageBox, msg, conf.Title, wx.OK | wx.ICON_WARNING)

            if successes:
                if len(successes) > 1:
                    status =  " and ".join(util.plural(c, vv)
                                           for c, vv in sorted(successes.items()))
                else: status = "%s %s" % (util.plural(*next(iter(successes.items()))),
                                          util.join(", ", (fmt_entity(x, force=False)
                                                           for x in next(iter(successes.values())))))
                guibase.status('Exported %s to "%s".', status, filename2, log=True)
            else:
                guibase.status("Failed to export to %s.", filename2)

            if is_samefile:
                self.reload_schema(count=True)
                self.update_page_header(updated=True)
            elif result["result"]:
                wx.PostEvent(self, OpenDatabaseEvent(self.Id, file=filename2))


        if not data:
            # Purely structure export: do not open export panel
            busy = controls.BusyPanel(self, 'Exporting structure to "%s".' % filename2)
            subtasks, errors = {}, []
            def progress(result=None, name=None, error=None, **_):
                """Callback function for worker and ExportProgressPanel."""
                if error:
                    if name: subtasks.setdefault(name, {})["error"] = error
                    else: errors.append(error)
                elif name: subtasks.setdefault(name, {})["result"] = True
                def after(result, name, error):
                    if not self: return
                    if error:
                        t = error
                        if name: t = "%s: %s" % (grammar.quote(name, force=True), t)
                        guibase.status("Failed to export %s.", t)
                    if result:
                        busy.Close()
                        result = dict(result, subtasks=subtasks, error=result.get("error", "\n".join(errors)))
                        on_complete(result)

                if result or name or error: wx.CallAfter(after, result, name, error)
                return True

            func = functools.partial(importexport.export_to_db, progress=progress, **args)
            workers.WorkerThread(progress).work(func)
            return

        opts = {"filename": filename2, "multi": True, "name": "export to db",
                "callable": functools.partial(importexport.export_to_db, **args),
                "on_complete": on_complete, "open": False}
        self.Freeze()
        try:
            self.notebook.SetSelection(self.pageorder[self.page_data])
            self.splitter_data.Hide()
            self.panel_data_export.Show()
            self.panel_data_export.Run(opts)
            self.Layout()
        except Exception as e:
            msg = "Error exporting to %s." % filename2
            logger.exception(msg); guibase.status(msg)
            error = msg[:-1] + (":\n\n%s" % util.format_exc(e))
            wx.MessageBox(error, conf.Title, wx.OK | wx.ICON_ERROR)
        finally: self.Thaw()


    def on_import_event(self, event):
        """
        Handler for import dialog event, refreshes schema,
        opens table if specified.
        """
        VARS = "table", "open", "count", "parse"
        table, open, count, parse = (getattr(event, x, None) for x in VARS)
        if table and (count or parse):
            self.db.populate_schema(category="table", name=table, count=count, parse=parse)
        if table:
            self.reload_schema()
            self.update_page_header(updated=True)
        if table not in self.data_pages["table"] \
        and open and self.tree_data.FindAndActivateItem(type="table", name=table):
            self.notebook.SetSelection(self.pageorder[self.page_data])


    def on_truncate(self, names, event=None):
        """Handler for deleting all rows from a table, confirms choice."""
        names = [names] if isinstance(names, six.string_types) else names

        if wx.YES != controls.YesNoMessageBox(
            "Are you sure you want to delete all rows from %s %s?\n\n"
            "This action is not undoable." % (
                util.plural("table", names, numbers=False),
                util.join(", ", map(fmt_entity, names))
            ),
            conf.Title, wx.ICON_WARNING, default=wx.NO
        ): return


        locks = [n for n in names if self.db.get_lock("table", n)]
        if locks: return wx.MessageBox("%s, cannot truncate." % "\n".join(locks),
                                       conf.Title, wx.OK | wx.ICON_WARNING)

        count = 0
        for name in names:
            sql = "DELETE FROM %s" % grammar.quote(name)
            count += self.db.executeaction(sql, name="TRUNCATE")
            self.db.schema["table"][name]["count"] = 0
            self.db.schema["table"][name].pop("is_count_estimated", None)

            if name in self.data_pages["table"]:
                self.data_pages["table"][name].Reload(force=True)

        self.load_tree_data()
        self.update_page_header(updated=True)
        wx.MessageBox("Deleted %s from %s %s." % (
                          util.plural("row", count),
                          util.plural("table", names, numbers=False),
                          util.join(", ", map(fmt_entity, names)),
                      ), conf.Title)


    def on_truncate_all(self, event=None):
        """Handler for deleting all rows from all tables, confirms choice."""
        items = [x for x in self.db.get_category("table").values() if x.get("count")]
        if not items: return

        if wx.YES != controls.YesNoMessageBox(
            "Are you sure you want to delete all rows from all tables?\n\n"
            "This action is not undoable.",
            conf.Title, wx.ICON_WARNING, default=wx.NO
        ): return

        if wx.YES != controls.YesNoMessageBox(
            "Are you REALLY sure you want to delete all rows from all tables?\n\n"
            "Database currently contains %s." % util.count(items, "row"),
            conf.Title, wx.ICON_WARNING, default=wx.NO
        ): return

        names = [x["name"] for x in items]
        pages = {x: self.data_pages["table"].get(x) for x in names}
        locks = set(filter(bool, (self.db.get_lock("table", x, skip=pages[x])
                                  for x in names)))
        if locks: return wx.MessageBox("Cannot truncate:\n\n%s." % ".\n".join(locks),
                                       conf.Title, wx.OK | wx.ICON_WARNING)

        sqls, count = [], 0
        busy = controls.BusyPanel(self, "Truncating tables..")
        try:
            for name in names:
                page = pages[name]
                if page: page.CloseCursor(), page.Rollback(force=True)

                sql = "DELETE FROM %s" % grammar.quote(name)
                count += self.db.executeaction(sql)
                self.db.schema["table"][name]["count"] = 0
                self.db.schema["table"][name].pop("is_count_estimated", None)
                sqls.append(sql)
                if page: page.Reload(force=True)
        finally:
            busy.Close()
            if sqls:
                self.db.log_query("TRUNCATE", sqls)
                self.load_tree_data()
                self.update_page_header(updated=True)

        wx.MessageBox("Deleted %s from %s." % (util.plural("row", count),
                      util.plural("table", names)), conf.Title)


    def load_data(self):
        """Loads data from our Database."""

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
            tabid = wx.NewIdRef().Id if 0 != last_search.get("id") else 0
            self.notebook_search.InsertPage(0, html, title, tabid, info)

        dopts = conf.SchemaDiagrams.get(self.db.filename) or {}
        if "enabled" not in dopts: dopts["enabled" ] = conf.SchemaDiagramEnabled
        self.diagram.SetOptions(dopts, refresh=False)
        self.update_diagram_controls()
        self.tb_diagram.Disable()

        self.db.populate_schema(count=True)
        self.update_tabheader()
        if (wx.YieldIfNeeded() or True) and not self: return
        self.load_tree_data()
        if (wx.YieldIfNeeded() or True) and not self: return
        self.update_info_panel()
        if (wx.YieldIfNeeded() or True) and not self: return
        self.diagram.Populate(dopts)
        self.tb_diagram.Enable()
        if (wx.YieldIfNeeded() or True) and not self: return
        self.populate_diagram_finder()
        if (wx.YieldIfNeeded() or True) and not self: return
        self.Bind(components.EVT_DIAGRAM, self.on_diagram_event, self.diagram)
        if not self.db.temporary: self.on_diagram_event()
        if (wx.YieldIfNeeded() or True) and not self: return
        if self.diagram.Enabled \
        and not any(self.diagram.IsVisible(n) for c in ("table", "view")
                    for n in self.db.schema[c]):
            self.diagram.Scroll(0, 0)


        def progress(result=None, index=None, total=None, done=None):
            def after2():
                if not self: return

                if done:
                    self.gauge_schema.Hide()
                    self.gauge_schema.ContainingSizer.Layout()
                    guibase.status("")
                    after()
                elif total:
                    guibase.status("Parsing database schema.")
                    self.gauge_schema.Value = 100 * index // total
                    self.gauge_schema.ToolTip = "Parsing.. %s%% (%s of %s)" % (self.gauge_schema.Value, index, total)
                    if not self.gauge_schema.Shown:
                        self.gauge_schema.Show()
                        self.gauge_schema.ContainingSizer.Layout()
            wx.CallAfter(after2)
            return bool(self)


        def after():
            if not self: return

            for pmap in self.data_pages, self.schema_pages:
                for p in (p for d in pmap.values() for p in d.values()): p.Reload()
            if (wx.YieldIfNeeded() or True) and not self: return
            self.load_tree_schema()
            if (wx.YieldIfNeeded() or True) and not self: return
            self.on_update_stc_schema()
            if (wx.YieldIfNeeded() or True) and not self: return
            self.diagram.Populate()
            self.populate_diagram_finder()
            self.cb_diagram_rels.Enable(self.diagram.Enabled)
            self.cb_diagram_labels.Enable(self.diagram.Enabled and self.cb_diagram_rels.Value)
            self.update_autocomp()
            if (wx.YieldIfNeeded() or True) and not self: return
            self.db.generate_schema(progress=lambda *_, **__: (wx.YieldIfNeeded() or True) and bool(self))
            if (wx.YieldIfNeeded() or True) and not self: return
            for p in (p for d in self.schema_pages.values() for p in d.values()): p.Reload()
            if (wx.YieldIfNeeded() or True) and not self: return
            self.on_update_stc_schema()

        func = functools.partial(self.db.populate_schema, parse=True, progress=progress)
        wx.CallLater(100, workers.WorkerThread(progress).work, func)
        self.on_update_statistics()


    def reload_schema(self, count=False):
        """Reloads database schema and refreshes relevant controls"""
        if not self or self.flags.get("reload_schema_underway"): return

        self.flags["reload_schema_underway"] = True
        self.db.populate_schema(count=count, parse=True)
        self.on_pragma_refresh(reload=True)
        for pmap in self.data_pages, self.schema_pages:
            for p in (p for d in pmap.values() for p in d.values()): p.Reload()
        self.button_refresh_data.Disable()
        self.button_refresh_schema.Disable()
        ff = [self.load_tree_data, self.load_tree_schema, self.on_update_stc_schema,
              self.diagram.Populate, self.populate_diagram_finder,
              self.update_autocomp, self.update_info_panel, self.on_update_statistics]
        for func in ff:
            if (wx.YieldIfNeeded() or True) and not self: return
            func()
        self.flags.pop("reload_schema_underway", None)


    def populate_diagram_finder(self):
        """Refreshes schema items diagram quickfind dropdown."""
        combo = self.combo_diagram_find
        combo.Disable() # So that combo event handler knows to disregard change
        combo.Clear()
        for name in (x for c in ("table", "view") for x in self.db.schema[c]):
            combo.Append(util.unprint(name))
            combo.SetClientData(combo.Count - 1, name)
        combo.Enable(self.diagram.Enabled)


    def get_tree_state(self, tree, root):
        """
        Returns ({data, children: [{data, children}]} for expanded nodes,
                 {selected item data}).
        """
        if not root or not root.IsOk(): return None, None

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


    def set_tree_state(self, tree, root, state, have_selected=False):
        """Sets tree expanded state."""
        state, sel = state
        if not state and not sel: return have_selected

        key_match = lambda x, y, k, n=False: (n or x.get(k)) and x.get(k) == y.get(k)
        parent_match = lambda x, y: x.get("parent") and y.get("parent") \
                                    and key_match(x["parent"], y["parent"], "type") \
                                    and key_match(x["parent"], y["parent"], "category", True) \
                                    and (key_match(x["parent"], y["parent"], "name") or 
                                         key_match(x["parent"], y["parent"], "__id__"))
        has_match = lambda x, y: x == y or (
            key_match(y, x, "category") if "category" == y.get("type")
            else key_match(y, x, "type") and (
                key_match(y, x, "name") or key_match(y, x, "__id__") or parent_match(y, x)
            )
        )

        if state: tree.Expand(root)
        item = tree.GetNext(root)
        while item and item.IsOk():
            mydata = tree.GetItemPyData(item)
            if not have_selected and sel and has_match(sel, mydata):
                tree.SelectItem(item)
                have_selected = True
            mystate = next((x for x in state["children"] if has_match(x["data"], mydata)), None) \
                      if state and "children" in state else None
            if mystate: have_selected = self.set_tree_state(tree, item, (mystate, sel), have_selected)
            item = tree.GetNextSibling(item)
        return have_selected


    def load_tree_data(self, refresh=False):
        """Loads table and view data into data tree."""
        if not self or self.gauge_data.Shown: return

        tree, gauge = self.tree_data, self.gauge_data
        self.button_refresh_data.Disable()
        gauge.Value, gauge.ToolTip = 0, "Populating.. 0%"
        gauge.Show()
        gauge.ContainingSizer.Layout()
        expandeds = self.get_tree_state(tree, tree.RootItem)
        tree.DeleteAllItems()
        if (wx.YieldIfNeeded() or True) and not self: return

        tree.Freeze()
        try:
            try:
                if refresh: self.db.populate_schema(count=True)
            except Exception:
                msg = "Error loading data from %s." % self.db
                logger.exception(msg)
                return wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)

            root = tree.AddRoot("SQLITE")
            tree.SetItemPyData(root, {"type": "data"})

            tops, index = [], 0
            total = sum(len(self.db.schema.get(c, {})) for c in ("table", "view"))
            for category in "table", "view":
                # Fill data tree with information on row counts and columns
                items = list(self.db.get_category(category).values())
                if not items and "view" == category: continue # for category
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
                        t = "ERROR" if item["count"] is None else util.count(item, "row")
                    else:
                        t = "" if "view" == category else "Counting.."
                    tree.SetItemText(child, t, 1)

                    lks, fks = self.db.get_keys(item["name"]) if "table" == category else [(), ()]
                    for col in item["columns"]:
                        subchild = tree.AppendItem(child, util.unprint(col["name"]))
                        mytype = col.get("type", "")
                        if any(col["name"] in x["name"] for x in lks):
                            mytype = u"\u1d18\u1d0b  " + mytype # Unicode small caps "PK"
                        elif any(col["name"] in x["name"] for x in fks):
                            mytype = u"\u1da0\u1d4f  " + mytype # Unicode small "fk"
                        tree.SetItemText(subchild, mytype, 1)
                        tree.SetItemPyData(subchild, dict(col, parent=item, type="column"))

                    index += 1
                    gauge.Value = 100 * index // total
                    gauge.ToolTip = "Populating.. %s%% (%s of %s)" % (gauge.Value, index, total)
                    if (wx.YieldIfNeeded() or True) and not self: return

            tree.Expand(root)
            for top in tops if not any(expandeds) else (): tree.Expand(top)
            tree.SetColumnWidth(1, 100)
            tree.SetColumnWidth(0, tree.Size[0] - 130)
            self.set_tree_state(tree, tree.RootItem, expandeds)
        finally:
            if not self: return
            self.button_refresh_data.Enable()
            gauge.Hide()
            gauge.ContainingSizer.Layout()
            tree.Thaw()


    def load_tree_schema(self, refresh=False):
        """Loads database schema into schema tree."""
        if not self: return

        tree, gauge = self.tree_schema, self.gauge_schema

        self.button_refresh_schema.Disable()
        gauge.Value, gauge.ToolTip = 0, "Populating.. 0%"
        gauge.Show()
        gauge.ContainingSizer.Layout()
        expandeds = self.get_tree_state(tree, tree.RootItem)
        tree.DeleteAllItems()
        if (wx.YieldIfNeeded() or True) and not self: return

        tree.Freeze()
        try:
            try:
                if refresh: self.db.populate_schema(parse=True)
            except Exception:
                msg = "Error loading schema data from %s." % self.db
                logger.exception(msg)
                return wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_ERROR)

            def is_indirect_item(a, b):
                trg = next((x for x in (a, b) if x["type"] == "trigger"), None)
                tbv = next((x for x in (a, b) if x["type"] in ("table", "view")), None)
                if trg and tbv: return not util.lceq(trg["tbl_name"], tbv["name"])
                if a["type"] == b["type"] == "table":
                    return b["name"].lower() not in a.get("meta", {}).get("__tables__", ())
                return a["type"] == b["type"] == "view" and \
                       b["name"].lower() not in a.get("meta", {}).get("__tables__", ())

            italicfont = tree.Font
            italicfont.SetStyle(wx.FONTSTYLE_ITALIC)

            root = tree.AddRoot("SQLITE")
            tree.SetItemPyData(root, {"type": "schema"})
            imgs = self.tree_schema_images
            tops, index, total = [], 0, sum(len(vv) for vv in self.db.schema.values())
            for category in database.Database.CATEGORIES:
                items = list(self.db.get_category(category).values())
                categorydata = {"type": "category", "category": category, "level": "category", "items": items}

                t = util.plural(category).capitalize()
                if items: t += " (%s)" % len(items)
                top = tree.AppendItem(root, t)
                tree.SetItemPyData(top, categorydata)
                tops.append(top)
                for item in items:
                    itemdata = dict(item, parent=categorydata, level=category)
                    child = tree.AppendItem(top, util.unprint(item["name"]))
                    tree.SetItemPyData(child, itemdata)
                    columns, childtext = None, ""
                    relateds = self.db.get_related(category, item["name"])

                    if "table" == category:
                        columns = item.get("columns") or []
                        subcategories, emptysubs = ["table", "index", "trigger", "view"], True
                        childtext = util.plural("column", columns)
                    elif "index" == category:
                        childtext = "ON " + util.unprint(grammar.quote(item["tbl_name"]))
                        columns = copy.deepcopy(item.get("meta", {}).get("columns")
                                                or item.get("columns") or [])
                        table = self.db.schema.get("table", {}).get(item["tbl_name"])
                        for col in columns if table else ():
                            if table.get("columns") and col.get("name"):
                                tcol = next((x for x in table["columns"]
                                             if x["name"] == col["name"]), None)
                                if tcol: col["type"] = tcol.get("type", "")
                        subcategories, emptysubs = ["table"], True
                    elif "trigger" == category:
                        if "meta" in item: childtext = " ".join(filter(bool,
                            (item["meta"].get("upon"), item["meta"]["action"],
                             "ON", util.unprint(grammar.quote(item["meta"]["table"])))
                        ))
                        subcategories, emptysubs = ["table", "view"], False
                    elif "view" == category:
                        if "meta" in item:
                            names = [self.db.schema["table"][x]["name"] if x in self.db.schema["table"]
                                     else self.db.schema["view"][x]["name"] if x in self.db.schema["view"]
                                     else x for x in item["meta"].get("__tables__", ())]
                            childtext = "ON " + ", ".join(map(util.unprint, map(grammar.quote, names))) if names else ""
                        columns = item.get("columns") or []
                        subcategories, emptysubs = ["table", "trigger", "view"], False

                    tree.SetItemText(child, childtext, 1)

                    if columns is not None:
                        colchild = tree.AppendItem(child, "Columns (%s)" % len(columns))
                        tree.SetItemPyData(colchild, {"type": "columns", "parent": itemdata})
                        tree.SetItemImage(colchild, imgs["columns"], wx.TreeItemIcon_Normal)
                        lks, fks = self.db.get_keys(item["name"]) if "table" == category else [(), ()]
                        for col in columns:
                            subchild = tree.AppendItem(colchild, util.unprint(col.get("name") or col.get("expr")))
                            mytype = util.unprint(col.get("type", ""))
                            if any(col["name"] in x["name"] for x in lks):
                                mytype = u"\u1d18\u1d0b  " + mytype # Unicode small caps "PK"
                            elif any(col["name"] in x["name"] for x in fks):
                                mytype = u"\u1da0\u1d4f  " + mytype # Unicode small "fk"
                            tree.SetItemText(subchild, mytype, 1)
                            tree.SetItemPyData(subchild, dict(col, parent=itemdata, type="column", level=item["name"]))
                    for subcategory in subcategories:
                        subitems = list(relateds.get(subcategory, {}).values())
                        if not subitems and (not emptysubs or category == subcategory):
                            continue # for subcategory

                        subitems.sort(key=lambda x: (is_indirect_item(item, x), x["name"].lower()))
                        t = util.plural(subcategory).capitalize()
                        if "table" == category == subcategory:
                            t = "Related tables"
                        if subitems: t += " (%s)" % len(subitems)
                        categchild = tree.AppendItem(child, t)
                        subcategorydata = {"type": "category", "category": subcategory, "items": subitems, "parent": itemdata}
                        tree.SetItemPyData(categchild, subcategorydata)
                        if subcategory in imgs:
                            tree.SetItemImage(categchild, imgs[subcategory], wx.TreeItemIcon_Normal)

                        for subitem in subitems:
                            subchild = tree.AppendItem(categchild, util.unprint(subitem["name"]))
                            subdata = dict(subitem, parent=itemdata, level=item["name"])
                            if "__id__" in subdata:
                                subdata["__id__"] = "%s-%s-%s" % (category, subcategory, subdata["__id__"])
                            tree.SetItemPyData(subchild, subdata)
                            t = ""
                            if "index" == subcategory:
                                t = ", ".join(util.unprint(x.get("name", x.get("expr")))
                                              for x in subitem.get("meta", {}).get("columns", subitem.get("columns", [])))
                            elif "table" == category == subcategory:
                                texts = []
                                lks, fks = self.db.get_keys(subitem["name"])
                                fmtkeys = lambda x: ("(%s)" if len(x) > 1 else "%s") % ", ".join(map(util.unprint, map(grammar.quote, x)))
                                for col in lks:
                                    for table, keys in col.get("table", {}).items():
                                        if not util.lceq(table, item["name"]): continue # for table, keys
                                        texts.append("%s REFERENCES %s.%s" % (fmtkeys(keys),
                                            util.unprint(grammar.quote(subitem["name"])), fmtkeys(col["name"])))
                                for col in fks:
                                    for table, keys in col.get("table", {}).items():
                                        if not util.lceq(table, item["name"]): continue # for table, keys
                                        texts.append("%s.%s REFERENCES %s" % (
                                        util.unprint(grammar.quote(subitem["name"])), fmtkeys(col["name"]),
                                        fmtkeys(keys)))
                                t = ", ".join(texts)
                            elif "trigger" == subcategory:
                                if "meta" in subitem:
                                    t = " ".join(filter(bool, (subitem["meta"].get("upon"), subitem["meta"]["action"])))
                                if is_indirect_item(item, subitem):
                                    t += " ON %s" % util.unprint(grammar.quote(subitem["tbl_name"]))
                            tree.SetItemText(subchild, t, 1)
                            if is_indirect_item(item, subitem): tree.SetItemFont(subchild, italicfont)

                    index += 1
                    gauge.Value = 100 * index // total
                    gauge.ToolTip = "Populating.. %s%% (%s of %s)" % (gauge.Value, index, total)
                    if (wx.YieldIfNeeded() or True) and not self: return

                tree.Collapse(top)
            tree.SetColumnWidth(0, tree.Size[0] - 180)
            tree.SetColumnWidth(1, 150)
            tree.Expand(root)
            for top in tops if not any(expandeds) else (): tree.Expand(top)
            self.set_tree_state(tree, tree.RootItem, expandeds)
        finally:
            if not self: return
            self.button_refresh_schema.Enable()
            gauge.Hide()
            gauge.ContainingSizer.Layout()
            tree.Thaw()


    def on_change_tree_data(self, event):
        """Handler for activating a schema item, loads object."""
        if not self.splitter_data.Shown: return
        item, tree = event.GetItem(), self.tree_data
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item) or {}
        data = data if data.get("type") in database.Database.CATEGORIES \
               else data.get("parent") if "column" == data.get("type") else None

        if data:
            nb = self.notebook_data
            p = self.data_pages[data["type"]].get(data["name"])
            if p: nb.SetSelection(nb.GetPageIndex(p))
            else: self.add_data_page(self.db.get_category(data["type"], data["name"]))
            tree.Expand(tree.GetItemParent(item))
        else:
            tree.Collapse(item) if tree.IsExpanded(item) else tree.Expand(item)


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
            else: self.add_schema_page(self.db.get_category(data["type"], data["name"]))
            tree.Expand(tree.GetItemParent(item))
        else:
            tree.Collapse(item) if tree.IsExpanded(item) else tree.Expand(item)


    def on_size_tree(self, event):
        """Sizes last tree column to available space."""
        event.Skip()
        tree = event.EventObject
        tree.SetColumnWidth(1, tree.Size.width - tree.GetColumnWidth(0) - 30)


    def on_key_tree(self, event):
        """Handler for pressing keys in data/schema trees, opens rename dialog."""
        tree = event.EventObject
        tree = tree if isinstance(tree, controls.TreeListCtrl) else \
               tree.Parent if isinstance(tree, wx.lib.agw.hypertreelist.TreeListMainWindow) else None
        if not tree or event.KeyCode not in (wx.WXK_F2, wx.WXK_NUMPAD_F2):
            return event.Skip()
        item = tree.GetSelection()
        data = tree.GetItemPyData(item)
        if data and isinstance(data, dict) \
        and data.get("type") in self.db.CATEGORIES + ["column"]:
            tree.EditLabel(item)


    def on_editstart_tree(self, event):
        """Handler for clicking to edit tree item, allows if schema item node."""
        tree = event.EventObject
        data = tree.GetItemPyData(event.GetItem())
        if not data or data.get("type") not in self.db.CATEGORIES + ["column"] \
        or tree.GetEditControl() \
        or tree is self.tree_schema \
        and data.get("parent", {}).get("level") not in ("category", "table"):
            event.Veto()


    def on_editend_tree(self, event):
        """Handler for clicking to edit tree item, allows if schema item node."""
        if event.IsEditCancelled(): return

        do_veto = True
        try:
            data = event.EventObject.GetItemPyData(event.GetItem())
            name2 = event.GetLabel().strip()
            if name2:
                cmd, args = "rename", (data["type"], data["name"], name2)
                if "column" == data["type"]:
                    cmd = "rename column"
                    args = data["parent"]["name"], data["name"], name2
                do_veto = not self.handle_command(cmd, *args)
        finally:
            if do_veto:
                event.Veto()
                event.EventObject.SetFocus()


    def on_rclick_tree_data(self, event):
        """
        Handler for right-clicking an item in the tables list,
        opens popup menu for choices to export data.
        """
        tree = self.tree_data
        if isinstance(event, wx.ContextMenuEvent): item = tree.GetSelection()
        else: item = event.GetItem()
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item)
        if not data: return

        def select_item(item, *_, **__):
            if not self: return
            tree.SelectItem(item)
        def open_data(data, *_, **__):
            tree.FindAndActivateItem(type=data["type"], name=data["name"])
        def open_meta(data, *_, **__):
            if self.tree_schema.FindAndActivateItem(type=data["type"],
                name=data["name"], level=data["type"]
            ):
                self.notebook.SetSelection(self.pageorder[self.page_schema])
        def import_data(*_, **__):
            dlg = components.ImportDialog(self, self.db)
            if "table" == data["type"]: dlg.SetTable(data["name"], fixed=True)
            dlg.ShowModal()
        def clipboard_copy(text, label, *_, **__):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text() if callable(text) else text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
                if label: guibase.status("Copied %s to clipboard.", label)
        def toggle_items(node, *_, **__):
            tree.ToggleItem(node)
        def create_object(category, *_, **__):
            newdata = {"type": category,
                       "meta": {"__type__": "CREATE %s" % category.upper()}}
            self.notebook.SetSelection(self.pageorder[self.page_schema])
            self.add_schema_page(newdata)

        boldfont = wx.Font(self.Font.PointSize, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName=self.Font.FaceName)

        menu = wx.Menu()
        item_file = item_file_single = item_database = item_import = None
        item_reindex = item_reindex_all = item_truncate = None
        item_rename = item_clone = item_create = None
        item_drop = item_drop_all = item_drop_col = None
        if data.get("type") in ("table", "view"): # Single table/view
            item_name = wx.MenuItem(menu, -1, "%s %s" % (
                        data["type"].capitalize(), fmt_entity(data["name"])))
            item_open = wx.MenuItem(menu, -1, "&Open %s data" % data["type"])
            item_open_meta = wx.MenuItem(menu, -1, "Open %s &schema" % data["type"])
            item_copy      = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql  = wx.MenuItem(menu, -1, "Copy %s S&QL" % data["type"])

            item_name.Font = boldfont

            menu.Append(item_name)
            menu.AppendSeparator()
            menu.Append(item_open)
            menu.Append(item_open_meta)
            menu.Append(item_copy)
            menu.Append(item_copy_sql)

            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                      item_name)
            menu.Bind(wx.EVT_MENU, functools.partial(open_data, data), item_open)
            menu.Bind(wx.EVT_MENU, functools.partial(open_meta, data), item_open_meta)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"], "%s name" % data["type"]),
                      item_copy)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"], "%s SQL" % data["type"]),
                      item_copy_sql)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                      functools.partial(self.db.get_sql, data["type"], data["name"]), "%s SQL" % data["type"]), item_copy_sql)

            item_file = wx.MenuItem(menu, -1, "Export %s to &file" % data["type"])
            if data["type"] in ("table", "view"):
                item_database = wx.MenuItem(menu, -1, "Export %s to another data&base" % data["type"])
                item_clone    = wx.MenuItem(menu, -1, "C&lone %s" % data["type"])
            if "table" == data["type"]:
                item_import   = wx.MenuItem(menu, -1, "&Import into table from file")
                item_truncate = wx.MenuItem(menu, -1, "Truncate table")
                item_reindex  = wx.MenuItem(menu, -1, "Reindex table")
            item_rename = wx.MenuItem(menu, -1, "Rena&me %s\t(F2)" % data["type"])
            item_drop   = wx.MenuItem(menu, -1, "Drop %s" % data["type"])

        elif "column" == data.get("type"): # Column
            item_name = wx.MenuItem(menu, -1, 'Column "%s.%s"' % (
                        fmt_entity(data["parent"]["name"], force=False),
                        fmt_entity(data["name"], force=False)))
            item_open      = wx.MenuItem(menu, -1, "&Open %s data" % data["parent"]["type"])
            item_open_meta = wx.MenuItem(menu, -1, "Open %s &schema" % data["parent"]["type"])
            item_copy      = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql  = wx.MenuItem(menu, -1, "Copy column S&QL")
            item_renamecol = wx.MenuItem(menu, -1, "Rena&me column\t(F2)") \
                             if "table" == data["parent"]["type"] else None
            item_drop_col  = wx.MenuItem(menu, -1, "Drop column") \
                             if "table" == data["parent"]["type"] else None

            item_name.Font = boldfont

            menu.Append(item_name)
            menu.AppendSeparator()
            menu.Append(item_open)
            menu.Append(item_open_meta)
            menu.Append(item_copy)
            menu.Append(item_copy_sql)
            if item_renamecol or item_drop_col:
                menu.AppendSeparator()
            if item_renamecol:
                menu.Append(item_renamecol)
            if item_drop_col:
                if len(data["parent"]["columns"]) == 1: item_drop_col.Enable(False)
                menu.Append(item_drop_col)

            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                      item_name)
            menu.Bind(wx.EVT_MENU, functools.partial(open_data, data["parent"]), item_open)
            menu.Bind(wx.EVT_MENU, functools.partial(open_meta, data["parent"]), item_open_meta)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"], "column name"), item_copy)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                    functools.partial(self.db.get_sql, data["parent"]["type"], data["parent"]["name"], data["name"]),
                "column SQL"), item_copy_sql)
            if item_renamecol:
                menu.Bind(wx.EVT_MENU, lambda e: tree.EditLabel(item), item_renamecol)
            if item_drop_col:
                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop column", data["parent"]["name"], data["name"]), item_drop_col)

        elif "category" == data.get("type"): # Category list
            item_copy = wx.MenuItem(menu, -1, "&Copy %s names" % data["category"])
            item_file = wx.MenuItem(menu, -1, "Export all %s to &file" % util.plural(data["category"]))
            item_file_single = wx.MenuItem(menu, -1, "Export all %s to single spreads&heet" % util.plural(data["category"]))

            menu.Append(item_copy)

            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, ", ".join(data["items"]), "%s names" % data["category"]), item_copy)

            if data["category"] in ("table", "view"):
                item_database    = wx.MenuItem(menu, -1, "Export all %s to another data&base" % util.plural(data["category"]))
            if "table" == data["category"]:
                item_import      = wx.MenuItem(menu, -1, "&Import into table from file")
                item_reindex_all = wx.MenuItem(menu, -1, "Reindex all")

            item_drop_all = wx.MenuItem(menu, -1, "Drop all %s" % util.plural(data["category"]))
            item_create   = wx.MenuItem(menu, -1, "Create &new %s" % data["category"])
        else: # Root
            item_dump   = wx.MenuItem(menu, -1, "Save database d&ump as SQL")
            item_database_meta = wx.MenuItem(menu, -1, "Export all to another data&base")
            menu.Append(item_dump)
            menu.Append(item_database_meta)
            menu.Bind(wx.EVT_MENU, self.on_dump, item_dump)
            menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_to_db),
                      item_database_meta)
            submenu = wx.Menu()
            menu.AppendSubMenu(submenu, text="Create ne&w ..")
            for category, key in (("table", "t"), ("view", "v")):
                it = wx.MenuItem(submenu, -1, "New " + category.replace(key, "&" + key, 1))
                submenu.Append(it)
                menu.Bind(wx.EVT_MENU, functools.partial(create_object, category), it)
            item_drop_schema = wx.MenuItem(menu, -1, "Drop everything")
            menu.Append(item_drop_schema)
            menu.Bind(wx.EVT_MENU, functools.partial(self.handle_command, "drop schema"),
                      item_drop_schema)
            item_drop_schema.Enabled = any(self.db.schema.values())

        if item_file:
            menu.AppendSeparator()
            menu.Append(item_file)
            if item_file_single: menu.Append(item_file_single)
            if item_database: menu.Append(item_database)
            if item_import: menu.Append(item_import)
            if item_reindex:
                menu.AppendSeparator()
                menu.Append(item_reindex)
            if item_truncate:
                menu.Append(item_truncate)
            if item_drop_all:
                menu.AppendSeparator()
                menu.Append(item_drop_all)
                menu.Append(item_create)
            if item_rename:
                menu.Append(item_rename)
            if item_reindex_all:
                menu.Append(item_reindex_all)
            if item_clone:
                menu.Append(item_clone)
            if item_drop:
                menu.Append(item_drop)
            names = data["items"] if "category" == data["type"] else data["name"]
            category = data["category"] if "category" == data["type"] else data["type"]
            menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_data_file, category, names),
                      item_file)
            if item_file_single:
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_singlefile, category),
                          item_file_single)
            if item_database:
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_to_db, category=category, names=names),
                          item_database)
            if item_import:
                menu.Bind(wx.EVT_MENU, import_data, item_import)
            if item_reindex:
                item_reindex.Enable("index" == data["type"] or "index" in self.db.get_related("table", data["name"], own=True))
                menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("reindex", data["type"], data["name"]), item_reindex)
            if item_reindex_all:
                if not self.db.schema.get("index"): item_reindex_all.Enable(False)
                menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("reindex", data["category"]), item_reindex_all)
            if item_truncate:
                if not self.db.schema["table"][data["name"]].get("count"):
                    item_truncate.Enable(False)
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_truncate, data["name"]), item_truncate)
            if item_rename:
                menu.Bind(wx.EVT_MENU, lambda e: tree.EditLabel(item), item_rename)
            if item_clone:
                menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("clone", data["type"], data["name"], "table" == data["type"]), item_clone)
            if item_drop:
                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop", data["type"], [data["name"]]), item_drop)

        if item_drop_all:
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop", data["category"], data["items"]),
                      item_drop_all)
        if item_create:
            menu.Bind(wx.EVT_MENU, functools.partial(create_object, data["category"]),
                      item_create)
        if item_file_single:
            if not data["items"]:
                item_copy.Enable(False)
                item_file.Enable(False)
                item_file_single.Enable(False)
                if item_database: item_database.Enable(False)
                item_drop_all.Enable(False)
            if not importexport.xlsxwriter: item_file_single.Enable(False)

        if tree.HasChildren(item):
            item_expand   = wx.MenuItem(menu, -1, "&Toggle expanded/collapsed")
            menu.Bind(wx.EVT_MENU, functools.partial(toggle_items, item), item_expand)
            if menu.MenuItemCount: menu.AppendSeparator()
            menu.Append(item_expand)

        item0 = tree.GetSelection()
        if item != item0: select_item(item)
        tree.PopupMenu(menu)
        if item0 and item != item0: select_item(item0)


    def on_rclick_tree_schema(self, event):
        """
        Handler for right-clicking an item in the schema tree,
        opens popup menu for choices.
        """
        tree = self.tree_schema
        if isinstance(event, wx.ContextMenuEvent): item = tree.GetSelection()
        else: item = event.GetItem()
        if not item or not item.IsOk(): return
        data = tree.GetItemPyData(item)
        if not data: return

        def select_item(it, *_, **__):
            if not self: return
            tree.SelectItem(it)
        def clipboard_copy(text, label, *_, **__):
            if wx.TheClipboard.Open():
                d = wx.TextDataObject(text() if callable(text) else text)
                wx.TheClipboard.SetData(d), wx.TheClipboard.Close()
                if label: guibase.status("Copied %s to clipboard.", label)
        def toggle_items(node, *_, **__):
            tree.ToggleItem(node)
        def open_data(data, *_, **__):
            if self.tree_data.FindAndActivateItem(type=data["type"], name=data["name"]):
                self.notebook.SetSelection(self.pageorder[self.page_data])
        def open_meta(data, *_, **__):
            tree.FindAndActivateItem(type=data["type"], name=data["name"],
                                     level=data["level"])
        def create_object(category, column=None, *_, **__):
            args = []
            if data.get("type") in self.db.CATEGORIES:
                args = data["type"], data["name"]
            elif data.get("parent"):
                args = data["parent"]["type"], data["parent"]["name"]
            if column:
                if "trigger" == category:
                    args += ({"columns": [{"name": column}], "action": "UPDATE"}, )
                elif "index" == category:
                    args += ({"columns": [{"name": column}]}, )
            self.handle_command("create", category, *args)
        def copy_related(*_, **__):
            self.handle_command("copy", "related", data["type"], data["name"])

        menu = wx.Menu()
        boldfont = self.Font
        boldfont.SetWeight(wx.FONTWEIGHT_BOLD)
        boldfont.SetFaceName(self.Font.FaceName)
        boldfont.SetPointSize(self.Font.PointSize)

        if "schema" == data["type"]:
            submenu, keys = wx.Menu(), []
            if any(self.db.schema.values()):
                item_copy_sql = wx.MenuItem(menu, -1, "Copy schema S&QL")
                item_save_sql = wx.MenuItem(menu, -1, "Save schema SQL to fi&le")
                item_database_meta = wx.MenuItem(menu, -1, "Export all structures to another data&base")
                menu.Append(item_copy_sql)
                menu.Append(item_save_sql)
                menu.Append(item_database_meta)
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, self.db.get_sql, "schema SQL"),
                          item_copy_sql)
                menu.Bind(wx.EVT_MENU, lambda e: self.save_sql(self.db.get_sql()),
                          item_save_sql)
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_to_db, data=False),
                          item_database_meta)

            menu.AppendSubMenu(submenu, text="Create ne&w ..")
            for category in database.Database.CATEGORIES:
                key = next((x for x in category if x not in keys), category[0])
                keys.append(key)
                it = wx.MenuItem(submenu, -1, "New " + category.replace(key, "&" + key, 1))
                submenu.Append(it)
                menu.Bind(wx.EVT_MENU, functools.partial(create_object, category, None), it)
            item_drop_schema = wx.MenuItem(menu, -1, "Drop everything")
            menu.Append(item_drop_schema)
            menu.Bind(wx.EVT_MENU, functools.partial(self.handle_command, "drop schema"),
                      item_drop_schema)
            item_drop_schema.Enabled = any(self.db.schema.values())
        elif "category" == data["type"]:
            sqlkws = {"category": data["category"]}
            if data.get("parent"): sqlkws["name"] = [x["name"] for x in data["items"]]
            names = [x["name"] for x in data["items"]]
            item_reindex = None

            if names:
                item_drop_all = wx.MenuItem(menu, -1, "Drop all %s" % util.plural(data["category"]))
                item_copy     = wx.MenuItem(menu, -1, "&Copy %s names" % data["category"])
                item_copy_sql = wx.MenuItem(menu, -1, "Copy %s S&QL" % util.plural(data["category"]))
                item_save_sql = wx.MenuItem(menu, -1, "Save %s SQL to fi&le" % util.plural(data["category"]))
                if data["category"] in ("table", "index"):
                    item_reindex = wx.MenuItem(menu, -1, "Reindex all")
                    menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("reindex", data["category"]), item_reindex)

                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop", data["category"], names),
                          item_drop_all)
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, lambda: "\n".join(map(grammar.quote, names)), "%s names" % data["category"]),
                          item_copy)
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                          functools.partial(self.db.get_sql, **sqlkws), "%s SQL" % util.plural(data["category"])), item_copy_sql)
                menu.Bind(wx.EVT_MENU, lambda e: self.save_sql(self.db.get_sql(**sqlkws), util.plural(data["category"])), item_save_sql)

            item_create = wx.MenuItem(menu, -1, "Create &new %s" % data["category"])

            if names:
                menu.Append(item_copy)
                menu.Append(item_copy_sql)
                menu.Append(item_save_sql)

                if data["category"] in ("table", "view"):
                    item_database_meta = wx.MenuItem(menu, -1, "Export all %s structures to another data&base" % data["category"])
                    menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_to_db, category=data["category"], names=names, data=False),
                              item_database_meta)
                    menu.Append(item_database_meta)

                menu.AppendSeparator()
                if item_reindex: menu.Append(item_reindex)
                menu.Append(item_drop_all)
            menu.Append(item_create)
            menu.Bind(wx.EVT_MENU, functools.partial(create_object, data["category"], None), item_create)
        elif "column" == data["type"]:
            has_name, has_sql, table = True, True, {}
            submenu_col_create, item_renamecol, item_dropcol = None, None, None
            if "view" == data["parent"]["type"]:
                has_sql = False
            elif "index" == data["parent"]["type"]:
                has_name = "name" in data
                table = self.db.schema.get("table", {}).get(data["parent"]["tbl_name"])
                sqltext = " ".join(filter(bool, (
                    grammar.quote(data["name"]) if has_name else data.get("expr"),
                    "COLLATE %s" % data["collate"] if data.get("collate") else "",
                    data.get("order"),
                )))
            else:
                table = self.db.schema.get("table", {}).get(data["parent"]["name"])
                sqlkws = {"category": "table", "name": table["name"], "column": data["name"]}
                sqltext = functools.partial(self.db.get_sql, **sqlkws)

                submenu_col_create, keys = wx.Menu(), []
                for category in database.Database.CATEGORIES :
                    key = next((x for x in category if x not in keys), category[0])
                    keys.append(key)
                    if category not in ("index", "trigger"): continue # for category
                    it = wx.MenuItem(submenu_col_create, -1, "New " + category.replace(key, "&" + key, 1))
                    submenu_col_create.Append(it)
                    menu.Bind(wx.EVT_MENU, functools.partial(create_object, category, data["name"]), it)

                item_renamecol = wx.MenuItem(menu, -1, "Rena&me column\t(F2)")
                menu.Bind(wx.EVT_MENU, lambda e: tree.EditLabel(item), item_renamecol)
                item_dropcol   = wx.MenuItem(menu, -1, "Drop column")
                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop column", data["parent"]["name"], data["name"]), item_dropcol)

            if has_name:
                parts = [fmt_entity(x, force=False)
                         for x in (table.get("name"), data["name"]) if x]
                inter = " ." if len(parts) > 1 and parts[0][-2:] == ".." else "."
                title = ("%s" if any('"' in x for x in parts) else '"%s"') % inter.join(parts)
                item_name = wx.MenuItem(menu, -1, 'Column %s' % title)
                item_name.Font = boldfont
                item_copy = wx.MenuItem(menu, -1, "&Copy name")

            if has_sql:
                item_copy_sql = wx.MenuItem(menu, -1, "Copy column S&QL")

            if has_name:
                menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                          item_name)
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"], "column name"),
                          item_copy)
            if has_sql:
                menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, sqltext, "column SQL"),
                          item_copy_sql)

            if has_name:
                menu.Append(item_name)
                menu.AppendSeparator()
                menu.Append(item_copy)
            if has_sql:
                menu.Append(item_copy_sql)
            if submenu_col_create or item_renamecol or item_dropcol:
                menu.AppendSeparator()
            if submenu_col_create:
                menu.AppendSubMenu(submenu_col_create, text="Create &new ..")
            if item_renamecol:
                menu.Append(item_renamecol)
            if item_dropcol:
                if len(data["parent"]["columns"]) == 1: item_dropcol.Enable(False)
                menu.Append(item_dropcol)
        elif "columns" == data["type"]:
            cols = data["parent"].get("columns") or data["parent"].get("meta", {}).get("columns", [])
            names = [x["name"] for x in cols]
            item_copy = wx.MenuItem(menu, -1, "&Copy column names")
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, lambda: "\n".join(map(grammar.quote, names)), "column names"),
                      item_copy)
            menu.Append(item_copy)
        else: # Single category item, like table
            sqlkws = {"category": data["type"], "name": data["name"]}

            item_name   = wx.MenuItem(menu, -1, "%s %s" % (
                          data["type"].capitalize(), fmt_entity(data["name"])))
            item_open = wx.MenuItem(menu, -1, "&Open %s schema" % data["type"])
            item_open_data = wx.MenuItem(menu, -1, "Open %s &data" % data["type"]) \
                             if data["type"] in ("table", "view") else None
            item_copy      = wx.MenuItem(menu, -1, "&Copy name")
            item_copy_sql  = wx.MenuItem(menu, -1, "Copy %s S&QL" % data["type"])
            item_copy_rel  = wx.MenuItem(menu, -1, "Copy all &related SQL")
            item_rename    = wx.MenuItem(menu, -1, "Rena&me %s\t(F2)" % data["type"]) \
                             if "category" == data.get("parent", {}).get("type") else None
            item_clone     = wx.MenuItem(menu, -1, "C&lone %s structure" % data["type"]) \
                             if data["type"] in ("table", "view") else None
            item_drop      = wx.MenuItem(menu, -1, "Drop %s" % data["type"])
            item_reindex   = wx.MenuItem(menu, -1, "Reindex") \
                             if data["type"] in ("table", "index") else None

            item_name.Font = boldfont

            menu.Append(item_name)
            menu.AppendSeparator()
            menu.Append(item_open)
            if item_open_data: menu.Append(item_open_data)
            menu.Append(item_copy)
            menu.Append(item_copy_sql)
            menu.Append(item_copy_rel)

            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, select_item, item),
                      item_name)
            menu.Bind(wx.EVT_MENU, functools.partial(open_meta, data), item_open)
            if item_open_data:
                menu.Bind(wx.EVT_MENU, functools.partial(open_data, data),
                          item_open_data)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy, data["name"], "%s name" % data["type"]),
                      item_copy)
            menu.Bind(wx.EVT_MENU, functools.partial(clipboard_copy,
                      functools.partial(self.db.get_sql, **sqlkws), "%s SQL" % data["type"]), item_copy_sql)
            menu.Bind(wx.EVT_MENU, copy_related, item_copy_rel)
            if item_rename:
                menu.Bind(wx.EVT_MENU, lambda e: tree.EditLabel(item), item_rename)
            menu.Bind(wx.EVT_MENU, functools.partial(wx.CallAfter, self.handle_command, "drop", data["type"], [data["name"]]),
                      item_drop)

            if data["type"] in ("table", "view"):
                item_database_meta = wx.MenuItem(menu, -1, "Export %s structure to another data&base" % data["type"])
                menu.Append(item_database_meta)
                menu.Bind(wx.EVT_MENU, functools.partial(self.on_export_to_db, category=data["type"], names=data["name"], data=False),
                          item_database_meta)

            menu.AppendSeparator()

            if data["type"] in ("table", "view"):
                submenu, keys = wx.Menu(), []
                menu.AppendSubMenu(submenu, text="Create &new ..")
                for category in database.Database.CATEGORIES:
                    key = next((x for x in category if x not in keys), category[0])
                    keys.append(key)
                    if "view" == data["type"] and category not in ["trigger"]:
                        continue # for category
                    if category == data["type"]: continue # for category
                    it = wx.MenuItem(submenu, -1, "New " + category.replace(key, "&" + key, 1))
                    submenu.Append(it)
                    menu.Bind(wx.EVT_MENU, functools.partial(create_object, category, None), it)

            if item_rename:
                menu.Append(item_rename)
            if item_clone:
                menu.Append(item_clone)
                menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("clone", data["type"], data["name"]), item_clone)
            menu.Append(item_drop)
            if item_reindex:
                menu.Append(item_reindex)
                item_reindex.Enable("index" == data["type"] or "index" in self.db.get_related("table", data["name"], own=True))
                menu.Bind(wx.EVT_MENU, lambda e: self.handle_command("reindex", data["type"], data["name"]), item_reindex)

        if tree.HasChildren(item):
            item_expand   = wx.MenuItem(menu, -1, "&Toggle expanded/collapsed")
            if menu.MenuItemCount: menu.AppendSeparator()
            menu.Append(item_expand)
            menu.Bind(wx.EVT_MENU, functools.partial(toggle_items, item), item_expand)

        item0 = tree.GetSelection()
        if item != item0: select_item(item)
        tree.PopupMenu(menu)
        if item0 and item != item0: select_item(item0)


    def update_autocomp(self):
        """Add PRAGMAS, and table/view/column names to SQL autocomplete."""
        if not self: return
        words = list(database.Database.PRAGMA) + database.Database.EXTRA_PRAGMAS
        subwords = {}

        for category in ("table", "view"):
            for item in self.db.schema.get(category, {}).values():
                myname = grammar.quote(item["name"])
                words.append(myname)
                if not item.get("columns"): continue # for item
                subwords[myname] = [grammar.quote(c["name"]) for c in item["columns"]]
        for p in self.sql_pages.values(): p.SetAutoComp(words, subwords)


    def update_tabheader(self):
        """Updates page tab header with option to close page."""
        if not self: return
        self.ready_to_close = True
        wx.PostEvent(self, DatabasePageEvent(self.Id, source=self, ready=True))



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
        self.Bind(wx.EVT_CLOSE,  lambda e: self.Destroy())
        self.Bind(wx.EVT_BUTTON, lambda e: self.Destroy(), id=wx.ID_OK)

        self.Layout()
        self.Size = (self.Size[0], html.VirtualSize[1] + 70)
        self.CenterOnParent()


    def OnSysColourChange(self, event):
        """Handler for system colour change, refreshes content."""
        event.Skip()
        def dorefresh():
            if not self: return
            self.html.SetPage(self.content() if callable(self.content) else self.content)
            self.html.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)
            self.html.ForegroundColour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
        wx.CallAfter(dorefresh) # Postpone to allow conf to update


def make_unique_page_title(title, notebook, maxlen=None, front=False, skip=-1):
    """
    Returns a title that is unique for the given notebook - if the specified
    title already exists, appends a counter to the end, e.g. "name (2)".

    @param   notebook  notebook with GetPageCount() and GetPageText()
    @param   maxlen    defaults to conf.MaxTabTitleLength, ignored if <= 0
    @param   front     whether to ellipsize title from the front or the back
                       if longer than maxlen
    @param   skip      index of notebook page to skip, if any
    """
    if maxlen is None: maxlen = conf.MaxTabTitleLength
    if maxlen > 0: title = util.ellipsize(title, maxlen, front=front)
    all_titles = [notebook.GetPageText(i).rstrip("*")
                  for i in range(notebook.GetPageCount()) if i != skip]
    return util.make_unique(title, all_titles, suffix=" (%s)", case=True)
