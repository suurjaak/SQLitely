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
@modified    03.02.2025
------------------------------------------------------------------------------
"""
try: from configparser import RawConfigParser                 # Py3
except ImportError: from ConfigParser import RawConfigParser  # Py2
import copy
import datetime
import json
import os
import platform
import sys

try: import appdirs
except ImportError: appdirs = None
try: from urllib.parse import quote_plus           # Py3
except ImportError: from urllib import quote_plus  # Py2
try: import wx
except ImportError: wx = None


"""Program title, version number and version date."""
Title = "SQLitely"
Version = "2.4"
VersionDate = "03.02.2025"

Frozen, Snapped = getattr(sys, "frozen", False), (sys.executable or "").startswith("/snap/")
if Frozen: # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable)
    ApplicationFile = os.path.realpath(sys.executable)
    ResourceDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "res")
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

"""Whether to ignore user-specific config paths."""
ConfigFileStatic = False

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = ["AllowMultipleInstances", "ConsoleHistoryCommands", "DBFiles",
    "DBSort", "FindReplaceHistory", "LastActivePages", "LastExportType", "LastSearchResults",
    "LastSelectedFiles", "LastUpdateCheck", "ParseCache", "Plugins", "RecentFiles",
    "SchemaDiagrams", "SearchHistory", "SearchInMeta", "SearchInData",
    "SearchUseNewTab", "SearchCaseSensitive", "SQLWindowTexts", "TextLineNumbers",
    "TextWordWraps", "TrayIconEnabled", "UpdateCheckAutomatic", "WindowMaximized",
    "WindowMinimizedToTray", "WindowPosition", "WindowSize",
]
"""List of user-modifiable attributes, saved if changed from default."""
OptionalFileDirectives = [
    "DBExtensions", "ExportOptions", "LogSQL", "MinWindowSize",
    "MaxConsoleHistory", "MaxDBSizeForFullCount", "MaxTableRowIDForFullCount",
    "MaxHistoryInitialMessages", "MaxImportFilesizeForCount", "MaxRecentFiles",
    "MaxSearchHistory", "MaxSearchResults", "MaxParseCache", "PopupUnexpectedErrors",
    "RunChecksums", "RunStatistics", "SchemaDiagramEnabled", "SearchResultsChunk",
    "SeekLength", "SeekLeapLength", "StatisticsPlotWidth", "StatusFlashLength",
    "UpdateCheckInterval",
]
Defaults = {}
Overrides = []

"""---------------------------- File directives: ----------------------------"""

"""Whether program can have multiple instances running, or reuses one instance."""
AllowMultipleInstances = False

"""History of commands entered in console."""
ConsoleHistoryCommands = []

"""Database filename extensions, as ('.extension', )."""
DBExtensions = [".db", ".db3", ".s3db", ".sl3", ".sqlite", ".sqlite3", ".sqlitedb"]

"""All detected/added databases."""
DBFiles = []

"""Database list sort state, [col, ascending]."""
DBSort = []

"""History of search/replace texts in find/replace dialogs, as {"find": [..], "replace": [..]}."""
FindReplaceHistory = {}

"""Identifier for inter-process communication."""
IPCName = quote_plus("%s-%s" % (wx.GetUserId(), ApplicationFile)).encode("latin1", "replace") \
          if wx else ""

"""
Port for inter-process communication, receiving data from other
launched instances if not AllowMultipleInstances.
"""
IPCPort = 59987

"""Index of last active page in database tab, {db path: index}."""
LastActivePages = {}

"""Last export format, for uniform setting across components."""
LastExportType = "html"

"""HTMLs of last search result, {db path: {"content", "info", "title"}}."""
LastSearchResults = {}

"""Files selected in the database lists on last run."""
LastSelectedFiles = []

"""Date string of last time updates were checked."""
LastUpdateCheck = None

"""Whether to log all SQL statements to log window."""
LogSQL = False

"""Maximum number of console history commands to store."""
MaxConsoleHistory = 1000

"""Maximum database file size for doing full COUNT(*) instead of estimating from MAX(ROWID)."""
MaxDBSizeForFullCount = 500000000

"""Maximum import file size to do full row count for."""
MaxImportFilesizeForCount = 10 * 1e6

"""Maximum number of cached SQL parse results."""
MaxParseCache = 500

"""How many items in the Recent Files menu."""
MaxRecentFiles = 20

"""Maximum number of search texts to store."""
MaxSearchHistory = 500

"""Maximum number of results to show in search results."""
MaxSearchResults = 500

"""Maximum table ROWID for doing full COUNT(*) if database size over MaxDBSizeForFullCount."""
MaxTableRowIDForFullCount = 1000

"""Minimum allowed size for the main window, as (width, height)."""
MinWindowSize = (600, 400)

"""Cached parse results, as {CREATE SQL: {meta}}."""
ParseCache = {}

"""
User-defined plugins, as {category: [{..}]}.

