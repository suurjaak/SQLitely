# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    23.08.2019
------------------------------------------------------------------------------
"""
from ConfigParser import RawConfigParser
import datetime
import json
import os
import sys

from lib import util

"""Program title, version number and version date."""
Title = "SQLiteMate"
Version = "1.0.dev2"
VersionDate = "23.08.2019"

if getattr(sys, "frozen", False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable)
    ResourceDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "media")
else:
    ApplicationDirectory = os.path.dirname(__file__)
    ResourceDirectory = os.path.join(ApplicationDirectory, "media")

"""Name of file where FileDirectives are kept."""
ConfigFile = "%s.ini" % os.path.join(ApplicationDirectory, "etc", Title.lower())

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = ["ConsoleHistoryCommands", "DBDoBackup",  "DBFiles",
    "LastActivePage", "LastSearchResults", "LastSelectedFiles",
    "LastUpdateCheck", "RecentFiles", "SearchHistory",
    "SearchInNames", "SearchInTables", "SearchUseNewTab",
    "SQLWindowTexts", "TrayIconEnabled",
    "UpdateCheckAutomatic", "WindowIconized", "WindowPosition", "WindowSize",
]
"""List of attributes saved if changed from default."""
OptionalFileDirectives = [
    "ExportDbTemplate", "LogSQL", "MinWindowSize", "MaxConsoleHistory",
    "MaxHistoryInitialMessages", "MaxRecentFiles", "MaxSearchHistory",
    "MaxSearchMessages", "MaxSearchTableRows", "SearchResultsChunk",
    "StatusFlashLength", "UpdateCheckInterval",
]
OptionalFileDirectiveDefaults = {}

"""---------------------------- FileDirectives: ----------------------------"""

"""Whether a backup copy is made of a database before it's changed."""
DBDoBackup = False

"""All detected/added databases."""
DBFiles = []

"""History of commands entered in console."""
ConsoleHistoryCommands = []

"""Index of last active page in database tab, {db path: index}."""
LastActivePage = {}

"""HTMLs of last search result, {db path: {"content", "info", "title"}}."""
LastSearchResults = {}

"""Files selected in the database lists on last run."""
LastSelectedFiles = ["", ""]

"""Contents of Recent Files menu."""
RecentFiles = []

"""
Texts entered in global search, used for drop down auto-complete.
Last value can be an empty string: search box had no text.
"""
SearchHistory = []

"""Whether to create a new tab for each search or reuse current."""
SearchUseNewTab = True

"""Whether to search in table and column names."""
SearchInNames = False

"""Whether to search in all columns of all tables."""
SearchInTables = True

"""Texts in SQL window, loaded on reopening a database {filename: text, }."""
SQLWindowTexts = {}

"""Whether the program tray icon is used."""
TrayIconEnabled = True

"""Whether the program checks for updates every UpdateCheckInterval."""
UpdateCheckAutomatic = True

"""Whether the program has been minimized and hidden."""
WindowIconized = False

"""Main window position, (x, y)."""
WindowPosition = None

"""Main window size in pixels, [w, h] or [-1, -1] for maximized."""
WindowSize = (1080, 710)

"""---------------------------- /FileDirectives ----------------------------"""

"""Whether logging to log window is enabled."""
LogEnabled = True

"""Whether to log all SQL statements to log window."""
LogSQL = False

"""URLs for download list, changelog, submitting feedback and homepage."""
DownloadURL  = "https://erki.lap.ee/downloads/SQLiteMate/"
ChangelogURL = "https://suurjaak.github.com/SQLiteMate/changelog.html"
HomeUrl = "https://suurjaak.github.com/SQLiteMate/"

"""Minimum allowed size for the main window, as (width, height)."""
MinWindowSize = (600, 400)

"""Console window size in pixels, (width, height)."""
ConsoleSize = (800, 300)

"""Maximum number of console history commands to store."""
MaxConsoleHistory = 1000

"""Maximum number of search texts to store."""
MaxSearchHistory = 500

"""Days between automatic update checks."""
UpdateCheckInterval = 7

"""Date string of last time updates were checked."""
LastUpdateCheck = None

"""Maximum length of a tab title, overflow will be cut on the left."""
MaxTabTitleLength = 60

"""Maximum number of messages to show in search results."""
MaxSearchMessages = 500

"""Maximum number of table rows to show in search results."""
MaxSearchTableRows = 500

"""Number of search results to yield in one chunk from search thread."""
SearchResultsChunk = 50

"""Number of contact search results to yield in one chunk."""
SearchContactsChunk = 10

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

"""Colours for main screen database list."""
DBListBackgroundColour = "#ECF4FC"
DBListForegroundColour = "#000000"

"""Colour used for titles."""
TitleColour = "#3399FF"

"""Descriptive text shown in history searchbox."""
SearchDescription = "Search for.."

"""Foreground colour for error labels."""
LabelErrorColour = "#CC3232"

"""Color set to database table list tables that have been changed."""
DBTableChangedColour = "blue"

"""Colour set to table/list rows that have been changed."""
GridRowChangedColour = "#FFCCCC"

"""Colour set to table/list rows that have been inserted."""
GridRowInsertedColour = "#88DDFF"

"""Colour set to table/list cells that have been changed."""
GridCellChangedColour = "#FF7777"

"""Duration of "flashed" status message on StatusBar, in milliseconds."""
StatusFlashLength = 30000

"""How many items in the Recent Files menu."""
MaxRecentFiles = 20

"""Font files used for measuring text extent in export."""
FontXlsxFile = os.path.join(ResourceDirectory, "Carlito.ttf")
FontXlsxBoldFile = os.path.join(ResourceDirectory, "CarlitoBold.ttf")


def load():
    """Loads FileDirectives from ConfigFile into this module's attributes."""
    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        parser.read(ConfigFile)

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

        for name in FileDirectives:
            [setattr(module, name, v) for v, s in [parse_value(name)] if s]
        for name in OptionalFileDirectives:
            OptionalFileDirectiveDefaults[name] = getattr(module, name, None)
            [setattr(module, name, v) for v, s in [parse_value(name)] if s]
    except Exception:
        pass # Fail silently


def save():
    """Saves FileDirectives into ConfigFile."""
    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    parser.add_section(section)
    try:
        f, fname = open(ConfigFile, "wb"), util.longpath(ConfigFile)
        f.write("# %s %s configuration written on %s.\n" % (Title, Version,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        for name in FileDirectives:
            try: parser.set(section, name, json.dumps(getattr(module, name)))
            except Exception: pass
        for name in OptionalFileDirectives:
            try:
                value = getattr(module, name, None)
                if OptionalFileDirectiveDefaults.get(name) != value:
                    parser.set(section, name, json.dumps(value))
            except Exception: pass
        parser.write(f)
        f.close()
    except Exception:
        pass # Fail silently
