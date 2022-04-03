# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    02.04.2022
------------------------------------------------------------------------------
"""
try: from ConfigParser import RawConfigParser                 # Py2
except ImportError: from configparser import RawConfigParser  # Py3
import datetime
import json
import os
import platform
import sys

import appdirs
import six
import wx


"""Program title, version number and version date."""
Title = "SQLitely"
Version = "2.0"
VersionDate = "02.04.2022"

if getattr(sys, "frozen", False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable)
    ApplicationFile = os.path.realpath(sys.executable)
    ResourceDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "media")
    BinDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "bin")
    EtcDirectory = ApplicationDirectory
else:
    ApplicationDirectory = os.path.realpath(os.path.dirname(__file__))
    ApplicationFile = os.path.join(ApplicationDirectory, "main.py")
    ResourceDirectory = os.path.join(ApplicationDirectory, "media")
    BinDirectory = os.path.join(ApplicationDirectory, "bin")
    EtcDirectory = os.path.join(ApplicationDirectory, "etc")

"""Name of file where FileDirectives are kept."""
ConfigFile = "%s.ini" % os.path.join(EtcDirectory, Title.lower())

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = ["AllowMultipleInstances", "ConsoleHistoryCommands", "DBFiles",
    "DBSort", "LastActivePages", "LastExportType", "LastSearchResults",
    "LastSelectedFiles", "LastUpdateCheck", "ParseCache", "RecentFiles",
    "SchemaDiagrams", "SearchHistory", "SearchInMeta", "SearchInData",
    "SearchUseNewTab", "SearchCaseSensitive", "SQLWindowTexts", "TrayIconEnabled",
    "UpdateCheckAutomatic", "WindowMaximized", "WindowMinimizedToTray",
    "WindowPosition", "WindowSize",
]
"""List of user-modifiable attributes, saved if changed from default."""
OptionalFileDirectives = [
    "DBExtensions", "ExportDbTemplate", "LogSQL", "MinWindowSize",
    "MaxConsoleHistory", "MaxDBSizeForFullCount", "MaxTableRowIDForFullCount",
    "MaxHistoryInitialMessages", "MaxImportFilesizeForCount", "MaxRecentFiles",
    "MaxSearchHistory", "MaxSearchResults", "MaxParseCache", "PopupUnexpectedErrors",
    "RunChecksums", "RunStatistics", "SchemaDiagramEnabled", "SchemaLineNumbered",
    "SchemaWordWrap", "SearchResultsChunk", "SeekLength", "SeekLeapLength",
    "StatisticsPlotWidth", "StatusFlashLength", "UpdateCheckInterval",
]
Defaults = {}

"""---------------------------- FileDirectives: ----------------------------"""

"""All detected/added databases."""
DBFiles = []

"""Database filename extensions, as ('.extension', )."""
DBExtensions = [".db", ".db3", ".s3db", ".sl3", ".sqlite", ".sqlite3", ".sqlitedb"]

"""Database list sort state, [col, ascending]."""
DBSort = []

"""Whether program can have multiple instances running, or reuses one instance."""
AllowMultipleInstances = False

"""
Port for inter-process communication, receiving data from other
launched instances if not AllowMultipleInstances.
"""
IPCPort = 59987

"""Identifier for inter-process communication."""
IPCName = six.moves.urllib.parse.quote_plus(
    "%s-%s" % (wx.GetUserId(), ApplicationFile)
).encode("latin1", "replace")

"""History of commands entered in console."""
ConsoleHistoryCommands = []

"""Index of last active page in database tab, {db path: index}."""
LastActivePages = {}

"""Last export format, for uniform setting across components."""
LastExportType = "html"

"""HTMLs of last search result, {db path: {"content", "info", "title"}}."""
LastSearchResults = {}

"""Files selected in the database lists on last run."""
LastSelectedFiles = []

"""Maximum database file size for doing full COUNT(*) instead of estimating from MAX(ROWID)."""
MaxDBSizeForFullCount = 500000000

"""Maximum table ROWID for doing full COUNT(*) if database size over MaxDBSizeForFullCount."""
MaxTableRowIDForFullCount = 1000

"""Maximum import file size to do full row count for."""
MaxImportFilesizeForCount = 10 * 1e6

"""Number of rows to seek ahead on data grids, when scrolling to end of retrieved rows."""
SeekLength = 100

"""Number of rows to seek ahead on data grids, when scrolling freely or jumping to data grid bottom."""
SeekLeapLength = 10000

"""Cached parse results, as {CREATE SQL: {meta}}."""
ParseCache = {}

"""Contents of Recent Files menu."""
RecentFiles = []

"""Run checksum calculations automatically (may take a while for large databases)."""
RunChecksums = True

"""Run statistics analysis automatically (may take a while for large databases)."""
RunStatistics = True

"""Database schema diagram settings, as {path: {..}}."""
SchemaDiagrams = {}

"""Whether database schema diagram is enabled."""
SchemaDiagramEnabled = True

"""Show line numbers in SQL controls, like database full schema panel."""
SchemaLineNumbered = False

"""Word-wrap lines in SQL controls, like database full schema panel."""
SchemaWordWrap = True

"""
Texts entered in global search, used for drop down auto-complete.
Last value can be an empty string: search box had no text.
"""
SearchHistory = []

"""Whether to create a new tab for each search or reuse current."""
SearchUseNewTab = True

"""Whether to do case-sensitive search."""
SearchCaseSensitive = False

"""Whether to search in database CREATE SQL."""
SearchInMeta = False

"""Whether to search in all columns of all tables and views."""
SearchInData = True

"""Texts in SQL window, loaded on reopening a database {filename: [(name, text), ], }."""
SQLWindowTexts = {}

"""Whether the program tray icon is used."""
TrayIconEnabled = True

"""Whether the program checks for updates every UpdateCheckInterval."""
UpdateCheckAutomatic = True

"""Whether the program has been minimized and hidden to tray."""
WindowMinimizedToTray = False

"""Whether the program window has been maximized."""
WindowMaximized = False

"""Main window position, (x, y)."""
WindowPosition = None

"""Main window size in pixels, as [w, h]."""
WindowSize = (1080, 720)

"""---------------------------- /FileDirectives ----------------------------"""

"""Currently opened databases, as {filename: db}."""
DBsOpen = {}

"""Path to SQLite analyzer tool."""
DBAnalyzer = os.path.join(BinDirectory, "sqlite3_analyzer" + (
    ".exe"   if "win32"  == sys.platform else
    "_osx"   if "darwin" == sys.platform else
    "_linux" if "64" not in platform.architecture()[0] else "_linux_x64"
))


"""Whether logging to log window is enabled."""
LogEnabled = True

"""Whether to log all SQL statements to log window."""
LogSQL = False

"""Whether to pop up message dialogs for unhandled errors."""
PopupUnexpectedErrors = True

"""Number of unhandled errors encountered during current runtime."""
UnexpectedErrorCount = 0

"""URLs for download list, changelog, submitting feedback and homepage."""
DownloadURL  = "https://erki.lap.ee/downloads/SQLitely/"
ChangelogURL = "https://suurjaak.github.io/SQLitely/changelog.html"
HomeUrl      = "https://suurjaak.github.io/SQLitely"

"""Minimum allowed size for the main window, as (width, height)."""
MinWindowSize = (600, 400)

"""Console window size in pixels, (width, height)."""
ConsoleSize = (800, 300)

"""Maximum number of console history commands to store."""
MaxConsoleHistory = 1000

"""Maximum number of cached SQL parse results."""
MaxParseCache = 500

"""Maximum number of search texts to store."""
MaxSearchHistory = 500

"""Days between automatic update checks."""
UpdateCheckInterval = 7

"""Date string of last time updates were checked."""
LastUpdateCheck = None

"""Maximum length of a tab title, overflow will be cut on the left."""
MaxTabTitleLength = 60

"""Maximum number of results to show in search results."""
MaxSearchResults = 500

"""Number of search results to yield in one chunk from search thread."""
SearchResultsChunk = 50

"""Name of font used in HTML content."""
HtmlFontName = "Tahoma"

"""Window background colour."""
BgColour = "#FFFFFF"

"""Text colour."""
FgColour = "#000000"

"""Main screen background colour."""
MainBgColour = "#FFFFFF"

"""Widget (button etc) background colour."""
WidgetColour = "#D4D0C8"

"""Foreground colour for gauges."""
GaugeColour = "#008000"

"""Disabled text colour."""
DisabledColour = "#808080"

"""Table border colour in search help."""
HelpBorderColour = "#D4D0C8"

"""Code element text colour in search help."""
HelpCodeColour = "#006600"

"""Colour for clickable links."""
LinkColour = "#0000FF"

"""Colour for links in export."""
ExportLinkColour = "#3399FF"

"""Background colour of exported HTML."""
ExportBackgroundColour = "#8CBEFF"

"""Colours for main screen database list."""
DBListBackgroundColour = "#ECF4FC"
DBListForegroundColour = "#000000"

"""Colour used for titles."""
TitleColour = "#3399FF"

"""Descriptive text shown in history searchbox."""
SearchDescription = "Search for.."

"""Foreground colour for error labels."""
LabelErrorColour = "#CC3232"

"""Colour set to table/list rows that have been changed."""
GridRowChangedColour = "#FFCCCC"

"""Colour set to table/list rows that have been inserted."""
GridRowInsertedColour = "#B9EAFF"

"""Colour set to table/list cells that have been changed."""
GridCellChangedColour = "#FFA5A5"

"""Width of the database statistics plots, in pixels."""
StatisticsPlotWidth = 200

"""Colour for tables plot in database statistics."""
PlotTableColour = "#3399FF"

"""Colour for indexes plot in database statistics."""
PlotIndexColour = "#1DAB48"

"""Background colour for plots in database statistics."""
PlotBgColour = "#DDDDDD"

"""Duration of status messages on StatusBar, in seconds."""
StatusFlashLength = 20

"""How many items in the Recent Files menu."""
MaxRecentFiles = 20

"""Font files used for measuring text extent in export."""
FontXlsxFile     = os.path.join(ResourceDirectory, "Carlito.ttf")
FontXlsxBoldFile = os.path.join(ResourceDirectory, "CarlitoBold.ttf")


def load():
    """Loads FileDirectives from ConfigFile into this module's attributes."""
    global Defaults, ConfigFile

    configpaths = [ConfigFile]
    if not Defaults:
        # Instantiate OS- and user-specific path
        try:
            p = appdirs.user_config_dir(Title, appauthor=False)
            # Try user-specific path first, then path under application folder
            configpaths.insert(0, os.path.join(p, "%s.ini" % Title.lower()))
        except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    VARTYPES = six.string_types + six.integer_types + (bool, list, tuple, dict, type(None))
    Defaults = {k: v for k, v in vars(module).items() if not k.startswith("_")
                and isinstance(v, VARTYPES)}

    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        for path in configpaths[::-1]:
            if os.path.isfile(path) and parser.read(path):
                break # for path

        def parse_value(name):
            try: # parser.get can throw an error if value not found
                value_raw = parser.get(section, name)
            except Exception:
                return None, False
            try: # Try to interpret as JSON, fall back on raw string
                value = json.loads(value_raw)
            except ValueError:
                value = value_raw
            return value, True

        for name in FileDirectives + OptionalFileDirectives:
            [setattr(module, name, v) for v, s in [parse_value(name)] if s]
    except Exception:
        pass # Fail silently


def save():
    """Saves FileDirectives into ConfigFile."""
    configpaths = [ConfigFile]
    try:
        p = appdirs.user_config_dir(Title, appauthor=False)
        userpath = os.path.join(p, "%s.ini" % Title.lower())
        # Pick only userpath if exists, else try application folder first
        if os.path.isfile(userpath): configpaths = [userpath]
        else: configpaths.append(userpath)
    except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    parser.add_section(section)
    try:
        for path in configpaths:
            try: os.makedirs(os.path.split(path)[0])
            except Exception: pass
            try: f = open(path, "w")
            except Exception: continue # for path
            else: break # for path

        f.write("# %s configuration written on %s.\n" %
                (Title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        for name in FileDirectives:
            try: parser.set(section, name, json.dumps(getattr(module, name)))
            except Exception: pass
        for name in OptionalFileDirectives:
            try:
                value = getattr(module, name, None)
                if Defaults.get(name) != value:
                    parser.set(section, name, json.dumps(value))
            except Exception: pass
        parser.write(f)
        f.close()
    except Exception:
        pass # Fail silently
