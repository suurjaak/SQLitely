"""
Simple small script for generating a nicely formatted Python module with
embedded binary resources and docstrings.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author    Erki Suurjaak
@created   21.08.2019
@modified  26.05.2020
------------------------------------------------------------------------------
"""
import base64
import datetime
import os
import shutil
import wx.tools.img2py

"""Target Python script to write."""
TARGET = os.path.join("..", "sqlitely", "images.py")

Q3 = '"""'

"""Application icons of different size and colour depth."""
APPICONS = [("Icon{0}x{0}_{1}bit.png".format(s, b),
             "SQLitely application {0}x{0} icon, {1}-bit colour.".format(s, b))
            for s in (16, 24, 32, 40, 48, 64, 256) for b in (32, 8)]
IMAGES = {
    "ButtonClear.png":
        "Small icon for clear list button on start page.",
    "ButtonDetect.png":
        "Large icon for detect databases button on start page.",
    "ButtonFolder.png":
        "Large icon for import folder button on start page.",
    "ButtonExport.png":
        "Small icon for export button on start page.",
    "ButtonHome.png":
        "Large icon for home on start page.",
    "ButtonListDatabase.png":
        "Button for databases in database list.",
    "ButtonNew.png":
        "Large icon for new database on start page.",
    "ButtonOpen.png":
        "Button for open file on main page.",
    "ButtonOpenA.png":
        "Large icon for open database button on start page.",
    "ButtonRemove.png":
        "Small icon for remove database button on start page.",
    "ButtonRemoveMissing.png":
        "Small icon for remove missing button on start page.",
    "ButtonRemoveType.png":
        "Small icon for remove by type button on start page.",
    "ButtonSaveAs.png":
        "Small icon for save as button on start page.",
    "HelpData.png":
        "Help image on default search page for data page.",
    "HelpInfo.png":
        "Help image on default search page for information page.",
    "HelpPragma.png":
        "Help image on default search page for pragma page.",
    "HelpSchema.png":
        "Help image on default search page for schema page.",
    "HelpSearch.png":
        "Help image on default search page for search page.",
    "HelpSQL.png":
        "Help image on default search page for SQL window page.",
    "PageData.png":
        "Icon for the Data page in a database tab.",
    "PageInfo.png":
        "Icon for the Info page in a database tab.",
    "PagePragma.png":
        "Icon for the Pragma page in a database tab.",
    "PageSchema.png":
        "Icon for the Schema page in a database tab.",
    "PageSearch.png":
        "Icon for the Search page in a database tab.",
    "PageSQL.png":
        "Icon for the SQL Window page in a database tab.",
    "ToolbarCase.png":
        "Toolbar icon for case-insensitive toggle button in data grids.",
    "ToolbarClear.png":
        "Toolbar icon for reset sort/filter button in data grids.",
    "ToolbarCommit.png":
        "Toolbar icon for commit button in database table grids.",
    "ToolbarDelete.png":
        "Toolbar icon for delete button in database table grids.",
    "ToolbarForm.png":
        "Toolbar icon for form button in data grids.",
    "ToolbarGoto.png":
        "Toolbar icon for goto button in data grids.",
    "ToolbarInsert.png":
        "Toolbar icon for insert button in database table grids.",
    "ToolbarRefresh.png":
        "Toolbar icon for refresh button.",
    "ToolbarRollback.png":
        "Toolbar icon for rollback button in database table grids.",
    "ToolbarStop.png":
        "Toolbar icon for stop button on search page.",
    "ToolbarStopped.png":
        "Toolbar icon for inactive stop button on search page.",
    "ToolbarData.png":
        "Toolbar icon for data button on search page.",
    "ToolbarTabs.png":
        "Toolbar icon for tabs toggle button on search page.",
    "ToolbarTitle.png":
        "Toolbar icon for title toggle button on search page.",
    "TransparentPixel.gif":
        "Transparent 1x1 GIF.",
}
HEADER = """%s
Contains embedded image and icon resources for SQLitely. Auto-generated.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    %s
------------------------------------------------------------------------------
%s
try:
    import wx
    from wx.lib.embeddedimage import PyEmbeddedImage
except ImportError:
    class PyEmbeddedImage(object):
        \"\"\"Data stand-in for wx.lib.embeddedimage.PyEmbeddedImage.\"\"\"
        def __init__(self, data):
            self.data = data
""" % (Q3, datetime.date.today().strftime("%d.%m.%Y"), Q3)


def create_py(target):
    global HEADER, APPICONS, IMAGES
    f = open(target, "w")
    f.write(HEADER)
    icons = [os.path.splitext(x)[0] for x, _ in APPICONS]
    icon_parts = [", ".join(icons[4*i:4*i+4]) for i in range(len(icons) / 4)]
    iconstr = ",\n        ".join(icon_parts)
    f.write("\n\n%s%s%s\ndef get_appicons():\n    icons = wx.IconBundle()\n"
            "    [icons.AddIcon(i.Icon) "
            "for i in [\n        %s\n    ]]\n    return icons\n" % (Q3,
        "Returns the application icon bundle, "
        "for several sizes and colour depths.",
        Q3, iconstr.replace("'", "").replace("[", "").replace("]", "")
    ))
    for filename, desc in APPICONS:
        name, extension = os.path.splitext(filename)
        f.write("\n\n%s%s%s\n%s = PyEmbeddedImage(\n" % (Q3, desc, Q3, name))
        data = base64.b64encode(open(filename, "rb").read())
        while data:
            f.write("    \"%s\"\n" % data[:72])
            data = data[72:]
        f.write(")\n")
    for filename, desc in sorted(IMAGES.items()):
        name, extension = os.path.splitext(filename)
        f.write("\n\n%s%s%s\n%s = PyEmbeddedImage(\n" % (Q3, desc, Q3, name))
        data = base64.b64encode(open(filename, "rb").read())
        while data:
            f.write("    \"%s\"\n" % data[:72])
            data = data[72:]
        f.write(")\n")
    f.close()


if "__main__" == __name__:
    create_py(TARGET)
