# -*- coding: utf-8 -*-
"""
Stand-alone GUI components for wx:

- BusyPanel(wx.Window):
  Primitive hover panel with a message that stays in the center of parent
  window.

- ByteTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for byte editing.
  Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.

- ColourManager(object):
  Updates managed component colours on Windows system colour change.

- FileDrop(wx.FileDropTarget):
  A simple file drag-and-drop handler.

- FormDialog(wx.Dialog):
  Dialog for displaying a complex editable form.

- HexTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for hexadecimal editing.
  Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.

- HintedTextCtrl(wx.TextCtrl):
  A text control with a hint text shown when no value, hidden when focused.

- JSONTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for JSON syntax highlighting and folding.

- MessageDialog(wx.Dialog):
  A modal message dialog that is closable from another thread.

- NonModalOKDialog(wx.Dialog):
  A simple non-modal dialog with an OK button, stays on top of parent.

- NoteButton(wx.Panel, wx.Button):
  A large button with a custom icon, main label, and additional note.
  Inspired by wx.CommandLinkButton, which does not support custom icons
  (at least not of wx 2.9.4).

- ProgressWindow(wx.Dialog):
  A simple non-modal ProgressDialog, stays on top of parent frame.

- PropertyDialog(wx.Dialog):
  Dialog for displaying an editable property grid. Supports strings,
  integers, booleans, and tuples interpreted as wx.Size.

- ResizeWidget(wx.lib.resizewidget.ResizeWidget):
  A specialized panel that provides a resize handle for a widget,
  with configurable resize directions.

- SortableUltimateListCtrl(wx.lib.agw.ultimatelistctrl.UltimateListCtrl,
                           wx.lib.mixins.listctrl.ColumnSorterMixin):
  A sortable list view that can be batch-populated, autosizes its columns,
  supports clipboard copy.

- SQLiteTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for SQLite syntax highlighting.

- TabbedHtmlWindow(wx.Panel):
  wx.html.HtmlWindow with tabs for different content pages.

- TextCtrlAutoComplete(wx.TextCtrl):
  A text control with autocomplete using a dropdown list of choices. During
  typing, the first matching choice is appended to textbox value, with the
  appended text auto-selected.
  If wx.PopupWindow is not available (Mac), behaves like a common TextCtrl.
  Based on TextCtrlAutoComplete by Michele Petrazzo, from a post
  on 09.02.2006 in wxPython-users thread "TextCtrlAutoComplete",
  http://wxpython-users.1045709.n5.nabble.com/TextCtrlAutoComplete-td2348906.html

- TreeListCtrl(wx.lib.gizmos.TreeListCtrl):
  A tree control with a more convenient API.

- YAMLTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for YAML syntax highlighting and folding.

- YesNoMessageBox(message, caption, icon=wx.ICON_NONE, default=wx.YES):
  Opens a Yes/No messagebox that is closable by pressing Escape,
  returns dialog result.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.01.2012
@modified    28.03.2022
------------------------------------------------------------------------------
"""
import collections
import copy
import functools
import locale
import math
import os
import re
import string
import struct
import sys

import wx
import wx.html
import wx.lib.agw.flatnotebook
import wx.lib.agw.labelbook
try: # ShapedButton requires PIL, might not be installed
    import wx.lib.agw.shapedbutton
except Exception: pass
import wx.lib.agw.ultimatelistctrl
import wx.lib.embeddedimage
import wx.lib.gizmos
import wx.lib.mixins.listctrl
import wx.lib.newevent
import wx.lib.resizewidget
import wx.lib.wordwrap
import wx.stc


try:
    integer_types, string_types, text_type = (int, long), (basestring, ), unicode  # Py2
except NameError:
    integer_types, string_types, text_type = (int, ),     (str, ),        str      # Py3
try:              unichr = unichr  # Py2
except NameError: unichr = chr     # Py3


# Convenience methods for creating a wx.Brush and wx.Pen or returning cached.
BRUSH = lambda c,      s=wx.BRUSHSTYLE_SOLID: wx.TheBrushList.FindOrCreateBrush(c,    s)
PEN   = lambda c, w=1, s=wx.PENSTYLE_SOLID:   wx.ThePenList  .FindOrCreatePen  (c, w, s)

# Linux produces wx.Button with no visible text if less than 35px
BUTTON_MIN_WIDTH = 35 if "linux" in sys.platform else 20

# Multiplier for wx.ComboBox width ~100px ranges
COMBO_WIDTH_FACTOR = 1.5 if "linux" in sys.platform else 1


class KEYS(object):
    """Keycode groupings, includes numpad keys."""
    UP         = wx.WXK_UP,       wx.WXK_NUMPAD_UP
    DOWN       = wx.WXK_DOWN,     wx.WXK_NUMPAD_DOWN
    LEFT       = wx.WXK_LEFT,     wx.WXK_NUMPAD_LEFT
    RIGHT      = wx.WXK_RIGHT,    wx.WXK_NUMPAD_RIGHT
    PAGEUP     = wx.WXK_PAGEUP,   wx.WXK_NUMPAD_PAGEUP
    PAGEDOWN   = wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN
    ENTER      = wx.WXK_RETURN,   wx.WXK_NUMPAD_ENTER
    INSERT     = wx.WXK_INSERT,   wx.WXK_NUMPAD_INSERT
    DELETE     = wx.WXK_DELETE,   wx.WXK_NUMPAD_DELETE
    HOME       = wx.WXK_HOME,     wx.WXK_NUMPAD_HOME
    END        = wx.WXK_END,      wx.WXK_NUMPAD_END
    SPACE      = wx.WXK_SPACE,    wx.WXK_NUMPAD_SPACE
    BACKSPACE  = wx.WXK_BACK,
    TAB        = wx.WXK_TAB,      wx.WXK_NUMPAD_TAB
    ESCAPE     = wx.WXK_ESCAPE,

    ARROW      = UP + DOWN + LEFT + RIGHT
    PAGING     = PAGEUP + PAGEDOWN
    NAVIGATION = ARROW + PAGING + HOME + END + TAB
    COMMAND    = ENTER + INSERT + DELETE + SPACE + BACKSPACE + ESCAPE

    PLUS       = ord("+"), wx.WXK_NUMPAD_ADD
    MINUS      = ord("-"), wx.WXK_NUMPAD_SUBTRACT
    MULTIPLY  =  ord("*"), wx.WXK_NUMPAD_MULTIPLY

    NUMPAD_ARROW = wx.WXK_NUMPAD_END,  wx.WXK_NUMPAD_DOWN,  wx.WXK_NUMPAD_PAGEDOWN, \
                   wx.WXK_NUMPAD_LEFT,                      wx.WXK_NUMPAD_RIGHT,    \
                   wx.WXK_NUMPAD_HOME, wx.WXK_NUMPAD_UP,    wx.WXK_NUMPAD_PAGEUP

    NAME_CTRL  = "Cmd" if "darwin" == sys.platform else "Ctrl"



