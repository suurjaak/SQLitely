# -*- coding: utf-8 -*-
"""
Update functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    27.03.2022
------------------------------------------------------------------------------
"""
import logging
import os
import platform
import re
import ssl
import sys
import tempfile

from six.moves import html_parser, urllib
import wx

from . lib import controls
from . lib import util
from . import conf

logger = logging.getLogger(__name__)


"""Current update dialog window, if any, for avoiding concurrent updates."""
update_window = None

"""URL-opener with program useragent."""
url_opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
)


def check_newest_version(callback=None):
    """
    Queries the program download page for available newer releases.

    @param   callback  function to call with check result, if any
             @result   (version, url, changes) if new version up,
                       () if up-to-date, None if query failed
    """
    global update_window, url_opener
    result = ()
    update_window = True
    try:
        logger.info("Checking for new version at %s.", conf.DownloadURL)
        html = util.to_unicode(url_opener.open(conf.DownloadURL).read())
        links = re.findall(r"<a[^>]*\shref=['\"](.+)['\"][^>]*>", html, re.I)
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
            # Extract version number like 1.3.2a from myprogram_1.3.2a_x64.exe
            version = (re.findall(r"(\d[\da-z.]+)", link) + [None])[0]
            if version:
                logger.info("Newest %s version is %s.", install_type, version)
            try:
                if (version != conf.Version
                and canonic_version(conf.Version) >= canonic_version(version)):
                    version = None
            except Exception: pass
            if version and version != conf.Version:
                changes = ""
                try:
                    logger.info("Reading changelog from %s.", conf.ChangelogURL)
                    html = util.to_unicode(url_opener.open(conf.ChangelogURL).read())
                    match = re.search(r"<h4[^>]*>(v%s,.*)</h4\s*>" % version,
                                      html, re.I)
                    if match:
                        ul = html[match.end(0):html.find("</ul", match.end(0))]
                        lis = re.findall(r"(<li[^>]*>(.+)</li\s*>)+", ul, re.I)
                        items = [re.sub("<[^>]+>", "", x[1]) for x in lis]
                        items = list(map(html_parser.HTMLParser().unescape, items))
                        changes = "\n".join("- " + i.strip() for i in items)
                        if changes:
                            title = match.group(1)
                            changes = "Changes in %s\n\n%s" % (title, changes)
                except Exception:
                    logger.exception("Failed to read changelog.")
                url = urllib.parse.urljoin(conf.DownloadURL, link)
                result = (version, url, changes)
    except Exception:
        logger.exception("Failed to retrieve new version from %s", conf.DownloadURL)
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
        logger.info("Downloading %s to %s.", url, filepath)
        filesize = int(urlfile.headers.get("content-length", sys.maxsize))
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
                    break # while len(buf)
                wx.YieldIfNeeded()
                buf = urlfile.read(BLOCKSIZE)
        dlg_progress.Destroy()
        update_window = None
        if is_cancelled:
            logger.info("Upgrade cancelled, erasing temporary file %s.", filepath)
            util.try_until(lambda: os.unlink(filepath))
            util.try_until(lambda: os.rmdir(tmp_dir))
        else:
            logger.info("Successfully downloaded %s of %s.",
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
        logger.exception("Failed to download new version from %s.", url)


def get_install_type():
    """Returns the current program installation type (src|x64|x86)."""
    prog_text = sys.argv[0].lower()
    if not prog_text.endswith(".exe"):
        result = "src"
    elif util.is_python_64bit():
        result = "x64"
    else:
        result = "x86"
    return result


def canonic_version(v):
    """Returns a numeric version representation: "1.3.2a" to 10301,99885."""
    nums = [int(re.sub(r"[^\d]", "", x)) for x in v.split(".")][::-1]
    nums[0:0] = [0] * (3 - len(nums)) # Zero-pad if version like 1.4 or just 2
    # Like 1.4a: subtract 1 and add fractions to last number to make < 1.4
    if re.findall(r"\d+([\D]+)$", v):
        ords = [ord(x) for x in re.findall(r"\d+([\D]+)$", v)[0]]
        nums[0] += sum(x / (65536. ** (i + 1)) for i, x in enumerate(ords)) - 1
    return sum((x * 100 ** i) for i, x in enumerate(nums))


url_opener.addheaders = [("User-agent", "%s %s (%s) (Python %s; wx %s; %s)" % (
    conf.Title, conf.Version, get_install_type(),
    ".".join(map(str, sys.version_info[:3])),
    ".".join(map(str, wx.VERSION[:4])),
    platform.platform() + ("-x64" if platform.machine().endswith("64") else "")
))]
