# -*- coding: utf-8 -*-
"""
Updates.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    22.08.2019
------------------------------------------------------------------------------
"""
import base64
import datetime
import hashlib
import HTMLParser
import os
import platform
import re
import sys
import tempfile
import traceback
import urllib
import urllib2
import urlparse
import wx

from lib import controls
from lib import wx_accel
from lib import util

import conf
import main

"""Current update dialog window, if any, for avoiding concurrent updates."""
update_window = None

"""URL-opener with SQLiteMate useragent."""
url_opener = urllib2.build_opener()


def check_newest_version(callback=None):
    """
    Queries the SQLiteMate download page for available newer releases.

    @param   callback  function to call with check result, if any
             @result   (version, url, changes) if new version up,
                       () if up-to-date, None if query failed
    """
    global update_window, url_opener
    result = ()
    update_window = True
    try:
        main.log("Checking for new version at %s.", conf.DownloadURL)
        html = url_opener.open(conf.DownloadURL).read()
        links = re.findall("<a[^>]*\\shref=['\"](.+)['\"][^>]*>", html, re.I)
        if links:
            # Determine release types
            linkmap = {} # {"src": link, "x86": link, "x64": link}
            for link in links[:3]:
                link_text = link.lower()
                if link_text.endswith(".zip"):
                    linkmap["src"] = link
                elif link_text.endswith(".exe") and "_x64" in link_text:
                    linkmap["x64"] = link
                elif link_text.endswith(".exe"):
                    linkmap["x86"] = link

            install_type = get_install_type()
            link = linkmap.get(install_type) or ''
            # Extract version number like 1.3.2a from sqlitemate_1.3.2a_x64.exe
            version = (re.findall("(\\d[\\da-z.]+)", link) + [None])[0]
            if version:
                main.log("Newest %s version is %s.", install_type, version)
            try:
                if (version != conf.Version
                and canonic_version(conf.Version) >= canonic_version(version)):
                    version = None
            except Exception: pass
            if version and version != conf.Version:
                changes = ""
                try:
                    main.log("Reading changelog from %s.", conf.ChangelogURL)
                    html = url_opener.open(conf.ChangelogURL).read()
                    match = re.search("<h4[^>]*>(v%s,.*)</h4\\s*>" % version,
                                      html, re.I)
                    if match:
                        ul = html[match.end(0):html.find("</ul", match.end(0))]
                        lis = re.findall("(<li[^>]*>(.+)</li\\s*>)+", ul, re.I)
                        items = [re.sub("<[^>]+>", "", x[1]) for x in lis]
                        items = map(HTMLParser.HTMLParser().unescape, items)
                        changes = "\n".join("- " + i.strip() for i in items)
                        if changes:
                            title = match.group(1)
                            changes = "Changes in %s\n\n%s" % (title, changes)
                except Exception:
                    main.log("Failed to read changelog.\n\n%s.",
                             traceback.format_exc())
                url = urlparse.urljoin(conf.DownloadURL, link)
                result = (version, url, changes)
    except Exception:
        main.log("Failed to retrieve new version from %s.\n\n%s",
                 conf.DownloadURL, traceback.format_exc())
        result = None
    update_window = None
    if callback:
        callback(result)
    return result