class BusyPanel(wx.Window):
    """
    Primitive hover panel with a message that stays in the center of parent
    window.
    """
    FOREGROUND_COLOUR = wx.WHITE
    BACKGROUND_COLOUR = wx.Colour(110, 110, 110, 255)
    REFRESH_INTERVAL  = 500

    def __init__(self, parent, label):
        wx.Window.__init__(self, parent)
        self.Hide() # Avoid initial flicker

        timer = self._timer = wx.Timer(self)

        label = wx.StaticText(self, label=label, style=wx.ST_ELLIPSIZE_END)

        self.BackgroundColour  = self.BACKGROUND_COLOUR
        label.ForegroundColour = self.FOREGROUND_COLOUR

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(label, border=15, flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        self.Fit()

        maxsize = [self.Parent.Size.width // 2, self.Parent.Size.height * 2 // 3]
        self.Size = tuple(min(a, b) for a, b in zip(self.Size, maxsize))

        self.Bind(wx.EVT_PAINT, lambda e: (e.Skip(), self.Refresh()))
        self.Bind(wx.EVT_TIMER, lambda e: (e.Skip(), self.Refresh()))
        self.Bind(wx.EVT_WINDOW_DESTROY, self._OnDestroy)

        self.Layout()
        self.CenterOnParent()
        self.Show()
        parent.Refresh()
        wx.Yield()
        timer.Start(self.REFRESH_INTERVAL)


    def _OnDestroy(self, event):
        event.Skip()
        try: self._timer.Stop()
        except Exception: pass


    def Close(self):
        try: self.Destroy(); self.Parent.Refresh()
        except Exception: pass



class ColourManager(object):
    """
    Updates managed component colours on Windows system colour change.
    """
    colourcontainer   = None
    colourmap         = {} # {colour name in container: wx.SYS_COLOUR_XYZ}
    darkcolourmap     = {} # {colour name in container: wx.SYS_COLOUR_XYZ}
    darkoriginals     = {} # {colour name in container: original value}
    regctrls          = set() # {ctrl, }
    # {ctrl: (prop name: colour name in container or wx.SYS_COLOUR_XYZ)}
    ctrlprops         = collections.defaultdict(dict)


    @classmethod
    def Init(cls, window, colourcontainer, colourmap, darkcolourmap):
        """
        Hooks WM_SYSCOLORCHANGE on Windows, updates colours in container
        according to map.

        @param   window           application main window
        @param   colourcontainer  object with colour attributes
        @param   colourmap        {"attribute": wx.SYS_COLOUR_XYZ}
        @param   darkcolourmap    colours changed if dark background,
                                  {"attribute": wx.SYS_COLOUR_XYZ or wx.Colour}
        """
        cls.colourcontainer = colourcontainer
        cls.colourmap.update(colourmap)
        cls.darkcolourmap.update(darkcolourmap)
        for name in darkcolourmap:
            if not hasattr(colourcontainer, name): continue # for name
            cls.darkoriginals[name] = getattr(colourcontainer, name)

        cls.UpdateContainer()

        # Hack: monkey-patch FlatImageBook with non-hardcoded background
        class HackContainer(wx.lib.agw.labelbook.ImageContainer):
            WHITE_BRUSH = wx.WHITE_BRUSH
            def OnPaint(self, event):
                bgcolour = cls.ColourHex(wx.SYS_COLOUR_WINDOW)
                if "#FFFFFF" != bgcolour: wx.WHITE_BRUSH = BRUSH(bgcolour)
                try: result = HackContainer.__base__.OnPaint(self, event)
                finally: wx.WHITE_BRUSH = HackContainer.WHITE_BRUSH
                return result
        wx.lib.agw.labelbook.ImageContainer = HackContainer

        # Hack: monkey-patch TreeListCtrl with working Colour properties
        wx.lib.gizmos.TreeListCtrl.BackgroundColour = property(
            wx.lib.gizmos.TreeListCtrl.GetBackgroundColour,
            wx.lib.gizmos.TreeListCtrl.SetBackgroundColour
        )
        wx.lib.gizmos.TreeListCtrl.ForegroundColour = property(
            wx.lib.gizmos.TreeListCtrl.GetForegroundColour,
            wx.lib.gizmos.TreeListCtrl.SetForegroundColour
        )

        window.Bind(wx.EVT_SYS_COLOUR_CHANGED, cls.OnSysColourChange)


    @classmethod
    def Manage(cls, ctrl, prop, colour):
        """
        Starts managing a control colour property.

        @param   ctrl    wx component
        @param   prop    property name like "BackgroundColour",
                         tries using ("Set" + prop)() if no such property
        @param   colour  colour name in colour container like "BgColour",
                         or system colour ID like wx.SYS_COLOUR_WINDOW
        """
        if not ctrl: return
        cls.ctrlprops[ctrl][prop] = colour
        cls.UpdateControlColour(ctrl, prop, colour)


    @classmethod
    def Register(cls, ctrl):
        """
        Registers a control for special handling, e.g. refreshing STC colours
        for instances of wx.py.shell.Shell on system colour change.
        """
        if isinstance(ctrl, wx.py.shell.Shell):
            cls.regctrls.add(ctrl)
            cls.SetShellStyles(ctrl)


    @classmethod
    def OnSysColourChange(cls, event):
        """
        Handler for system colour change, refreshes configured colours
        and updates managed controls.
        """
        event.Skip()
        cls.UpdateContainer()
        cls.UpdateControls()


    @classmethod
    def ColourHex(cls, idx):
        """Returns wx.Colour or system colour as HTML colour hex string."""
        colour = idx if isinstance(idx, wx.Colour) \
                 else wx.SystemSettings.GetColour(idx)
        return colour.GetAsString(wx.C2S_HTML_SYNTAX)


    @classmethod
    def GetColour(cls, colour):
        if isinstance(colour, wx.Colour): return colour
        return wx.Colour(getattr(cls.colourcontainer, colour)) \
               if isinstance(colour, string_types) \
               else wx.SystemSettings.GetColour(colour)


    @classmethod
    def Adjust(cls, colour1, colour2, ratio=0.5):
        """
        Returns first colour adjusted towards second.
        Arguments can be wx.Colour, RGB tuple, colour hex string,
        or wx.SystemSettings colour index.

        @param   ratio    RGB channel adjustment ratio towards second colour
        """
        colour1 = wx.SystemSettings.GetColour(colour1) \
                  if isinstance(colour1, integer_types) else wx.Colour(colour1)
        colour2 = wx.SystemSettings.GetColour(colour2) \
                  if isinstance(colour2, integer_types) else wx.Colour(colour2)
        rgb1, rgb2 = tuple(colour1)[:3], tuple(colour2)[:3]
        delta  = tuple(a - b for a, b in zip(rgb1, rgb2))
        result = tuple(a - (d * ratio) for a, d in zip(rgb1, delta))
        result = tuple(min(255, max(0, x)) for x in result)
        return wx.Colour(result)


    @classmethod
    def UpdateContainer(cls):
        """Updates configuration colours with current system theme values."""
        for name, colourid in cls.colourmap.items():
            setattr(cls.colourcontainer, name, cls.ColourHex(colourid))

        if "#FFFFFF" != cls.ColourHex(wx.SYS_COLOUR_WINDOW):
            for name, colourid in cls.darkcolourmap.items():
                setattr(cls.colourcontainer, name, cls.ColourHex(colourid))
        else:
            for name, value in cls.darkoriginals.items():
                setattr(cls.colourcontainer, name, value)


    @classmethod
    def UpdateControls(cls):
        """Updates all managed controls."""
        for ctrl, props in list(cls.ctrlprops.items()):
            if not ctrl: # Component destroyed
                cls.ctrlprops.pop(ctrl)
                continue # for ctrl, props

            for prop, colour in props.items():
                cls.UpdateControlColour(ctrl, prop, colour)

        for ctrl in list(cls.regctrls):
            if not ctrl: cls.regctrls.discard(ctrl)
            elif isinstance(ctrl, wx.py.shell.Shell): cls.SetShellStyles(ctrl)


    @classmethod
    def UpdateControlColour(cls, ctrl, prop, colour):
        """Sets control property or invokes "Set" + prop."""
        mycolour = cls.GetColour(colour)
        if hasattr(ctrl, prop):
            setattr(ctrl, prop, mycolour)
        elif hasattr(ctrl, "Set" + prop):
            getattr(ctrl, "Set" + prop)(mycolour)


    @classmethod
    def SetShellStyles(cls, stc):
        """Sets system colours to Python shell console."""

        fg    = cls.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        bg    = cls.GetColour(wx.SYS_COLOUR_WINDOW)
        btbg  = cls.GetColour(wx.SYS_COLOUR_BTNFACE)
        grfg  = cls.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        ibg   = cls.GetColour(wx.SYS_COLOUR_INFOBK)
        ifg   = cls.GetColour(wx.SYS_COLOUR_INFOTEXT)
        hlfg  = cls.GetColour(wx.SYS_COLOUR_HOTLIGHT)
        q3bg  = cls.GetColour(wx.SYS_COLOUR_INFOBK)
        q3sfg = wx.Colour(127,   0,   0) # brown  #7F0000
        deffg = wx.Colour(  0, 127, 127) # teal   #007F7F
        eolbg = wx.Colour(224, 192, 224) # pink   #E0C0E0
        strfg = wx.Colour(127,   0, 127) # purple #7F007F

        if sum(fg) > sum(bg): # Background darker than foreground
            deffg = cls.Adjust(deffg, bg, -1)
            eolbg = cls.Adjust(eolbg, bg, -1)
            q3bg  = cls.Adjust(q3bg,  bg)
            q3sfg = cls.Adjust(q3sfg, bg, -1)
            strfg = cls.Adjust(strfg, bg, -1)

        faces = dict(wx.py.editwindow.FACES,
                     q3bg =cls.ColourHex(q3bg),  backcol  =cls.ColourHex(bg),
                     q3fg =cls.ColourHex(ifg),   forecol  =cls.ColourHex(fg),
                     deffg=cls.ColourHex(deffg), calltipbg=cls.ColourHex(ibg),
                     eolbg=cls.ColourHex(eolbg), calltipfg=cls.ColourHex(ifg),
                     q3sfg=cls.ColourHex(q3sfg), linenobg =cls.ColourHex(btbg),
                     strfg=cls.ColourHex(strfg), linenofg =cls.ColourHex(grfg),
                     keywordfg=cls.ColourHex(hlfg))

        # Default style
        stc.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d,"
                                                   "back:%(backcol)s,fore:%(forecol)s" % faces)
        stc.SetCaretForeground(fg)
        stc.StyleClearAll()
        stc.SetSelForeground(True, cls.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT))
        stc.SetSelBackground(True, cls.GetColour(wx.SYS_COLOUR_HIGHLIGHT))

        # Built in styles
        stc.StyleSetSpec(wx.stc.STC_STYLE_LINENUMBER,  "back:%(linenobg)s,fore:%(linenofg)s,"
                                                       "face:%(mono)s,size:%(lnsize)d" % faces)
        stc.StyleSetSpec(wx.stc.STC_STYLE_CONTROLCHAR, "face:%(mono)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT,  "fore:#0000FF,back:#FFFF88")
        stc.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD,    "fore:#FF0000,back:#FFFF88")

        # Python styles
        stc.StyleSetSpec(wx.stc.STC_P_DEFAULT,      "face:%(mono)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_COMMENTLINE,  "fore:#007F00,face:%(mono)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_NUMBER,       "")
        stc.StyleSetSpec(wx.stc.STC_P_STRING,       "fore:%(strfg)s,face:%(mono)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_CHARACTER,    "fore:%(strfg)s,face:%(mono)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_WORD,         "fore:%(keywordfg)s,bold" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_TRIPLE,       "fore:%(q3sfg)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_TRIPLEDOUBLE, "fore:%(q3fg)s,back:%(q3bg)s" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_CLASSNAME,    "fore:%(deffg)s,bold" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_DEFNAME,      "fore:%(deffg)s,bold" % faces)
        stc.StyleSetSpec(wx.stc.STC_P_OPERATOR,     "")
        stc.StyleSetSpec(wx.stc.STC_P_IDENTIFIER,   "")
        stc.StyleSetSpec(wx.stc.STC_P_COMMENTBLOCK, "fore:#7F7F7F")
        stc.StyleSetSpec(wx.stc.STC_P_STRINGEOL,    "fore:#000000,face:%(mono)s,"
                                                    "back:%(eolbg)s,eolfilled" % faces)

        stc.CallTipSetBackground(faces['calltipbg'])
        stc.CallTipSetForeground(faces['calltipfg'])



class FileDrop(wx.FileDropTarget):
    """
    A simple file drag-and-drop handler.

    @param   on_files    callback(path) for file drop
    @param   on_folders  callback(path) for folder drop
    """
    def __init__(self, on_files=None, on_folders=None):
        super(FileDrop, self).__init__()
        self.on_files   = on_files
        self.on_folders = on_folders


    def OnDropFiles(self, x, y, filenames):
        # CallAfter to allow UI to clear up the dragged icons
        wx.CallAfter(self.ProcessFiles, filenames)
        return True


    def ProcessFiles(self, paths):
        if not self: return
        folders   = list(filter(os.path.isdir,  paths))
        filenames = list(filter(os.path.isfile, paths))
        if folders   and self.on_folders: self.on_folders(folders)
        if filenames and self.on_files:   self.on_files(filenames)



class FormDialog(wx.Dialog):
    """
    Dialog for displaying a complex editable form.
    Uses ComboBox for fields with choices.
    Uses two ListBoxes for list fields.

    @param   props    [{
       name:          field name
       ?type:         (bool | list | anything) if field has direct content,
                      or callback(dialog, field, panel, data) making controls
       ?label:        field label if not using name
       ?help:         field tooltip
       ?path:         [data path, if, more, complex, nesting]
       ?choices:      [value, ] or callback(field, path, data) returning list
       ?choicesedit:  true if value not limited to given choices
       ?component:    specific wx component to use
       ?exclusive:    if true, list-type choices are removed from left list
                      when added to the right
       ?dropempty:    true if field should be deleted from data when set value is empty
       ?toggle:       if true, field is toggle-able and children hidden when off
       ?togglename: { an additional child editbox for name right next to toggle
         name:        data subpath for editbox value
         ?label:      editbox label if not using name for label
         ?toggle:     if true, editbox is toggle-able and hidden when off
       }
       ?children:     [{field}, ]
       ?link:         "name" of linked field, cleared and repopulated on change,
                      or callable(data) doing required change and returning field name
       ?tb:           [{type, ?help, ?toggle, ?on}] for SQLiteTextCtrl component,
                      adds toolbar, supported toolbar buttons "numbers", "wrap",
                      "copy", "paste", "open" and "save", plus "sep" for separator
    }]
    @param   autocomp  list of words to add to SQLiteTextCtrl autocomplete,
                       or a dict for words and subwords
    @param   onclose   callable(data) on closing dialog, returning whether to close
    @param   footer    { a separate SQLiteTextCtrl in dialog footer
       ?label:         label for footer, if any
       ?tb:            [{type, ?help, ?handler}] for SQLiteTextCtrl component, adds toolbar,
                       supported toolbar buttons "copy", "paste", plus "sep" for separator
       populate:       function(dialog, ctrl) invoked on startup and each change
    }
    """

    WIDTH = 640 if "linux" in sys.platform else 440
    HEIGHT_FOOTER = 100 if "linux" in sys.platform else 65


    def __init__(self, parent, title, props=None, data=None, edit=None, autocomp=None, onclose=None, footer=None):
        wx.Dialog.__init__(self, parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self._ignore_change = False
        self._editmode = bool(edit) if edit is not None else True
        self._comps    = collections.defaultdict(list) # {(path): [wx component, ]}
        self._autocomp = autocomp
        self._onclose  = onclose
        self._footer   = dict(footer) if footer and footer.get("populate") else None
        self._toggles  = {} # {(path): wx.CheckBox, }
        self._props    = []
        self._data     = {}
        self._rows     = 0

        splitter = wx.SplitterWindow(self, style=wx.BORDER_NONE) if self._footer else None
        panel_wrap  = wx.ScrolledWindow(splitter or self)
        panel_items = self._panel = wx.Panel(panel_wrap)

        panel_wrap.SetScrollRate(0, 20)

        self.Sizer        = wx.BoxSizer(wx.VERTICAL)
        panel_footer      = self._AddFooter(splitter, self._footer) if self._footer else None
        sizer_buttons     = self.CreateButtonSizer(wx.OK | (wx.CANCEL if self._editmode else 0))
        panel_wrap.Sizer  = wx.BoxSizer(wx.VERTICAL)
        panel_items.Sizer = wx.GridBagSizer(hgap=5, vgap=0)

        panel_items.Sizer.SetEmptyCellSize((0, 0))
        panel_wrap.Sizer.Add(panel_items, border=10, proportion=1, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)

        self.Sizer.Add(splitter or panel_wrap, proportion=1, flag=wx.GROW)
        self.Sizer.Add(sizer_buttons, border=5, flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)

        self.Bind(wx.EVT_BUTTON, self._OnClose, id=wx.ID_OK)

        for x in self, panel_wrap, panel_items:
            ColourManager.Manage(x, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
            ColourManager.Manage(x, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        self.Populate(props, data, edit)

        if splitter:
            splitter.SetSashGravity(1) # Grow top window only
            splitter.SetMinimumPaneSize(45)
            splitter.SplitHorizontally(panel_wrap, panel_footer)

        self.Fit()
        FRAMEH = 2 * wx.SystemSettings.GetMetric(wx.SYS_FRAMESIZE_Y) + wx.SystemSettings.GetMetric(wx.SYS_CAPTION_Y)
        MINH = 25 + (self.HEIGHT_FOOTER if panel_footer else 0)
        self.Size = self.MinSize = (self.WIDTH, panel_wrap.VirtualSize[1] + MINH + sizer_buttons.Size[1] + FRAMEH)
        if splitter:
            splitter.SetSashPosition(splitter.Size[1] - 65)
        self.CenterOnParent()


    def Populate(self, props=None, data=None, edit=None):
        """
        Clears current content, if any, adds controls to dialog,
        and populates with data; non-null arguments override current settings.
        """
        self._ignore_change = True

        def walk(x, callback):
            """
            Walks through the collection of nested dicts or lists or tuples, invoking
            callback(child) for each element, recursively.
            """
            if isinstance(x, collections.Iterable) and not isinstance(x, string_types):
                for k, v in enumerate(x):
                    if isinstance(x, collections.Mapping): k, v = v, x[v]
                    callback(v)
                    walk(v, callback)

        if props is not None:
            memo = {} # copy-module produces invalid result for wx.Bitmap
            walk(props, lambda v: memo.update({id(v): v}) if isinstance(v, wx.Bitmap) else None)
            self._props = copy.deepcopy(props, memo=memo)
        if data  is not None: self._data = copy.deepcopy(data)
        if edit  is not None: self._editmode = bool(edit)
        self._rows  = 0

        self.Freeze()
        sizer = self._panel.Sizer
        while sizer.Children: sizer.Remove(0)
        for c in self._panel.Children: c.Destroy()
        self._toggles.clear()
        self._comps.clear()

        for f in self._props: self._AddField(f)

        for f in self._props: self._PopulateField(f)
        if not sizer.IsColGrowable(sizer.Cols - 2):
            sizer.AddGrowableCol(sizer.Cols - 2, proportion=1)
        if len(self._comps) == 1 and not sizer.IsRowGrowable(0):
            sizer.AddGrowableRow(0, proportion=1)
        self.PopulateFooter(immediate=True)
        self._ignore_change = False
        self.Layout()
        self.Thaw()


    def GetData(self):
        """Returns the current data values."""
        result = copy.deepcopy(self._data)
        for p in sorted(self._toggles, key=len, reverse=True):
            if not self._toggles[p].Value:
                ptr = result
                for x in p[:-1]: ptr = ptr.get(x) or {}
                ptr.pop(p[-1], None)
        return result


    def PopulateFooter(self, immediate=False):
        """Populates footer, if any."""
        if self._footer:
            self._footer["populate"](self, self._footer["ctrl"], immediate=immediate)


    def _GetValue(self, field, path=()):
        """Returns field data value."""
        ptr = self._data
        path = field.get("path") or path
        for x in path: ptr = ptr.get(x, {}) if isinstance(ptr, dict) else ptr[x]
        return ptr.get(field["name"])


    def _SetValue(self, field, value, path=()):
        """Sets field data value."""
        ptr = parent = self._data
        path = field.get("path") or path
        for x in path:
            ptr = ptr.get(x) if isinstance(ptr, dict) else ptr[x]
            if ptr is None: ptr = parent[x] = {}
            parent = ptr
        ptr[field["name"]] = value
        if not self._ignore_change: self.PopulateFooter()


    def _DelValue(self, field, path=()):
        """Deletes field data value."""
        ptr = self._data
        path = field.get("path") or path
        for x in path: ptr = ptr.get(x, {}) if isinstance(ptr, dict) else ptr[x]
        ptr.pop(field["name"], None)
        if not self._ignore_change: self.PopulateFooter()


    def _GetField(self, name, path=()):
        """Returns field from props."""
        fields, path = self._props, list(path) + [name]
        while fields:
            stepped = False
            for f in fields:
                if [f["name"]] == path: return f
                if f["name"] == path[0] and f.get("children"):
                    fields, path, stepped = f["children"], path[1:], True
                    break # for f
            if not stepped: break # while fields


    def _GetChoices(self, field, path):
        """Returns the choices list for field, if any."""
        result = field.get("choices") or []
        if callable(result):
            if path:
                parentfield = self._GetField(path[-1], path[:-1])
                data = self._GetValue(parentfield, path[:-1])
            else: data = self.GetData()
            result = result(data)
        return result


    def _Unprint(self, s, escape=True):
        """Returns string with unprintable characters escaped or stripped."""
        repl = (lambda m: m.group(0).encode("unicode-escape").decode("latin1")) if escape else ""
        return re.sub(r"[\x00-\x1f]", repl, s)


    def _AddField(self, field, path=()):
        """Adds field controls to dialog."""
        callback = field["type"] if callable(field.get("type")) \
                   and field["type"] not in (bool, list) else None
        if not callback and not self._editmode and self._GetValue(field, path) is None: return
        MAXCOL = 8
        parent, sizer = self._panel, self._panel.Sizer
        col, fpath = len(path), path + (field["name"], )

        if field.get("toggle"):
            mysizer = wx.BoxSizer(wx.HORIZONTAL)
            toggle = wx.CheckBox(parent)
            if field.get("help"): toggle.ToolTip = field["help"]
            if self._editmode:
                toggle.Label = field["label"] if "label" in field else field["name"]
                sizer.Add(toggle, border=5, pos=(self._rows, col), span=(1, 1), flag=wx.TOP | wx.BOTTOM)
                col += 1
            else: # Show ordinary label in view mode, checkbox goes very gray
                label = wx.StaticText(parent, label=field["label"] if "label" in field else field["name"])
                if field.get("help"): label.ToolTip = field["help"]
                mysizer.Add(toggle, border=5, flag=wx.RIGHT)
                mysizer.Add(label)
            if field.get("togglename") and field["togglename"].get("name"):
                # Show the additional name-editbox, with an additional optional toggle
                mysizer.AddSpacer(30)
                namefield, edittoggle = field["togglename"], None
                nfpath = fpath + (namefield["name"], )
                if namefield.get("toggle"):
                    edittoggle = wx.CheckBox(parent)
                    if self._editmode:
                        edittoggle.Label = namefield.get("label", namefield["name"])
                    mysizer.Add(edittoggle)
                    self._BindHandler(self._OnToggleField, edittoggle, namefield, fpath, edittoggle)
                    self._comps[nfpath].append(edittoggle)
                    self._toggles[nfpath] = edittoggle
                if not namefield.get("toggle") or not self._editmode:
                    editlabel = wx.StaticText(parent, label=namefield.get("label", namefield["name"]))
                    mysizer.Add(editlabel, border=5, flag=wx.LEFT)
                    self._comps[nfpath].append(editlabel)

                placeholder = wx.StaticText(parent, label=" ") # Ensure constant row height
                editbox = wx.TextCtrl(parent)

                placeholder.Size = placeholder.MinSize = placeholder.MaxSize = (1, editbox.Size[1])
                mysizer.Add(placeholder)
                mysizer.Add(editbox, border=5, flag=wx.LEFT)
                self._BindHandler(self._OnChange, editbox, namefield, fpath)
                self._comps[nfpath].append(editbox)
            if not mysizer.IsEmpty():
                colspan = 2 if not callback and any(field.get(x) for x in ["type", "choices", "component"]) \
                          else MAXCOL - col
                sizer.Add(mysizer, border=5, pos=(self._rows, col), span=(1, colspan), flag=wx.TOP | wx.BOTTOM)
                col += colspan
            self._comps[fpath].append(toggle)
            self._toggles[tuple(field.get("path") or ()) + fpath] = toggle
            self._BindHandler(self._OnToggleField, toggle, field, path, toggle)

        if callback: callback(self, field, parent, self._data)
        elif not field.get("toggle") or any(field.get(x) for x in ["type", "choices", "component"]):
            ctrls = self._MakeControls(field, path)
            for i, c in enumerate(ctrls):
                colspan = 1 if isinstance(c, wx.StaticText) or i < len(ctrls) - 2 else \
                          MAXCOL - col - bool(col)
                brd, BRD = (5, wx.BOTTOM) if isinstance(c, wx.CheckBox) else (0, 0)
                GRW = 0 if isinstance(c, (wx.CheckBox, wx.TextCtrl)) else wx.GROW
                sizer.Add(c, border=brd, pos=(self._rows, col), span=(1, colspan), flag=BRD | GRW)
                col += colspan

        self._rows += 1
        for f in field.get("children") or (): self._AddField(f, fpath)


    def _AddFooter(self, parent, footer):
        """Adds footer component to dialog, returns footer panel."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        label, tb, ctrl = None, None, None
        accname = "footer_%s" % wx.NewIdRef().Id

        if footer.get("label"):
            label = wx.StaticText(panel, label=footer["label"], name=accname + "_label")
        if footer.get("tb"):
            def OnCopy(prop, event=None):
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(ctrl.Text))
                    wx.TheClipboard.Close()
            def OnPaste(prop, event=None):
                if wx.TheClipboard.Open():
                    d = wx.TextDataObject()
                    if wx.TheClipboard.GetData(d):
                        sql = d.GetText()
                        if prop.get("handler"): prop["handler"](self, ctrl, sql)
                        else:
                            ctrl.SetEditable(True)
                            ctrl.Text = sql
                            ctrl.SetEditable(False)
                    wx.TheClipboard.Close()

            OPTS = {"copy":  {"id": wx.ID_COPY,  "bmp": wx.ART_COPY,  "handler": OnCopy},
                    "paste": {"id": wx.ID_PASTE, "bmp": wx.ART_PASTE, "handler": OnPaste}, }

            tb = wx.ToolBar(panel, style=wx.TB_FLAT | wx.TB_NODIVIDER)
            for prop in footer["tb"]:
                if "sep" == prop["type"]:
                    tb.AddSeparator()
                    continue # for prop
                opts = OPTS[prop["type"]]
                bmp = wx.ArtProvider.GetBitmap(opts["bmp"], wx.ART_TOOLBAR, (16, 16))
                tb.SetToolBitmapSize(bmp.Size)
                tb.AddTool(opts["id"], "", bmp, shortHelp=prop.get("help", ""))
                tb.Bind(wx.EVT_TOOL, functools.partial(opts["handler"], prop), id=opts["id"])
            tb.Realize()


        sep = wx.StaticLine(panel)
        ctrl = self._footer["ctrl"] = SQLiteTextCtrl(panel, traversable=True, size=(-1, 60),
                                                     name=accname, style=wx.BORDER_SUNKEN)
        ctrl.SetCaretLineVisible(False)

        sizer.Add(sep, flag=wx.GROW)

        if label or tb:
            hsizer = wx.BoxSizer(wx.HORIZONTAL)
            if label: hsizer.Add(label, border=5, flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL)
            hsizer.AddStretchSpacer()
            if tb: hsizer.Add(tb)
            sizer.Add(hsizer, flag=wx.GROW)

        sizer.Add(ctrl, proportion=1, flag=wx.GROW)
        return panel


    def _PopulateField(self, field, path=()):
        """Populates field controls with data state."""
        if not self._editmode and self._GetValue(field, path) is None: return
        fpath = path + (field["name"], )
        choices = self._GetChoices(field, path)
        value = self._GetValue(field, path)

        ctrls = [x for x in self._comps[fpath]
                 if not isinstance(x, (wx.StaticText, wx.Sizer))]
        if list is field.get("type"):
            value = value or []
            if field.get("exclusive"):
                choices = [x for x in choices if x not in value]
            listbox1, listbox2 = (x for x in ctrls if isinstance(x, wx.ListBox))
            for listbox, vv in zip((listbox1, listbox2), (choices, value)):
                listbox.SetItems(list(map(self._Unprint, vv)))
                for j, x in enumerate(vv): listbox.SetClientData(j, x)
                listbox.Enable(self._editmode)
            for c in ctrls:
                if isinstance(c, wx.Button): c.Enable(self._editmode)
        else:
            for i, c in enumerate(ctrls):
                if not i and isinstance(c, wx.CheckBox) and field.get("toggle"):
                    c.Value = (value is not None)
                    self._OnToggleField(field, path, c)
                    c.Enable(self._editmode)

                    if field.get("togglename") and field["togglename"].get("name"):
                        namefield = field["togglename"]
                        nfpath = fpath + (namefield["name"], )
                        nfvalue = self._GetValue(namefield, fpath)
                        nfshown = c.Value and (self._editmode or bool(nfvalue))
                        cb, cl, ce = None, None, None
                        if namefield.get("toggle"):
                            if self._editmode: cb, ce = self._comps[nfpath] # CheckBox, EditCtrl
                            else: cb, cl, ce = self._comps[nfpath] # CheckBox, StaticText, EditCtrl
                        else:
                            if self._editmode: ce,  = self._comps[nfpath] # EditCtrl
                            else: cl, ce = self._comps[nfpath] # StaticText, EditCtrl
                        if cl: cl.Show(nfshown)
                        ce.Value = "" if nfvalue is None else nfvalue
                        ce.Enable(self._editmode)
                        ce.Show(nfshown)
                        if cb:
                            cb.Value = bool(nfvalue)
                            cb.Enable(self._editmode)
                            cb.Show(nfshown)
                            self._OnToggleField(namefield, fpath, cb)

                    continue # for i, c
                if isinstance(c, wx.stc.StyledTextCtrl):
                    c.SetText(value or "")
                    if self._autocomp and isinstance(c, SQLiteTextCtrl):
                        c.AutoCompClearAdded()
                        c.AutoCompAddWords(self._autocomp)
                        if isinstance(self._autocomp, dict):
                            for w, ww in self._autocomp.items():
                                c.AutoCompAddSubWords(w, ww)
                elif isinstance(c, wx.CheckBox): c.Value = bool(value)
                else:
                    if isinstance(value, (list, tuple)): value = "".join(value)
                    if isinstance(c, wx.ComboBox):
                        c.SetItems(list(map(self._Unprint, choices)))
                        for j, x in enumerate(choices): c.SetClientData(j, x)
                        value = self._Unprint(value) if value else value
                    c.Value = "" if value is None else value

                if isinstance(c, wx.TextCtrl): c.SetEditable(self._editmode)
                else: c.Enable(self._editmode)

        for f in field.get("children") or (): self._PopulateField(f, fpath)


    def _MakeControls(self, field, path=()):
        """Returns a list of wx components for field."""
        result = []
        parent, ctrl = self._panel, None
        fpath = path + (field["name"], )
        label = field["label"] if "label" in field else field["name"]
        accname = "ctrl_%s" % self._rows # Associating label click with control

        if list is field.get("type"):
            # Add two listboxes side by side, with buttons to the right of both
            sizer_f = wx.BoxSizer(wx.VERTICAL)
            sizer_l = wx.BoxSizer(wx.HORIZONTAL)
            sizer_b1 = wx.BoxSizer(wx.VERTICAL)
            sizer_b2 = wx.BoxSizer(wx.VERTICAL)
            ctrl1 = wx.ListBox(parent, style=wx.LB_EXTENDED)
            b1    = wx.Button(parent, label=">", size=(max(30, BUTTON_MIN_WIDTH), -1))
            b2    = wx.Button(parent, label="<", size=(max(30, BUTTON_MIN_WIDTH), -1))
            ctrl2 = wx.ListBox(parent, style=wx.LB_EXTENDED)
            b3    = wx.Button(parent, label=u"\u2191", size=(BUTTON_MIN_WIDTH, -1))
            b4    = wx.Button(parent, label=u"\u2193", size=(BUTTON_MIN_WIDTH, -1))

            b1.ToolTip = "Add selected from left to right"
            b2.ToolTip = "Remove selected from right"
            b3.ToolTip = "Move selected items higher"
            b4.ToolTip = "Move selected items lower"
            ctrl1.SetName(accname)
            ctrl1.MinSize = ctrl2.MinSize = (100, 100)
            if field.get("help"): ctrl1.ToolTip = field["help"]

            sizer_b1.Add(b1); sizer_b1.Add(b2)
            sizer_b2.Add(b3); sizer_b2.Add(b4)
            sizer_l.Add(ctrl1, proportion=1)
            sizer_l.Add(sizer_b1, flag=wx.ALIGN_CENTER_VERTICAL)
            sizer_l.Add(ctrl2, proportion=1)
            sizer_l.Add(sizer_b2, flag=wx.ALIGN_CENTER_VERTICAL)

            toplabel = wx.StaticText(parent, label=label, name=accname + "_label")
            sizer_f.Add(toplabel, flag=wx.GROW)
            sizer_f.Add(sizer_l, border=10, proportion=1, flag=wx.BOTTOM | wx.GROW)

            result.append(sizer_f)
            self._comps[fpath].extend([toplabel, ctrl1, b1, b2, ctrl2, b3, b4])

            self._BindHandler(self._OnAddToList,      ctrl1, field, path)
            self._BindHandler(self._OnAddToList,      b1,    field, path)
            self._BindHandler(self._OnRemoveFromList, b2,    field, path)
            self._BindHandler(self._OnRemoveFromList, ctrl2, field, path)
            self._BindHandler(self._OnMoveInList,     b3,    field, path, -1)
            self._BindHandler(self._OnMoveInList,     b4,    field, path, +1)
        elif field.get("tb") and field.get("component") is SQLiteTextCtrl:
            # Special case, add toolbar buttons for STC
            sizer_top = wx.BoxSizer(wx.HORIZONTAL)
            sizer_stc = wx.BoxSizer(wx.VERTICAL)

            mylabel = wx.StaticText(parent, label=label, name=accname + "_label")
            tb = wx.ToolBar(parent, style=wx.TB_FLAT | wx.TB_NODIVIDER)
            ctrl = field["component"](parent, traversable=True, style=wx.BORDER_SUNKEN)

            ctrl.SetName(accname)
            ctrl.SetMarginCount(1)
            ctrl.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
            ctrl.SetMarginCursor(0, wx.stc.STC_CURSORARROW)
            ctrl.SetMarginWidth(0, 0)
            ctrl.SetWrapMode(wx.stc.STC_WRAP_WORD)

            OPTS = {"numbers": {"id": wx.ID_INDENT, "bmp": wx.ART_HELP,      "handler": self._OnToggleLineNumbers},
                    "wrap":    {"id": wx.ID_STATIC, "bmp": wx.ART_HELP,      "handler": self._OnToggleWordWrap},
                    "open":    {"id": wx.ID_OPEN,   "bmp": wx.ART_FILE_OPEN, "handler": self._OnOpenFile},
                    "save":    {"id": wx.ID_SAVE,   "bmp": wx.ART_FILE_SAVE, "handler": self._OnSaveFile},
                    "copy":    {"id": wx.ID_COPY,   "bmp": wx.ART_COPY,      "handler": self._OnCopy},
                    "paste":   {"id": wx.ID_PASTE,  "bmp": wx.ART_PASTE,     "handler": self._OnPaste}, }
            for prop in field["tb"]:
                if "sep" == prop["type"]:
                    tb.AddSeparator()
                    continue # for prop
                opts = OPTS[prop["type"]]
                bmp = prop.get("bmp") or wx.ArtProvider.GetBitmap(opts["bmp"], wx.ART_TOOLBAR, (16, 16))
                tb.SetToolBitmapSize(bmp.Size)
                kind = wx.ITEM_CHECK if prop.get("toggle") else wx.ITEM_NORMAL
                tb.AddTool(opts["id"], "", bmp, shortHelp=prop.get("help", ""), kind=kind)
                if prop.get("toggle") and prop.get("on"):
                    tb.ToggleTool(opts["id"], True)

                if "numbers" == prop["type"] and prop.get("on"):
                    ctrl.SetMarginWidth(0, 25)
                if "wrap" == prop["type"] and not prop.get("on"):
                    ctrl.SetWrapMode(wx.stc.STC_WRAP_NONE)

                tb.Bind(wx.EVT_TOOL, functools.partial(opts["handler"], field, path), id=opts["id"])
            tb.Realize()

            sizer_top.Add(mylabel, border=5, flag=wx.BOTTOM | wx.ALIGN_BOTTOM)
            sizer_top.AddStretchSpacer()
            sizer_top.Add(tb, flag=wx.ALIGN_BOTTOM)

            sizer_stc.Add(sizer_top, flag=wx.GROW)
            sizer_stc.Add(ctrl, proportion=1, flag=wx.GROW)

            result.append(sizer_stc)
            self._comps[fpath].append(ctrl)

            self._BindHandler(self._OnChange, ctrl, field, path)
        else:
            if not field.get("toggle") and field.get("type") not in (bool, list):
                result.append(wx.StaticText(parent, label=label, name=accname + "_label"))

            if field.get("component"):
                ctrl = field["component"](parent)
                if isinstance(ctrl, SQLiteTextCtrl):
                    ctrl.MinSize = (-1, 60)
                    ctrl.Traversable = True
                    ctrl.Wheelable   = False
                    ctrl.SetCaretLineVisible(False)
            elif bool is field.get("type"):
                if self._editmode:
                    ctrl = wx.CheckBox(parent, label=label)
                else: # Show ordinary label in view mode, checkbox goes very gray
                    myctrl = wx.CheckBox(parent)
                    mylabel = wx.StaticText(parent, label=label)
                    ctrl = wx.BoxSizer(wx.HORIZONTAL)
                    ctrl.Add(myctrl, border=5, flag=wx.RIGHT)
                    ctrl.Add(mylabel)
                    self._comps[fpath].append(myctrl)
                    if field.get("help"): myctrl.ToolTip = field["help"]
            elif "choices" in field:
                style = wx.CB_DROPDOWN | (0 if field.get("choicesedit") else wx.CB_READONLY)
                ctrl = wx.ComboBox(parent, size=(200, -1), style=style)
            else:
                ctrl = wx.TextCtrl(parent)

            result.append(ctrl)
            if isinstance(ctrl, wx.Control):
                self._BindHandler(self._OnChange, ctrl, field, path)

        for i, x in enumerate(result):
            if not isinstance(x, wx.Window): continue # for i, x
            self._comps[fpath].append(x)
            if not i:
                if field.get("help"): x.ToolTip = field["help"]
                continue # for i, x
            x.SetName(accname)
            if field.get("help"): x.ToolTip = field["help"]
        return result


    def _BindHandler(self, handler, ctrl, *args):
        """Binds appropriate handler for control type."""
        if isinstance(ctrl, wx.stc.StyledTextCtrl): events = [wx.stc.EVT_STC_CHANGE]
        elif isinstance(ctrl, wx.Button):   events = [wx.EVT_BUTTON]
        elif isinstance(ctrl, wx.CheckBox): events = [wx.EVT_CHECKBOX]
        elif isinstance(ctrl, wx.ComboBox): events = [wx.EVT_TEXT, wx.EVT_COMBOBOX]
        elif isinstance(ctrl, wx.ListBox): events = [wx.EVT_LISTBOX_DCLICK]
        else: events = [wx.EVT_TEXT]
        for e in events: self.Bind(e, functools.partial(handler, *args), ctrl)


    def _OnChange(self, field, path, event):
        """
        Handler for changing field content, updates data,
        refreshes linked field if any.
        """
        if self._ignore_change: return
        value, src = event.EventObject.Value, event.EventObject

        if isinstance(value, string_types) \
        and (not isinstance(src, wx.stc.StyledTextCtrl)
        or not value.strip()): value = value.strip()
        if isinstance(src, wx.ComboBox) and src.HasClientData():
            value = src.GetClientData(src.Selection)
        if value in (None, "") and field.get("dropempty"): self._DelValue(field, path)
        else: self._SetValue(field, value, path)
        if field.get("link"):
            name = field["link"]
            if callable(name):
                name = field["link"](self)
                linkfield = self._GetField(name, path)
            else:
                linkfield = self._GetField(name, path)
                if linkfield: self._DelValue(linkfield, path)
            if linkfield: self._PopulateField(linkfield, path)


    def _OnAddToList(self, field, path, event):
        """Handler from adding items from listbox on the left to the right."""
        indexes = []

        listbox1, listbox2 = (x for x in self._comps[path + (field["name"], )]
                              if isinstance(x, wx.ListBox))
        if isinstance(event.EventObject, wx.ListBox):
            indexes.append(event.GetSelection())
        else:
            indexes.extend(listbox1.GetSelections())
            if not indexes and listbox1.GetCount(): indexes.append(0)
        selecteds = list(map(listbox1.GetClientData, indexes))

        if field.get("exclusive"):
            for i in indexes[::-1]: listbox1.Delete(i)
        listbox2.AppendItems(list(map(self._Unprint, selecteds)))
        for j, x in enumerate(selecteds, listbox2.Count - len(selecteds)):
            listbox2.SetClientData(j, x)
        items2 = list(map(listbox2.GetClientData, range(listbox2.Count)))
        self._SetValue(field, items2, path)


    def _OnRemoveFromList(self, field, path, event):
        """Handler from removing items from listbox on the right."""
        indexes = []
        listbox1, listbox2 = (x for x in self._comps[path + (field["name"], )]
                              if isinstance(x, wx.ListBox))
        if isinstance(event.EventObject, wx.ListBox):
            indexes.append(event.GetSelection())
        else:
            indexes.extend(listbox2.GetSelections())
            if not indexes and listbox2.GetCount(): indexes.append(0)

        for i in indexes[::-1]: listbox2.Delete(i)
        items2 = list(map(listbox2.GetClientData, range(listbox2.Count)))
        allchoices = self._GetChoices(field, path)
        listbox1.SetItems([self._Unprint(x) for x in allchoices if x not in items2])
        for j, x in enumerate(x for x in allchoices if x not in items2):
            listbox1.SetClientData(j, x)
        self._SetValue(field, items2, path)


    def _OnMoveInList(self, field, path, direction, event):
        """Handler for moving selected items up/down within listbox."""
        _, listbox2 = (x for x in self._comps[path + (field["name"], )]
                       if isinstance(x, wx.ListBox))
        indexes = listbox2.GetSelections()
        items = list(map(listbox2.GetClientData, range(listbox2.Count)))

        if not indexes or direction < 0 and not indexes[0] \
        or direction > 0 and indexes[-1] == len(items) - 1: return

        for i in list(range(len(items)))[::-direction]:
            if i not in indexes: continue # for i
            i2 = i + direction
            items[i], items[i2] = items[i2], items[i]

        listbox2.SetItems(list(map(self._Unprint, items)))
        for j, x in enumerate(items): listbox2.SetClientData(j, x)
        for i in indexes: listbox2.Select(i + direction)
        self._SetValue(field, items, path)


    def _OnToggleField(self, field, path, ctrl, event=None):
        """
        Handler for toggling a field (and subfields) on/off, updates display.
        """
        fpath = path + (field["name"], )
        ctrls = [] # [(field, path, ctrl)]
        for c in self._comps.get(fpath, []):
            ctrls.append((field, path, c))
        if field.get("togglename") and field["togglename"].get("name"):
            for c in self._comps.get(fpath + (field["togglename"]["name"], ), []):
                if c not in (x for _, _, x in ctrls):
                    ctrls.append((field["togglename"], fpath, c))
        for f in field.get("children", []):
            for c in self._comps.get(fpath + (f["name"], ), []):
                if c not in (x for _, _, x in ctrls):
                    ctrls.append((f, fpath, c))

        on = event.EventObject.Value if event else ctrl.Value
        for f, p, c in ctrls:
            # Never hide field-level toggle itself
            if isinstance(c, wx.CheckBox) and f.get("toggle") and p == path:
                continue # for f, p, c

            fon = on
            # Hide field children that are toggled off
            if not isinstance(c, wx.CheckBox) and f.get("toggle") \
            and (p != path and self._GetValue(f, p) is None or
                 f == field.get("togglename") and
                 not getattr(self._toggles.get(fpath + (f["name"], )), "Value", False)
            ):
                fon = False

            c.Show(fon)
        if self._ignore_change: return

        if on and self._GetValue(field, path) is None:
            self._SetValue(field, {} if field.get("children") else "", path)
        if on and self._editmode and (path and
        field == self._GetField(path[-1], path[:-1]).get("togglename")
        or "text" == field.get("type")):
            edit = next((c for _, _, c in ctrls if isinstance(c, wx.TextCtrl)), None)
            if edit: edit.SetFocus(), edit.SelectAll() # Focus toggle's name-box
        if field.get("link"):
            name = field["link"]
            if callable(name):
                name = field["link"](self)
                linkfield = self._GetField(name, path)
            else:
                linkfield = self._GetField(name, path)
                if linkfield: self._DelValue(linkfield, path)
            if linkfield: self._PopulateField(linkfield, path)
        if self._footer: self._footer["populate"](self, self._footer["ctrl"])
        self._panel.Parent.SendSizeEvent()


    def _OnToggleLineNumbers(self, field, path, event):
        """Handler for toggling STC line numbers."""
        fpath = path + (field["name"], )
        ctrl, w = self._comps[fpath][0], 0
        if event.IsChecked():
            w = max(25, 5 + 10 * int(math.log(ctrl.LineCount, 10)))
        ctrl.SetMarginWidth(0, w)


    def _OnToggleWordWrap(self, field, path, event):
        """Handler for toggling STC word-wrap."""
        fpath = path + (field["name"], )
        ctrl = self._comps[fpath][0]
        mode = wx.stc.STC_WRAP_WORD if event.IsChecked() else wx.stc.STC_WRAP_NONE
        ctrl.SetWrapMode(mode)


    def _OnOpenFile(self, field, path, event=None):
        """Handler for opening file dialog and loading file contents to STC field."""
        dialog = wx.FileDialog(
            self, message="Open file", defaultFile="",
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_FILE_MUST_EXIST | wx.FD_OPEN |
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return
        fpath = path + (field["name"], )
        ctrl = self._comps[fpath][0]
        filename = dialog.GetPath()
        ctrl.LoadFile(filename)
        self._SetValue(field, ctrl.GetText(), path)


    def _OnSaveFile(self, field, path, event=None):
        """Handler for opening file dialog and saving STC field contents to file."""
        dialog = wx.FileDialog(
            self, message="Save file", defaultFile=field["name"],
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_OVERWRITE_PROMPT | wx.FD_SAVE |
                  wx.FD_CHANGE_DIR | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return
        fpath = path + (field["name"], )
        ctrl = self._comps[fpath][0]
        filename = dialog.GetPath()
        ctrl.SaveFile(filename)


    def _OnCopy(self, field, path, event=None):
        """Handler for copying STC field contents to clipboard."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject(self._GetValue(field, path))
            wx.TheClipboard.SetData(d)
            wx.TheClipboard.Close()


    def _OnPaste(self, field, path, event=None):
        """Handler for pasting clipboard contents to STC field."""
        if wx.TheClipboard.Open():
            d = wx.TextDataObject()
            if wx.TheClipboard.GetData(d):
                fpath = path + (field["name"], )
                self._comps[fpath][0].SetText(d.GetText())
                self._SetValue(field, d.GetText(), path)
            wx.TheClipboard.Close()


    def _OnClose(self, event):
        """Handler for clicking OK/Cancel, hides the dialog."""
        if self._onclose and not self._onclose(self._data): return
        self.EndModal(wx.ID_OK)



class HintedTextCtrl(wx.TextCtrl):
    """
    A text control with a hint text shown when no value, hidden when focused.
    Fires EVT_TEXT_ENTER event on text change.
    Clears entered value on pressing Escape.
    """


    def __init__(self, parent, hint="", escape=True, adjust=False, **kwargs):
        """
        @param   hint    hint text shown when no value and no focus
        @param   escape  whether to clear entered value on pressing Escape
        @param   adjust  whether to adjust hint colour more towards background
        """
        super(HintedTextCtrl, self).__init__(parent, **kwargs)
        self._text_colour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
        self._hint_colour = ColourManager.GetColour(wx.SYS_COLOUR_GRAYTEXT) if not adjust else \
                            ColourManager.Adjust(wx.SYS_COLOUR_GRAYTEXT, wx.SYS_COLOUR_WINDOW)
        self.SetForegroundColour(self._text_colour)

        self._hint = hint
        self._adjust = adjust
        self._hint_on = False # Whether textbox is filled with hint value
        self._ignore_change = False # Ignore value change
        if not self.Value:
            self.Value = self._hint
            self.SetForegroundColour(self._hint_colour)
            self._hint_on = True

        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,  self.OnSysColourChange)
        self.Bind(wx.EVT_SET_FOCUS,           self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,          self.OnFocus)
        self.Bind(wx.EVT_TEXT,                self.OnText)
        if escape: self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)


    def OnFocus(self, event):
        """
        Handler for focusing/unfocusing the control, shows/hides hint.
        """
        event.Skip() # Allow to propagate to parent, to show having focus
        self._ignore_change = True
        if self and self.FindFocus() is self:
            if self._hint_on:
                self.SetForegroundColour(self._text_colour)
                wx.TextCtrl.ChangeValue(self, "")
                self._hint_on = False
            self.SelectAll()
        elif self:
            if self._hint and not self.Value:
                # Control has been unfocused, set and colour hint
                wx.TextCtrl.ChangeValue(self, self._hint)
                self.SetForegroundColour(self._hint_colour)
                self._hint_on = True
        wx.CallAfter(setattr, self, "_ignore_change", False)


    def OnKeyDown(self, event):
        """Handler for keypress, empties text on escape."""
        event.Skip()
        if event.KeyCode in [wx.WXK_ESCAPE] and self.Value:
            self.Value = ""
            evt = wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER, self.Id)
            evt.EventObject = self
            evt.String = self.Value
            wx.PostEvent(self, evt)


    def OnText(self, event):
        """Handler for text change, fires TEXT_ENTER event."""
        event.Skip()
        if self._ignore_change: return
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER, self.Id)
        evt.SetEventObject(self)
        evt.SetString(self.Value)
        wx.PostEvent(self, evt)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates text colour."""
        event.Skip()
        self._text_colour = ColourManager.GetColour(wx.SYS_COLOUR_BTNTEXT)
        self._hint_colour = ColourManager.GetColour(wx.SYS_COLOUR_GRAYTEXT) if not self._adjust else \
                            ColourManager.Adjust(wx.SYS_COLOUR_GRAYTEXT, wx.SYS_COLOUR_WINDOW)
        def after():
            if not self: return
            colour = self._hint_colour if self._hint_on else self._text_colour
            self.SetForegroundColour(colour)
        wx.CallAfter(after)


    def SetBackgroundColour(self, colour):
        """Sets the background colour of the control."""
        if colour != self.BackgroundColour and self.Value \
        and not self._hint_on and "linux" in sys.platform:
            # Workaround for existing text background colour remaining same in Linux
            self._ignore_change = True
            sel, val = self.GetSelection(), self.Value
            wx.TextCtrl.SetValue(self, "")
            wx.TextCtrl.SetBackgroundColour(self, colour)
            wx.TextCtrl.SetValue(self, val)
            self.SetSelection(*sel)
            self._ignore_change = False
            return True
        return wx.TextCtrl.SetBackgroundColour(self, colour)
    BackgroundColour = property(wx.TextCtrl.GetBackgroundColour, SetBackgroundColour)


    def GetHint(self):
        """Returns the current hint."""
        return self._hint
    def SetHint(self, hint):
        """Sets the hint value."""
        self._hint = hint
        if self._hint_on or not self.Value and not self.HasFocus():
            self._ignore_change = True
            wx.TextCtrl.ChangeValue(self, self._hint)
            self.SetForegroundColour(self._hint_colour)
            self._hint_on = True
            wx.CallAfter(setattr, self, "_ignore_change", False)
    Hint = property(GetHint, SetHint)


    def GetValue(self):
        """
        Returns the current value in the text field, or empty string if filled
        with hint.
        """
        return "" if self._hint_on else wx.TextCtrl.GetValue(self)
    def SetValue(self, value):
        """Sets the value in the text entry field."""
        self._ignore_change = True
        if value or self.FindFocus() is self:
            self.SetForegroundColour(self._text_colour)
            self._hint_on = False
            wx.TextCtrl.SetValue(self, value)
        elif not value and self.FindFocus() is not self:
            wx.TextCtrl.SetValue(self, self._hint)
            self.SetForegroundColour(self._hint_colour)
            self._hint_on = True
        wx.CallAfter(setattr, self, "_ignore_change", False)
    Value = property(GetValue, SetValue)


    def ChangeValue(self, value):
        """Sets the new text control value."""
        self._ignore_change = True
        if value or self.FindFocus() is self:
            self.SetForegroundColour(self._text_colour)
            self._hint_on = False
            wx.TextCtrl.ChangeValue(self, value)
        elif not value and self.FindFocus() is not self:
            wx.TextCtrl.SetValue(self, self._hint)
            self.SetForegroundColour(self._hint_colour)
            self._hint_on = True
        wx.CallAfter(setattr, self, "_ignore_change", False)



class MessageDialog(wx.Dialog):
    """
    A modal message dialog that is closable from another thread.
    """

    BSTYLES = (wx.OK, wx.CANCEL,  wx.YES, wx.NO, wx.APPLY, wx.CLOSE, wx.HELP,
               wx.CANCEL_DEFAULT, wx.NO_DEFAULT)
    ISTYLES = {wx.ICON_INFORMATION: wx.ART_INFORMATION, wx.ICON_QUESTION: wx.ART_QUESTION,
               wx.ICON_WARNING:     wx.ART_WARNING,     wx.ICON_ERROR:    wx.ART_ERROR}
    IDS = {wx.OK: wx.ID_OK, wx.CANCEL: wx.ID_CANCEL, wx.YES: wx.ID_YES, wx.NO: wx.ID_NO,
           wx.APPLY: wx.ID_APPLY, wx.CLOSE: wx.ID_CLOSE, wx.HELP: wx.ID_HELP}
    AFFIRMS = (wx.YES,    wx.OK)
    ESCAPES = (wx.CANCEL, wx.NO, wx.CLOSE)

    def __init__(self, parent, message, caption=wx.MessageBoxCaptionStr,
                 style=wx.OK | wx.CAPTION | wx.CLOSE_BOX, pos=wx.DefaultPosition):

        bstyle, wstyle = 0, (style | wx.CAPTION | wx.CLOSE_BOX)
        for b in self.BSTYLES:
            if style & b: bstyle, wstyle = bstyle | b, wstyle ^ b
        for b in self.ISTYLES:
            if style & b: bstyle, wstyle = bstyle ^ b, wstyle ^ b
        super(MessageDialog, self).__init__(parent, title=caption, style=wstyle, pos=pos)

        self._text = wx.StaticText(self, label=message)
        self._icon = None
        for b, i in self.ISTYLES.items():
            if style & b:
                bmp = wx.ArtProvider.GetBitmap(i, wx.ART_FRAME_ICON, (32, 32))
                self._icon = wx.StaticBitmap(self, bitmap=bmp)
                break # for b, i

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_text    = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = self.CreateStdDialogButtonSizer(style)

        if self._icon: sizer_text.Add(self._icon, border=10, flag=wx.RIGHT)
        sizer_text.Add(self._text, flag=wx.GROW)
        self.Sizer.Add(sizer_text, border=10, flag=wx.ALL)
        self.Sizer.Add(sizer_buttons, border=10, flag=wx.ALL | wx.ALIGN_RIGHT)

        for b in self.BSTYLES:
            if bstyle & b and b in self.IDS:
                self.Bind(wx.EVT_BUTTON, self._OnButton, id=self.IDS[b])

        affirm = next((self.IDS[b] for b in self.AFFIRMS if bstyle & b), None)
        escape = next((self.IDS[b] for b in self.ESCAPES if bstyle & b), None)
        if affirm: self.SetAffirmativeId(affirm)
        if escape: self.SetEscapeId(escape)

        self.Layout()
        self.Fit()
        self.CenterOnParent()


    def _OnButton(self, event):
        self.EndModal(event.EventObject.Id)



class NonModalOKDialog(wx.Dialog):
    """A simple non-modal dialog with an OK button, stays on top of parent."""

    def __init__(self, parent, title, message):
        wx.Dialog.__init__(self, parent, title=title,
                           style=wx.CAPTION | wx.CLOSE_BOX |
                                 wx.FRAME_FLOAT_ON_PARENT)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.label_message = wx.StaticText(self, label=message)
        self.Sizer.Add(self.label_message, proportion=1,
                       border=2*8, flag=wx.ALL)
        sizer_buttons = self.CreateButtonSizer(wx.OK)
        self.Sizer.Add(sizer_buttons, proportion=0, border=8,
                       flag=wx.ALIGN_CENTER | wx.BOTTOM)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=wx.ID_OK)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Fit()
        self.Layout()
        self.CenterOnParent()
        self.Show()


    def OnClose(self, event):
        event.Skip()
        self.Close()



class NoteButton(wx.Panel, wx.Button):
    """
    A large button with a custom icon, main label, and additional note.
    Inspired by wx.CommandLinkButton, which does not support custom icons
    (at least not of wx 2.9.4).
    """

    """Stipple bitmap for focus marquee line."""
    BMP_MARQUEE = None

    def __init__(self, parent, label=wx.EmptyString, note=wx.EmptyString,
                 bmp=wx.NullBitmap, id=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0, name=wx.PanelNameStr):
        wx.Panel.__init__(self, parent, id, pos, size,
                          style | wx.FULL_REPAINT_ON_RESIZE, name)
        self._label = label
        self._note = note
        self._bmp = bmp
        self._bmp_disabled = bmp
        if bmp is not None and bmp.IsOk():
            img = bmp.ConvertToImage().ConvertToGreyscale()
            self._bmp_disabled = wx.Bitmap(img) if img.IsOk() else bmp
        self._hover = False # Whether button is being mouse hovered
        self._press = False # Whether button is being mouse pressed
        self._align = style & (wx.ALIGN_RIGHT | wx.ALIGN_CENTER)
        self._enabled = True
        self._size = self.Size

        # Wrapped texts for both label and note
        self._text_label = None
        self._text_note = None
        # (width, height, lineheight) for wrapped texts in current DC
        self._extent_label = None
        self._extent_note = None

        self._cursor_hover   = wx.Cursor(wx.CURSOR_HAND)
        self._cursor_default = wx.Cursor(wx.CURSOR_DEFAULT)

        self.Bind(wx.EVT_MOUSE_EVENTS,       self.OnMouseEvent)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.OnMouseCaptureLostEvent)
        self.Bind(wx.EVT_PAINT,              self.OnPaint)
        self.Bind(wx.EVT_SIZE,               self.OnSize)
        self.Bind(wx.EVT_SET_FOCUS,          self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnFocus)
        self.Bind(wx.EVT_ERASE_BACKGROUND,   self.OnEraseBackground)
        self.Bind(wx.EVT_KEY_DOWN,           self.OnKeyDown)
        self.Bind(wx.EVT_CHAR_HOOK,          self.OnChar)

        self.SetCursor(self._cursor_hover)
        ColourManager.Manage(self, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        self.WrapTexts()


    def GetMinSize(self):
        return self.DoGetBestSize()


    def DoGetBestSize(self):
        w = 40 if self.Size.width  < 40 else self.Size.width
        h = 40 if self.Size.height < 40 else self.Size.height
        if self._bmp:
            w = max(w, self._bmp.Size.width  + 20)
            h = max(h, self._bmp.Size.height + 20)
        if self._extent_label:
            h1 = 10 + self._bmp.Size.height + 10
            h2 = 10 + self._extent_label[1] + 10 + self._extent_note[1] + 10
            h  = max(h1, h2)
        return wx.Size(w, h)


    def Draw(self, dc):
        """Draws the control on the given device context."""
        global BRUSH, PEN
        width, height = self.GetClientSize()
        if not self.Shown or not (width > 20 and height > 20):
            return
        if not self._extent_label:
            self.WrapTexts()

        x, y = 10, 10
        if (self._align & wx.ALIGN_RIGHT):
            x = width - 10 - self._bmp.Size.width
        elif (self._align & wx.ALIGN_CENTER):
            x = 10 + (width - self.DoGetBestSize().width) // 2

        dc.Font = self.Font
        dc.Brush = BRUSH(self.BackgroundColour)
        if self.IsThisEnabled():
            dc.TextForeground = self.ForegroundColour
        else:
            graycolour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
            dc.TextForeground = graycolour
        dc.Pen = PEN(dc.TextForeground)
        dc.Clear()

        is_focused = (self.FindFocus() is self)

        if is_focused:
            # Draw simple border around button
            dc.Brush = wx.TRANSPARENT_BRUSH
            dc.DrawRectangle(0, 0, width, height)

            # Create cached focus marquee
            if not NoteButton.BMP_MARQUEE:
                NoteButton.BMP_MARQUEE = wx.Bitmap(2, 2)
                dc_bmp = wx.MemoryDC()
                dc_bmp.SelectObject(NoteButton.BMP_MARQUEE)
                dc_bmp.Background = wx.Brush(self.BackgroundColour)
                dc_bmp.Clear()
                dc_bmp.Pen = wx.Pen(self.ForegroundColour)
                dc_bmp.DrawPointList([(0, 1), (1, 0)])
                dc_bmp.SelectObject(wx.NullBitmap)

            # Draw focus marquee
            try:
                pen = PEN(dc.TextForeground, 1, wx.PENSTYLE_STIPPLE)
                pen.Stipple, dc.Pen = NoteButton.BMP_MARQUEE, pen
                dc.DrawRectangle(4, 4, width - 8, height - 8)
            except wx.wxAssertionError: # Gtk does not support stippled pens
                brush = BRUSH(dc.TextForeground)
                brush.SetStipple(NoteButton.BMP_MARQUEE)
                dc.Brush = brush
                dc.Pen = wx.TRANSPARENT_PEN
                dc.DrawRectangle(4, 4, width - 8, height - 8)
                dc.Brush = BRUSH(self.BackgroundColour)
                dc.DrawRectangle(5, 5, width - 10, height - 10)
            dc.Pen = PEN(dc.TextForeground)

        if self._press or (is_focused and any(wx.GetKeyState(x) for x in KEYS.SPACE)):
            # Button is being clicked with mouse: create sunken effect
            colours = [(128, 128, 128)] * 2
            lines   = [(1, 1, width - 2, 1), (1, 1, 1, height - 2)]
            dc.DrawLineList(lines, [PEN(wx.Colour(*c)) for c in colours])
            x += 1; y += 1
        elif self._hover and self.IsThisEnabled():
            # Button is being hovered with mouse: create raised effect
            colours  = [(255, 255, 255)] * 2
            if wx.WHITE == self.BackgroundColour:
                colours =  [(158, 158, 158)] * 2
            lines    = [(0, 0, 0, height - 1), (0, 0, width - 1, 0)]
            colours += [(128, 128, 128)] * 2
            lines   += [(1, height - 2, width - 1, height - 2),
                        (width - 2, 1, width - 2, height - 2)]
            colours += [(64, 64, 64)] * 2
            lines   += [(0, height - 1, width, height - 1),
                        (width - 1, 0, width - 1, height - 1)]
            dc.DrawLineList(lines, [PEN(wx.Colour(*c)) for c in colours])

        if self._bmp:
            bmp = self._bmp if self.IsThisEnabled() else self._bmp_disabled
            dc.DrawBitmap(bmp, x, y)

        if self._align & wx.ALIGN_RIGHT:
            x -= 10 + max(self._extent_label[0], self._extent_note[0])
        else:
            x += self._bmp.Size.width + 10

        # Draw label and accelerator key underlines
        dc.Font = wx.Font(dc.Font.PointSize, dc.Font.Family, dc.Font.Style,
                          wx.FONTWEIGHT_BOLD, faceName=dc.Font.FaceName)
        text_label = self._text_label
        if "&" in self._label:
            text_label, h = "", y - 1
            dc.Pen = wx.Pen(dc.TextForeground)
            for line in self._text_label.splitlines():
                i, chars = 0, ""
                while i < len(line):
                    if "&" == line[i]:
                        i += 1
                        if i < len(line) and "&" != line[i]:
                            extent = dc.GetTextExtent(line[i])
                            extent_all = dc.GetTextExtent(chars)
                            x1, y1 = x + extent_all[0], h + extent[1]
                            dc.DrawLine(x1, y1, x1 + extent[0], y1)
                        elif i < len(line):
                            chars += line[i] # Double ampersand: add as one
                    if i < len(line):
                        chars += line[i]
                    i += 1
                h += self._extent_label[1]
                text_label += chars + "\n"
        dc.DrawText(text_label, x, y)

        # Draw note
        _, label_h = dc.GetMultiLineTextExtent(self._text_label)
        y += label_h + 10
        dc.Font = self.Font
        dc.DrawText(self._text_note, x, y)


    def WrapTexts(self):
        """Wraps button texts to current control size."""
        self._text_label, self._text_note = self._label, self._note

        if not self._label and not self._note:
            self._extent_label = self._extent_note = (0, 0)
            return

        WORDWRAP = wx.lib.wordwrap.wordwrap
        width, height = self.Size
        if width > 20 and height > 20:
            dc = wx.ClientDC(self)
        else: # Not properly sized yet: assume a reasonably fitting size
            dc, width, height = wx.MemoryDC(), 500, 100
            dc.SelectObject(wx.Bitmap(500, 100))
        dc.Font = self.Font
        x = 10 + self._bmp.Size.width + 10
        self._text_note = WORDWRAP(self._text_note, width - 10 - x, dc)
        dc.Font = wx.Font(dc.Font.PointSize, dc.Font.Family, dc.Font.Style,
                          wx.FONTWEIGHT_BOLD, faceName=dc.Font.FaceName)
        self._text_label = WORDWRAP(self._text_label, width - 10 - x, dc)
        self._extent_label = dc.GetMultiLineTextExtent(self._text_label)
        self._extent_note = dc.GetMultiLineTextExtent(self._text_note)


    def OnPaint(self, event):
        """Handler for paint event, calls Draw()."""
        dc = wx.BufferedPaintDC(self)
        self.Draw(dc)


    def OnSize(self, event):
        """Handler for size event, resizes texts and repaints control."""
        event.Skip()
        if event.Size != self._size:
            self._size = event.Size
            wx.CallAfter(lambda: self and (self.WrapTexts(), self.Refresh(),
                         self.InvalidateBestSize(), self.Parent.Layout()))


    def OnFocus(self, event):
        """Handler for receiving/losing focus, repaints control."""
        if self: # Might get called when control already destroyed
            self.Refresh()


    def OnEraseBackground(self, event):
        """Handles the wx.EVT_ERASE_BACKGROUND event."""
        pass # Intentionally empty to reduce flicker.


    def OnKeyDown(self, event):
        """Refreshes display if pressing space (showing sunken state)."""
        if not event.AltDown() and event.UnicodeKey in KEYS.SPACE:
            self.Refresh()
        else: event.Skip()


    def OnChar(self, event):
        """Queues firing button event on pressing space or enter."""
        skip = True
        if not event.AltDown() \
        and event.UnicodeKey in KEYS.SPACE + KEYS.ENTER:
            button_event = wx.PyCommandEvent(wx.EVT_BUTTON.typeId, self.Id)
            button_event.EventObject = self
            wx.CallLater(1, wx.PostEvent, self, button_event)
            skip = False
            self.Refresh()
        if skip: event.Skip()


    def OnMouseEvent(self, event):
        """
        Mouse handler, creates hover/press border effects and fires button
        event on click.
        """
        event.Skip()
        refresh = False
        if event.Entering():
            refresh = True
            self._hover = True
            if self.HasCapture():
                self._press = True
        elif event.Leaving():
            refresh = True
            self._hover = self._press = False
        elif event.LeftDown():
            refresh = True
            self._press = True
            self.CaptureMouse()
        elif event.LeftUp():
            refresh = True
            self._press = False
            if self.HasCapture():
                self.ReleaseMouse()
                if self._hover:
                    btnevent = wx.PyCommandEvent(wx.EVT_BUTTON.typeId, self.Id)
                    btnevent.EventObject = self
                    wx.PostEvent(self, btnevent)
        if refresh:
            self.Refresh()


    def OnMouseCaptureLostEvent(self, event):
        """Handles MouseCaptureLostEvent, updating control UI if needed."""
        self._hover = self._press = False


    def ShouldInheritColours(self):
        return True


    def InheritsBackgroundColour(self):
        return True


    def Disable(self):
        return self.Enable(False)


    def Enable(self, enable=True):
        """
        Enable or disable this control for user input, returns True if the
        control state was changed.
        """
        result = (self._enabled != enable)
        if not result: return result

        self._enabled = enable
        wx.Panel.Enable(self, enable)
        self.Refresh()
        return result
    def IsEnabled(self): return wx.Panel.IsEnabled(self)
    Enabled = property(IsEnabled, Enable)


    def IsThisEnabled(self):
        """Returns the internal enabled state, independent of parent state."""
        if hasattr(wx.Panel, "IsThisEnabled"):
            result = wx.Panel.IsThisEnabled(self)
        else:
            result = self._enabled
        return result


    def GetLabel(self):
        return self._label
    def SetLabel(self, label):
        if label != self._label:
            self._label = label
            self.WrapTexts()
            self.InvalidateBestSize()
            self.Refresh()
    Label = property(GetLabel, SetLabel)


    def SetNote(self, note):
        if note != self._note:
            self._note = note
            self.WrapTexts()
            self.InvalidateBestSize()
            self.Refresh()
    def GetNote(self):
        return self._note
    Note = property(GetNote, SetNote)



class ProgressWindow(wx.Dialog):
    """
    A simple non-modal ProgressDialog, stays on top of parent frame.
    """

    def __init__(self, parent, title, message="", maximum=100, cancel=True,
                 style=wx.CAPTION | wx.CLOSE_BOX | wx.FRAME_FLOAT_ON_PARENT,
                 agwStyle=wx.ALIGN_LEFT):
        """
        @param   message   message shown on top of gauge
        @param   maximum   gauge maximum value
        @param   cancel    whether dialog is cancelable and has cancel-button,
                           optionally a callable returning whether to cancel
        @param   agwStyle  message alignment flags
        """
        wx.Dialog.__init__(self, parent=parent, title=title, style=style)
        self._is_cancelled = False
        self._oncancel = cancel if callable(cancel) else lambda *a, **kw: True

        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)

        label = self._label = wx.StaticText(self, label=message, style=agwStyle)
        sizer.Add(label, border=2*8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.GROW)
        gauge = self._gauge = wx.Gauge(self, range=maximum, size=(300,-1),
                                       style=wx.GA_HORIZONTAL | wx.PD_SMOOTH)
        sizer.Add(gauge, border=2*8, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.GROW)
        gauge.Value = 0
        if cancel:
            self._button_cancel = wx.Button(self, id=wx.ID_CANCEL)
            sizer.Add(self._button_cancel, border=8,
                      flag=wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL)
            self.Bind(wx.EVT_BUTTON, self._OnCancel, self._button_cancel)
            self.Bind(wx.EVT_CLOSE,  self._OnCancel)
        else:
            sizer.Add((8, 8))

        self.Fit()
        self.Layout()
        self.Refresh()
        self.Show()


    def Update(self, value, message=None):
        """
        Updates the progressbar value, and message if given.

        @return  False if dialog was cancelled by user, True otherwise
        """
        if message is not None:
            self._label.Label = message
        self._gauge.Value = value
        self.Layout()
        return not self._is_cancelled


    def Pulse(self, pulse=True):
        """Sets the progress bar to pulse, or stops pulse."""
        if pulse: self._gauge.Pulse()
        else: self._gauge.Value = self._gauge.Value


    def GetValue(self):
        """Returns progress bar value."""
        return self._gauge.Value
    def SetValue(self, value):
        """Sets progress bar value."""
        self._gauge.Value = value
    Value = property(GetValue, SetValue)


    def GetMessage(self):
        """Returns message value."""
        return self._label.Label
    def SetMessage(self, message):
        """Sets message value."""
        self._label.Label = message
        self.Fit()
        self.Layout()
    Message = property(GetMessage, SetMessage)


    def SetGaugeForegroundColour(self, colour):
        self._gauge.ForegroundColour = colour


    def _OnCancel(self, event):
        """Handler for cancelling the dialog, hides the window."""
        if not self._oncancel(): return
        self._is_cancelled = True
        self.Hide()



class PropertyDialog(wx.Dialog):
    """
    Dialog for displaying an editable property grid. Supports strings,
    integers, booleans, and wx classes like wx.Size interpreted as tuples.
    """


    COLOUR_ERROR = wx.RED

    def __init__(self, parent, title):
        wx.Dialog.__init__(self, parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self.properties = [] # [(name, type, orig_val, default, label, ctrl), ]

        panelwrap = wx.Panel(self)
        panel = self.panel = wx.ScrolledWindow(panelwrap)

        self.Sizer      = wx.BoxSizer(wx.VERTICAL)
        panelwrap.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel.Sizer     = wx.BoxSizer(wx.VERTICAL)
        sizer_items = self.sizer_items = wx.GridBagSizer(hgap=5, vgap=1)

        sizer_buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        button_ok     = next((x.Window for x in sizer_buttons.Children
                              if x.Window and wx.ID_OK == x.Window.Id), None)
        button_reset  = wx.Button(self, label="Restore defaults")
        if button_ok:
            button_ok.Label = "Save"
            button_reset.MoveAfterInTabOrder(button_ok)

        panel.Sizer.Add(sizer_items, proportion=1, border=5, flag=wx.GROW | wx.RIGHT)
        panelwrap.Sizer.Add(panel, proportion=1, border=10, flag=wx.GROW | wx.ALL)
        self.Sizer.Add(panelwrap, proportion=1, flag=wx.GROW)
        sizer_buttons.Insert(min(2, sizer_buttons.ItemCount), button_reset)
        self.Sizer.Add(sizer_buttons, border=10, flag=wx.ALL | wx.ALIGN_RIGHT)

        self.Bind(wx.EVT_BUTTON, self._OnSave,   id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._OnReset,  button_reset)
        self.Bind(wx.EVT_BUTTON, self._OnReset,  id=wx.ID_APPLY)

        self.MinSize, self.Size = (320, 180), (420, 420)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def AddProperty(self, name, value, help="", default=None, typeclass=text_type):
        """Adds a property to the frame."""
        row = len(self.properties) * 2
        label = wx.StaticText(self.panel, label=name)
        if bool == typeclass:
            ctrl = wx.CheckBox(self.panel)
            ctrl_flag = wx.ALIGN_CENTER_VERTICAL
            label_handler = lambda e: ctrl.SetValue(not ctrl.IsChecked())
        else:
            ctrl = wx.TextCtrl(self.panel, style=wx.BORDER_SIMPLE)
            ctrl_flag = wx.GROW | wx.ALIGN_CENTER_VERTICAL
            label_handler = lambda e: (ctrl.SetFocus(), ctrl.SelectAll())
        tip = wx.StaticText(self.panel, label=help.replace("&", "&&"))

        ctrl.Value = self._GetValueForCtrl(value, typeclass)
        label.ToolTip = "Value of type %s%s." % (typeclass.__name__,
                        "" if default is None else ", default %s" % repr(default))
        ctrl.ToolTip = label.ToolTip.Tip
        ColourManager.Manage(tip, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)
        tipfont, tipfont.PixelSize = tip.Font, (0, 9)
        tip.Font = tipfont
        tip.Wrap(self.panel.Size[0] - 30)
        for x in (label, tip): x.Bind(wx.EVT_LEFT_UP, label_handler)

        self.sizer_items.Add(label, pos=(row, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        self.sizer_items.Add(ctrl, pos=(row, 1), flag=ctrl_flag)
        self.sizer_items.Add(tip, pos=(row + 1, 0), span=(1, 2),
                             flag=wx.BOTTOM, border=3)
        self.properties.append((name, typeclass, value, default, label, ctrl))


    def Realize(self):
        """Lays out the properties, to be called when adding is completed."""
        self.panel.SetScrollRate(0, 20)
        self.sizer_items.AddGrowableCol(1) # Grow ctrl column


    def GetProperties(self):
        """
        Returns the current legal property values, as [(name, value), ].
        Illegal values are replaced with initial values.
        """
        result = []
        for name, typeclass, orig, default, label, ctrl in self.properties:
            value = self._GetValueForType(ctrl.Value, typeclass)
            result.append((name, orig if value is None else value))
        return result


    def _OnSave(self, event):
        """
        Handler for clicking save, checks values and hides the dialog if all
        ok, highlights errors otherwise.
        """
        all_ok = True
        for name, typeclass, orig, default, label, ctrl in self.properties:
            if self._GetValueForType(ctrl.Value, typeclass) is None:
                all_ok = False
                label.ForegroundColour = ctrl.ForegroundColour = self.COLOUR_ERROR
            else:
                label.ForegroundColour = ctrl.ForegroundColour = self.ForegroundColour
        event.Skip() if all_ok else self.Refresh()


    def _OnReset(self, event):
        """Handler for clicking reset, restores default values if available."""
        for name, typeclass, orig, default, label, ctrl in self.properties:
            if default is not None:
                ctrl.Value = self._GetValueForCtrl(default, typeclass)
            if self.COLOUR_ERROR == ctrl.ForegroundColour:
                label.ForegroundColour = ctrl.ForegroundColour = self.ForegroundColour
        self.Refresh()


    def _GetValueForType(self, value, typeclass):
        """Returns value in type expected, or None on failure."""
        try:
            result = typeclass(value)
            if isinstance(result, integer_types) and result < 0:
                raise ValueError() # Reject negative numbers
            isinstance(result, string_types) and result.strip()[0] # Reject empty
            return result
        except Exception:
            return None


    def _GetValueForCtrl(self, value, typeclass):
        """Returns the value in type suitable for appropriate wx control."""
        value = tuple(value) if isinstance(value, list) else value
        if isinstance(value, tuple):
            value = tuple(str(x) if isinstance(x, text_type) else x for x in value)
        return "" if value is None else value \
               if isinstance(value, (string_types, bool)) else text_type(value)



class ResizeWidget(wx.lib.resizewidget.ResizeWidget):
    """
    A specialized panel that provides a resize handle for a widget,
    with configurable resize directions. Sizes to fit on double-clicking
    resize handle (sticky).
    """
    BOTH = wx.HORIZONTAL | wx.VERTICAL


    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.TAB_TRAVERSAL, name="", direction=wx.HORIZONTAL | wx.VERTICAL):
        """
        @param   direction  either wx.HORIZONTAL and/or wx.VERTICAL to allow
                            resize in one or both directions
        """
        self._direction = direction if direction & self.BOTH else self.BOTH
        self._fit = False
        self._ignoresizeevt = False
        super(ResizeWidget, self).__init__(parent, id, pos, size, style, name)
        self.ToolTip = "Drag to resize, double-click to fit"
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDClick)
        self.Bind(wx.EVT_SIZE,        self.OnSize)

    def GetDirection(self):
        """Returns the resize direction of the window."""
        return self._direction
    def SetDirection(self, direction):
        """
        Sets resize direction of the window,
        either wx.HORIZONTAL and/or wx.VERTICAL.
        """
        self._direction = direction if direction & self.BOTH else self.BOTH
    Direction = property(GetDirection, SetDirection)


    def Fit(self):
        """Resizes control to fit managed child."""
        def doFit():
            size = self.GetBestChildSize()
            if size == self.ManagedChild.Size: return

            self.ManagedChild.Size = size
            self.AdjustToSize(size)
            self.Parent.ContainingSizer.Layout()
        self._fit = True
        doFit()
        wx.CallLater(1, doFit) # Might need recalculation after first layout


    def GetBestChildSize(self):
        """Returns size for managed child fitting content in resize directions."""
        linesmax, widthmax = -1, -1
        if "posix" == os.name:
            # GetLineLength() does not account for wrapped lines in linux
            w, dc = self.ManagedChild.Size[0], wx.ClientDC(self.ManagedChild)
            t = wx.lib.wordwrap.wordwrap(self.ManagedChild.Value, w, dc)
            linesmax = t.count("\n")
            # DoGetBorderSize() appears not implemented under Gtk
            borderw, borderh = (x / 2. for x in self.ManagedChild.GetWindowBorderSize())
        else:
            while self.ManagedChild.GetLineLength(linesmax + 1) >= 0:
                linesmax += 1
                t = self.ManagedChild.GetLineText(linesmax)
                widthmax = max(widthmax, self.ManagedChild.GetTextExtent(t)[0])
            borderw, borderh = self.ManagedChild.DoGetBorderSize()
        _, charh = self.ManagedChild.GetTextExtent("X")
        size = self.Size
        size[0] -= wx.lib.resizewidget.RW_THICKNESS
        size[1] -= wx.lib.resizewidget.RW_THICKNESS

        if self._direction & wx.HORIZONTAL:
            size[0] = 2 * borderw + widthmax
        if self._direction & wx.VERTICAL:
            size[1] = 2 * borderh + charh * (linesmax + 1)
        return size


    def OnLeftDClick(self, event=None):
        """Handles the wx.EVT_LEFT_DCLICK event, toggling fit-mode on or off."""
        if self._fit:
            self._fit = False
            self.ManagedChild.Size = self.ManagedChild.EffectiveMinSize
            self.AdjustToSize(self.ManagedChild.Size)
            self.Parent.ContainingSizer.Layout()
        else: self.Fit()


    def OnLeftUp(self, evt):
        """Handles the wx.EVT_LEFT_UP event."""
        self._dragPos = None
        if self.HasCapture():
            self.ReleaseMouse()
            self.InvalidateBestSize()


    def OnMouseLeave(self, event):
        """Handles the wx.EVT_LEAVE_WINDOW event."""
        if not self.HasCapture() and self._resizeCursor:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
            self._resizeCursor = False


    def OnMouseMove(self, evt):
        """
        Handles wx.EVT_MOTION event. Overrides inherited .OnMouseMove
        to constrain resize to configured directions only.
        """
        pos = evt.GetPosition()
        if self._hitTest(pos) and self._resizeEnabled:
            if not self._resizeCursor:
                self.SetCursor(wx.Cursor(wx.CURSOR_SIZENWSE))
                self._resizeCursor = True
        elif not self.HasCapture():
            if self._resizeCursor:
                self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
                self._resizeCursor = False

        if evt.Dragging() and self._dragPos is not None:
            self._fit = False
            delta, posDelta = wx.Size(), self._dragPos - pos
            if self._direction & wx.HORIZONTAL: delta[0] = posDelta[0]
            if self._direction & wx.VERTICAL:   delta[1] = posDelta[1]
            newSize = self.GetSize() - delta
            self._adjustNewSize(newSize)
            if newSize != self.GetSize():
                self.SetSize(newSize)
                self._dragPos = pos
                self._bestSize = newSize
                self.InvalidateBestSize()
                self._sendEvent()


    def OnSize(self, evt):
        """Handles wx.EVT_SIZE event, resizing control if control fitted."""
        if self._ignoresizeevt: return
        super(ResizeWidget, self).OnSize(evt)
        if self._fit and not self._ignoresizeevt:
            self._ignoresizeevt = True
            wx.CallAfter(self.Fit)
            wx.CallLater(100, setattr, self, "_ignoresizeevt", False)


    def DoGetBestSize(self):
        """Returns the best size."""
        if self.HasCapture(): return self._bestSize

        HANDLE = wx.lib.resizewidget.RW_THICKNESS
        c = self.ManagedChild
        size, csize = wx.Size(*self._bestSize), c.EffectiveMinSize
        # Allow external resizing to function from child size
        if not self._direction & wx.HORIZONTAL: size[0] = csize[0] + HANDLE
        if not self._direction & wx.VERTICAL:   size[1] = csize[1] + HANDLE

        return size



class SortableUltimateListCtrl(wx.lib.agw.ultimatelistctrl.UltimateListCtrl,
                               wx.lib.mixins.listctrl.ColumnSorterMixin):
    """
    A sortable list control that can be batch-populated, autosizes its columns,
    can be filtered by string value matched on any row column,
    supports clipboard copy.
    """
    COL_PADDING = 30

    SORT_ARROW_UP = wx.lib.embeddedimage.PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAADxJ"
        "REFUOI1jZGRiZqAEMFGke2gY8P/f3/9kGwDTjM8QnAaga8JlCG3CAJdt2MQxDCAUaOjyjKMp"
        "cRAYAABS2CPsss3BWQAAAABJRU5ErkJggg==")

    #----------------------------------------------------------------------
    SORT_ARROW_DOWN = wx.lib.embeddedimage.PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAEhJ"
        "REFUOI1jZGRiZqAEMFGke9QABgYGBgYWdIH///7+J6SJkYmZEacLkCUJacZqAD5DsInTLhDR"
        "bcPlKrwugGnCFy6Mo3mBAQChDgRlP4RC7wAAAABJRU5ErkJggg==")


    def __init__(self, *args, **kwargs):
        kwargs.setdefault("agwStyle", 0)
        if hasattr(wx.lib.agw.ultimatelistctrl, "ULC_USER_ROW_HEIGHT"):
            kwargs["agwStyle"] |= wx.lib.agw.ultimatelistctrl.ULC_USER_ROW_HEIGHT
        if hasattr(wx.lib.agw.ultimatelistctrl, "ULC_SHOW_TOOLTIPS"):
            kwargs["agwStyle"] |= wx.lib.agw.ultimatelistctrl.ULC_SHOW_TOOLTIPS

        wx.lib.agw.ultimatelistctrl.UltimateListCtrl.__init__(self, *args, **kwargs)
        wx.lib.mixins.listctrl.ColumnSorterMixin.__init__(self, 0)
        try:
            ColourManager.Manage(self._headerWin, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
            ColourManager.Manage(self._mainWin,   "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        except Exception: pass
        self.itemDataMap = {}   # {item_id: [values], } for ColumnSorterMixin
        self._data_map = {}     # {item_id: row dict, } currently visible data
        self._id_rows = []      # [(item_id, {row dict}), ] all data items
        self._id_images = {}    # {item_id: imageIds}
        self._columns = []      # [(name, label), ]
        self._filter = ""       # Filter string
        self._col_widths = {}   # {col_index: width in pixels, }
        self._col_maxwidth = -1 # Maximum width for auto-sized columns
        self._top_row = None    # List top row data dictionary, if any
        self._drag_start = None # Item index currently dragged
        self.counter = lambda x={"c": 0}: x.update(c=1+x["c"]) or x["c"]
        self.AssignImageList(self._CreateImageList(), wx.IMAGE_LIST_SMALL)

        # Default row column formatter function
        frmt = lambda: lambda r, c: "" if r.get(c) is None else text_type(r[c])
        self._formatters = collections.defaultdict(frmt)
        id_copy = wx.NewIdRef().Id
        entries = [(wx.ACCEL_CMD, x, id_copy) for x in KEYS.INSERT + (ord("C"), )]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))
        self.Bind(wx.EVT_MENU, self.OnCopy, id=id_copy)
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnSort)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_DRAG,  self.OnDragStart)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_END_DRAG,    self.OnDragStop)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_RDRAG, self.OnDragCancel)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)


    def GetScrollThumb(self, orientation):
        """Returns the scrollbar size in pixels."""
        # Workaround for wxpython v4 bug of missing orientation parameter
        return self._mainWin.GetScrollThumb(orientation) if self._mainWin else 0


    def GetScrollRange(self, orientation):
        """Returns the scrollbar range in pixels."""
        # Workaround for wxpython v4 bug of missing orientation parameter
        return self._mainWin.GetScrollRange(orientation) if self._mainWin else 0


    def GetSortImages(self):
        """For ColumnSorterMixin."""
        return (0, 1)


    def AssignImages(self, images):
        """
        Assigns images associated with the control.
        SetTopRow/AppendRow/InsertRow/Populate use imageIds from this list.

        @param   images  list of wx.Bitmap objects
        """
        for x in images: self.GetImageList(wx.IMAGE_LIST_SMALL).Add(x)
        if hasattr(self, "SetUserLineHeight"):
            h = images[0].Size[1]
            self.SetUserLineHeight(int(h * 1.5))


    def SetTopRow(self, data, imageIds=()):
        """
        Adds special top row to list, not subject to sorting or filtering.

        @param   data      item data dictionary
        @param   imageIds  list of indexes for the images associated to top row
        """
        self._top_row = data
        if imageIds: self._id_images[-1] = self._ConvertImageIds(imageIds)
        else: self._id_images.pop(-1, None)
        self._PopulateTopRow()


    def SetColumnFormatters(self, formatters):
        """
        Sets the functions used for formatting displayed column values.

        @param   formatters  {col_name: function(rowdict, col_name), }
        """
        self._formatters.clear()
        if formatters: self._formatters.update(formatters)


    def Populate(self, rows, imageIds=()):
        """
        Populates the control with rows, clearing previous data, if any.
        Re-selects the previously selected row, if any.

        @param   rows      a list of data dicts
        @param   imageIds  list of indexes for the images associated to rows
        """
        if rows: self._col_widths.clear()
        self._id_rows[:] = []
        if imageIds: imageIds = self._ConvertImageIds(imageIds)
        for r in rows:
            item_id = self.counter()
            self._id_rows += [(item_id, r)]
            if imageIds: self._id_images[item_id] = imageIds
        self.RefreshRows()


    def AppendRow(self, data, imageIds=()):
        """
        Appends the specified data to the control as a new row.

        @param   data      item data dictionary
        @param   imageIds  list of indexes for the images associated to this row
        """
        self.InsertRow(self.GetItemCount(), data, imageIds)


    def InsertRow(self, index, data, imageIds=()):
        """
        Inserts the specified data to the control at specified index as a new row.

        @param   data      item data dictionary
        @param   imageIds  list of indexes for the images associated to this row
        """
        item_id = self.counter()
        if imageIds:
            imageIds = self._id_images[item_id] = self._ConvertImageIds(imageIds)

        index = min(index, self.GetItemCount())
        if self._RowMatchesFilter(data):
            columns = [c[0] for c in self._columns]
            for i, col_name in enumerate(columns):
                col_value = self._formatters[col_name](data, col_name)

                if imageIds and not i: self.InsertImageStringItem(index, col_value, imageIds)
                elif not i: self.InsertStringItem(index, col_value)
                else: self.SetStringItem(index, i, col_value)
            self.SetItemData(index, item_id)
            self.itemDataMap[item_id] = [data[c] for c in columns]
            self._data_map[item_id] = data
            self.SetItemTextColour(index, self.ForegroundColour)
            self.SetItemBackgroundColour(index, self.BackgroundColour)
        self._id_rows.insert(index - (1 if self._top_row else 0), (item_id, data))
        if self.GetSortState()[0] >= 0:
            self.SortListItems(*self.GetSortState())


    def GetFilter(self):
        return self._filter
    def SetFilter(self, value, force_refresh=False):
        """
        Sets the text to filter list by. Any row not containing the text in any
        column will be hidden.

        @param   force_refresh  if True, all content is refreshed even if
                                filter value did not change
        """
        if force_refresh or value != self._filter:
            self._filter = value
            if force_refresh: self._col_widths.clear()
            if self._id_rows: self.RefreshRows()


    def FindItem(self, text):
        """
        Find an item whose primary label matches the text.

        @return   item index, or -1 if not found
        """
        for i in range(self.GetItemCount()):
            if self.GetItemText(i) == text: return i
        return -1


    def RefreshRows(self):
        """
        Clears the list and inserts all unfiltered rows, auto-sizing the
        columns.
        """
        selected_ids, selected_idxs, selected = [], [], self.GetFirstSelected()
        while selected >= 0:
            selected_ids.append(self.GetItemData(selected))
            selected_idxs.append(selected)
            selected = self.GetNextSelected(selected)

        self.Freeze()
        try:
            for i in selected_idxs:
                self._mainWin.SendNotify(i, wx.wxEVT_COMMAND_LIST_ITEM_DESELECTED)
            wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
            self._PopulateTopRow()
            self._PopulateRows(selected_ids)
        finally: self.Thaw()


    def RefreshRow(self, row):
        """Refreshes row with specified index from item data."""
        if not self.GetItemCount(): return
        if row < 0: row = row % self.GetItemCount()
        data = not row and self._top_row or self._data_map.get(self.GetItemData(row))
        if not data: return

        for i, col_name in enumerate([c[0] for c in self._columns]):
            col_value = self._formatters[col_name](data, col_name)
            self.SetStringItem(row, i, col_value)
        self.SetItemTextColour(row,       self.ForegroundColour)
        self.SetItemBackgroundColour(row, self.BackgroundColour)


    def ResetColumnWidths(self):
        """Resets the stored column widths, triggering a fresh autolayout."""
        self._col_widths.clear()
        self.RefreshRows()


    def DeleteItem(self, index):
        """Deletes the row at the specified index."""
        item_id = self.GetItemData(index)
        data = self._data_map.get(item_id)
        del self._data_map[item_id]
        self._id_rows.remove((item_id, data))
        self._id_images.pop(item_id, None)
        return wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteItem(self, index)


    def DeleteAllItems(self):
        """Deletes all items data and clears the list."""
        self.itemDataMap = {}
        self._data_map = {}
        self._id_rows = []
        for item_id in self._id_images:
            if item_id >= 0: self._id_images.pop(item_id)
        self.Freeze()
        try:
            result = wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
            self._PopulateTopRow()
        finally: self.Thaw()
        return result


    def GetItemCountFull(self):
        """Returns the full row count, including items hidden by filter."""
        return len(self._id_rows) + bool(self._top_row)


    def GetItemTextFull(self, idx):
        """Returns item text by index, including items hidden by filter."""
        data, col_name = self._id_rows[idx][-1], self._columns[0][0]
        return self._formatters[col_name](data, col_name)


    def SetColumnsMaxWidth(self, width):
        """Sets the maximum width for all columns, used in auto-size."""
        self._col_maxwidth = width


    def SetColumns(self, columns):
        """
        Sets the list columns, clearing current columns if any.

        @param   columns  [(column name, column label), ]
        """
        self.ClearAll()
        self.SetColumnCount(len(columns))
        for i, (name, label) in enumerate(columns):
            col_label = label + "  " # Keep space for sorting arrows.
            self.InsertColumn(i, col_label)
            self._col_widths[i] = max(self._col_widths.get(i, 0),
                self.GetTextExtent(col_label)[0] + self.COL_PADDING)
            self.SetColumnWidth(i, self._col_widths[i])
        self._columns = copy.deepcopy(columns)


    def SetColumnAlignment(self, column, align):
        """
        Sets alignment for column at specified index.

        @param   align  one of ULC_FORMAT_LEFT, ULC_FORMAT_RIGHT, ULC_FORMAT_CENTER
        """
        item = self.GetColumn(column)
        item.SetAlign(align)
        self.SetColumn(column, item)


    def GetItemMappedData(self, index):
        """Returns the data mapped to the specified row index."""
        data_id = self.GetItemData(index)
        data = self._data_map.get(data_id)
        return data


    def GetListCtrl(self):
        """Required by ColumnSorterMixin."""
        return self


    def SortListItems(self, col=-1, ascending=1):
        """Sorts the list items on demand."""
        selected_ids, selected = [], self.GetFirstSelected()
        while selected >= 0:
            selected_ids.append(self.GetItemData(selected))
            selected = self.GetNextSelected(selected)

        wx.lib.mixins.listctrl.ColumnSorterMixin.SortListItems(
            self, col, ascending)

        if selected_ids: # Re-select the previously selected items
            idindx = dict((self.GetItemData(i), i)
                          for i in range(self.GetItemCount()))
            [self.Select(idindx[i]) for i in selected_ids if i in idindx]


    def GetColumnSorter(self):
        """
        Override ColumnSorterMixin.GetColumnSorter to specify our sorting,
        which accounts for None values.
        """
        sorter = self.__ColumnSorter if hasattr(self, "itemDataMap") \
            else wx.lib.mixins.listctrl.ColumnSorterMixin.GetColumnSorter(self)
        return sorter


    def OnSysColourChange(self, event):
        """
        Handler for system colour change, updates sort arrow and item colours.
        """
        event.Skip()
        il, il2  = self.GetImageList(wx.IMAGE_LIST_SMALL), self._CreateImageList()
        for i in range(il2.GetImageCount()): il.Replace(i, il2.GetBitmap(i))
        self.RefreshRows()


    def OnCopy(self, event):
        """Copies selected rows to clipboard."""
        rows, i = [], self.GetFirstSelected()
        while i >= 0:
            data = self.GetItemMappedData(i)
            rows.append("\t".join(self._formatters[n](data, n)
                                  for n, l in self._columns))
            i = self.GetNextSelected(i)
        if rows:
            clipdata = wx.TextDataObject()
            clipdata.SetText("\n".join(rows))
            wx.TheClipboard.Open()
            wx.TheClipboard.SetData(clipdata)
            wx.TheClipboard.Close()


    def OnSort(self, event):
        """Handler on clicking column, sorts list."""
        col, ascending = self.GetSortState()
        if col == event.GetColumn() and not ascending: # Clear sort
            self._col = -1
            self._colSortFlag = [0] * self.GetColumnCount()
            self.ClearColumnImage(col)
            self.RefreshRows()
        else:
            ascending = 1 if col != event.GetColumn() else 1 - ascending
            self.SortListItems(event.GetColumn(), ascending)


    def OnDragStop(self, event):
        """Handler for stopping drag in the list, rearranges list."""
        start, stop = self._drag_start, max(1, event.GetIndex())
        if not start or start == stop: return

        selecteds, selected = [], self.GetFirstSelected()
        while selected > 0:
            selecteds.append(selected)
            selected = self.GetNextSelected(selected)

        idx = stop if start > stop else stop - len(selecteds)
        if not selecteds: # Dragged beyond last item
            idx, selecteds = self.GetItemCount() - 1, [start]

        datas     = list(map(self.GetItemMappedData, selecteds))
        image_ids = list(map(self._id_images.get, map(self.GetItemData, selecteds)))

        self.Freeze()
        try:
            for x in selecteds[::-1]: self.DeleteItem(x)
            for i, (data, imageIds) in enumerate(zip(datas, image_ids)):
                imageIds0 = self._ConvertImageIds(imageIds, reverse=True)
                self.InsertRow(idx + i, data, imageIds0)
                self.Select(idx + i)
            self._drag_start = None
        finally: self.Thaw()


    def OnDragStart(self, event):
        """Handler for dragging items in the list, cancels dragging."""
        if self.GetSortState()[0] < 0 \
        and (not self._top_row or event.GetIndex()):
            self._drag_start = event.GetIndex()
        else:
            self._drag_start = None
            self.OnDragCancel(event)


    def OnDragCancel(self, event):
        """Handler for cancelling item drag in the list, cancels dragging."""
        class HackEvent(object): # UltimateListCtrl hack to cancel drag.
            def __init__(self, pos=wx.Point()): self._position = pos
            def GetPosition(self): return self._position
        wx.CallAfter(lambda: self and self.Children[0].DragFinish(HackEvent()))


    def _CreateImageList(self):
        """
        Creates image list for the control, populated with sort arrow images.
        Arrow colours are adjusted for system foreground colours if necessary.
        """
        il = wx.lib.agw.ultimatelistctrl.PyImageList(*self.SORT_ARROW_UP.Bitmap.Size)
        fgcolour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
        defrgb, myrgb = "\x00" * 3, "".join(map(chr, fgcolour.Get()))[:3]

        for embedded in self.SORT_ARROW_UP, self.SORT_ARROW_DOWN:
            if myrgb != defrgb:
                img = embedded.Image.Copy()
                if not img.HasAlpha(): img.InitAlpha()
                data = img.GetDataBuffer()
                for i in range(embedded.Image.Width * embedded.Image.Height):
                    rgb = data[i*3:i*3 + 3]
                    if rgb == defrgb: data[i*3:i*3 + 3] = myrgb
                il.Add(img.ConvertToBitmap())
            else:
                il.Add(embedded.Bitmap)
        return il


    def _ConvertImageIds(self, imageIds, reverse=False):
        """Returns user image indexes adjusted by internal image count."""
        if not imageIds: return imageIds
        shift = (-1 if reverse else 1) * len(self.GetSortImages() or [])
        return [x + shift for x in imageIds]


    def _PopulateTopRow(self):
        """Populates top row state, if any."""
        if not self._top_row: return

        columns = [c[0] for c in self._columns]
        col_value = self._formatters[columns[0]](self._top_row, columns[0])
        if -1 in self._id_images:
            self.InsertImageStringItem(0, col_value, self._id_images[-1])
        else: self.InsertStringItem(0, col_value)
        for i, col_name in enumerate(columns[1:], 1):
            col_value = self._formatters[col_name](self._top_row, col_name)
            self.SetStringItem(0, i, col_value)
        self.SetItemBackgroundColour(0, self.BackgroundColour)
        self.SetItemTextColour(0, self.ForegroundColour)

        def resize():
            if not self: return
            w = sum((self.GetColumnWidth(i) for i in range(1, len(self._columns))), 0)
            width = self.Size[0] - w - 5 # Space for padding
            if self.GetScrollRange(wx.VERTICAL) > 1:
                width -= self.GetScrollThumb(wx.VERTICAL) # Space for scrollbar
            self.SetColumnWidth(0, width)
        if self.GetItemCount() == 1: wx.CallAfter(resize)


    def _PopulateRows(self, selected_ids=()):
        """Populates all rows, restoring previous selecteds if any"""

        # To map list item data ID to row, ListCtrl allows only integer per row
        row_data_map = {} # {item_id: {row dict}, }
        item_data_map = {} # {item_id: [row values], }
        # For measuring by which to set column width: header or value
        header_lengths = {} # {col_name: integer}
        col_lengths = {} # {col_name: integer}
        for col_name, col_label in self._columns:
            col_lengths[col_name] = 0
            # Keep space for sorting arrows.
            width = self.GetTextExtent(col_label + "  ")[0] + self.COL_PADDING
            header_lengths[col_name] = width
        index = self.GetItemCount()
        for item_id, row in self._id_rows:
            if not self._RowMatchesFilter(row): continue # for item_id, row
            col_name = self._columns[0][0]
            col_value = self._formatters[col_name](row, col_name)
            col_lengths[col_name] = max(col_lengths[col_name],
                                        self.GetTextExtent(col_value)[0] + self.COL_PADDING)

            if item_id in self._id_images:
                self.InsertImageStringItem(index, col_value, self._id_images[item_id])
            else: self.InsertStringItem(index, col_value)

            self.SetItemData(index, item_id)
            item_data_map[item_id] = {0: row[col_name]}
            row_data_map[item_id] = row
            col_index = 1 # First was already inserted
            for col_name, col_label in self._columns[col_index:]:
                col_value = self._formatters[col_name](row, col_name)
                col_width = self.GetTextExtent(col_value)[0] + self.COL_PADDING
                col_lengths[col_name] = max(col_lengths[col_name], col_width)
                self.SetStringItem(index, col_index, col_value)
                item_data_map[item_id][col_index] = row.get(col_name)
                col_index += 1
            self.SetItemTextColour(index, self.ForegroundColour)
            self.SetItemBackgroundColour(index, self.BackgroundColour)
            index += 1
        self._data_map = row_data_map
        self.itemDataMap = item_data_map

        if self._id_rows and not self._col_widths:
            if self._col_maxwidth > 0:
                for col_name, width in col_lengths.items():
                    col_lengths[col_name] = min(width, self._col_maxwidth)
                for col_name, width in header_lengths.items():
                    header_lengths[col_name] = min(width, self._col_maxwidth)
            for i, (col_name, col_label) in enumerate(self._columns):
                col_width = max(col_lengths[col_name], header_lengths[col_name])
                self.SetColumnWidth(i, col_width)
                self._col_widths[i] = col_width
        elif self._col_widths:
            for col, width in self._col_widths.items():
                self.SetColumnWidth(col, width)
        if self.GetSortState()[0] >= 0:
            self.SortListItems(*self.GetSortState())

        if selected_ids: # Re-select the previously selected items
            idindx = dict((self.GetItemData(i), i)
                          for i in range(self.GetItemCount()))
            for item_id in selected_ids:
                if item_id not in idindx: continue # for item_id
                self.Select(idindx[item_id])
                if idindx[item_id] >= self.GetCountPerPage():
                    lh = self.GetUserLineHeight()
                    dy = (idindx[item_id] - self.GetCountPerPage() // 2) * lh
                    self.ScrollList(0, dy)


    def _RowMatchesFilter(self, row):
        """Returns whether the row dict matches the current filter."""
        result = True
        if self._filter:
            result = False
            patterns = list(map(re.escape, self._filter.split()))
            for col_name, col_label in self._columns:
                col_value = self._formatters[col_name](row, col_name)
                if all(re.search(p, col_value, re.I | re.U) for p in patterns):
                    result = True
                    break
        return result


    def __ColumnSorter(self, key1, key2):
        """
        Sort function fed to ColumnSorterMixin, is given two integers which we
        have mapped on our own. Returns -1, 0 or 1.
        """
        if key1 not in self.itemDataMap or key2 not in self.itemDataMap:
            return 0

        col = self._col
        ascending = self._colSortFlag[col]
        item1 = self.itemDataMap[key1][col]
        item2 = self.itemDataMap[key2][col]

        #--- Internationalization of string sorting with locale module
        if isinstance(item1, text_type) and isinstance(item2, text_type):
            cmpVal = locale.strcoll(item1.lower(), item2.lower())
        elif isinstance(item1, bytes) or isinstance(item2, bytes):
            item1 = item1.lower() if isinstance(item1, bytes) else str(item1).encode("latin1").lower()
            item2 = item2.lower() if isinstance(item2, bytes) else str(item2).encode("latin1").lower()
            cmpVal = locale.strcoll(text_type(item1), text_type(item2))
        else:
            if item1 is None:
                cmpVal = -1
            elif item2 is None:
                cmpVal = 1
            else:
                cmpVal = cmp(item1, item2)

        # If items are equal, pick something else to make the sort value unique
        if cmpVal == 0:
            cmpVal = cmp(*self.GetSecondarySortValues(col, key1, key2))

        result = cmpVal if ascending else -cmpVal
        return result



class SQLiteTextCtrl(wx.stc.StyledTextCtrl):
    """
    A StyledTextCtrl configured for SQLite syntax highlighting.

    Supports hiding caret line highlight when not focused (caretline_focus=True).
    Supports traversable mode (traversable=True) - propagates Tab to parent,
    swallows Enter if a single line visible.
    Supports non-wheelable mode (wheelable=False) - propagates mouse wheel events
    to parent.
    """

    """SQLite reserved keywords."""
    KEYWORDS = list(map(text_type, sorted([
        "ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ANALYZE",
        "AND", "AS", "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE",
        "BEGIN", "BETWEEN", "BINARY", "BY", "CASCADE", "CASE", "CAST",
        "CHECK", "COLLATE", "COLUMN", "COMMIT", "CONFLICT", "CONSTRAINT",
        "CREATE", "CROSS", "CURRENT_DATE", "CURRENT_TIME",
        "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT", "DEFERRABLE",
        "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DROP",
        "EACH", "ELSE", "END", "ESCAPE", "EXCEPT", "EXCLUSIVE",
        "EXISTS", "EXPLAIN", "FAIL", "FOR", "FOREIGN", "FROM", "FULL",
        "GLOB", "GROUP", "HAVING", "IF", "IGNORE", "IMMEDIATE", "IN",
        "INDEX", "INDEXED", "INITIALLY", "INNER", "INSERT", "INSTEAD",
        "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "KEY", "LEFT", "LIKE",
        "LIMIT", "MATCH", "NATURAL", "NO", "NOCASE", "NOT", "NOTNULL",
        "NULL", "OF", "OFFSET", "ON", "OR", "ORDER", "OUTER", "PLAN",
        "PRAGMA", "PRIMARY", "QUERY", "RAISE", "REFERENCES", "REGEXP",
        "REINDEX", "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RIGHT",
        "ROLLBACK", "ROW", "ROWID", "RTRIM", "SAVEPOINT", "SELECT", "SET",
        "TABLE", "TEMP", "TEMPORARY", "THEN", "TO", "TRANSACTION", "TRIGGER",
        "UNION", "UNIQUE", "UPDATE", "USING", "VACUUM", "VALUES", "VIEW",
        "VIRTUAL", "WHEN", "WHERE", "WITHOUT",
    ])))
    """SQLite data types."""
    TYPEWORDS = list(map(text_type, sorted([
        "BLOB",
        "INTEGER", "BIGINT", "INT", "INT2", "INT8", "MEDIUMINT", "SMALLINT",
                   "TINYINT", "UNSIGNED",
        "NUMERIC", "BOOLEAN", "DATE", "DATETIME", "DECIMAL",
        "TEXT", "CHARACTER", "CLOB", "NCHAR", "NVARCHAR", "VARCHAR", "VARYING",
        "REAL", "DOUBLE", "FLOAT", "PRECISION",
    ])))
    AUTOCOMP_STOPS = " .,;:([)]}'\"\\<>%^&+-=*/|`"
    """String length from which autocomplete starts."""
    AUTOCOMP_LEN = 2
    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"
    """Regex for matching unprintable characters (\x00 etc)."""
    SAFEBYTE_RGX = re.compile(r"[\x00-\x20\x7f-\xa0]")


    def __init__(self, *args, **kwargs):
        self.caretline_focus = kwargs.pop("caretline_focus", None)
        self.traversable     = kwargs.pop("traversable", False)
        self.wheelable       = kwargs.pop("wheelable", True)

        if "linux" in sys.platform:
            # If no explicit border specified, set BORDER_SIMPLE to make control visible
            # (STC in Linux supports only BORDER_SIMPLE and by default has no border)
            ALLBORDERS = (wx.BORDER_DOUBLE | wx.BORDER_MASK | wx.BORDER_NONE | wx.BORDER_RAISED |
                          wx.BORDER_SIMPLE | wx.BORDER_STATIC | wx.BORDER_SUNKEN | wx.BORDER_THEME)
            if not kwargs.get("style", 0) & ALLBORDERS:
                kwargs["style"] = kwargs.get("style", 0) | wx.BORDER_SIMPLE

        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)
        self.autocomps_added = set(["sqlite_master"])
        # All autocomps: added + KEYWORDS
        self.autocomps_total = self.KEYWORDS[:]
        # {word.upper(): set(words filled in after word+dot), }
        self.autocomps_subwords = {}

        self.SetLexer(wx.stc.STC_LEX_SQL)
        self.SetMarginWidth(1, 0) # Get rid of left margin
        self.SetTabWidth(4)
        # Keywords must be lowercase, required by StyledTextCtrl
        self.SetKeyWords(0, u" ".join(self.KEYWORDS + self.TYPEWORDS).lower())
        self.AutoCompStops(self.AUTOCOMP_STOPS)
        self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(True)
        self.AutoCompSetIgnoreCase(True)

        self.SetStyleSpecs()

        self.Bind(wx.EVT_KEY_DOWN,           self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,          self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnKillFocus)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,       self.OnZoom)
        if self.caretline_focus: self.SetCaretLineVisible(False)
        if self.traversable: self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)
        if self.wheelable is False: self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        fgcolour, bgcolour, highcolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW
                      if self.Enabled else wx.SYS_COLOUR_BTNFACE,
                      wx.SYS_COLOUR_HOTLIGHT)
        )


        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleClearAll() # Apply the new default style to all styles
        self.StyleSetSpec(wx.stc.STC_SQL_DEFAULT,   "face:%s" % self.FONT_FACE)
        self.StyleSetSpec(wx.stc.STC_SQL_STRING,    "fore:#FF007F") # "
        self.StyleSetSpec(wx.stc.STC_SQL_CHARACTER, "fore:#FF007F") # "
        self.StyleSetSpec(wx.stc.STC_SQL_QUOTEDIDENTIFIER, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_WORD,  "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_WORD2, "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_USER1, "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_USER2, "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_USER3, "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_USER4, "fore:%s,bold" % highcolour)
        self.StyleSetSpec(wx.stc.STC_SQL_SQLPLUS, "fore:#ff0000,bold")
        self.StyleSetSpec(wx.stc.STC_SQL_SQLPLUS_COMMENT, "back:#ffff00")
        self.StyleSetSpec(wx.stc.STC_SQL_SQLPLUS_PROMPT,  "back:#00ff00")
        # 01234567890.+-e
        self.StyleSetSpec(wx.stc.STC_SQL_NUMBER, "fore:#FF00FF")
        # + - * / % = ! ^ & . , ; <> () [] {}
        self.StyleSetSpec(wx.stc.STC_SQL_OPERATOR, "fore:%s" % highcolour)
        # --...
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENTLINE, "fore:#008000")
        # #...
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENTLINEDOC, "fore:#008000")
        # /*...*/
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENT, "fore:#008000")
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENTDOC, "fore:#008000")
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENTDOCKEYWORD, "back:#AAFFAA")
        self.StyleSetSpec(wx.stc.STC_SQL_COMMENTDOCKEYWORDERROR, "back:#AAFFAA")

        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD, "fore:#FF0000")


    def AutoCompAddWords(self, words):
        """Adds more words used in autocompletion."""
        words = [x for x in words if not self.SAFEBYTE_RGX.search(x)]
        if not words: return

        self.autocomps_added.update(map(text_type, words))
        # A case-insensitive autocomp has to be sorted, will not work
        # properly otherwise. UserList would support arbitrarily sorting.
        self.autocomps_total = sorted(list(self.autocomps_added) +
                                      list(map(text_type, self.KEYWORDS)),
                                      key=lambda x: x.lower())


    def AutoCompAddSubWords(self, word, subwords):
        """
        Adds more subwords used in autocompletion, will be shown after the word
        and a dot.
        """
        subwords = [x for x in subwords if not self.SAFEBYTE_RGX.search(x)]
        if not subwords or self.SAFEBYTE_RGX.search(word): return

        word, subwords = text_type(word), map(text_type, subwords)
        if word not in self.autocomps_added:
            self.AutoCompAddWords([word])
        if subwords:
            word_key = word.upper()
            self.autocomps_subwords.setdefault(word_key, set())
            self.autocomps_subwords[word_key].update(subwords)


    def AutoCompClearAdded(self):
        """Clears words added in AutoCompAddWords and AutoCompAddSubWords."""
        self.autocomps_added &= set(["sqlite_master"])
        self.autocomps_total = self.KEYWORDS[:]
        self.autocomps_subwords.clear()


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(self.__class__, self).Enable(enable)
        self.SetStyleSpecs()
        return result

    def IsTraversable(self):
        """Returns whether control is in traversable mode."""
        return self.traversable


    def SetTraversable(self, traversable):
        """Sets control traversable mode."""
        self.Unbind(wx.EVT_CHAR_HOOK, handler=self.OnChar)
        self.traversable = traversable
        if traversable: self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)
    Traversable = property(IsTraversable, SetTraversable)


    def IsWheelable(self):
        """
        Returns whether control is in wheelable mode
        (mouse wheel events not propagated to parent).
        """
        return self.wheelable


    def SetWheelable(self, wheelable):
        """
        Sets control wheelable mode
        (mouse wheel events not propagated to parent).
        """
        self.Unbind(wx.EVT_MOUSEWHEEL, handler=self.OnWheel)
        self.wheelable = wheelable
        if wheelable is False: self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
    Wheelable = property(IsWheelable, SetWheelable)


    def OnFocus(self, event):
        """Handler for control getting focus, shows caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_LINE)
        if self.caretline_focus: self.SetCaretLineVisible(True)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides autocomplete and caret."""
        event.Skip()
        self.AutoCompCancel()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)
        if self.caretline_focus: self.SetCaretLineVisible(False)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        self.SetStyleSpecs()


    def OnZoom(self, event):
        """Disables zoom."""
        if self.Zoom: self.Zoom = 0


    def OnWheel(self, event):
        """Propagates wheel events to parent control."""
        event.Skip()
        event.ResumePropagation(1)
        self.Parent.ProcessWindowEvent(event)


    def OnChar(self, event):
        """
        Goes to next/previous control on Tab/Shift+Tab,
        swallows Enter.
        """
        if self.AutoCompActive() or event.CmdDown() \
        or event.KeyCode not in KEYS.TAB: return event.Skip()
        if event.KeyCode in KEYS.ENTER and self.LinesOnScreen() < 2: return

        direction = wx.NavigationKeyEvent.IsBackward if event.ShiftDown() \
                    else wx.NavigationKeyEvent.IsForward
        self.Parent.NavigateIn(direction)


    def OnKeyDown(self, event):
        """
        Shows autocomplete if user is entering a known word, or pressed
        Ctrl-Space. Added autocomplete words are listed first, SQL keywords
        second.
        """
        skip = True
        if self.CallTipActive():
            self.CallTipCancel()
        if not self.AutoCompActive() and not event.AltDown():
            do_autocomp = False
            words = self.autocomps_total
            autocomp_len = 0
            if event.UnicodeKey in KEYS.SPACE and event.CmdDown():
                # Start autocomp when user presses Ctrl+Space
                do_autocomp = True
            elif not event.CmdDown():
                # Check if we have enough valid text to start autocomplete
                char = None
                try: # Not all keycodes can be chars
                    char = chr(event.UnicodeKey)
                    char = char.decode("latin1")
                except Exception:
                    pass
                if char not in KEYS.ENTER and char is not None:
                    # Get a slice of the text on the current text up to caret.
                    line_text = self.GetTextRange(
                        self.PositionFromLine(self.GetCurrentLine()),
                        self.GetCurrentPos()
                    )
                    text = u""
                    for last_word in re.findall(r"(\w+)$", line_text, re.I):
                        text += last_word
                    text = text.upper()
                    if "." == char:
                        # User entered "word.", show subword autocompletion if
                        # defined for the text.
                        if text in self.autocomps_subwords:
                            words = sorted(self.autocomps_subwords[text], key=lambda x: x.lower())
                            do_autocomp = True
                            skip = False
                            self.AddText(char)
                    else:
                        text += char
                        if len(text) >= self.AUTOCOMP_LEN and any(x for x in
                        self.autocomps_total if x.upper().startswith(text)):
                            do_autocomp = True
                            current_pos = self.GetCurrentPos() - 1
                            while chr(self.GetCharAt(current_pos)).isalnum():
                                current_pos -= 1
                            autocomp_len = self.GetCurrentPos() - current_pos - 1
            if do_autocomp:
                if skip: event.Skip()
                self.AutoCompShow(autocomp_len, u" ".join(words))
        elif self.AutoCompActive() and event.KeyCode in KEYS.DELETE:
            self.AutoCompCancel()
        if skip: event.Skip()


    def stricmp(self, a, b):
        return cmp(a.lower(), b.lower())



CaretPositionEvent, EVT_CARET_POS = wx.lib.newevent.NewCommandEvent()
LinePositionEvent,  EVT_LINE_POS  = wx.lib.newevent.NewCommandEvent()
SelectionEvent,     EVT_SELECT    = wx.lib.newevent.NewCommandEvent()

class HexByteCommand(wx.Command):
    """Undoable-redoable action for HexTextCtrl/ByteTextCtrl undo-redo."""
    ATTRS = ["_bytes", "_bytes0"]

    def __init__(self, ctrl):
        """Takes snapshot of current control state for do."""
        super(HexByteCommand, self).__init__(canUndo=True)
        self._ctrl   = ctrl
        self._done   = False
        self._state1 = copy.deepcopy({k: getattr(ctrl, k) for k in self.ATTRS})
        self._state1["Selection"] = ctrl.GetSelection()
        self._state2 = None

    def Store(self, value=None):
        """
        Takes snapshot of current control state for undo,
        stores command in command processor.
        """
        self._state2 = self._GetState(value)
        self._ctrl._undoredo.Store(self)
        self._done = True
        self._UpdateMirror(self._state2)

    def Submit(self, value=None, value0=None, selection=None, mirror=False):
        """
        Takes snapshot of current control state for undo,
        stores command in command processor and carries out do.
        """
        self._state2 = self._GetState(value, value0, selection)
        self._ctrl._undoredo.Submit(self)
        self._done = True
        if mirror: self._UpdateMirror(self._state2)

    def Do(self, mirror=False):
        """Applies control do-action."""
        result = self._Apply(self._state2)
        if self._done and result and self._ctrl.Mirror and mirror:
            self._ctrl.Mirror.Redo()
        return result

    def Undo(self, mirror=False):
        """Applies control undo-action."""
        result = self._Apply(self._state1)
        if result and self._ctrl.Mirror and mirror:
            self._ctrl.Mirror.Undo()
        return result

    def _GetState(self, value=None, value0=None, selection=None):
        """Returns current control state."""
        state = {k: getattr(self._ctrl, k) for k in self.ATTRS}
        state["Selection"] = selection or self._ctrl.GetSelection()
        if value is not None:
            state["_bytes"] = bytearray(value)
            if value0 is not None:
                state["_bytes0"] = value0
            else:
                diff = len(state["_bytes0"]) - len(state["_bytes"])
                if diff < 0: state["_bytes0"] = state["_bytes0"] + [None] * abs(diff)
                elif diff:   state["_bytes0"] = state["_bytes0"][:len(state["_bytes0"]) - diff]
        return copy.deepcopy(state)

    def _UpdateMirror(self, state):
        """Updates linked control, if any."""
        if not self._ctrl.Mirror: return
        v, v0, sel = (state[k] for k in self.ATTRS + ["Selection"])
        HexByteCommand(self._ctrl.Mirror).Submit(v, v0, sel)

    def _Apply(self, state):
        """Applies state to control and populates it."""
        if not self._ctrl: return False
        for k in self.ATTRS: setattr(self._ctrl, k, state[k])
        self._ctrl._Populate()
        self._ctrl.SetSelection(*state["Selection"])
        return True


class HexByteCommandProcessor(wx.CommandProcessor):
    """Command processor for mirrored hex and byte controls."""

    def __init__(self, ctrl, maxCommands=-1):
        super(HexByteCommandProcessor, self).__init__(maxCommands)
        self._ctrl = ctrl

    def Redo(self, mirror=False):
        result = super(HexByteCommandProcessor, self).Redo()
        if result and mirror and self._ctrl.Mirror:
            self._ctrl.Mirror.Redo(mirror=False)
        return result

    def Undo(self, mirror=False):
        result = super(HexByteCommandProcessor, self).Undo()
        if result and mirror and self._ctrl.Mirror:
            self._ctrl.Mirror.Undo(mirror=False)
        return result


class HexTextCtrl(wx.stc.StyledTextCtrl):
    """
    A StyledTextCtrl configured for hexadecimal editing.
    Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.
    """

    NUMPAD_NUMS = {wx.WXK_NUMPAD0: 0, wx.WXK_NUMPAD1: 1, wx.WXK_NUMPAD2: 2,
                   wx.WXK_NUMPAD3: 3, wx.WXK_NUMPAD4: 4, wx.WXK_NUMPAD5: 5,
                   wx.WXK_NUMPAD6: 6, wx.WXK_NUMPAD7: 7, wx.WXK_NUMPAD8: 8,
                   wx.WXK_NUMPAD7: 9}

    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"
    """Acceptable input characters."""
    MASK = string.hexdigits
    """Number of hex bytes on one line."""
    WIDTH = 16
    """Identifier for address margin styling."""
    STYLE_MARGIN = 11
    """Identifier for changed bytes styling."""
    STYLE_CHANGED = 12
    """Foreground colour for changed bytes."""
    COLOUR_CHANGED = "red"


    def __init__(self, *args, **kwargs):
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self._fixed    = False # Fixed-length value
        self._type     = str   # Value type: str, unicode, int, float, long
        self._bytes0   = []    # [byte or None, ]
        self._bytes    = bytearray()
        self._mirror   = None # Linked control
        self._undoredo = HexByteCommandProcessor(self)

        self.SetStyleSpecs()
        cw = self.TextWidth(0, "X")

        self.SetEOLMode(wx.stc.STC_EOL_LF)
        self.SetWrapMode(wx.stc.STC_WRAP_CHAR)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(False)

        self.SetMarginCount(1)
        self.SetMarginType(0, wx.stc.STC_MARGIN_TEXT)
        self.SetMarginWidth(0, cw * 9)
        self.SetMarginCursor(0, wx.stc.STC_CURSORARROW)
        self.SetMargins(3, 0)

        self.SetOvertype(True)
        self.SetUseTabs(False)
        w = cw * self.WIDTH * 3 + self.GetMarginWidth(0) + \
            sum(max(x, 0) for x in self.GetMargins()) + \
            wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        self.MinSize = self.MaxSize = w, -1

        self.Bind(wx.EVT_KEY_DOWN,                self.OnKeyDown)
        self.Bind(wx.EVT_CHAR_HOOK,               self.OnChar)
        self.Bind(wx.EVT_SET_FOCUS,               self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,              self.OnKillFocus)
        self.Bind(wx.EVT_MOUSE_EVENTS,            self.OnMouse)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,      self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,            self.OnZoom)
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_PASTE, self.OnPaste)
        self.Bind(wx.stc.EVT_STC_START_DRAG,      lambda e: e.SetString(""))


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        if not self: return
        fgcolour, bgcolour, mbgcolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW
                      if self.Enabled else wx.SYS_COLOUR_BTNFACE,
                      wx.SYS_COLOUR_BTNFACE)
        )

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleClearAll() # Apply the new default style to all styles

        self.StyleSetSpec(self.STYLE_CHANGED, "fore:%s" % self.COLOUR_CHANGED)
        self.StyleSetSpec(self.STYLE_MARGIN,  "back:%s" % mbgcolour)


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(self.__class__, self).Enable(enable)
        self.SetStyleSpecs()
        return result


    def GetMirror(self):
        """Returns the linked control that gets updated on any local change."""
        return self._mirror
    def SetMirror(self, mirror):
        """Sets the linked control that gets updated on any local change."""
        self._mirror = mirror
    Mirror = property(GetMirror, SetMirror)


    def GetLength(self):
        """Returns the number of bytes in the document."""
        return len(self._bytes)
    Length = property(GetLength)


    def GetText(self):
        """Returns current content as non-hex-encoded string."""
        return bytes(self._bytes).decode("latin1")
    def SetText(self, text):
        """Set current content as non-hex-encoded string."""
        return self.SetValue(text if isinstance(text, string_types) else str(text))
    Text = property(GetText, SetText)


    def GetValue(self):
        """Returns current content as original type (string or number)."""
        v = bytes(self._bytes)
        if v == b"" and self._type in integer_types + (float, ): v = None
        elif is_fixed_long(self._type(), v): v = struct.unpack(">q", v)[0]
        elif self._type is     int:          v = struct.unpack(">l", v)[0]
        elif self._type is   float:          v = struct.unpack(">f", v)[0]
        elif self._type is text_type:
            try: v = v.decode("utf-8")
            except Exception: v = v.decode("latin1")
        return v

    def SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        self._SetValue(value)
        self._Populate()

    Value = property(GetValue, SetValue)


    def GetOriginalBytes(self): return list(self._bytes0)
    OriginalBytes = property(GetOriginalBytes)


    def UpdateValue(self, value, mirror=False):
        """Update current content as typed value (string or number)."""
        HexByteCommand(self).Submit(self._AdaptValue(value), mirror=mirror)


    def GetAnchor(self):
        sself = super(HexTextCtrl, self)
        result = self._PosOut(sself.Anchor)
        if sself.Anchor == self.GetLastPosition(): result += 1
        return result
    def SetAnchor(self, anchor):
        return super(HexTextCtrl, self).SetAnchor(self._PosIn(anchor))
    Anchor = property(GetAnchor, SetAnchor)


    def GetCurrentPos(self):
        sself = super(HexTextCtrl, self)
        result = self._PosOut(sself.CurrentPos)
        if sself.CurrentPos == self.GetLastPosition(): result += 1
        return result
    def SetCurrentPos(self, caret):
        return super(HexTextCtrl, self).SetCurrentPos(self._PosIn(caret))
    CurrentPos = property(GetCurrentPos, SetCurrentPos)


    def GetSelection(self):
        """Returns the current byte selection span, as (from_, to_)."""
        from_, to_ = super(HexTextCtrl, self).GetSelection()
        return self._PosOut(from_), self._PosOut(to_) + (from_ != to_)
    def SetSelection(self, from_, to_):
        """Selects the bytes from first position up to but not including second."""
        return super(HexTextCtrl, self).SetSelection(self._PosIn(from_), self._PosIn(to_) - (from_ != to_))
    Selection = property(GetSelection)


    def GetHex(self):
        """Returns current content as hex-encoded string with spaces and newlines."""
        return super(HexTextCtrl, self).Text


    def InsertInto(self, text):
        """Inserts string at current insertion point."""
        pos = self.InsertionPoint
        if self._fixed and not self._bytes: return # NULL number
        if pos == self.GetLastPosition() and self._fixed: pass

        self._QueueEvents()

        cmd = HexByteCommand(self)
        selection = self.GetSelection()
        if selection[0] != selection[1] and not self._fixed:
            del self._bytes [selection[0]:selection[1] + 1]
            del self._bytes0[selection[0]:selection[1] + 1]

        bpos = pos // 3 + (pos == self.GetLastPosition())
        text = re.sub("[^0-9a-fA-F]", "", self._AdaptValue(text))
        text = text[:len(text) - len(text) % 2]
        v = bytearray.fromhex(text)
        maxlen = min(len(v), len(self._bytes) - bpos) if self._fixed else len(v)
        v = v[:maxlen]

        if bpos + maxlen > len(self._bytes):
            self._bytes0.extend([None] * (bpos + maxlen - len(self._bytes)))
        if self.Overtype:
            self._bytes[bpos:bpos + maxlen] = v
        else:
            self._bytes [bpos:bpos] = v
            self._bytes0[bpos:bpos] = [None] * len(v)

        self._Populate()
        self.SetSelection(selection[0] + len(v), selection[0] + len(v))
        self.EnsureCaretVisible()
        cmd.Store()


    def EmptyUndoBuffer(self, mirror=False):
        """Deletes undo history."""
        super(HexTextCtrl, self).EmptyUndoBuffer()
        self._undoredo.ClearCommands()
        if mirror and self._mirror:  self._mirror.EmptyUndoBuffer()


    def Undo(self, mirror=False):
        """Undos the last change, if any."""
        if not self._undoredo.CanUndo(): return
        self._undoredo.Undo(mirror=mirror)
        evt = wx.stc.StyledTextEvent(wx.stc.wxEVT_STC_MODIFIED, self.Id)
        evt.SetModificationType(wx.stc.STC_PERFORMED_UNDO)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)


    def Redo(self, mirror=False):
        """Redos the last undo, if any."""
        if not self._undoredo.CanRedo(): return
        self._undoredo.Redo(mirror=mirror)
        evt = wx.stc.StyledTextEvent(wx.stc.wxEVT_STC_MODIFIED, self.Id)
        evt.SetModificationType(wx.stc.STC_PERFORMED_REDO)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)


    def _PosIn(self, pos):
        line, linebpos = divmod(pos, self.WIDTH)
        return line * self.WIDTH * 3 + linebpos * 3
    def _PosOut(self, pos):
        line = self.LineFromPosition(pos)
        linepos = pos - self.PositionFromLine(self.LineFromPosition(pos))
        return line * self.WIDTH + linepos // 3


    def _Populate(self):
        """Sets current content to widget."""
        fulltext, count = [], len(self._bytes)
        for i, c in enumerate(self._bytes):
            text, line = "%02X" % c, i // self.WIDTH
            if i < count - 1:
                text += "\n" if i and not (i + 1) % self.WIDTH else " "
            fulltext.append(text)
        super(HexTextCtrl, self).ChangeValue("".join(fulltext))
        self._Restyle()
        self._Remargin()


    def _Restyle(self):
        """Restyles current content according to changed state."""
        self.StartStyling(0)
        self.SetStyling(super(HexTextCtrl, self).Length, 0)
        for i, c in enumerate(self._bytes):
            if c == self._bytes0[i]: continue # for i, c
            self.StartStyling(i * 3)
            self.SetStyling(2, self.STYLE_CHANGED)


    def _Remargin(self):
        """Rebuilds hex address margin."""
        sself = super(HexTextCtrl, self)
        margintexts = []
        self.MarginTextClearAll()
        for line in range((sself.Length + self.WIDTH - 1) // self.WIDTH):
            self.MarginSetStyle(line, self.STYLE_MARGIN)
            self.MarginSetText (line, " %08X " % line)


    def _SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        is_long = is_fixed_long(value)
        v = self._AdaptValue(value)

        self._type      = type(value) if is_long or not is_long_long(value) else str
        self._fixed     = is_long or value is None or is_fixed(value)
        self._bytes0[:] = [x if isinstance(x, int) else ord(x) for x in v]
        self._bytes[:]  = v
        if self._fixed: self.SetOvertype(True)
        self._undoredo.ClearCommands()


    def OnFocus(self, event):
        """Handler for control getting focus, shows caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_LINE)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        wx.CallAfter(self.SetStyleSpecs)


    def OnZoom(self, event):
        """Disables zoom."""
        if self.Zoom: self.Zoom = 0


    def OnPaste(self, event):
        """Handles paste event."""
        text = event.String
        event.SetString("") # Cancel default paste
        self.InsertInto(text)


    def OnChar(self, event):
        """Handler for keypress, cancels event if not acceptable character."""

        if event.CmdDown() and not event.AltDown() and not event.ShiftDown() \
        and ord("Z") == event.KeyCode:
            return self.Undo(mirror=True)

        if event.CmdDown() and not event.AltDown() and (not event.ShiftDown() \
        and ord("Y") == event.KeyCode) or (event.ShiftDown() and ord("Z") == event.KeyCode):
            return self.Redo(mirror=True)

        if event.CmdDown() and not event.AltDown() and (not event.ShiftDown()
        and ord("V") == event.KeyCode or event.ShiftDown() and event.KeyCode in KEYS.INSERT):
            text = None
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                    o = wx.TextDataObject()
                    wx.TheClipboard.GetData(o)
                    text = o.Text
                wx.TheClipboard.Close()
            if text is not None: self.InsertInto(text)
            return

        if not event.HasModifiers() and (event.KeyCode in KEYS.ENTER + KEYS.SPACE
        or (unichr(event.UnicodeKey) not in self.MASK and event.KeyCode not in self.NUMPAD_NUMS) \
        and event.KeyCode not in KEYS.NAVIGATION + KEYS.COMMAND):
            return
        event.Skip()


    def OnKeyDown(self, event):
        """Handler for key down, moves caret to word boundary."""
        self._QueueEvents()
        sself = super(HexTextCtrl, self)

        if event.KeyCode in KEYS.LEFT + KEYS.RIGHT:
            direction = -1 if event.KeyCode in KEYS.LEFT else 1
            pos0 = sself.CurrentPos
            linepos0 = pos0 - self.PositionFromLine(self.LineFromPosition(pos0))
            if event.ShiftDown():
                func = self.WordLeftExtend if direction < 0 else self.WordRightEndExtend
            else:
                func = self.WordLeft if direction < 0 else self.WordRight
            func()
            pos = sself.CurrentPos
            linepos = pos - self.PositionFromLine(self.LineFromPosition(pos))
            if not event.ShiftDown() and linepos >= self.WIDTH * 3 - 1 \
            or event.ShiftDown() and (not linepos and not linepos0 or not linepos0 and linepos >= self.WIDTH * 3 - 1):
                func()
            if direction < 0 and not self.GetSelectionEmpty() and pos > sself.GetSelection()[0]:
                self.CharLeftExtend()

        elif event.KeyCode in KEYS.END and not event.CmdDown():
            if event.ShiftDown(): self.LineEndExtend()
            else:
                pos = self.GetLineEndPosition(self.CurrentLine)
                sself.SetSelection(pos, pos)
        elif event.KeyCode in KEYS.DELETE + KEYS.BACKSPACE:
            if self._fixed: return

            cmd = HexByteCommand(self)
            selection = self.GetSelection()
            if selection[0] != selection[1]:
                del self._bytes [selection[0]:selection[1]]
                del self._bytes0[selection[0]:selection[1]]
                self.SetSelection(selection[0], selection[0])
                cmd.Submit(mirror=True)
                return

            pos        = sself.CurrentPos
            line0      = sself.FirstVisibleLine
            line       = self.LineFromPosition(pos)
            linepos    = pos - self.PositionFromLine(line)
            direction  = -(event.KeyCode in KEYS.BACKSPACE)
            is_lastpos = (pos == self.GetLastPosition())

            if not self._bytes or not pos and direction \
            or is_lastpos and not direction:
                return

            bpos, idx = self.CurrentPos, linepos % 3
            if is_lastpos: bpos, idx = min(bpos, len(self._bytes) - 1), 0
            elif direction and not idx: bpos -= 1 # Backspacing over previous byte
            for bb in self._bytes, self._bytes0: del bb[bpos]

            if line == self.LineCount - 1 and (not direction or linepos):
                # Last line and not backspacing from first byte
                frompos = max(pos + (-idx if idx else direction * 3), 0)
                topos   = sself.Length if frompos + 3 > sself.Length else frompos + 3
                self.Remove(frompos, topos)
                if idx:
                    if bpos >= len(self._bytes): self.DeleteBack()
                    sself.SetSelection(frompos, frompos)
            else:
                self._Populate()
                sself.SetSelection(*(pos + direction * 3 - idx, ) * 2)
            cmd.Store()
        elif not event.HasModifiers() \
        and (unichr(event.UnicodeKey) in self.MASK or event.KeyCode in self.NUMPAD_NUMS) \
        and (not event.ShiftDown() or unichr(event.UnicodeKey) not in string.digits):
            if self._fixed and not self._bytes: return # NULL number

            cmd = HexByteCommand(self)
            selection = self.GetSelection()
            if selection[0] != selection[1] and not self._fixed:
                del self._bytes [selection[0]:selection[1] + 1]
                del self._bytes0[selection[0]:selection[1] + 1]

            line0 = sself.FirstVisibleLine
            pos   = sself.CurrentPos
            linepos = pos - self.PositionFromLine(self.LineFromPosition(pos))
            bpos, idx = self.CurrentPos, linepos % 3
            if pos == self.GetLastPosition():
                if self._fixed: return
                pos, bpos, idx = pos + bool(self._bytes), bpos + bool(self._bytes), 0
                self._bytes.append(0), self._bytes0.append(None)
            elif idx > 1: idx, pos = 0, pos - idx
            elif not idx and not self.Overtype:
                self._bytes.insert(bpos, 0), self._bytes0.insert(bpos, None)
            bpos = min(bpos, len(self._bytes) - 1)

            number = self.NUMPAD_NUMS[event.KeyCode] if event.KeyCode in self.NUMPAD_NUMS \
                     else int(unichr(event.UnicodeKey), 16)
            byte = self._bytes[bpos]

            b1 = byte >> 4 if idx else number
            b2 = number if idx else byte & 0x0F
            byte = b1 * 16 + b2
            self._bytes[bpos] = byte

            if selection[0] != selection[1] and not self._fixed \
            or not ((self.Overtype or idx) and pos < self.GetLastPosition()):
                self._Populate()
                self.SetFirstVisibleLine(line0)
            else:
                sself.Replace(pos - idx, pos - idx + 2, "%02X" % byte)
                self.StartStyling(pos - idx)
                self.SetStyling(2, self.STYLE_CHANGED if self._bytes[bpos] != self._bytes0[bpos] else 0)
            sself.SetSelection(pos + 1 + idx, pos + 1 + idx)
            cmd.Store()
        elif event.KeyCode in KEYS.INSERT and not event.HasAnyModifiers():
            if not self._fixed: event.Skip() # Disallow changing overtype if length fixed
        elif event.KeyCode not in KEYS.TAB:
            event.Skip()


    def OnMouse(self, event):
        """Handler for mouse event, moves care to word boundary."""
        event.Skip()
        self._QueueEvents(singlepos=event.LeftUp())


    def _AdaptValue(self, value):
        """Returns the value as bytes() for hex representation."""
        is_long = is_fixed_long(value) and not is_long_long(value)
        if is_long:                    v = struct.pack(">q", value)
        elif isinstance(value, int):   v = struct.pack(">l", value)
        elif isinstance(value, float): v = struct.pack(">f", value)
        elif value is None:            v = b""
        elif isinstance(value, text_type):
            try: v = value.encode("latin1")
            except Exception: v = value.encode("utf-8")
        else: v = value
        if not isinstance(v, bytes):
            v = str(v).encode("latin1")
        return v


    def _QueueEvents(self, singlepos=False):
        """Raises CaretPositionEvent or LinePositionEvent or SelectionEvent if changed after."""
        sself = super(HexTextCtrl, self)
        pos, firstline = self.CurrentPos, self.FirstVisibleLine
        notselected, selection = self.GetSelectionEmpty(), list(sself.GetSelection())

        def after():
            if not self: return

            notselected2, selection2 = self.GetSelectionEmpty(), list(sself.GetSelection())
            if singlepos or selection2[0] != selection2[1] and not self.HasCapture():
                linepos1 = selection2[0] - self.PositionFromLine(self.LineFromPosition(selection2[0]))
                linepos2 = selection2[1] - self.PositionFromLine(self.LineFromPosition(selection2[1]))
                if linepos1 % 3: selection2[0] += 1 if linepos1 % 3 == 2 else -1
                if notselected2: selection2[1] = selection2[0]
                elif linepos1 != linepos2 and linepos2 % 3 != 2:
                    selection2[1] += 1 if linepos2 % 3 == 1 else -1
            if selection2 != list(sself.GetSelection()):
                if sself.Anchor == selection2[0]: sself.SetSelection(*selection2)
                else: sself.SetAnchor(selection2[1]), sself.SetCurrentPos(selection2[0])

            if pos != self.CurrentPos:
                evt = CaretPositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.CurrentPos)
                wx.PostEvent(self, evt)
            elif firstline != self.FirstVisibleLine:
                evt = LinePositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.FirstVisibleLine)
                wx.PostEvent(self, evt)
            if notselected != notselected2 \
            or not notselected and selection != selection2:
                evt = SelectionEvent(self.Id)
                evt.SetEventObject(self)
                wx.PostEvent(self, evt)
        wx.CallAfter(after)



