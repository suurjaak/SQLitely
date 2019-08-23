# -*- coding: utf-8 -*-
"""
SQLiteMate UI application main window class and project-specific UI classes.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    23.08.2019
------------------------------------------------------------------------------
"""
import ast
import base64
import collections
import copy
import datetime
import functools
import hashlib
import inspect
import math
import os
import re
import shutil
import sys
import textwrap
import time
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

from lib import controls
from lib import util
from lib.vendor import step

import conf
import database
import export
import guibase
import images
import main
import support
import templates
import workers


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

        self.init_colours()
        self.db_filename = None # Current selected file in main list
        self.db_filenames = {}  # added DBs {filename: {size, last_modified,
                                #            tables, error},}
        self.dbs = {}           # Open databases {filename: Database, }
        self.db_pages = {}      # {DatabasePage: Database, }
        self.page_db_latest = None    # Last opened database page
        # List of Notebook pages user has visited, used for choosing page to
        # show when closing one.
        self.pages_visited = []
        self.db_drag_start = None

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
        abouticon = "%s.png" % conf.Title.lower() # Program icon shown in About window
        raw = base64.b64decode(images.Icon48x48_32bit.data)
        self.memoryfs["handler"].AddFile(abouticon, raw, wx.BITMAP_TYPE_PNG)
        self.memoryfs["files"][abouticon] = 1
        # Screenshots look better with colouring if system has off-white colour
        tint_colour = wx.NamedColour(conf.BgColour)
        tint_factor = [((4 * x) % 256) / 255. for x in tint_colour]
        # Images shown on the default search content page
        for name in ["Search", "Info", "Tables", "SQL"]:
            bmp = getattr(images, "Help" + name, None)
            if not bmp: continue # Continue for name in [..]
            bmp = bmp.Image.AdjustChannels(*tint_factor)
            raw = util.img_wx_to_raw(bmp)
            filename = "Help%s.png" % name
            self.memoryfs["handler"].AddFile(filename, raw, wx.BITMAP_TYPE_PNG)
            self.memoryfs["files"][filename] = 1

        self.worker_detection = \
            workers.DetectDatabaseThread(self.on_detect_databases_callback)
        self.Bind(EVT_DETECTION_WORKER, self.on_detect_databases_result)
        self.Bind(EVT_OPEN_DATABASE, self.on_open_database_event)

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
                self.update_notebook_header()

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
        if self.list_db.GetItemCount() > 1:
            self.list_db.SetFocus()
        else:
            self.button_detect.SetFocus()

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


    def init_colours(self):
        """Update configuration colours with current system theme values."""
        colourhex = lambda index: (wx.SystemSettings.GetColour(index)
                                   .GetAsString(wx.C2S_HTML_SYNTAX))
        conf.FgColour = colourhex(wx.SYS_COLOUR_BTNTEXT)
        conf.BgColour = colourhex(wx.SYS_COLOUR_WINDOW)
        conf.DisabledColour = colourhex(wx.SYS_COLOUR_GRAYTEXT)
        conf.WidgetColour = colourhex(wx.SYS_COLOUR_BTNFACE)
        if "#FFFFFF" != conf.BgColour: # Potential default colour mismatch
            conf.DBListForegroundColour = conf.FgColour
            conf.DBListBackgroundColour = conf.BgColour
            conf.LinkColour = colourhex(wx.SYS_COLOUR_HOTLIGHT)
            conf.TitleColour = colourhex(wx.SYS_COLOUR_HOTLIGHT)
            conf.MainBgColour = conf.WidgetColour
            conf.HelpCodeColour = colourhex(wx.SYS_COLOUR_HIGHLIGHT)
            conf.HelpBorderColour = colourhex(wx.SYS_COLOUR_ACTIVEBORDER)

            # Hack: monkey-patch FlatImageBook with non-hardcoded background
            class HackContainer(wx.lib.agw.labelbook.ImageContainer):
                BRUSH1, BRUSH2 = wx.WHITE_BRUSH, wx.Brush(conf.BgColour)
                def OnPaint(self, event):
                    wx.WHITE_BRUSH = HackContainer.BRUSH2
                    try: result = HackContainer.__base__.OnPaint(self, event)
                    finally: wx.WHITE_BRUSH = HackContainer.BRUSH1
                    return result
            wx.lib.agw.labelbook.ImageContainer = HackContainer


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
                if self.db_filename: # Load database focused in dblist
                    page = self.load_database_page(self.db_filename)
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
        l, p = self.list_db, self.panel_db_main.Parent # Right panel scroll
        fn = lambda: self and (p.Layout(), l.SetColumnWidth(0, l.Size[1] - 5))
        wx.CallAfter(fn)


    def on_move(self, event):
        """Handler for window move event, saves position."""
        conf.WindowPosition = event.Position[:]
        conf.save()
        event.Skip()


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


    def on_dragstop_list_db(self, event):
        """Handler for stopping drag in the database list, rearranges list."""
        start, stop = self.db_drag_start, max(1, event.GetIndex())
        if start and start != stop:
            filename = self.list_db.GetItemText(start)
            self.list_db.DeleteItem(start)
            idx = stop if start > stop else stop - 1
            self.list_db.InsertImageStringItem(idx, filename, [1])
            fgcolour = wx.NamedColour(conf.DBListForegroundColour)
            bgcolour = wx.NamedColour(conf.DBListBackgroundColour)
            self.list_db.SetItemBackgroundColour(idx, bgcolour)
            self.list_db.SetItemTextColour(idx, fgcolour)
            self.list_db.Select(idx)
        self.db_drag_start = None


    def on_dragstart_list_db(self, event):
        """Handler for dragging items in the database list, cancels dragging."""
        if event.GetIndex():
            self.db_drag_start = event.GetIndex()
        else:
            self.db_drag_start = None
            self.on_cancel_drag_list_db(event)


    def on_cancel_drag_list_db(self, event):
        """Handler for dragging items in the database list, cancels dragging."""
        class HackEvent(object): # UltimateListCtrl hack to cancel drag.
            def __init__(self, pos=wx.Point()): self._position = pos
            def GetPosition(self): return self._position
        try:
            wx.CallAfter(self.list_db.Children[0].DragFinish, HackEvent())
        except: raise


    def create_page_main(self, notebook):
        """Creates the main page with database list and buttons."""
        page = self.page_main = wx.Panel(notebook)
        page.BackgroundColour = conf.MainBgColour
        notebook.AddPage(page, "Databases")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        agw_style = (wx.LC_REPORT | wx.LC_NO_HEADER |
                     wx.LC_SINGLE_SEL | wx.BORDER_NONE)
        if hasattr(wx.lib.agw.ultimatelistctrl, "ULC_USER_ROW_HEIGHT"):
            agw_style |= wx.lib.agw.ultimatelistctrl.ULC_USER_ROW_HEIGHT
        list_db = self.list_db = wx.lib.agw.ultimatelistctrl. \
            UltimateListCtrl(parent=page, agwStyle=agw_style)
        list_db.MinSize = 400, -1 # Maximize-restore would resize width to 100
        list_db.InsertColumn(0, "")
        il = wx.ImageList(*images.ButtonHome.Bitmap.Size)
        il.Add(images.ButtonHome.Bitmap)
        il.Add(images.ButtonListDatabase.Bitmap)
        list_db.AssignImageList(il, wx.IMAGE_LIST_SMALL)
        list_db.InsertImageStringItem(0, "Home", [0])
        list_db.TextColour = wx.NamedColour(conf.DBListForegroundColour)
        list_bgcolour = wx.NamedColour(conf.DBListBackgroundColour)
        list_db.BackgroundColour = list_bgcolour
        list_db.SetItemBackgroundColour(0, list_bgcolour)
        if hasattr(list_db, "SetUserLineHeight"):
            h = images.ButtonListDatabase.Bitmap.Size[1]
            list_db.SetUserLineHeight(int(h * 1.5))
        list_db.Select(0)

        panel_right = wx.lib.scrolledpanel.ScrolledPanel(page)
        panel_right.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        panel_main = self.panel_db_main = wx.Panel(panel_right)
        panel_detail = self.panel_db_detail = wx.Panel(panel_right)
        panel_main.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_detail.Sizer = wx.BoxSizer(wx.VERTICAL)

        # Create main page label and buttons
        label_main = wx.StaticText(panel_main,
                                   label="Welcome to %s" % conf.Title)
        label_main.SetForegroundColour(conf.TitleColour)
        label_main.Font = wx.Font(14, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        BUTTONS_MAIN = [
            ("new", "&New database", images.ButtonNew, 
             "Create a new SQLite database."),
            ("opena", "&Open a database..", images.ButtonOpenA, 
             "Choose a database from your computer to open."),
            ("detect", "Detect databases", images.ButtonDetect,
             "Auto-detect databases from user folders."),
            ("folder", "&Import from folder.", images.ButtonFolder,
             "Select a folder where to look for databases "),
            ("missing", "Remove missing", images.ButtonRemoveMissing,
             "Remove non-existing files from the database list."),
            ("clear", "C&lear list", images.ButtonClear,
             "Clear the current database list."), ]
        for name, label, img, note in BUTTONS_MAIN:
            button = controls.NoteButton(panel_main, label, note, img.Bitmap)
            setattr(self, "button_" + name, button)
            exec("button_%s = self.button_%s" % (name, name)) in {}, locals()
        button_missing.Hide(); button_clear.Hide()

        # Create detail page labels, values and buttons
        label_db = self.label_db = wx.TextCtrl(parent=panel_detail, value="",
            style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH)
        label_db.Font = wx.Font(12, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        label_db.BackgroundColour = panel_detail.BackgroundColour
        label_db.SetEditable(False)

        sizer_labels = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        LABELS = [("path", "Location"), ("size", "Size"),
                  ("modified", "Last modified"), ("tables", "Tables")]
        for field, title in LABELS:
            lbltext = wx.StaticText(parent=panel_detail, label="%s:" % title)
            valtext = wx.TextCtrl(parent=panel_detail, value="",
                                  size=(300, -1), style=wx.NO_BORDER)
            valtext.BackgroundColour = panel_detail.BackgroundColour
            valtext.SetEditable(False)
            lbltext.ForegroundColour = conf.DisabledColour
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
            exec("button_%s = self.button_%s" % (name, name)) # Hack local name

        children = list(panel_main.Children) + list(panel_detail.Children)
        for c in [panel_main, panel_detail] + children:
            c.BackgroundColour = page.BackgroundColour 
        panel_right.SetupScrolling(scroll_x=False)
        panel_detail.Hide()

        list_db.Bind(wx.EVT_LIST_ITEM_SELECTED,  self.on_select_list_db)
        list_db.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_open_from_list_db)
        list_db.Bind(wx.EVT_CHAR_HOOK,           self.on_list_db_key)
        list_db.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_DRAG,
                     self.on_dragstart_list_db)
        list_db.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_END_DRAG,
                     self.on_dragstop_list_db)
        list_db.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_RDRAG,
                     self.on_cancel_drag_list_db)
        button_new.Bind(wx.EVT_BUTTON,           self.on_new_database)
        button_opena.Bind(wx.EVT_BUTTON,         self.on_open_database)
        button_detect.Bind(wx.EVT_BUTTON,        self.on_detect_databases)
        button_folder.Bind(wx.EVT_BUTTON,        self.on_add_from_folder)
        button_missing.Bind(wx.EVT_BUTTON,       self.on_remove_missing)
        button_clear.Bind(wx.EVT_BUTTON,         self.on_clear_databases)
        button_open.Bind(wx.EVT_BUTTON,          self.on_open_current_database)
        button_saveas.Bind(wx.EVT_BUTTON,        self.on_save_database_as)
        button_remove.Bind(wx.EVT_BUTTON,        self.on_remove_database)

        panel_main.Sizer.Add(label_main, border=10, flag=wx.ALL)
        panel_main.Sizer.Add((0, 10))
        panel_main.Sizer.Add(button_new, flag=wx.GROW)
        panel_main.Sizer.Add(button_opena, flag=wx.GROW)
        panel_main.Sizer.Add(button_detect, flag=wx.GROW)
        panel_main.Sizer.Add(button_folder, flag=wx.GROW)
        panel_main.Sizer.AddStretchSpacer()
        panel_main.Sizer.Add(button_missing, flag=wx.GROW)
        panel_main.Sizer.Add(button_clear, flag=wx.GROW)
        panel_detail.Sizer.Add(label_db, border=10, flag=wx.ALL | wx.GROW)
        panel_detail.Sizer.Add(sizer_labels, border=10, flag=wx.ALL | wx.GROW)
        panel_detail.Sizer.AddStretchSpacer()
        panel_detail.Sizer.Add(button_open, flag=wx.GROW)
        panel_detail.Sizer.Add(button_saveas, flag=wx.GROW)
        panel_detail.Sizer.Add(button_remove, flag=wx.GROW)
        panel_right.Sizer.Add(panel_main, proportion=1, flag=wx.GROW)
        panel_right.Sizer.Add(panel_detail, proportion=1, flag=wx.GROW)
        sizer.Add(list_db, border=10, proportion=6, flag=wx.ALL | wx.GROW)
        sizer.Add(panel_right, border=10, proportion=4, flag=wx.ALL | wx.GROW)
        for filename in conf.DBFiles:
            self.update_database_list(filename)


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


    def on_toggle_autoupdate_check(self, event):
        """Handler for toggling automatic update checking, changes conf."""
        conf.UpdateCheckAutomatic = event.IsChecked()
        conf.save()


    def on_list_db_key(self, event):
        """
        Handler for pressing a key in dblist, loads selected database on Enter
        and removes from list on Delete.
        """
        if self.list_db.GetFirstSelected() > 0 and not event.AltDown() \
        and event.KeyCode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.load_database_page(self.db_filename)
        elif event.KeyCode in [wx.WXK_DELETE] and self.db_filename:
            self.on_remove_database(None)
        event.Skip()


    def on_menu_homepage(self, event):
        """Handler for opening SQLiteMate webpage from menu,"""
        webbrowser.open(conf.HomeUrl)


    def on_about(self, event):
        """
        Handler for clicking "About SQLiteMate" menu, opens a small info frame.
        """
        text = step.Template(templates.ABOUT_HTML).expand()
        AboutDialog(self, text).ShowModal()


    def on_check_update(self, event):
        """
        Handler for checking for updates, starts a background process for
        checking for and downloading the newest version.
        """
        if not support.update_window:
            main.status("Checking for new version of %s.", conf.Title)
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
        main.status("")
        if check_result:
            version, url, changes = check_result
            MAX = 1000
            changes = changes[:MAX] + ".." if len(changes) > MAX else changes
            main.status_flash("New %s version %s available.",
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
        main.logstatus("Searching local computer for databases..")
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
                    main.log("Detected database %s.", f)
        if "count" in result:
            name = ("" if result["count"] else "additional ") + "database"
            main.logstatus_flash("Detected %s.", 
                                  util.plural(name, result["count"]))
        if result.get("done", False):
            self.button_detect.Enabled = True
            wx.Bell()


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
            data = collections.defaultdict(lambda: None)
            if os.path.exists(filename):
                data["size"] = os.path.getsize(filename)
                data["last_modified"] = datetime.datetime.fromtimestamp(
                                        os.path.getmtime(filename))
            data_old = self.db_filenames.get(filename)
            if not data_old or data_old["size"] != data["size"] \
            or data_old["last_modified"] != data["last_modified"]:
                if filename not in self.db_filenames:
                    self.db_filenames[filename] = data
                    idx = self.list_db.GetItemCount()
                    self.list_db.InsertImageStringItem(idx, filename, [1])
                    fgcolour = wx.NamedColour(conf.DBListForegroundColour)
                    bgcolour = wx.NamedColour(conf.DBListBackgroundColour)
                    self.list_db.SetItemBackgroundColour(idx, bgcolour)
                    self.list_db.SetItemTextColour(idx, fgcolour)
                    # self is not shown: form creation time, reselect last file
                    if not self.Shown and filename in conf.LastSelectedFiles:
                        self.list_db.Select(idx)
                        def scroll_to_selected():
                            if idx < self.list_db.GetCountPerPage(): return
                            lh = self.list_db.GetUserLineHeight()
                            dy = (idx - self.list_db.GetCountPerPage() / 2) * lh
                            self.list_db.ScrollList(0, dy)
                        wx.CallAfter(lambda: self and scroll_to_selected())
                    result = True

        self.button_missing.Shown = (self.list_db.GetItemCount() > 1)
        self.button_clear.Shown = (self.list_db.GetItemCount() > 1)
        if self.Shown:
            self.list_db.SetColumnWidth(0, self.list_db.Size.width - 5)
        return result


    def on_clear_databases(self, event):
        """Handler for clicking to clear the database list."""
        if (self.list_db.GetItemCount() > 1) and wx.OK == wx.MessageBox(
            "Are you sure you want to clear the list of all databases?",
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            while self.list_db.GetItemCount() > 1:
                self.list_db.DeleteItem(1)
            del conf.DBFiles[:]
            del conf.LastSelectedFiles[:]
            del conf.RecentFiles[:]
            conf.LastSearchResults.clear()
            while self.history_file.Count:
                self.history_file.RemoveFileFromHistory(0)
            self.db_filenames.clear()
            conf.save()
            self.update_database_list()


    def on_save_database_as(self, event):
        """Handler for clicking to save a copy of a database in the list."""
        original = self.db_filename
        if not os.path.exists(original):
            wx.MessageBox(
                "The file \"%s\" does not exist on this computer." % original,
                conf.Title, wx.OK | wx.ICON_INFORMATION
            )
            return

        dialog = wx.FileDialog(parent=self, message="Save a copy..",
            defaultDir=os.path.split(original)[0],
            defaultFile=os.path.basename(original),
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE | wx.RESIZE_BORDER
        )
        if wx.ID_OK == dialog.ShowModal():
            wx.YieldIfNeeded() # Allow UI to refresh
            newpath = dialog.GetPath()
            success = False
            try:
                shutil.copyfile(original, newpath)
                success = True
            except Exception as e:
                main.log("%r when trying to copy %s to %s.",
                         e, original, newpath)
                wx.MessageBox("Failed to copy \"%s\" to \"%s\"." %
                              (original, newpath), conf.Title,
                              wx.OK | wx.ICON_WARNING)
            if success:
                main.logstatus_flash("Saved a copy of %s as %s.",
                                     original, newpath)
                self.update_database_list(newpath)


    def on_remove_database(self, event):
        """Handler for clicking to remove an item from the database list."""
        filename = self.db_filename
        if filename and wx.OK == wx.MessageBox(
            "Remove %s from database list?" % filename,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            for lst in conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles:
                if filename in lst: lst.remove(filename)
            for dct in conf.LastSearchResults, self.db_filenames:
                dct.pop(filename, None)
            for i in range(self.list_db.GetItemCount()):
                if self.list_db.GetItemText(i) == filename:
                    self.list_db.DeleteItem(i)
                    break # break for i in range(self.list_db..
            # Remove from recent file history
            historyfiles = [(i, self.history_file.GetHistoryFile(i))
                            for i in range(self.history_file.Count)]
            for i in [i for i, f in historyfiles if f == filename]:
                self.history_file.RemoveFileFromHistory(i)
            self.db_filename = None
            self.list_db.Select(0)
            self.update_database_list()
            conf.save()


    def on_remove_missing(self, event):
        """Handler to remove nonexistent files from the database list."""
        selecteds = range(1, self.list_db.GetItemCount())
        filter_func = lambda i: not os.path.exists(self.list_db.GetItemText(i))
        selecteds = list(filter(filter_func, selecteds))
        filenames = list(map(self.list_db.GetItemText, selecteds))
        for i in range(len(selecteds)):
            # - i, as item count is getting smaller one by one
            selected = selecteds[i] - i
            filename = self.list_db.GetItemText(selected)
            for lst in conf.DBFiles, conf.RecentFiles, conf.LastSelectedFiles:
                if filename in lst: lst.remove(filename)
            for dct in conf.LastSearchResults, self.db_filenames:
                dct.pop(filename, None)
            self.list_db.DeleteItem(selected)
        self.update_database_list()

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

        for name in sorted(conf.OptionalFileDirectives):
            value, help = getattr(conf, name, None), get_field_doc(name)
            default = conf.OptionalFileDirectiveDefaults.get(name)
            if value is None and default is None:
                continue # continue for name
            kind = wx.Size if isinstance(value, (tuple, list)) else type(value)
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
        dialog = wx.FileDialog(
            parent=self, message="Open", defaultFile="",
            wildcard="SQLite database (*.db)|*.db|All files|*.*",
            style=wx.FD_FILE_MUST_EXIST | wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK == dialog.ShowModal():
            filename = dialog.GetPath()
            if filename:
                self.update_database_list(filename)
                self.load_database_page(filename)


    def on_new_database(self, event):
        """
        Handler for new database menu or button, displays a save file dialog,
        creates and loads the chosen database.
        """
        self.dialog_savefile.Filename = "database"
        self.dialog_savefile.Message = "Save new database as"
        self.dialog_savefile.Wildcard = "SQLite database (*.db)|*.db"
        self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
        if wx.ID_OK != self.dialog_savefile.ShowModal():
            return

        filename = self.dialog_savefile.GetPath()
        try:
            with open(filename, "w"): pass
        except Exception:
            main.log("Error creating %s.\n\n%s", filename,
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
            main.logstatus("Detecting databases under %s.", folder)
            wx.YieldIfNeeded()
            count = 0
            for filename in database.find_databases(folder):
                if filename not in self.db_filenames:
                    main.log("Detected database %s.", filename)
                    self.update_database_list(filename)
                    count += 1
            self.button_folder.Enabled = True
            main.logstatus_flash("Detected %s under %s.",
                util.plural("new database", count), folder)


    def on_open_current_database(self, event):
        """Handler for clicking to open selected files from database list."""
        if self.db_filename:
            self.load_database_page(self.db_filename)


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
            main.log("Error opening %s.\n\n%s", filename,
                     traceback.format_exc())
            return
        try:
            tables = db.get_tables()
            self.label_tables.Value = str(len(tables))
            if tables:
                s = ""
                for t in tables:
                    s += (", " if s else "") + t["name"]
                    if len(s) > 40:
                        s += ", .."
                        break # for t
                self.label_tables.Value += " (%s)" % s

            data = self.db_filenames.get(filename, {})
            data["tables"] = self.label_tables.Value
        except Exception as e:
            self.label_tables.Value = util.format_exc(e)
            self.label_tables.ForegroundColour = conf.LabelErrorColour
            main.log("Error loading data from %s.\n\n%s", filename,
                     traceback.format_exc())
        if db and not db.has_consumers():
            db.close()
            if filename in self.dbs:
                del self.dbs[filename]


    def on_select_list_db(self, event):
        """Handler for selecting an item in main list, updates info panel."""
        if event.GetIndex() > 0 \
        and event.GetText() != self.db_filename:
            filename = self.db_filename = event.GetText()
            path, tail = os.path.split(filename)
            self.label_db.Value = tail
            self.label_path.Value = path
            self.label_size.Value = self.label_modified.Value = ""
            self.label_tables.Value = ""
            self.label_tables.ForegroundColour = self.ForegroundColour
            self.label_size.ForegroundColour = self.ForegroundColour
            if not self.panel_db_detail.Shown:
                self.panel_db_main.Hide()
                self.panel_db_detail.Show()
                self.panel_db_detail.Parent.Layout()
            if os.path.exists(filename):
                sz = os.path.getsize(filename)
                dt = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
                self.label_size.Value = util.format_bytes(sz)
                self.label_modified.Value = dt.strftime("%Y-%m-%d %H:%M:%S")
                data = self.db_filenames[filename]
                if data["size"] == sz and data["last_modified"] == dt \
                and data.get("tables") is not None:
                    # File does not seem changed: use cached values
                    self.label_tables.Value = data["tables"]
                else:
                    wx.CallLater(10, self.update_database_stats, filename)
            else:
                self.label_size.Value = "File does not exist."
                self.label_size.ForegroundColour = conf.LabelErrorColour
        elif event.GetIndex() == 0 and not self.panel_db_main.Shown:
            self.db_filename = None
            self.panel_db_main.Show()
            self.panel_db_detail.Hide()
            self.panel_db_main.Parent.Layout()
        # Save last selected files in db lists, to reselect them on rerun
        del conf.LastSelectedFiles[:]
        selected = self.list_db.GetFirstSelected()
        while selected > 0:
            filename = self.list_db.GetItemText(selected)
            conf.LastSelectedFiles.append(filename)
            selected = self.list_db.GetNextSelected(selected)


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
            conf.DBFiles = [self.list_db.GetItemText(i)
                            for i in range(1, self.list_db.GetItemCount())]
            del conf.LastSelectedFiles[:]
            selected = self.list_db.GetFirstSelected()
            while selected > 0:
                filename = self.list_db.GetItemText(selected)
                conf.LastSelectedFiles.append(filename)
                selected = self.list_db.GetNextSelected(selected)
            if not conf.WindowIconized:
                conf.WindowPosition = self.Position[:]
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
        main.log("Closed database tab for %s." % page.db)
        conf.save()

        # Close databases, if not used in any other page
        page.db.unregister_consumer(page)
        if not page.db.has_consumers():
            if page.db.filename in self.dbs:
                del self.dbs[page.db.filename]
            page.db.close()
            main.log("Closed database %s." % page.db)
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
                    main.log("Opened %s (%s).", db, util.format_bytes(
                             db.filesize))
                    main.status_flash("Reading database file %s.", db)
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
                main.status_flash("Opening database file %s." % db)
                tab_title = self.get_unique_tab_title(db.filename)
                page = DatabasePage(self.notebook, tab_title, db, self.memoryfs)
                self.db_pages[page] = db
                self.UpdateAccelerators()
                conf.save()
                self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS,
                          self.on_clear_searchall, page.edit_searchall)
        if page:
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
        self.memoryfs = memoryfs
        parent_notebook.InsertPage(1, self, title)
        busy = controls.BusyPanel(self, "Loading \"%s\"." % db.filename)
        self.counter = lambda x={"c": 0}: x.update(c=1+x["c"]) or x["c"]

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
        idx1 = il.Add(images.PageTables.Bitmap)
        idx2 = il.Add(images.PageSQL.Bitmap)
        idx3 = il.Add(images.PageSearch.Bitmap)
        idx4 = il.Add(images.PageInfo.Bitmap)
        notebook.AssignImageList(il)

        self.create_page_tables(notebook)
        self.create_page_sql(notebook)
        self.create_page_search(notebook)
        self.create_page_info(notebook)

        notebook.SetPageImage(0, idx1)
        notebook.SetPageImage(1, idx2)
        notebook.SetPageImage(2, idx3)
        notebook.SetPageImage(3, idx4)

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
        self.notebook.SetSelection(self.pageorder[self.page_tables])
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
        html.SetTabAreaColour(tb.BackgroundColour)
        html.Font.PixelSize = (0, 8)

        label_html.BackgroundColour = tb.BackgroundColour
        
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
        notebook.AddPage(page, "Tables")
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
        tree.AddColumn("Table")
        tree.AddColumn("Info")
        tree.AddRoot("Loading data..")
        tree.SetMainColumn(0)
        tree.SetColumnAlignment(1, wx.ALIGN_RIGHT)
        self.Bind(wx.EVT_BUTTON, self.on_refresh_tables, button_refresh)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_change_tree_tables, tree)

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
        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK, self.on_sort_grid_column)
        grid.GridWindow.Bind(wx.EVT_MOTION, self.on_mouse_over_grid)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK,
                  self.on_filter_grid_column)
        grid.Bind(wx.grid.EVT_GRID_CELL_CHANGE, self.on_change_table)
        label_help = wx.StaticText(panel2, label="Double-click on column "
                                   "header to sort, right click to filter.")
        label_help.ForegroundColour = "grey"
        sizer2.Add(sizer_tb, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)
        sizer2.Add(grid, border=5, proportion=2,
                   flag=wx.GROW | wx.LEFT | wx.RIGHT)
        sizer2.Add(label_help, border=5, flag=wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        splitter.SplitVertically(panel1, panel2, 270)


    def create_page_sql(self, notebook):
        """Creates a page for executing arbitrary SQL."""
        page = self.page_sql = wx.Panel(parent=notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "SQL window")
        sizer = page.Sizer = wx.BoxSizer(wx.VERTICAL)
        splitter = self.splitter_sql = \
            wx.SplitterWindow(parent=page, style=wx.BORDER_NONE)
        splitter.SetMinimumPaneSize(100)

        panel1 = self.panel_sql1 = wx.Panel(parent=splitter)
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        label_stc = wx.StaticText(parent=panel1, label="SQ&L:")
        stc = self.stc_sql = controls.SQLiteTextCtrl(parent=panel1,
            style=wx.BORDER_STATIC | wx.TE_PROCESS_TAB | wx.TE_PROCESS_ENTER)
        stc.Bind(wx.EVT_KEY_DOWN, self.on_keydown_sql)
        stc.SetText(conf.SQLWindowTexts.get(self.db.filename, ""))
        stc.EmptyUndoBuffer() # So that undo does not clear the STC
        sizer1.Add(label_stc, border=5, flag=wx.ALL)
        sizer1.Add(stc, border=5, proportion=1, flag=wx.GROW | wx.LEFT)

        panel2 = self.panel_sql2 = wx.Panel(parent=splitter)
        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)
        label_help = wx.StaticText(panel2, label=
            "Alt-Enter runs the query contained in currently selected text or "
            "on the current line. Ctrl-Space shows autocompletion list.")
        label_help.ForegroundColour = "grey"
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
        grid.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK,
                  self.on_sort_grid_column)
        grid.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK,
                  self.on_filter_grid_column)
        grid.Bind(wx.EVT_SCROLLWIN, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_SCROLL_CHANGED, self.on_scroll_grid_sql)
        grid.Bind(wx.EVT_KEY_DOWN, self.on_scroll_grid_sql)
        grid.GridWindow.Bind(wx.EVT_MOTION, self.on_mouse_over_grid)
        label_help_grid = wx.StaticText(panel2, label="Double-click on column "
                                        "header to sort, right click to filter.")
        label_help_grid.ForegroundColour = "grey"

        sizer2.Add(label_help, border=5, flag=wx.GROW | wx.LEFT | wx.BOTTOM)
        sizer2.Add(sizer_buttons, border=5, flag=wx.GROW | wx.ALL)
        sizer2.Add(grid, border=5, proportion=2,
                   flag=wx.GROW | wx.LEFT | wx.RIGHT)
        sizer2.Add(label_help_grid, border=5, flag=wx.GROW | wx.LEFT | wx.TOP)

        sizer.Add(splitter, proportion=1, flag=wx.GROW)
        sash_pos = self.Size[1] / 3
        splitter.SplitHorizontally(panel1, panel2, sashPosition=sash_pos)


    def create_page_info(self, notebook):
        """Creates a page for seeing general database information."""
        page = self.page_info = wx.lib.scrolledpanel.ScrolledPanel(notebook)
        self.pageorder[page] = len(self.pageorder)
        notebook.AddPage(page, "Information")
        sizer = page.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        panel1 = self.panel_accountinfo = wx.Panel(parent=page)
        panel2 = wx.Panel(parent=page)
        panel1.BackgroundColour = panel2.BackgroundColour = conf.BgColour
        sizer1 = panel1.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_account = wx.BoxSizer(wx.HORIZONTAL)
        label_account = wx.StaticText(parent=panel1,
                                      label="Main account information")
        label_account.Font = wx.Font(10, wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        sizer1.Add(label_account, border=5, flag=wx.ALL)

        sizer_accountinfo = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        self.sizer_accountinfo = sizer_accountinfo
        sizer_accountinfo.AddGrowableCol(1, 1)

        sizer_account.Add(sizer_accountinfo, proportion=1, flag=wx.GROW)
        sizer1.Add(sizer_account, border=20, proportion=1,
                   flag=wx.TOP | wx.GROW)

        sizer2 = panel2.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_file = wx.FlexGridSizer(cols=2, vgap=3, hgap=10)
        label_file = wx.StaticText(parent=panel2, label="Database information")
        label_file.Font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                  wx.FONTWEIGHT_BOLD, face=self.Font.FaceName)
        sizer2.Add(label_file, border=5, flag=wx.ALL)

        names = ["edit_info_path", "edit_info_size", "edit_info_modified",
                 "edit_info_sha1", "edit_info_md5", ]
        labels = ["Full path", "File size", "Last modified",
                  "SHA-1 checksum", "MD5 checksum",  ]
        for name, label in zip(names, labels):
            if not name and not label:
                sizer_file.AddSpacer(20), sizer_file.AddSpacer(20)
                continue # continue for i, (name, label) in enumerate(..
            labeltext = wx.StaticText(parent=panel2, label="%s:" % label)
            labeltext.ForegroundColour = wx.Colour(102, 102, 102)
            valuetext = wx.TextCtrl(parent=panel2, value="Analyzing..",
                style=wx.NO_BORDER | wx.TE_MULTILINE | wx.TE_RICH)
            valuetext.MinSize = (-1, 35)
            valuetext.BackgroundColour = panel2.BackgroundColour
            valuetext.SetEditable(False)
            sizer_file.Add(labeltext, border=5, flag=wx.LEFT)
            sizer_file.Add(valuetext, proportion=1, flag=wx.GROW)
            setattr(self, name, valuetext)
        self.edit_info_path.Value = self.db.filename

        button_vacuum = self.button_vacuum = \
            wx.Button(parent=panel2, label="Vacuum")
        button_check = self.button_check_integrity = \
            wx.Button(parent=panel2, label="Check for corruption")
        button_refresh = self.button_refresh_fileinfo = \
            wx.Button(parent=panel2, label="Refresh")
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

        sizer_file.AddGrowableCol(1, 1)
        sizer2.Add(sizer_file, border=20, proportion=1, flag=wx.TOP | wx.GROW)
        sizer2.Add(sizer_buttons, proportion=2, flag=wx.GROW)

        sizer.Add(panel1, proportion=1, border=5,
                  flag=wx.LEFT  | wx.TOP | wx.BOTTOM | wx.GROW)
        sizer.Add(panel2, proportion=1, border=5,
                  flag=wx.RIGHT | wx.TOP | wx.BOTTOM | wx.GROW)
        page.SetupScrolling()


    def on_check_integrity(self, event):
        """
        Handler for checking database integrity, offers to save a fixed
        database if corruption detected.
        """
        msg = "Checking integrity of %s." % self.db.filename
        main.logstatus_flash(msg)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        try:
            errors = self.db.check_integrity()
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        main.status_flash("")
        if not errors:
            wx.MessageBox("No database errors detected.",
                          conf.Title, wx.ICON_INFORMATION)
        else:
            err = "\n- ".join(errors)
            main.log("Errors found in %s: %s", self.db, err)
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
                        main.status_flash("Recovering data from %s to %s.",
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
                        main.status_flash("Recovery to %s complete." % newfile)
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
        main.logstatus_flash(msg)
        busy = controls.BusyPanel(self, msg)
        wx.YieldIfNeeded()
        errors = []
        try:
            self.db.execute("VACUUM")
        except Exception as e:
            errors = e.args[:]
        busy.Close()
        main.status_flash("")
        if errors:
            err = "\n- ".join(errors)
            main.log("Error running vacuum on %s: %s", self.db, err)
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
                table = next((t for t in self.db.get_tables()
                              if t["name"].lower() == table_name), None)
                item = self.tree_tables.GetNext(self.tree_tables.RootItem)
                while table and item and item.IsOk():
                    table2 = self.tree_tables.GetItemPyData(item)
                    if table2 and table2.lower() == table["name"].lower():
                        tableitem = item
                        break # break while table and item and itek.IsOk()
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
                    messageBox(e, conf.Title, wx.OK | wx.ICON_INFORMATION)
            elif table_name:
                tableitem = None
                table_name = table_name.lower()
                table = next((t for t in self.db.get_tables()
                              if t["name"].lower() == table_name), None)
                item = self.tree_tables.GetNext(self.tree_tables.RootItem)
                while table and item and item.IsOk():
                    table2 = self.tree_tables.GetItemPyData(item)
                    if table2 and table2.lower() == table["name"].lower():
                        tableitem = item
                        break # while table
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
                        table["columns"] = self.db.get_table_columns(table_name)
                        id_fields = [c["name"] for c in table["columns"]
                                     if c.get("pk_id")]
                        if not id_fields: # No primary key fields: take all
                            id_fields = [c["name"] for c in table["columns"]]
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
            main.status_flash("Finished searching for \"%s\" in %s.",
                result["search"]["text"], self.db.filename
            )
            self.tb_search_settings.SetToolNormalBitmap(
                wx.ID_STOP, images.ToolbarStopped.Bitmap)
            if search_id in self.workers_search:
                self.workers_search[search_id].stop()
                del self.workers_search[search_id]
        if "error" in result:
            main.log("Error searching %s:\n\n%s", self.db, result["error"])
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
            main.status_flash("Searching for \"%s\" in %s.",
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
        if grid_source.Table:
            if grid_source is self.grid_table:
                table = self.db.tables[grid_source.Table.table.lower()]["name"]
                title = "Table - \"%s\"" % table
                self.dialog_savefile.Wildcard = export.TABLE_WILDCARD
            else:
                title = "SQL query"
                self.dialog_savefile.Wildcard = export.QUERY_WILDCARD
                grid_source.Table.SeekAhead(True)
            self.dialog_savefile.Filename = util.safe_filename(title)
            self.dialog_savefile.Message = "Save table as"
            self.dialog_savefile.WindowStyle |= wx.FD_OVERWRITE_PROMPT
            if wx.ID_OK == self.dialog_savefile.ShowModal():
                filename = self.dialog_savefile.GetPath()
                exts = export.TABLE_EXTS if grid_source is self.grid_table \
                       else export.QUERY_EXTS
                extname = exts[self.dialog_savefile.FilterIndex]
                if not filename.lower().endswith(".%s" % extname):
                    filename += ".%s" % extname
                busy = controls.BusyPanel(self, "Exporting \"%s\"." % filename)
                main.status("Exporting \"%s\".", filename)
                try:
                    export.export_grid(grid_source, filename, title,
                                       self.db, sql, table)
                    main.logstatus_flash("Exported %s.", filename)
                    util.start_file(filename)
                except Exception:
                    msg = "Error saving %s:\n\n%s" % \
                          (filename, traceback.format_exc())
                    main.logstatus_flash(msg)
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
                                   grid.Table.table, self.db)
                        msg, msgfull = template % e, template % traceback.format_exc()
                        main.status_flash(msg), main.log(msgfull)
                        wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                        return
                else: grid.Table.UndoChanges()
                self.on_change_table(None)

            i = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while i:
                self.tree_tables.SetItemBold(i, False)
                i = self.tree_tables.GetNextSibling(i)

            self.db_grids.pop(grid.Table.table, None)

        grid.SetTable(None)
        grid.Parent.Refresh()

        if is_table:
            self.label_table.Label = ""
            self.tb_grid.EnableTool(wx.ID_ADD, False)
            self.tb_grid.EnableTool(wx.ID_DELETE, False)
            self.button_export_table.Enabled = False
            self.button_reset_grid_table.Enabled = False
            self.button_close_grid_table.Enabled = False
        else:
            self.button_export_sql.Enabled = False
            self.button_reset_grid_sql.Enabled = False
            self.button_close_grid_sql.Enabled = False


    def on_keydown_sql(self, event):
        """
        Handler for pressing a key in SQL editor, listens for Alt-Enter and
        executes the currently selected line, or currently active line.
        """
        stc = event.GetEventObject()
        if event.AltDown() and wx.WXK_RETURN == event.KeyCode:
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
        sql = self.stc_sql.SelectedText.strip() or self.stc_sql.Text.strip()
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
                main.log("Executing SQL script \"%s\".", sql)
                self.db.connection.executescript(sql)
                self.grid_sql.SetTable(None)
                self.grid_sql.CreateGrid(1, 1)
                self.grid_sql.SetColLabelValue(0, "Affected rows")
                self.grid_sql.SetCellValue(0, 0, "-1")
                self.button_reset_grid_sql.Enabled = False
                self.button_export_sql.Enabled = False
                size = self.grid_sql.Size
                self.grid_sql.Fit()
                # Jiggle size by 1 pixel to refresh scrollbars
                self.grid_sql.Size = size[0], size[1]-1
                self.grid_sql.Size = size[0], size[1]
        except Exception as e:
            msg = util.format_exc(e)
            main.logstatus_flash(msg)
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
            main.logstatus_flash("Executed SQL \"%s\" (%s).", sql, self.db)
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
            main.logstatus_flash(msg)
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
                           grid.table, self.db)
                msg, msgfull = template % e, template % traceback.format_exc()
                main.status_flash(msg), main.log(msgfull)
                wx.MessageBox(msg, conf.Title, wx.OK | wx.ICON_WARNING)
                break # break for grid
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
            if list_table:
                if list_table.lower() == grid_data.table.lower():
                    self.tree_tables.SetItemTextColour(item, colour)
                    break # break while item and item.IsOk()
            item = self.tree_tables.GetNextSibling(item)

        # Mark database as changed/pristine in the parent notebook tabs
        for i in range(self.parent_notebook.GetPageCount()):
            if self.parent_notebook.GetPage(i) == self:
                suffix = "*" if self.get_unsaved_grids() else ""
                title = self.title + suffix
                if self.parent_notebook.GetPageText(i) != title:
                    self.parent_notebook.SetPageText(i, title)
                break # break for i in range(self.parent_notebook..


    def on_commit_table(self, event):
        """Handler for clicking to commit the changed database table."""
        info = self.grid_table.Table.GetChangedInfo()
        if wx.OK == wx.MessageBox(
            "Are you sure you want to commit these changes (%s)?" %
            info, conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
        ):
            main.log("Committing %s in table %s (%s).", info,
                     self.grid_table.Table.table, self.db)
            self.grid_table.Table.SaveChanges()
            self.on_change_table(None)
            # Refresh tables list with updated row counts
            tablemap = dict((t["name"], t) for t in self.db.get_tables(True))
            item = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while item and item.IsOk():
                table = self.tree_tables.GetItemPyData(item)
                if table:
                    self.tree_tables.SetItemText(item, "%d row%s" % (
                        tablemap[table]["rows"],
                        "s" if tablemap[table]["rows"] != 1 else " "
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
        table = None
        item = event.GetItem()
        if item and item.IsOk():
            table = self.tree_tables.GetItemPyData(item)
            lower = table.lower() if table else None
        if table and \
        (not self.grid_table.Table
         or self.grid_table.Table.table.lower() != lower):
            i = self.tree_tables.GetNext(self.tree_tables.RootItem)
            while i:
                text = self.tree_tables.GetItemText(i).lower()
                self.tree_tables.SetItemBold(i, text == lower)
                i = self.tree_tables.GetNextSibling(i)
            main.log("Loading table %s (%s).", table, self.db)
            busy = controls.BusyPanel(self, "Loading table \"%s\"." % table)
            try:
                grid_data = self.db_grids.get(lower)
                if not grid_data:
                    grid_data = SqliteGridBase(self.db, table=table)
                    self.db_grids[lower] = grid_data
                self.label_table.Label = "Table \"%s\":" % table
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
                busy.Close()
            except Exception:
                busy.Close()
                errormsg = "Could not load table %s.\n\n%s" % \
                           (table, traceback.format_exc())
                main.logstatus_flash(errormsg)
                wx.MessageBox(errormsg, conf.Title, wx.OK | wx.ICON_WARNING)


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
                dialog = wx.TextEntryDialog(self,
                    "Filter column \"%s\" by:" % grid_data.columns[col]["name"],
                    "Filter", defaultValue=current_filter,
                    style=wx.OK | wx.CANCEL)
                if wx.ID_OK == dialog.ShowModal():
                    new_filter = dialog.GetValue()
                    if len(new_filter):
                        busy = controls.BusyPanel(self.page_tables,
                            "Filtering column \"%s\" by \"%s\"." %
                            (grid_data.columns[col]["name"], new_filter))
                        grid_data.AddFilter(col, new_filter)
                        busy.Close()
                    else:
                        grid_data.RemoveFilter(col)
            grid.ContainingSizer.Layout() # React to grid size change


    def load_data(self):
        """Loads data from our Database."""
        self.label_title.Label = "Database \"%s\":" % self.db

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
            tables = self.db.get_tables()
            # Fill table tree with information on row counts and columns
            self.tree_tables.DeleteAllItems()
            root = self.tree_tables.AddRoot("SQLITE")
            child = None
            for table in tables:
                child = self.tree_tables.AppendItem(root, table["name"])
                self.tree_tables.SetItemText(child, "%d row%s" % (
                    table["rows"], "s" if table["rows"] != 1 else " "
                ), 1)
                self.tree_tables.SetItemPyData(child, table["name"])

                for col in self.db.get_table_columns(table["name"]):
                    subchild = self.tree_tables.AppendItem(child, col["name"])
                    self.tree_tables.SetItemText(subchild, col["type"], 1)
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
            for t in tables:
                coldata = self.db.get_table_columns(t["name"])
                fields = [c["name"] for c in coldata]
                self.stc_sql.AutoCompAddSubWords(t["name"], fields)
        except Exception:
            if self:
                errormsg = "Error loading table data from %s.\n\n%s" % \
                           (self.db, traceback.format_exc())
                main.log(errormsg)


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
        self.rowid_name = "ROWID%s" % int(time.time()) # Avoid collisions
        self.iterator_index = -1
        self.sort_ascending = False
        self.sort_column = None # Index of column currently sorted by
        self.filters = {} # {col: value, }
        self.attrs = {} # {"new": wx.grid.GridCellAttr, }

        if not self.is_query:
            self.sql = "SELECT rowid AS %s, * FROM %s" % (self.rowid_name, table)
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
                                  % table))["rows"]


    def GetColLabelValue(self, col):
        label = self.columns[col]["name"]
        if col == self.sort_column:
            label += u" ↑" if self.sort_ascending else u" ↓"
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
                if not self.is_query:
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
        """Returns a separate iterator producing all grid rows."""
        return self.db.execute(self.sql)


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
            if not row["__deleted__"] and self._is_row_unfiltered(row):
                self.rows_current.append(row)
        if self.sort_column is not None:
            pass#if self.View: self.View.Fit()
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
        self.rows_current.sort(cmp=compare, reverse=self.sort_ascending)
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
                    else: # For non-integers, insert returns ROWID
                        self.rowids[idx] = insert_id
                row["__new__"] = False
                self.idx_new.remove(idx)
            # Deleted all newly deleted rows
            for idx, row in self.rows_deleted.copy().items():
                self.db.delete_row(self.table, row, self.rowids.get(idx))
                del self.rows_deleted[idx]
                del self.rows_all[idx]
                self.idx_all.remove(idx)
        except Exception as e:
            main.logstatus("Error saving changes in %s.\n\n%s",
                           self.table, traceback.format_exc())
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
            if self._is_row_unfiltered(row):
                self.rows_current.append(row)
            self.row_count += 1
        self.NotifyViewChange(rows_before)
        if self.View: self.View.Refresh()


    def _is_row_unfiltered(self, rowdata):
        """
        Returns whether the row is not filtered out by the current filtering
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
        return is_unfiltered



class AboutDialog(wx.Dialog):
 
    def __init__(self, parent, content):
        wx.Dialog.__init__(self, parent, title="About %s" % conf.Title,
                           style=wx.CAPTION | wx.CLOSE_BOX)
        html = self.html = wx.html.HtmlWindow(self)
        button_update = wx.Button(self, label="Check for &updates")

        html.SetPage(content)
        html.BackgroundColour = conf.BgColour
        html.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                  lambda e: webbrowser.open(e.GetLinkInfo().Href))
        button_update.Bind(wx.EVT_BUTTON, parent.on_check_update)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(html, proportion=1, flag=wx.GROW)
        sizer_buttons = self.CreateButtonSizer(wx.OK)
        sizer_buttons.Insert(0, button_update, border=50, flag=wx.RIGHT)
        self.Sizer.Add(sizer_buttons, border=8, flag=wx.ALIGN_CENTER | wx.ALL)
        self.Layout()
        self.Size = (self.Size[0], html.VirtualSize[1] + 60)
        self.CenterOnParent()



def messageBox(message, title, style):
    """
    Shows a non-native message box, with no bell sound for any style, returning
    the message box result code."""
    dlg = wx.lib.agw.genericmessagedialog.GenericMessageDialog(
        None, message, title, style
    )
    result = dlg.ShowModal()
    dlg.Destroy()
    return result