E.g. {"ValueEditorFunctions": [{title, body, name, ?active}]} for column value editor.
"""
Plugins = {}

"""Whether to pop up message dialogs for unhandled errors."""
PopupUnexpectedErrors = True

"""Contents of Recent Files menu."""
RecentFiles = []

"""Run checksum calculations automatically (may take a while for large databases)."""
RunChecksums = True

"""Run statistics analysis automatically (may take a while for large databases)."""
RunStatistics = True

"""Whether database schema diagram is enabled."""
SchemaDiagramEnabled = True

"""Database schema diagram settings, as {path: {..}}."""
SchemaDiagrams = {}

"""Whether to do case-sensitive search."""
SearchCaseSensitive = False

"""
Texts entered in global search, used for drop down auto-complete.
Last value can be an empty string: search box had no text.
"""
SearchHistory = []

"""Whether to search in all columns of all tables and views."""
SearchInData = True

"""Whether to search in database CREATE SQL."""
SearchInMeta = False

"""Number of search results to yield in one chunk from search thread."""
SearchResultsChunk = 50

"""Whether to create a new tab for each search or reuse current."""
SearchUseNewTab = True

"""Number of rows to seek ahead on data grids, when scrolling freely or jumping to data grid bottom."""
SeekLeapLength = 10000

"""Number of rows to seek ahead on data grids, when scrolling to end of retrieved rows."""
SeekLength = 100

"""Texts in SQL window, loaded on reopening a database {filename: [(name, text, ?{opts}), ], }."""
SQLWindowTexts = {}

"""Width of the database statistics plots, in pixels."""
StatisticsPlotWidth = 200

"""Duration of status messages on StatusBar, in seconds."""
StatusFlashLength = 20

"""Show line numbers in SQL controls, like database full schema panel."""
TextLineNumbers = {}

"""Word-wrap lines in SQL controls, like database full schema panel."""
TextWordWraps = {"body": True, "entity": True, "pragma": True, "schema": True, "sql": True}

"""Whether the program tray icon is used."""
TrayIconEnabled = True

"""Whether the program checks for updates every UpdateCheckInterval."""
UpdateCheckAutomatic = True

"""Days between automatic update checks."""
UpdateCheckInterval = 7

"""Whether the program window has been maximized."""
WindowMaximized = False

"""Whether the program has been minimized and hidden to tray."""
WindowMinimizedToTray = False

"""Main window position, (x, y)."""
WindowPosition = None

"""Main window size in pixels, as [w, h]."""
WindowSize = (1080, 720)

"""---------------------------- /File directives ----------------------------"""

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

"""Number of unhandled errors encountered during current runtime."""
UnexpectedErrorCount = 0

"""URLs for download list, changelog, and homepage."""
DownloadURL  = "https://erki.lap.ee/downloads/SQLitely/"
ChangelogURL = "https://suurjaak.github.io/SQLitely/changelog.html"
HomeUrl      = "https://suurjaak.github.io/SQLitely"

"""Console window size in pixels, (width, height)."""
ConsoleSize = (800, 300)

"""Maximum length of a tab title, overflow will be cut on the left."""
MaxTabTitleLength = 60

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

"""Colour for tables plot in database statistics."""
PlotTableColour = "#3399FF"

"""Colour for indexes plot in database statistics."""
PlotIndexColour = "#1DAB48"

"""Background colour for plots in database statistics."""
PlotBgColour = "#DDDDDD"

"""Font files used for measuring text extent in export."""
FontXlsxFile     = os.path.join(ResourceDirectory, "Carlito.ttf")
FontXlsxBoldFile = os.path.join(ResourceDirectory, "CarlitoBold.ttf")

"""Font files used for schema daigram."""
FontDiagramFile     = os.path.join(ResourceDirectory, "OpenSans.ttf")
FontDiagramBoldFile = os.path.join(ResourceDirectory, "OpenSansBold.ttf")
FontDiagramSize     = 9

"""Path for licences of bundled open-source software."""
LicenseFile = os.path.join(ResourceDirectory, "3rd-party licenses.txt") \
              if Frozen or Snapped else None


def load(configfile=None):
    """
    Loads FileDirectives into this module's attributes.

    @param   configfile  name of configuration file to use from now if not module defaults
    """
    global Defaults, ConfigFile, ConfigFileStatic

    try: VARTYPES = (basestring, bool, float, int, long, list, tuple, dict, type(None))        # Py2
    except Exception: VARTYPES = (bytes, str, float, bool, int, list, tuple, dict, type(None)) # Py3

    def safecopy(v):
        """Tries to return a deep copy, or a shallow copy, or given value if copy fails."""
        for f in (copy.deepcopy, copy.copy, lambda x: x):
            try: return f(v)
            except Exception: pass

    if configfile:
        ConfigFile, ConfigFileStatic = configfile, True
    configpaths = [ConfigFile]
    if not Defaults and not ConfigFileStatic:
        # Instantiate OS- and user-specific paths
        try:
            p = appdirs.user_config_dir(Title, appauthor=False)
            userpath = os.path.join(p, "%s.ini" % Title.lower())
            # Try user-specific path first, then path under application folder
            if userpath not in configpaths: configpaths.insert(0, userpath)
        except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    Defaults = {k: safecopy(v) for k, v in vars(module).items()
                if not k.startswith("_") and isinstance(v, VARTYPES)}

    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        for path in configpaths:
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
        ALLOWED_OVERRIDES = ["Analyzer", "Colour", "Font", "Length", "Log", "Search", "Size"]
        for name in parser.options(section):
            if hasattr(module, name) and name not in FileDirectives + OptionalFileDirectives \
            and any(allowed in name for allowed in ALLOWED_OVERRIDES):
                value, success = parse_value(name)
                if success:
                    setattr(module, name, value)
                    Overrides.append(name)
    except Exception:
        pass # Fail silently


def save(configfile=None):
    """
    Saves FileDirectives into configuration file.

    @param   configfile  name of configuration file to use if not module defaults
    """
    configpaths = [configfile] if configfile else [ConfigFile]
    if not configfile and not ConfigFileStatic:
        try:
            p = appdirs.user_config_dir(Title, appauthor=False)
            userpath = os.path.join(p, "%s.ini" % Title.lower())
            # Pick only userpath if exists, else try application folder first
            if os.path.isfile(userpath): configpaths = [userpath]
            elif userpath not in configpaths: configpaths.append(userpath)
        except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    parser.add_section(section)
    try:
        for path in configpaths:
            try: os.makedirs(os.path.dirname(path))
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
        for name in Overrides:
            try: parser.set(section, name, json.dumps(getattr(module, name)))
            except Exception: pass
        parser.write(f)
        f.close()
    except Exception:
        pass # Fail silently