class ByteTextCtrl(wx.stc.StyledTextCtrl):
    """
    A StyledTextCtrl configured for byte editing.
    Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.
    """

    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"
    """Number of bytes on one line."""
    WIDTH = 16
    """Identifier for changed bytes styling."""
    STYLE_CHANGED = 12
    """Foreground colour for changed bytes."""
    COLOUR_CHANGED = "red"


    def __init__(self, *args, **kwargs):
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self._fixed  = False # Fixed-length value
        self._type   = str   # Value type: str, unicode, int, float, long
        self._bytes0 = []    # [byte or None, ]
        self._bytes  = bytearray() # Raw bytes
        self._mirror = None  # Linked control
        self._undoredo = HexByteCommandProcessor(self)

        self.SetEOLMode(wx.stc.STC_EOL_LF)
        self.SetWrapMode(wx.stc.STC_WRAP_CHAR)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(False)

        self.SetMarginCount(0)
        self.SetMargins(0, 0)

        self.SetStyleSpecs()
        self.SetOvertype(True)
        self.SetUseTabs(False)
        w = self.TextWidth(0, "X") * (self.WIDTH + 2) + wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        self.Size = self.MinSize = self.MaxSize = w, -1

        self.Bind(wx.EVT_CHAR,                    self.OnChar)
        self.Bind(wx.EVT_KEY_DOWN,                self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,               self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,              self.OnKillFocus)
        self.Bind(wx.EVT_MOUSE_EVENTS,            self.OnMouse)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,      self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,            self.OnZoom)
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_PASTE, self.OnPaste)
        self.Bind(wx.stc.EVT_STC_START_DRAG,      lambda e: e.SetString(""))


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        if not self: return
        fgcolour, bgcolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW
                      if self.Enabled else wx.SYS_COLOUR_BTNFACE)
        )

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleClearAll() # Apply the new default style to all styles

        self.StyleSetSpec(self.STYLE_CHANGED, "fore:%s" % self.COLOUR_CHANGED)


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(self.__class__, self).Enable(enable)
        self.SetStyleSpecs()
        return result


    def GetMirror(self):
        """Returns the linked control that gets updated on any local change."""
        return self._mirror
    def SetMirror(self, mirror):
        """Sets the linked control that gets updated on any local change."""
        self._mirror = mirror
    Mirror = property(GetMirror, SetMirror)


    def GetText(self):
        """Returns current content as raw byte string."""
        return str(self._bytes)
    def SetText(self, text):
        """Set current content as raw byte string."""
        return self.SetValue(self._AdaptValue(text))
    Text = property(GetText, SetText)


    def GetValue(self):
        """Returns current content as original type (string or number)."""
        v = bytes(self._bytes)
        if v == b"" and self._type in integer_types + (float, ): v = None
        elif is_fixed_long(self._type(), v): v = struct.unpack(">q", v)[0]
        elif self._type is     int:          v = struct.unpack(">l", v)[0]
        elif self._type is   float:          v = struct.unpack(">f", v)[0]
        elif self._type is text_type:
            try: v = v.decode("utf-8")
            except Exception: v = v.decode("latin1")
        return v

    def SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        self._SetValue(value)
        self._Populate()
        self._undoredo.ClearCommands()

    Value = property(GetValue, SetValue)


    def GetOriginalBytes(self): return list(self._bytes0)
    OriginalBytes = property(GetOriginalBytes)


    def UpdateValue(self, value, mirror=False):
        """Update current content as typed value (string or number), retaining history."""
        HexByteCommand(self).Submit(self._AdaptValue(value), mirror=mirror)


    def UpdateBytes(self, value):
        """Update current bytes as typed value (string or number), leaving text unchanged."""
        self._SetValue(value, noreset=True)
        if len(self._bytes0) < len(self._bytes):
            self._bytes0.extend([None] * (len(self._bytes) - len(self._bytes0)))
        self._Populate()


    def GetAnchor(self):
        return self._PosOut(super(ByteTextCtrl, self).Anchor)
    def SetAnchor(self, anchor):
        return super(ByteTextCtrl, self).SetAnchor(self._PosIn(anchor))
    Anchor = property(GetAnchor, SetAnchor)


    def GetCurrentPos(self):
        return self._PosOut(super(ByteTextCtrl, self).CurrentPos)
    def SetCurrentPos(self, caret):
        return super(ByteTextCtrl, self).SetCurrentPos(self._PosIn(caret))
    CurrentPos = property(GetCurrentPos, SetCurrentPos)


    def GetSelection(self):
        """Returns the current byte selection span, as (from_, to_)."""
        from_, to_ = super(ByteTextCtrl, self).GetSelection()
        return self._PosOut(from_), self._PosOut(to_)
    def SetSelection(self, from_, to_):
        from_, to_ = self._PosIn(from_), self._PosIn(to_)
        return super(ByteTextCtrl, self).SetSelection(from_, to_)
    Selection = property(GetSelection)


    def EmptyUndoBuffer(self, mirror=False):
        """Deletes undo history."""
        super(ByteTextCtrl, self).EmptyUndoBuffer()
        self._undoredo.ClearCommands()
        if mirror and self._mirror:  self._mirror.EmptyUndoBuffer()


    def Undo(self, mirror=False):
        """Undos the last change, if any."""
        if not self._undoredo.CanUndo(): return
        self._undoredo.Undo(mirror=mirror)
        evt = wx.stc.StyledTextEvent(wx.stc.wxEVT_STC_MODIFIED, self.Id)
        evt.SetModificationType(wx.stc.STC_PERFORMED_UNDO)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)


    def Redo(self, mirror=False):
        """Redos the last undo, if any."""
        if not self._undoredo.CanRedo(): return
        self._undoredo.Redo(mirror=mirror)
        evt = wx.stc.StyledTextEvent(wx.stc.wxEVT_STC_MODIFIED, self.Id)
        evt.SetModificationType(wx.stc.STC_PERFORMED_UNDO)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)


    def _PosIn(self, pos):
        line, linepos = divmod(pos, self.WIDTH)
        return line * (self.WIDTH + 1) + linepos
    def _PosOut(self, pos):
        return pos - self.LineFromPosition(pos)


    def _Populate(self):
        """Sets current content to widget."""
        count = len(self._bytes)
        fulltext = []
        for i, c in enumerate(self._bytes):
            fulltext.append(re.sub("[^\x20-\x7e]", ".", chr(self._bytes[i])))
            if i and i < count - 1 and not (i + 1) % self.WIDTH:
                fulltext.append("\n")
        fullstr = "".join(fulltext)
        if super(ByteTextCtrl, self).Text != fullstr:
            super(ByteTextCtrl, self).ChangeValue(fullstr)
        self._Restyle()


    def _Restyle(self):
        """Restyles current content according to changed state."""
        self.StartStyling(0)
        self.SetStyling(super(ByteTextCtrl, self).Length, 0)
        for i, c in enumerate(self._bytes):
            if c == self._bytes0[i]: continue # for i, c
            self.StartStyling(i // self.WIDTH + i)
            self.SetStyling(1, self.STYLE_CHANGED)


    def _SetValue(self, value, noreset=False):
        """Set current content as typed value (string or number)."""
        is_long = is_fixed_long(value)
        v = self._AdaptValue(value)

        self._bytes[:] = v
        if not noreset:
            self._type      = type(value) if is_long or not is_long_long(value) else str
            self._fixed     = is_long or value is None or is_fixed(value)
            self._bytes0[:] = [x if isinstance(x, int) else ord(x) for x in v]
        if self._fixed: self.SetOvertype(True)


    def OnFocus(self, event):
        """Handler for control getting focus, shows caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_LINE)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        wx.CallAfter(self.SetStyleSpecs)


    def OnZoom(self, event):
        """Disables zoom."""
        if self.Zoom: self.Zoom = 0


    def InsertInto(self, text):
        """Inserts string at current insertion point."""
        if self._fixed and not self._bytes: return # NULL number
        if self.CurrentPos == self.GetLastPosition() and self._fixed: pass

        self._QueueEvents()
        cmd = HexByteCommand(self)

        selection = self.GetSelection()
        if selection[0] != selection[1] and not self._fixed:
            del self._bytes [selection[0]:selection[1]]
            del self._bytes0[selection[0]:selection[1]]

        pos = self.CurrentPos
        v = self._AdaptValue(text)
        maxlen = min(len(v), self.Length - pos) if self._fixed else len(v)
        v = v[:maxlen]

        if pos + maxlen > len(self._bytes):
            self._bytes0.extend([None] * (pos + maxlen - len(self._bytes)))
        if self.Overtype:
            self._bytes[pos:pos + maxlen] = v
        else:
            self._bytes0[pos:pos] = [None] * len(v)
            self._bytes [pos:pos] = v
        self._Populate()
        self.SetSelection(selection[0] + len(v), selection[0] + len(v))
        self.EnsureCaretVisible()
        cmd.Store()


    def OnPaste(self, event):
        """Handles paste event."""
        text = event.String
        event.SetString("") # Cancel default paste
        self.InsertInto(text)


    def OnChar(self, event):
        """Handler for character input, displays printable character."""
        if self._fixed and not self._bytes: return # NULL number

        self._QueueEvents()
        cmd = HexByteCommand(self)
        selection = self.GetSelection()
        if selection[0] != selection[1] and not self._fixed:
            del self._bytes [selection[0]:selection[1] + 1]
            del self._bytes0[selection[0]:selection[1] + 1]
            self.DeleteBack()
        elif self._fixed:
            self.SetSelection(selection[0], selection[0])

        sself = super(ByteTextCtrl, self)
        if not event.UnicodeKey: event.Skip()
        elif sself.CurrentPos == self.GetLastPosition() and self._fixed: pass
        else:
            pos, bpos = sself.CurrentPos, self.CurrentPos
            tbyte = re.sub("[^\x20-\x7e]", ".", chr(event.KeyCode))
            if bpos >= len(self._bytes) or pos >= self.GetLastPosition():
                self._bytes0.append(None), self._bytes.append(0)
            elif not self.Overtype:
                self._bytes0.insert(pos, None), self._bytes.insert(pos, 0)
            if (not tbyte or event.KeyCode == self._bytes[bpos]) \
            and (selection[0] == selection[1] or self._fixed): return
            if tbyte: self._bytes[bpos] = event.KeyCode

            if self.Overtype and pos < self.GetLastPosition():
                self.Replace(pos, pos + 1, tbyte)
                self.StartStyling(pos)
                self.SetStyling(1, self.STYLE_CHANGED if self._bytes0[bpos] != self._bytes[bpos] else 0)
            else: self._Populate()
            self.SetSelection(pos + 1, pos + 1)
        cmd.Store()


    def OnKeyDown(self, event):
        """Handler for key down, fires position change events."""

        if event.CmdDown() and not event.AltDown() and not event.ShiftDown() \
        and ord("Z") == event.KeyCode:
            return self.Undo(mirror=True)

        elif event.CmdDown() and not event.AltDown() and (not event.ShiftDown() \
        and ord("Y") == event.KeyCode) or (event.ShiftDown() and ord("Z") == event.KeyCode):
            return self.Redo(mirror=True)

        elif event.CmdDown() and not event.AltDown() and not event.ShiftDown() \
        and event.KeyCode in KEYS.INSERT + (ord("C"), ):
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(str(self._bytes)))
                wx.TheClipboard.Close()
            return

        elif event.CmdDown() and not event.AltDown() and (not event.ShiftDown()
        and ord("V") == event.KeyCode or event.ShiftDown() and event.KeyCode in KEYS.INSERT):
            text = None
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                    o = wx.TextDataObject()
                    wx.TheClipboard.GetData(o)
                    text = o.Text
                wx.TheClipboard.Close()
            if text is not None: self.InsertInto(text)
            return

        elif event.KeyCode in KEYS.INSERT and not event.HasAnyModifiers():
            if not self._fixed: event.Skip() # Disallow changing overtype if length fixed

        if event.KeyCode in KEYS.LEFT + KEYS.RIGHT:
            self._QueueEvents()
            event.Skip()
            direction = -1 if event.KeyCode in KEYS.LEFT else 1
            if event.ShiftDown() and direction > 0:
                sself = super(ByteTextCtrl, self)
                pos = sself.CurrentPos
                linepos = pos - self.PositionFromLine(self.LineFromPosition(pos))
                if linepos >= self.WIDTH:  # Already at line end:
                    self.CharRightExtend() # include first char at next line

        elif event.KeyCode in KEYS.DELETE + KEYS.BACKSPACE:
            self._QueueEvents()
            if self._fixed: return

            cmd = HexByteCommand(self)
            selection = list(self.GetSelection())
            if selection[0] != selection[1]:
                del self._bytes [selection[0]:selection[1]]
                del self._bytes0[selection[0]:selection[1]]
                self.SetSelection(selection[0], selection[0])
                cmd.Submit(mirror=True)
                return

            sself = super(ByteTextCtrl, self)
            pos       = sself.CurrentPos
            line0     = sself.FirstVisibleLine
            line      = self.LineFromPosition(pos)
            linepos   = pos - self.PositionFromLine(line)
            direction = -(event.KeyCode in KEYS.BACKSPACE)

            if not self._bytes or not pos and direction \
            or pos == self.GetLastPosition() and not direction:
                return

            bpos = self.CurrentPos
            if pos == self.GetLastPosition(): bpos = bpos - 1
            for bb in self._bytes, self._bytes0: del bb[bpos]

            if line == self.LineCount - 1 and (not direction or linepos):
                # Last line and not backspacing from first byte
                frompos = max(pos + direction, 0)
                topos   = sself.Length if frompos + 1 > sself.Length else frompos + 1
                self.Remove(frompos, topos)
            else:
                self._Populate()
                sself.SetSelection(*(pos + direction, ) * 2)
            cmd.Store()
        elif event.KeyCode in KEYS.ENTER + KEYS.TAB: pass
        else:
            self._QueueEvents()
            event.Skip()


    def OnMouse(self, event):
        """Handler for mouse event, fires position change events."""
        self._QueueEvents()
        event.Skip()


    def _AdaptValue(self, value):
        """Returns the value as str for byte representation."""
        is_long = is_fixed_long(value) and not is_long_long(value)
        if is_long:                    v = struct.pack(">q", value)
        elif isinstance(value, int):   v = struct.pack(">l", value)
        elif isinstance(value, float): v = struct.pack(">f", value)
        elif value is None:            v = b""
        elif isinstance(value, text_type):
            try: v = value.encode("latin1")
            except Exception: v = value.encode("utf-8")
        else: v = value
        if not isinstance(v, bytes):
            v = str(v).encode("latin1")
        return v


    def _QueueEvents(self):
        """Raises CaretPositionEvent or LinePositionEvent or SelectionEvent if changed after."""

        pos, firstline = self.CurrentPos, self.FirstVisibleLine
        notselected, selection = self.GetSelectionEmpty(), self.GetSelection()

        def after():
            if not self: return
            if pos != self.CurrentPos:
                evt = CaretPositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.CurrentPos)
                wx.PostEvent(self, evt)
            elif firstline != self.FirstVisibleLine:
                evt = LinePositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.FirstVisibleLine)
                wx.PostEvent(self, evt)
            if notselected != self.GetSelectionEmpty() \
            or not self.GetSelectionEmpty() and selection != self.GetSelection():
                evt = SelectionEvent(self.Id)
                evt.SetEventObject(self)
                wx.PostEvent(self, evt)
        wx.CallAfter(after)



class JSONTextCtrl(wx.stc.StyledTextCtrl):
    """
    A StyledTextCtrl configured for JSON syntax highlighting and folding.
    """

    """JSON reserved keywords."""
    KEYWORDS = list(map(text_type, sorted(["null"])))
    AUTOCOMP_STOPS = " .,;:([)]}'\"\\<>%^&+-=*/|`"
    """String length from which autocomplete starts."""
    AUTOCOMP_LEN = 2
    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"


    def __init__(self, *args, **kwargs):
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self.SetLexer(wx.stc.STC_LEX_JSON)
        self.SetTabWidth(2)
        # Keywords must be lowercase, required by StyledTextCtrl
        self.SetKeyWords(0, u" ".join(self.KEYWORDS).lower())
        self.AutoCompStops(self.AUTOCOMP_STOPS)
        self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(False)
        self.AutoCompSetIgnoreCase(False)

        self.SetTabWidth(2)
        self.SetUseTabs(False)

        self.SetMarginCount(2)
        self.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(0, 25)
        self.SetMarginCursor(0, wx.stc.STC_CURSORARROW)

        self.SetProperty("fold", "1")
        self.SetMarginType(1, wx.stc.STC_MARGIN_SYMBOL)
        self.SetMarginMask(1, wx.stc.STC_MASK_FOLDERS)
        self.SetMarginSensitive(1, True)
        self.SetMarginWidth(1, 12)

        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPEN,    wx.stc.STC_MARK_BOXMINUS,          "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDER,        wx.stc.STC_MARK_BOXPLUS,           "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERSUB,     wx.stc.STC_MARK_VLINE,             "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERTAIL,    wx.stc.STC_MARK_LCORNER,           "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEREND,     wx.stc.STC_MARK_BOXPLUSCONNECTED,  "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPENMID, wx.stc.STC_MARK_BOXMINUSCONNECTED, "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERMIDTAIL, wx.stc.STC_MARK_TCORNER,           "white", "#808080")

        self.SetStyleSpecs()

        self.Bind(wx.EVT_KEY_DOWN,            self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,           self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,          self.OnKillFocus)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,  self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_MARGINCLICK, self.OnMarginClick)
        self.Bind(wx.stc.EVT_STC_UPDATEUI,    self.OnUpdateUI)


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        fgcolour, bgcolour, highcolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW
                      if self.Enabled else wx.SYS_COLOUR_BTNFACE,
                      wx.SYS_COLOUR_HOTLIGHT)
        )

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD, "fore:#FF0000")
        self.StyleClearAll() # Apply the new default style to all styles

        self.StyleSetSpec(wx.stc.STC_JSON_DEFAULT,   "face:%s" % self.FONT_FACE)
        self.StyleSetSpec(wx.stc.STC_JSON_STRING,    "fore:#FF007F") # "
        # 01234567890.+-e
        self.StyleSetSpec(wx.stc.STC_JSON_NUMBER, "fore:#FF00FF")
        # : [] {}
        self.StyleSetSpec(wx.stc.STC_JSON_OPERATOR, "fore:%s" % highcolour)
        # //...
        self.StyleSetSpec(wx.stc.STC_JSON_LINECOMMENT, "fore:#008000")
        # /*...*/
        self.StyleSetSpec(wx.stc.STC_JSON_BLOCKCOMMENT, "fore:#008000")


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(self.__class__, self).Enable(enable)
        self.SetStyleSpecs()
        return result

    def OnFocus(self, event):
        """Handler for control getting focus, shows caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_LINE)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides autocomplete and caret."""
        event.Skip()
        self.AutoCompCancel()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        self.SetStyleSpecs()


    def OnUpdateUI(self, evt):
        # check for matching braces
        braceAtCaret = -1
        braceOpposite = -1
        charBefore = None
        caretPos = self.GetCurrentPos()

        if caretPos > 0:
            charBefore = self.GetCharAt(caretPos - 1)
            styleBefore = self.GetStyleAt(caretPos - 1)

        # check before
        if charBefore and chr(charBefore) in "[]{}()" and styleBefore == wx.stc.STC_JSON_OPERATOR:
            braceAtCaret = caretPos - 1

        # check after
        if braceAtCaret < 0:
            charAfter = self.GetCharAt(caretPos)
            styleAfter = self.GetStyleAt(caretPos)

            if charAfter and chr(charAfter) in "[]{}()" and styleAfter == wx.stc.STC_JSON_OPERATOR:
                braceAtCaret = caretPos

        if braceAtCaret >= 0:
            braceOpposite = self.BraceMatch(braceAtCaret)

        if braceAtCaret != -1  and braceOpposite == -1:
            self.BraceBadLight(braceAtCaret)
        else:
            self.BraceHighlight(braceAtCaret, braceOpposite)
            #pt = self.PointFromPosition(braceOpposite)
            #self.Refresh(True, wxRect(pt.x, pt.y, 5,5))
            #print(pt)
            #self.Refresh(False)


    def ToggleFolding(self):
        """Toggles all current folding, off if all lines folded else on."""
        lineCount = self.GetLineCount()
        expanding = True

        # Find out if we are folding or unfolding
        for lineNum in range(lineCount):
            if self.GetFoldLevel(lineNum) & wx.stc.STC_FOLDLEVELHEADERFLAG:
                expanding = not self.GetFoldExpanded(lineNum)
                break

        lineNum = 0
        while lineNum < lineCount:
            level = self.GetFoldLevel(lineNum)
            if level & wx.stc.STC_FOLDLEVELHEADERFLAG \
            and (level & wx.stc.STC_FOLDLEVELNUMBERMASK) == wx.stc.STC_FOLDLEVELBASE:
                if expanding:
                    self.SetFoldExpanded(lineNum, True)
                    lineNum = self.ToggleLineFolding(lineNum, True)
                    lineNum = lineNum - 1
                else:
                    lastChild = self.GetLastChild(lineNum, -1)
                    self.SetFoldExpanded(lineNum, False)
                    if lastChild > lineNum:
                        self.HideLines(lineNum+1, lastChild)
            lineNum = lineNum + 1


    def ToggleLineFolding(self, line, doExpand, force=False, visLevels=0, level=-1):
        """Expands or collapses folding on specified line."""
        lastChild = self.GetLastChild(line, level)
        line = line + 1

        while line <= lastChild:
            if force:
                (self.ShowLines if visLevels > 0 else self.HideLines)(line, line)
            elif doExpand: self.ShowLines(line, line)

            if level == -1:
                level = self.GetFoldLevel(line)

            if level & self.STC_FOLDLEVELHEADERFLAG:
                if force:
                    self.SetFoldExpanded(line, visLevels > 1)

                    line = self.ToggleLineFolding(line, doExpand, force, visLevels-1)

                else:
                    on = doExpand and self.GetFoldExpanded(line)
                    line = self.ToggleLineFolding(line, on, force, visLevels-1)
            else:
                line += 1

        return line


    def OnMarginClick(self, event):
        """Handler for clicking margin, folds 2nd margin icons."""
        if event.GetMargin() != 1: return

        if event.GetShift() and event.GetControl():
            self.ToggleFolding()
            return

        lineClicked = self.LineFromPosition(event.GetPosition())
        if not self.GetFoldLevel(lineClicked) & wx.stc.STC_FOLDLEVELHEADERFLAG:
            return

        if event.GetShift():
            self.SetFoldExpanded(lineClicked, True)
            self.ToggleLineFolding(lineClicked, True, True, 1)
        elif event.GetControl():
            if self.GetFoldExpanded(lineClicked):
                self.SetFoldExpanded(lineClicked, False)
                self.ToggleLineFolding(lineClicked, False, True, 0)
            else:
                self.SetFoldExpanded(lineClicked, True)
                self.ToggleLineFolding(lineClicked, True, True, 100)
        else:
            self.ToggleFold(lineClicked)


    def OnKeyDown(self, event):
        """
        Shows autocomplete if user is entering a known word, or pressed
        Ctrl-Space.
        """
        skip = True
        if self.CallTipActive():
            self.CallTipCancel()
        if not self.AutoCompActive() and not event.AltDown():
            do_autocomp = False
            words = self.KEYWORDS
            autocomp_len = 0
            if event.UnicodeKey in KEYS.SPACE and event.CmdDown():
                # Start autocomp when user presses Ctrl+Space
                do_autocomp = True
            elif not event.CmdDown():
                # Check if we have enough valid text to start autocomplete
                char = None
                try: # Not all keycodes can be chars
                    char = chr(event.UnicodeKey).decode("latin1")
                except Exception:
                    pass
                if char not in KEYS.ENTER and char is not None:
                    # Get a slice of the text on the current text up to caret.
                    line_text = self.GetTextRange(
                        self.PositionFromLine(self.GetCurrentLine()),
                        self.GetCurrentPos()
                    )
                    text = u""
                    for last_word in re.findall(r"(\w+)$", line_text, re.I):
                        text += last_word
                    text = text.upper()
                    if char in string.ascii_letters:
                        text += char.upper()
                        if len(text) >= self.AUTOCOMP_LEN and any(x for x in
                        words if x.upper().startswith(text)):
                            do_autocomp = True
                            current_pos = self.GetCurrentPos() - 1
                            while chr(self.GetCharAt(current_pos)).isalnum():
                                current_pos -= 1
                            autocomp_len = self.GetCurrentPos() - current_pos - 1
            if do_autocomp:
                if skip: event.Skip()
                self.AutoCompShow(autocomp_len, u" ".join(words))
        elif self.AutoCompActive() and event.KeyCode in KEYS.DELETE:
            self.AutoCompCancel()
        if skip: event.Skip()



TabLeftDClickEvent, EVT_TAB_LEFT_DCLICK = wx.lib.newevent.NewEvent()

class TabbedHtmlWindow(wx.Panel):
    """
    HtmlWindow with tabs for different content pages.
    """

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.html.HW_DEFAULT_STYLE,
                 name=""):
        wx.Panel.__init__(self, parent, id=id, pos=pos, size=size, style=style)
        # [{"title", "content", "id", "info", "scrollpos", "scrollrange"}]
        self._tabs = []
        self._default_page = ""      # Content shown on the blank page
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_WINDOW)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        agwStyle = (wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                    wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                    wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                    wx.lib.agw.flatnotebook.FNB_VC8)
        if "linux" in sys.platform and wx.VERSION[:3] == (4, 1, 1):
            # wxPython 4.1.1 on Linux crashes with FNB_VC8
            agwStyle ^= wx.lib.agw.flatnotebook.FNB_VC8
        notebook = self._notebook = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=self, size=(-1, 27), style=wx.NB_TOP,
            agwStyle=agwStyle)
        self._html = wx.html.HtmlWindow(self, style=style, name=name)

        self.Sizer.Add(notebook, flag=wx.GROW)
        self.Sizer.Add(self._html, proportion=1, flag=wx.GROW)

        self._html.Bind(wx.EVT_SIZE, self._OnSize)
        notebook.GetTabArea().Bind(wx.EVT_LEFT_DCLICK, self._OnLeftDClickTabArea)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._OnChangeTab)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CONTEXT_MENU,
                      self._OnMenu)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_CLOSING,
                      self._OnDeleteTab)
        notebook.Bind(wx.lib.agw.flatnotebook.EVT_FLATNOTEBOOK_PAGE_DROPPED,
                      self._OnDropTab)
        self._html.Bind(wx.EVT_SCROLLWIN, self._OnScroll)

        ColourManager.Manage(notebook, "ActiveTabColour", wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "TabAreaColour", wx.SYS_COLOUR_BTNFACE)
        try: notebook._pages.GetSingleLineBorderColour = notebook.GetActiveTabColour
        except Exception: pass # Hack to get uniform background colour

        # Monkey-patch object with HtmlWindow and FlatNotebook attributes
        for name in ["Scroll", "GetScrollRange", "GetScrollPos",
                     "SelectAll", "SelectionToText",
                     "GetBackgroundColour", "SetBackgroundColour"]:
            setattr(self, name, getattr(self._html, name))
        for name in ["DeletePage", "GetPageCount", "GetTabAreaColour", "SetTabAreaColour"]:
            setattr(self, name, getattr(self._notebook, name))

        self._CreateTab(0, "") # Make default empty tab in notebook with no text
        self.Layout()


    def _OnLeftDClickTabArea(self, event):
        """Fires a TabLeftDClickEvent if a tab header was double-clicked."""
        area = self._notebook.GetTabArea()
        where, tab = area.HitTest(event.GetPosition())
        if wx.lib.agw.flatnotebook.FNB_TAB == where and tab < len(self._tabs) \
        and self._tabs[tab].get("info"):
            wx.PostEvent(self, TabLeftDClickEvent(Data=self._tabs[tab]))


    def _OnSize(self, event):
        """
        Handler for sizing the HtmlWindow, sets new scroll position based
        previously stored one (HtmlWindow loses its scroll position on resize).
        """
        event.Skip() # Allow event to propagate to wx handler
        if self._tabs:
            tab = self._tabs[self._notebook.GetSelection()]
            for i in range(2):
                orient = wx.VERTICAL if i else wx.HORIZONTAL
                # Division can be > 1 on first resizings, bound it to 1.
                pos, rng = tab["scrollpos"][i], tab["scrollrange"][i]
                ratio = pos / float(rng) if rng else 0.0
                ratio = min(1, pos / float(rng) if rng else 0.0)
                tab["scrollpos"][i] = ratio * self.GetScrollRange(orient)
            # Execute scroll later as something resets it after this handler
            try:
                wx.CallLater(50, lambda: self and
                             self.Scroll(*tab["scrollpos"]) if self else None)
            except Exception:
                pass # CallLater fails if not called from the main thread


    def _OnScroll(self, event):
        """
        Handler for scrolling the window, stores scroll position
        (HtmlWindow loses it on resize).
        """
        event.Skip() # Propagate to wx handler and get updated results later
        wx.CallAfter(self._StoreScrollPos)


    def _StoreScrollPos(self):
        """Stores the current scroll position for the current tab, if any."""
        if self and self._tabs:
            tab = self._tabs[self._notebook.GetSelection()]
            tab["scrollpos"]   = [self.GetScrollPos(wx.HORIZONTAL),
                                  self.GetScrollPos(wx.VERTICAL)]
            tab["scrollrange"] = [self.GetScrollRange(wx.HORIZONTAL),
                                  self.GetScrollRange(wx.VERTICAL)]


    def _OnChangeTab(self, event):
        """Handler for selecting another tab in notebook, loads tab content."""
        if self._tabs:
            self.SetSelection(self._notebook.GetSelection())
            wx.PostEvent(self, event) # Forward event to external listeners


    def _OnDropTab(self, event):
        """Handler for dropping a dragged tab, rearranges internal data."""
        new, old = event.GetSelection(), event.GetOldSelection()
        new = min(new, len(self._tabs) - 1) # Can go over the edge
        if self._tabs and new != old and new >= 0:
            self._tabs[old], self._tabs[new] = self._tabs[new], self._tabs[old]


    def _OnDeleteTab(self, event):
        """Handler for clicking in notebook to close a tab."""
        if not self._tabs: return event.Veto() # Cancel deleting default page

        nb = self._notebook
        pagecount = nb.GetPageCount()
        tab = self._tabs[event.GetSelection()]
        if 1 == pagecount: event.Veto() # Only page: reuse

        def after():
            if not self: return
            self._tabs.remove(tab)
            if 1 == pagecount: # Was the only page, reuse as default
                nb.SetPageText(0, "")
                self._SetPage(self._default_page)
                # Hide dropdown selector, remove X from tab style.
                style = nb.GetAGWWindowStyleFlag()
                style &= ~wx.lib.agw.flatnotebook.FNB_X_ON_TAB & \
                         ~wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST
                nb.SetAGWWindowStyleFlag(style)
            else:
                index = min(nb.GetSelection(), pagecount - 2)
                self.SetSelection(index)

        if tab.get("info"):
            evt = wx.lib.agw.flatnotebook.FlatNotebookEvent(event.EventType, self.Id)
            evt.SetSelection(event.GetSelection())
            evt.SetEventObject(self)
            wx.PostEvent(self, evt) # Forward event to external listeners
        wx.CallLater(1, after)


    def _OnMenu(self, event):
        """Handler for notebook page context menu, forwards event."""
        evt = wx.lib.agw.flatnotebook.FlatNotebookEvent(event.EventType, self.Id)
        evt.SetSelection(event.GetSelection())
        evt.SetEventObject(self)
        wx.PostEvent(self, evt) # Forward event to external listeners


    def _CreateTab(self, index, title):
        """Creates a new tab in the tab container at specified index."""
        p = wx.Panel(self, size=(0,0))
        p.Hide() # Dummy empty window as notebook needs something to hold
        self._notebook.InsertPage(index, page=p, text=title, select=True)


    def _SetPage(self, content):
        """Sets current HTML page content."""
        self._html.SetPage(content)
        ColourManager.Manage(self._html, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def SetCustomPage(self, content):
        """Sets custom page to show if there are no pages left."""
        self._default_page = content
        if not self._tabs:
            self._SetPage(self._default_page)


    def InsertPage(self, index, content, title, id, info=None):
        """
        Inserts a new tab with the specified title and content at the specified
        position, and activates the new tab.
        """
        tab = {"title": title, "content": content, "id": id,
               "scrollpos": [0, 0], "scrollrange": [0, 0], "info": info}
        is_empty = bool(self._tabs)
        self._tabs.insert(index, tab)
        if is_empty:
            self._CreateTab(index, tab["title"])
        else: # First real tab: fill the default empty one
            self._notebook.SetPageText(0, tab["title"])
            # Hide dropdown selector, remove X from tab style.
            style = self._notebook.GetAGWWindowStyleFlag()
            style |= wx.lib.agw.flatnotebook.FNB_X_ON_TAB | \
                     wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST
            self._notebook.SetAGWWindowStyleFlag(style)

        self._html.Freeze()
        try:     self._SetPage(tab["content"])
        finally: self._html.Thaw()


    def GetPage(self, page=None, id=None):
        """Returns the tab at the given position or with given ID, or None."""
        if page is not None:
            return self._tabs[page] if 0 <= page < len(self._tabs) else None
        return next((x for x in self._tabs if x["id"] == id), None)


    def GetPageIndex(self, win):
        """Returns the index at which the tab is found."""
        return next((i for i, x in enumerate(self._tabs) if x == win), -1)


    def SetPageData(self, id, title, content, info, new_id=None):
        """
        Sets the title, content and info of the tab with the specified ID.

        @param   info    additional info associated with the tab
        @param   new_id  if set, tab ID is updated to this
        """
        tab = next((x for x in self._tabs if x["id"] == id), None)
        if tab:
            tab["title"], tab["content"], tab["info"] = title, content, info
            if new_id is not None:
                tab["id"] = new_id
            self._notebook.SetPageText(self._tabs.index(tab), tab["title"])
            self._notebook.Refresh()
            if self._tabs[self._notebook.GetSelection()] == tab:
                self._html.Freeze()
                try:
                    self._SetPage(tab["content"])
                    self._html.Scroll(*tab["scrollpos"])
                finally: self._html.Thaw()


    def GetSelection(self):
        """Returns the currently selected page, or -1 if none was selected."""
        return self._notebook.GetSelection()


    def SetSelection(self, index=None, id=None):
        """Sets active the tab at the specified index, or with specified ID."""
        if id is not None:
            tab = next((x for x in self._tabs if x["id"] == id), None)
            index = self._tabs.index(tab)
        tab = self._tabs[index]
        self._notebook.SetSelection(index)
        self._html.Freeze()
        try:
            self._SetPage(tab["content"])
            self._html.Scroll(*tab["scrollpos"])
        finally: self._html.Thaw()

    Selection = property(GetSelection, SetSelection)


    def GetActiveTabData(self):
        """Returns all the data for the active tab."""
        if self._tabs:
            return self._tabs[self._notebook.GetSelection()]


    def GetHtmlWindow(self):
        """Returns HTML window."""
        return self._html


    def GetNotebook(self):
        """Returns tabbed notebook."""
        return self._notebook


    def GetTabArea(self):
        """Returns notebook tab area."""
        return self._notebook.GetTabArea()


    def GetTabCount(self):
        """Returns the number of tabs (default empty tab is not counted)."""
        return len(self._tabs)



class TextCtrlAutoComplete(wx.TextCtrl):
    """
    A text control with autocomplete using a dropdown list of choices. During
    typing, the first matching choice is appended to textbox value, with the
    appended text auto-selected.
    Fires a wx.EVT_LIST_DELETE_ALL_ITEMS event if user clicked to clear all
    choices.

    If wx.PopupWindow is not available (Mac), behaves like a common TextCtrl.
    Based on TextCtrlAutoComplete by Michele Petrazzo, from a post
    on 09.02.2006 in wxPython-users thread "TextCtrlAutoComplete",
    http://wxpython-users.1045709.n5.nabble.com/TextCtrlAutoComplete-td2348906.html
    """
    DROPDOWN_COUNT_PER_PAGE = 8
    DROPDOWN_CLEAR_TEXT = "Clear search history"


    def __init__(self, parent, choices=None, description="",
                 **kwargs):
        """
        @param   choices      list of auto-complete choices, if any
        @param   description  description text shown if nothing entered yet
        """
        if "style" in kwargs:
            kwargs["style"] = wx.TE_PROCESS_ENTER | kwargs["style"]
        else:
            kwargs["style"] = wx.TE_PROCESS_ENTER
        wx.TextCtrl.__init__(self, parent, **kwargs)
        self._text_colour = self._desc_colour = self._clear_colour = None
        ColourManager.Manage(self, "_text_colour",  wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(self, "_desc_colour",  wx.SYS_COLOUR_GRAYTEXT)
        ColourManager.Manage(self, "_clear_colour", wx.SYS_COLOUR_HOTLIGHT)

        self._choices = [] # Ordered case-insensitively
        self._choices_lower = [] # Cached lower-case choices
        self._ignore_textchange = False # ignore next OnText
        self._skip_autocomplete = False # skip setting textbox value in OnText
        self._lastinsertionpoint = None # For whether to show dropdown on click
        self._value_last = "" # For resetting to last value on Esc
        self._description = description
        self._description_on = False # Is textbox filled with description?
        if not self.Value:
            self.Value = self._description
            self.SetForegroundColour(self._desc_colour)
            self._description_on = True
        try:
            self._listwindow = wx.PopupWindow(self)
            self._listbox = wx.ListCtrl(self._listwindow, pos=(0, 0),
                                        style=wx.BORDER_SIMPLE | wx.LC_REPORT
                                        | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        except AttributeError:
            # Probably Mac, where wx.PopupWindow does not exist yet as of 2013.
            self._listbox = self._listwindow = None

        if self._listbox:
            ColourManager.Manage(self._listbox, "TextColour", wx.SYS_COLOUR_GRAYTEXT)
            self.SetChoices(choices or [])
            self._cursor = None
            # For changing cursor when hovering over final "Clear" item.
            self._cursor_action_hover = wx.Cursor(wx.CURSOR_HAND)
            self._cursor_default      = wx.Cursor(wx.CURSOR_DEFAULT)

            gp = self
            while gp is not None:
                # Dropdown has absolute position, must be moved when parent is.
                gp.Bind(wx.EVT_MOVE,                self.OnSizedOrMoved, gp)
                gp.Bind(wx.EVT_SIZE,                self.OnSizedOrMoved, gp)
                gp = gp.GetParent()
            self.Bind(wx.EVT_TEXT,                  self.OnText, self)
            self.Bind(wx.EVT_KEY_DOWN,              self.OnKeyDown, self)
            self.Bind(wx.EVT_LEFT_DOWN,             self.OnClickDown, self)
            self.Bind(wx.EVT_LEFT_UP,               self.OnClickUp, self)
            self._listbox.Bind(wx.EVT_LEFT_DOWN,    self.OnListClick)
            self._listbox.Bind(wx.EVT_LEFT_DCLICK,  self.OnListDClick)
            self._listbox.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
            self._listwindow.Bind(wx.EVT_LISTBOX,   self.OnListItemSelected,
                                  self._listbox)
        self.Bind(wx.EVT_SET_FOCUS,                 self.OnFocus, self)
        self.Bind(wx.EVT_KILL_FOCUS,                self.OnFocus, self)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,        self.OnSysColourChange)


    def OnSysColourChange(self, event):
        """
        Handler for system colour change, updates text colours.
        """
        event.Skip()
        colour = self._desc_colour if self._description_on else self._text_colour
        self.SetForegroundColour(colour)
        self.SetChoices(self._choices)


    def OnListClick(self, event):
        """Handler for clicking the dropdown list, selects the clicked item."""
        index, flag = self._listbox.HitTest(event.GetPosition())
        if len(self._choices) > index >= 0:
            self._listbox.Select(index)
        elif index == len(self._choices) + 1: # Clicked "Clear choices" item
            event = wx.CommandEvent(wx.wxEVT_COMMAND_LIST_DELETE_ALL_ITEMS,
                                    self.GetId())
            wx.PostEvent(self, event)


    def OnListDClick(self, event):
        """
        Handler for double-clicking the dropdown list, sets textbox value to
        selected item and fires TEXT_ENTER.
        """
        self.SetValueFromSelected()
        enterevent = wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER, self.GetId())
        wx.PostEvent(self, enterevent)


    def OnSizedOrMoved(self, event):
        """
        Handler for moving or sizing the control or any parent, hides dropdown.
        """
        event.Skip()
        if self: self.ShowDropDown(False)


    def OnClickDown(self, event):
        """
        Handler for clicking and holding left mouse button, remembers click
        position.
        """
        event.Skip()
        self._lastinsertionpoint = self.GetInsertionPoint()


    def OnClickUp(self, event):
        """
        Handler for releasing left mouse button, toggles dropdown list
        visibility on/off if clicking same spot in textbox.
        """
        event.Skip()
        if (self.GetInsertionPoint() == self._lastinsertionpoint):
            self.ShowDropDown(not self._listwindow.Shown)


    def OnListItemSelected(self, event):
        """
        Handler for selecting an item in the dropdown list, sets its value to
        textbox.
        """
        event.Skip()
        self.SetValueFromSelected()


    def OnFocus(self, event):
        """
        Handler for focusing/unfocusing the control, shows/hides description.
        """
        event.Skip() # Allow to propagate to parent, to show having focus
        if self and self.FindFocus() is self:
            if self._description_on:
                self.Value = ""
            self._value_last = self.Value
            self.SelectAll()
        elif self:
            if self._description and not self.Value:
                # Control has been unfocused, set and colour description
                self.Value = self._description
                self.SetForegroundColour(self._desc_colour)
                self._description_on = True
            if self._listbox:
                self.ShowDropDown(False)


    def OnMouse(self, event):
        """
        Handler for mouse events, changes cursor to pointer if hovering over
        action item like "Clear history".
        """
        event.Skip()
        index, flag = self._listbox.HitTest(event.GetPosition())
        if index == self._listbox.ItemCount - 1:
            if self._cursor != self._cursor_action_hover:
                self._cursor = self._cursor_action_hover
                self._listbox.SetCursor(self._cursor_action_hover)
        elif self._cursor == self._cursor_action_hover:
            self._cursor = self._cursor_default
            self._listbox.SetCursor(self._cursor_default)


    def OnKeyDown(self, event):
        """Handler for any keypress, changes dropdown items."""
        if not self._choices: return event.Skip()

        skip = True
        visible = self._listwindow.Shown
        selected = self._listbox.GetFirstSelected()
        selected_new = None
        if event.KeyCode in KEYS.UP + KEYS.DOWN:
            if visible:
                step = 1 if event.KeyCode in KEYS.DOWN else -1
                itemcount = len(self._choices)
                selected_new = min(itemcount - 1, max(0, selected + step))
                self._listbox.Select(selected_new)
                ensured = selected_new + (0
                          if selected_new != len(self._choices) - 1 else 2)
                self._listbox.EnsureVisible(ensured)
            self.ShowDropDown()
            skip = False
        elif event.KeyCode in KEYS.PAGING:
            if visible:
                step = 1 if event.KeyCode in KEYS.PAGEDOWN else -1
                self._listbox.ScrollPages(step)
                itemcount = len(self._choices)
                countperpage = self._listbox.CountPerPage
                next_pos = selected + countperpage * step
                selected_new = min(itemcount - 1, max(0, next_pos))
                ensured = selected_new + (0
                          if selected_new != len(self._choices) - 1 else 2)
                self._listbox.EnsureVisible(ensured)
                self._listbox.Select(selected_new)
            self.ShowDropDown()
            skip = False
        elif event.KeyCode in KEYS.DELETE + (wx.WXK_BACK, ):
            self._skip_autocomplete = True
            self.ShowDropDown()

        if visible:
            if selected_new is not None: # Replace textbox value with new text
                self._ignore_textchange = True
                self.Value = self._listbox.GetItemText(selected_new)
                self.SetInsertionPointEnd()
            if event.KeyCode in KEYS.ENTER:
                self.ShowDropDown(False)
            if wx.WXK_ESCAPE == event.KeyCode:
                self.ShowDropDown(False)
                skip = False
        else:
            if wx.WXK_ESCAPE == event.KeyCode:
                if self._value_last != self.Value:
                    self.Value = self._value_last
                    self.SelectAll()
            elif event.CmdDown() and event.KeyCode in map(ord, "AH"):
                # Avoid opening dropdown on Ctrl-A (select all) or Ctrl-H (backspace)
                self._ignore_textchange = True
        if skip: event.Skip()


    def OnText(self, event):
        """
        Handler for changing textbox value, auto-completes the text and selects
        matching item in dropdown list, if any.
        """
        event.Skip()
        if self._ignore_textchange:
            self._ignore_textchange = self._skip_autocomplete = False
            return
        text = self.Value
        if text and not self._description_on:
            found = False
            text_lower = text.lower()
            for i, choice in enumerate(self._choices):
                if self._choices_lower[i].startswith(text_lower):
                    choice = text + choice[len(text):]
                    found = True
                    self.ShowDropDown(True)
                    self._listbox.Select(i)
                    self._listbox.EnsureVisible(i)
                    if not self._skip_autocomplete:
                        # Use a callback function to change value - changing
                        # value inside handler causes multiple events in Linux.
                        def autocomplete_callback(choice):
                            if self and self.Value == text: # Can have changed
                                self._ignore_textchange = True # To skip OnText
                                self.Value = choice # Auto-complete text
                                self.SetSelection(len(text), -1) # Select added
                        wx.CallAfter(autocomplete_callback, choice)
                    break
            if not found: # Deselect currently selected item
                self._listbox.Select(self._listbox.GetFirstSelected(), False)
        else:
            self.ShowDropDown(False)
        self._skip_autocomplete = False


    def SetChoices(self, choices):
        """Sets the choices available in the dropdown list."""
        if choices:
            lower = [i.lower() for i in choices]
            sorted_all = sorted(zip(lower, choices)) # [("a", "A"), ("b", "b")]
            self._choices_lower, self._choices = map(list, zip(*sorted_all))
        else:
            self._choices_lower, self._choices = [], []

        if self._listbox:
            self._listbox.ClearAll()
            self._listbox.InsertColumn(0, "Select")
            choices = self._choices[:]
            choices += ["", self.DROPDOWN_CLEAR_TEXT] if choices else []
            for i, text in enumerate(choices):
                self._listbox.InsertItem(i, text)
            if choices: # Colour "Clear" item
                self._listbox.SetItemTextColour(i, self._clear_colour)

            itemheight = self._listbox.GetItemRect(0)[-1] if choices else 0
            itemcount = min(len(choices), self.DROPDOWN_COUNT_PER_PAGE)
            # Leave room vertically for border and padding.
            size = wx.Size(self.Size.width - 3, itemheight * itemcount + 5)
            self._listbox.Size = self._listwindow.Size = size
            # Leave room for vertical scrollbar
            self._listbox.SetColumnWidth(0, size.width - 16)
            self._listbox.SetScrollbar(wx.HORIZONTAL, 0, 0, 0)


    def SetValueFromSelected(self):
        """Sets the textbox value from the selected dropdown item, if any."""
        selected = self._listbox.GetFirstSelected()
        if len(self._choices) > selected >= 0:
            self.SetValue(self._listbox.GetItemText(selected))
            self.SetInsertionPointEnd()
            self.SetSelection(-1, -1)
            self.ShowDropDown(False)


    def ShowDropDown(self, show=True):
        """Toggles the dropdown list visibility on/off."""
        if show and self.IsShownOnScreen() and self._choices and self._listwindow:
            size = self._listwindow.GetSize()
            width, height = self.Size.width - 3, self.Size.height
            x, y = self.ClientToScreen(0, height - 2)
            if size.GetWidth() != width:
                size.SetWidth(width)
                self._listwindow.SetSize(size)
                self._listbox.SetSize(self._listwindow.GetClientSize())
                # Leave room for vertical scrollbar
                self._listbox.SetColumnWidth(0, width - 16)
                self._listbox.SetScrollbar(wx.HORIZONTAL, 0, 0, 0)
            if y + size.GetHeight() < wx.GetDisplaySize().height:
                self._listwindow.SetPosition((x, y))
            else: # No room at the bottom: show dropdown on top of textbox
                self._listwindow.SetPosition((x, y - height - size.height))
            self._listwindow.Show()
        elif self._listwindow:
            self._listwindow.Hide()


    def IsDropDownShown(self):
        """Returns whether the dropdown window is currently shown."""
        return self._listwindow.Shown


    def GetValue(self):
        """
        Returns the current value in the text field, or empty string if filled
        with description.
        """
        value = wx.TextCtrl.GetValue(self)
        if self._description_on:
            value = ""
        return value
    def SetValue(self, value):
        """Sets the value in the text entry field."""
        self.SetForegroundColour(self._text_colour)
        self._description_on = False
        self._ignore_textchange = True
        return wx.TextCtrl.SetValue(self, value)
    Value = property(GetValue, SetValue)



class TreeListCtrl(wx.lib.gizmos.TreeListCtrl):
    """
    A tree control with a more convenient API.
    Events should be registered directly via self.Bind,
    not via parent.Bind(source=self).
    """

    class DummyEvent(object):
        """Event to feed to directly invoked handlers."""
        def __init__(self, item): self._item = item
        def GetItem(self):        return self._item


    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.TR_DEFAULT_STYLE,
                 agwStyle=wx.lib.gizmos.TR_HAS_BUTTONS | wx.lib.gizmos.TR_LINES_AT_ROOT,
                 validator=wx.DefaultValidator,
                 name=wx.EmptyString):
        self._handlers = collections.defaultdict(list) # {event type: [handler, ]}
        super(TreeListCtrl, self).__init__(parent, id, pos, size, style,
                                           agwStyle, validator, name)
        self.Bind(wx.EVT_CHAR_HOOK, self._OnKey)
        self.GetMainWindow().Bind(wx.EVT_CHAR_HOOK, self._OnKey)


    RootItem = property(lambda x: x.GetRootItem())


    def AppendItem(self, *args, **kwargs):
        """Appends an item as a last child of its parent."""
        result = super(TreeListCtrl, self).AppendItem(*args, **kwargs)
        # Workaround for TreeListCtrl bug of not using our foreground colour
        self.SetItemTextColour(result, self.ForegroundColour)
        return result


    def Bind(self, event, handler, source=None, id=wx.ID_ANY, id2=wx.ID_ANY):
        """
        Binds an event to event handler,
        registering handler for FindAndActivateItem if wx.EVT_TREE_ITEM_ACTIVATED.
        """
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)
        super(TreeListCtrl, self).Bind(event, handler, source, id, id2)


    def FindAndActivateItem(self, match=None, **kwargs):
        """
        Selects tree item where match returns true for item data, and invokes
        handlers registered for wx.EVT_TREE_ITEM_ACTIVATED. Expands all item
        parents.

        @param    match   callback(data associated with item): bool
                          or {key: value} to match in associated data dict
        @param    kwargs  additional keyword arguments to match in data
        @return           success
        """
        fmatch = match if callable(match) else bool
        dmatch = dict(match if isinstance(match, dict) else {}, **kwargs)
        mymatch = match if callable(match) and not dmatch else lambda x: (
                  fmatch(x) and isinstance(x, dict)
                  and all(x.get(k) == dmatch.get(k) for k in dmatch))

        item, myitem = self.GetNext(self.GetRootItem()), None
        while item and item.IsOk():
            if mymatch(self.GetItemPyData(item)): myitem, item = item, None
            item = item and self.GetNext(item)

        if myitem:
            parent = self.GetItemParent(myitem)
            while parent and parent.IsOk():
                parent, _ = self.GetItemParent(parent), self.Expand(parent)

            self.SelectItem(myitem)
            evt = self.DummyEvent(myitem)
            for f in self._handlers.get(wx.EVT_TREE_ITEM_ACTIVATED): f(evt)
        return bool(myitem)


    def ToggleItem(self, item):
        """
        Toggles item and all children expanded if any collapsed,
        else toggles all collapsed.
        """
        items, it = [item], self.GetNext(item)
        while it and it.IsOk():
            items.append(it)
            it = self.GetNextSibling(it)
        if all(self.IsExpanded(x) or not self.HasChildren(x) for x in items):
            for x in items: self.Collapse(x)
        else: self.ExpandAllChildren(item)


    def _OnKey(self, event):
        """Fires EVT_TREE_ITEM_ACTIVATED event on pressing enter."""
        event.Skip()
        if event.KeyCode not in KEYS.ENTER or self.GetEditControl() is not None: return
        item = self.GetSelection()
        if item and item.IsOk():
            evt = self.DummyEvent(item)
            for f in self._handlers.get(wx.EVT_TREE_ITEM_ACTIVATED): f(evt)


    def CreateEditCtrl(self, item, column):
        """
        Creates an edit control for editing a label of an item.

        @param   item    an instance of TreeListItem
        @param   column  an integer specifying the column index
        """
        ctrl = super(TreeListCtrl, self).CreateEditCtrl(item, column)
        def on_kill_focus(event):
            event.Skip()
            if ctrl: wx.CallAfter(ctrl.StopEditing)
        ctrl.Bind(wx.EVT_KILL_FOCUS, on_kill_focus)
        return ctrl



class YAMLTextCtrl(wx.stc.StyledTextCtrl):
    """
    A StyledTextCtrl configured for YAML syntax highlighting and folding.
    """

    """YAML reserved keywords."""
    KEYWORDS = list(map(text_type, sorted(["true", "false", "null"])))
    AUTOCOMP_STOPS = " .,;:([)]}'\"\\<>%^&+-=*/|`"
    """String length from which autocomplete starts."""
    AUTOCOMP_LEN = 2
    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"


    def __init__(self, *args, **kwargs):
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self.SetLexer(wx.stc.STC_LEX_YAML)
        self.SetTabWidth(2)
        # Keywords must be lowercase, required by StyledTextCtrl
        self.SetKeyWords(0, u" ".join(self.KEYWORDS).lower())
        self.AutoCompStops(self.AUTOCOMP_STOPS)
        self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(False)
        self.AutoCompSetIgnoreCase(False)

        self.SetTabWidth(2)
        self.SetUseTabs(False)

        self.SetMarginCount(2)
        self.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(0, 25)
        self.SetMarginCursor(0, wx.stc.STC_CURSORARROW)

        self.SetProperty("fold", "1")
        self.SetMarginType(1, wx.stc.STC_MARGIN_SYMBOL)
        self.SetMarginMask(1, wx.stc.STC_MASK_FOLDERS)
        self.SetMarginSensitive(1, True)
        self.SetMarginWidth(1, 12)

        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPEN,    wx.stc.STC_MARK_BOXMINUS,          "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDER,        wx.stc.STC_MARK_BOXPLUS,           "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERSUB,     wx.stc.STC_MARK_VLINE,             "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERTAIL,    wx.stc.STC_MARK_LCORNER,           "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEREND,     wx.stc.STC_MARK_BOXPLUSCONNECTED,  "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPENMID, wx.stc.STC_MARK_BOXMINUSCONNECTED, "white", "#808080")
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERMIDTAIL, wx.stc.STC_MARK_TCORNER,           "white", "#808080")

        self.SetStyleSpecs()

        self.Bind(wx.EVT_KEY_DOWN,            self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,           self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,          self.OnKillFocus)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,  self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_MARGINCLICK, self.OnMarginClick)


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        fgcolour, bgcolour, highcolour, graycolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW
                      if self.Enabled else wx.SYS_COLOUR_BTNFACE,
                      wx.SYS_COLOUR_HOTLIGHT, wx.SYS_COLOUR_GRAYTEXT)
        )

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD,  "fore:#FF0000")
        self.StyleClearAll() # Apply the new default style to all styles

        self.StyleSetSpec(wx.stc.STC_YAML_IDENTIFIER, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_YAML_DOCUMENT,   "fore:%s" % graycolour)

        self.StyleSetSpec(wx.stc.STC_YAML_DEFAULT,    "face:%s" % self.FONT_FACE)
        self.StyleSetSpec(wx.stc.STC_YAML_TEXT,       "fore:#FF007F") # "
        # 01234567890.+-e
        self.StyleSetSpec(wx.stc.STC_YAML_NUMBER,     "fore:#FF00FF")
        # : [] {}
        self.StyleSetSpec(wx.stc.STC_YAML_OPERATOR,   "fore:%s" % highcolour)
        # #...
        self.StyleSetSpec(wx.stc.STC_YAML_COMMENT,    "fore:#008000")


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(self.__class__, self).Enable(enable)
        self.SetStyleSpecs()
        return result

    def OnFocus(self, event):
        """Handler for control getting focus, shows caret."""
        event.Skip()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_LINE)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides autocomplete and caret."""
        event.Skip()
        self.AutoCompCancel()
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        self.SetStyleSpecs()


    def ToggleFolding(self):
        """Toggles all current folding, off if all lines folded else on."""
        lineCount = self.GetLineCount()
        expanding = True

        # Find out if we are folding or unfolding
        for lineNum in range(lineCount):
            if self.GetFoldLevel(lineNum) & wx.stc.STC_FOLDLEVELHEADERFLAG:
                expanding = not self.GetFoldExpanded(lineNum)
                break

        lineNum = 0
        while lineNum < lineCount:
            level = self.GetFoldLevel(lineNum)
            if level & wx.stc.STC_FOLDLEVELHEADERFLAG \
            and (level & wx.stc.STC_FOLDLEVELNUMBERMASK) == wx.stc.STC_FOLDLEVELBASE:
                if expanding:
                    self.SetFoldExpanded(lineNum, True)
                    lineNum = self.ToggleLineFolding(lineNum, True)
                    lineNum = lineNum - 1
                else:
                    lastChild = self.GetLastChild(lineNum, -1)
                    self.SetFoldExpanded(lineNum, False)
                    if lastChild > lineNum:
                        self.HideLines(lineNum+1, lastChild)
            lineNum = lineNum + 1


    def ToggleLineFolding(self, line, doExpand, force=False, visLevels=0, level=-1):
        """Expands or collapses folding on specified line."""
        lastChild = self.GetLastChild(line, level)
        line = line + 1

        while line <= lastChild:
            if force:
                (self.ShowLines if visLevels > 0 else self.HideLines)(line, line)
            elif doExpand: self.ShowLines(line, line)

            if level == -1:
                level = self.GetFoldLevel(line)

            if level & self.STC_FOLDLEVELHEADERFLAG:
                if force:
                    self.SetFoldExpanded(line, visLevels > 1)

                    line = self.ToggleLineFolding(line, doExpand, force, visLevels-1)

                else:
                    on = doExpand and self.GetFoldExpanded(line)
                    line = self.ToggleLineFolding(line, on, force, visLevels-1)
            else:
                line += 1

        return line


    def OnMarginClick(self, event):
        """Handler for clicking margin, folds 2nd margin icons."""
        if event.GetMargin() != 1: return

        if event.GetShift() and event.GetControl():
            self.ToggleFolding()
            return

        lineClicked = self.LineFromPosition(event.GetPosition())
        if not self.GetFoldLevel(lineClicked) & wx.stc.STC_FOLDLEVELHEADERFLAG:
            return

        if event.GetShift():
            self.SetFoldExpanded(lineClicked, True)
            self.ToggleLineFolding(lineClicked, True, True, 1)
        elif event.GetControl():
            if self.GetFoldExpanded(lineClicked):
                self.SetFoldExpanded(lineClicked, False)
                self.ToggleLineFolding(lineClicked, False, True, 0)
            else:
                self.SetFoldExpanded(lineClicked, True)
                self.ToggleLineFolding(lineClicked, True, True, 100)
        else:
            self.ToggleFold(lineClicked)


    def OnKeyDown(self, event):
        """
        Shows autocomplete if user is entering a known word, or pressed
        Ctrl-Space.
        """
        skip = True
        if self.CallTipActive():
            self.CallTipCancel()
        if not self.AutoCompActive() and not event.AltDown():
            do_autocomp = False
            words = self.KEYWORDS
            autocomp_len = 0
            if event.UnicodeKey in KEYS.SPACE and event.CmdDown():
                # Start autocomp when user presses Ctrl+Space
                do_autocomp = True
            elif not event.CmdDown():
                # Check if we have enough valid text to start autocomplete
                char = None
                try: # Not all keycodes can be chars
                    char = chr(event.UnicodeKey).decode("latin1")
                except Exception:
                    pass
                if char not in KEYS.ENTER and char is not None:
                    # Get a slice of the text on the current text up to caret.
                    line_text = self.GetTextRange(
                        self.PositionFromLine(self.GetCurrentLine()),
                        self.GetCurrentPos()
                    )
                    text = u""
                    for last_word in re.findall(r"(\w+)$", line_text, re.I):
                        text += last_word
                    text = text.upper()
                    if char in string.ascii_letters:
                        text += char.upper()
                        if len(text) >= self.AUTOCOMP_LEN and any(x for x in
                        words if x.upper().startswith(text)):
                            do_autocomp = True
                            current_pos = self.GetCurrentPos() - 1
                            while chr(self.GetCharAt(current_pos)).isalnum():
                                current_pos -= 1
                            autocomp_len = self.GetCurrentPos() - current_pos - 1
            if do_autocomp:
                if skip: event.Skip()
                self.AutoCompShow(autocomp_len, u" ".join(words))
        elif self.AutoCompActive() and event.KeyCode in KEYS.DELETE:
            self.AutoCompCancel()
        if skip: event.Skip()