def download_and_install(url):
    """Downloads and launches the specified file."""
    global update_window, url_opener
    try:
        is_cancelled = False
        parent = wx.GetApp().TopWindow
        filename, tmp_dir = os.path.split(url)[-1], tempfile.mkdtemp()
        dlg_progress = \
            controls.ProgressWindow(parent, "Downloading %s" % filename)
        dlg_progress.SetGaugeForegroundColour(conf.GaugeColour)
        dlg_progress.Position = (
            parent.Position.x + parent.Size.width  - dlg_progress.Size.width,
            parent.Position.y + parent.Size.height - dlg_progress.Size.height)
        update_window = dlg_progress
        urlfile = url_opener.open(url)
        filepath = os.path.join(tmp_dir, filename)
        main.log("Downloading %s to %s.", url, filepath)
        filesize = int(urlfile.headers.get("content-length", sys.maxint))
        with open(filepath, "wb") as f:
            BLOCKSIZE = 65536
            bytes_downloaded = 0
            buf = urlfile.read(BLOCKSIZE)
            while len(buf):
                f.write(buf)
                bytes_downloaded += len(buf)
                percent = 100 * bytes_downloaded / filesize
                msg = "%d%% of %s" % (percent, util.format_bytes(filesize))
                is_cancelled = not dlg_progress.Update(percent, msg)
                if is_cancelled:
                    break # break while len(buf)
                wx.YieldIfNeeded()
                buf = urlfile.read(BLOCKSIZE)
        dlg_progress.Destroy()
        update_window = None
        if is_cancelled:
            main.log("Upgrade cancelled, erasing temporary file %s.", filepath)
            util.try_until(lambda: os.unlink(filepath))
            util.try_until(lambda: os.rmdir(tmp_dir))
        else:
            main.log("Successfully downloaded %s of %s.",
                     util.format_bytes(filesize), filename)
            dlg_proceed = controls.NonModalOKDialog(parent,
                "Update information",
                "Ready to open %s. You should close %s before upgrading."
                % (filename, conf.Title))
            def proceed_handler(event):
                global update_window
                update_window = None
                dlg_proceed.Destroy()
                util.start_file(filepath)
            update_window = dlg_proceed
            dlg_proceed.Bind(wx.EVT_CLOSE, proceed_handler)
    except Exception:
        main.log("Failed to download new version from %s.\n\n%s", url,
                 traceback.format_exc())


def take_screenshot(fullscreen=True):
    """Returns a wx.Bitmap screenshot taken of fullscreen or program window."""
    wx.YieldIfNeeded()
    if fullscreen:
        rect = wx.Rect(0, 0, *wx.DisplaySize())
    else:
        window = wx.GetApp().TopWindow
        rect   = window.GetRect()

        # adjust widths for Linux (figured out by John Torres 
        # http://article.gmane.org/gmane.comp.python.wxpython/67327)
        if "linux2" == sys.platform:
            client_x, client_y = window.ClientToScreen((0, 0))
            border_width       = client_x - rect.x
            title_bar_height   = client_y - rect.y
            rect.width        += (border_width * 2)
            rect.height       += title_bar_height + border_width

    dc = wx.ScreenDC()
    bmp = wx.EmptyBitmap(rect.width, rect.height)
    dc_bmp = wx.MemoryDC()
    dc_bmp.SelectObject(bmp)
    dc_bmp.Blit(0, 0, rect.width, rect.height, dc, rect.x, rect.y)
    dc_bmp.SelectObject(wx.NullBitmap)
    # Hack to drop screen transparency, wx issue when blitting from screen
    bmp = wx.BitmapFromIcon(wx.IconFromBitmap(bmp))
    return bmp


def get_install_type():
    """Returns the current SQLiteMate installation type (src|x64|x86)."""
    prog_text = sys.argv[0].lower()
    if not prog_text.endswith(".exe"):
        result = "src"
    elif util.is_os_64bit() and "program files\\" in prog_text:
        result = "x64"
    else:
        result = "x86"
    return result


def canonic_version(v):
    """Returns a numeric version representation: "1.3.2a" to 10301,99885."""
    nums = [int(re.sub("[^\\d]", "", x)) for x in v.split(".")][::-1]
    nums[0:0] = [0] * (3 - len(nums)) # Zero-pad if version like 1.4 or just 2
    # Like 1.4a: subtract 1 and add fractions to last number to make < 1.4
    if re.findall("\\d+([\\D]+)$", v):
        ords = map(ord, re.findall("\\d+([\\D]+)$", v)[0])
        nums[0] += sum(x / (65536. ** (i + 1)) for i, x in enumerate(ords)) - 1
    return sum((x * 100 ** i) for i, x in enumerate(nums))


url_opener.addheaders = [("User-agent", "%s %s (%s) (Python %s; wx %s; %s)" % (
    conf.Title, conf.Version, get_install_type(),
    ".".join(map(str, sys.version_info[:3])),
    ".".join(map(str, wx.VERSION[:4])),
    platform.platform() + ("-x64" if platform.machine().endswith("64") else "")
))]