def YesNoMessageBox(message, caption, icon=wx.ICON_NONE, default=wx.YES):
    """
    Opens a Yes/No messagebox that is closable by pressing Escape,
    returns dialog result.

    @param   icon     dialog icon to use, one of wx.ICON_XYZ
    @param   default  default selected button, wx.YES or wx.NO
    """
    style = icon | wx.OK | wx.CANCEL
    if wx.NO == default: style |= wx.CANCEL_DEFAULT
    dlg = wx.MessageDialog(None, message, caption, style)
    dlg.SetOKCancelLabels("&Yes", "&No")
    return wx.YES if wx.ID_OK == dlg.ShowModal() else wx.NO


def cmp(x, y):
    """Return negative if x<y, zero if x==y, positive if x>y."""
    if x == y: return 0
    if x is None: return -1
    if y is None: return +1
    try:
        return -1 if x < y else +1
    except TypeError:
        return -1 if str(x) < str(y) else +1


def get_dialog_path(dialog):
    """
    Returns the file path chosen in FileDialog, adding extension if dialog result
    has none even though a filter has been selected, or if dialog result has a
    different extension than what is available in selected filter.
    """
    result = dialog.GetPath()

    # "SQLite database (*.db;*.sqlite;*.sqlite3)|*.db;*.sqlite;*.sqlite3|All files|*.*"
    wcs = dialog.Wildcard.split("|")
    wcs = wcs[1::2] if len(wcs) > 1 else wcs
    wcs = [[y.lstrip("*") for y in x.split(";")] for x in wcs] # [['.ext1', '.ext2'], ..]

    extension = os.path.splitext(result)[-1].lower()
    selexts = wcs[dialog.FilterIndex] if 0 <= dialog.FilterIndex < len(wcs) else None
    if result and selexts and extension not in selexts and dialog.ExtraStyle & wx.FD_SAVE:
        ext = next((x for x in selexts if "*" not in x), None)
        if ext: result += ext

    return result


def get_tool_rect(toolbar, id_tool):
    """Returns position and size of a toolbar tool by ID."""
    bmpsize, toolsize, packing = toolbar.ToolBitmapSize, toolbar.ToolSize, toolbar.ToolPacking
    result = wx.Rect(0, 0, *toolsize)
    for i in range(toolbar.GetToolPos(id_tool)):
        tool = toolbar.GetToolByPos(i)
        result.x += packing + (1 if tool.IsSeparator() else bmpsize[0] if tool.IsButton()
                               else tool.Control.Size[0])

    return result


def is_fixed(value):
    """Returns whether value is fixed-size (float, or 32/64-bit integer)."""
    return isinstance(value, float) or isinstance(value, integer_types) and -2**63 <= value < 2**63


def is_fixed_long(value, bytevalue=None):
    """
    Returns whether value is integer smaller than 64 bits.
    In Python2, checks also that value is not int.

    @param   bytevalue  optional value buffer to check for length
    """
    if not isinstance(value, integer_types):
        return False
    if sys.version_info < (3, ):
        return isinstance(value, long) and -2**63 <= value < 2**63
    if bytevalue is not None:
        return len(bytevalue) == 8
    return not (-2**31 <= value < 2**31) and -2**63 <= value < 2**63


def is_long_long(value):
    """Returns whether value is integer larger than 64 bits."""
    return isinstance(value, integer_types) and not (-2**63 <= value < 2**63)
