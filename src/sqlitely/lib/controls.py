# -*- coding: utf-8 -*-
"""
Stand-alone GUI components for wx:

- BusyPanel(wx.Window):
  Primitive hover panel with a message that stays in the center of parent
  window.

- ByteTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for byte editing.
  Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.

- CallableManagerDialog(wx.Dialog):
  Dialog for displaying and managing a list of callables.

- ColourManager(object):
  Updates managed component colours on Windows system colour change.

- FileBrowseButton(wx.lib.filebrowsebutton.FileBrowseButton):
  FileBrowseButton using a cached file dialog.

- FileDrop(wx.FileDropTarget):
  A simple file drag-and-drop handler.

- FilterEntryDialog(wx.Dialog):
  Dialog allowing to set filter values on a single item.

- FindReplaceDialog(wx.Dialog):
  Dialog allowing to search and replace in wx controls.
  Supported controls: wx.TextCtrl, wx.stc.StyledTextCtrl, wx.grid.Grid.

- FormDialog(wx.Dialog):
  Dialog for displaying a complex editable form.

- HexTextCtrl(wx.stc.StyledTextCtrl):
  A StyledTextCtrl configured for hexadecimal editing.
  Raises CaretPositionEvent, LinePositionEvent and SelectionEvent.

- HintedTextCtrl(wx.TextCtrl):
  A text control with a hint text shown when no value, hidden when focused.

- ItemFilterDialog(wx.Dialog):
  Dialog allowing to set hidden-flag or filter values on a range of items.

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

- Patch(object):
  Monkey-patches wx API for general compatibility over different versions.

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
@modified    02.01.2025
------------------------------------------------------------------------------
"""
import binascii
import collections
import copy
import functools
import keyword
import locale
import math
import os
import re
import string
import struct
import sys
import time

import wx
import wx.adv
import wx.html
import wx.lib.agw.flatnotebook
import wx.lib.agw.labelbook
try: # ShapedButton requires PIL, might not be installed
    import wx.lib.agw.shapedbutton
except Exception: pass
import wx.lib.agw.ultimatelistctrl
import wx.lib.embeddedimage
import wx.lib.filebrowsebutton
import wx.lib.gizmos
import wx.lib.mixins.listctrl
import wx.lib.newevent
import wx.lib.resizewidget
import wx.lib.wordwrap
import wx.stc


try: import collections.abc as collections_abc    # Py2
except ImportError: collections_abc = collections # Py3
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

# wx.NewId() deprecated from around wxPython 4
NewId = (lambda: wx.NewIdRef().Id) if hasattr(wx, "NewIdRef") else wx.NewId


class KEYS(object):
    """Keycode groupings, includes numpad keys."""
    UP         = (wx.WXK_UP,       wx.WXK_NUMPAD_UP)
    DOWN       = (wx.WXK_DOWN,     wx.WXK_NUMPAD_DOWN)
    LEFT       = (wx.WXK_LEFT,     wx.WXK_NUMPAD_LEFT)
    RIGHT      = (wx.WXK_RIGHT,    wx.WXK_NUMPAD_RIGHT)
    PAGEUP     = (wx.WXK_PAGEUP,   wx.WXK_NUMPAD_PAGEUP)
    PAGEDOWN   = (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN)
    ENTER      = (wx.WXK_RETURN,   wx.WXK_NUMPAD_ENTER)
    INSERT     = (wx.WXK_INSERT,   wx.WXK_NUMPAD_INSERT)
    DELETE     = (wx.WXK_DELETE,   wx.WXK_NUMPAD_DELETE)
    HOME       = (wx.WXK_HOME,     wx.WXK_NUMPAD_HOME)
    END        = (wx.WXK_END,      wx.WXK_NUMPAD_END)
    SPACE      = (wx.WXK_SPACE,    wx.WXK_NUMPAD_SPACE)
    BACKSPACE  = (wx.WXK_BACK, )
    TAB        = (wx.WXK_TAB,      wx.WXK_NUMPAD_TAB)
    ESCAPE     = (wx.WXK_ESCAPE, )

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
        wx.BeginBusyCursor()
        wx.SafeYield()
        timer.Start(self.REFRESH_INTERVAL)


    def __enter__(self):
        """Context manager entry, returns self."""
        return self


    def __exit__(self, exc_type, exc_val, exc_trace):
        """Context manager exit, destroys panel."""
        self.Close()
        return exc_type is None


    def _OnDestroy(self, event):
        event.Skip()
        try: self._timer.Stop()
        except Exception: pass
        wx.EndBusyCursor()


    def Close(self):
        try: self and self.Destroy(); self.Parent.Refresh()
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
        if colour.Alpha() != wx.ALPHA_OPAQUE:
            colour = wx.Colour(colour[:3])  # GetAsString(C2S_HTML_SYNTAX) can raise if transparent
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
        Arguments can be wx.Colour, RGB tuple, colour hex string, or wx.SystemSettings colour index.

        @param   ratio    RGB channel adjustment ratio towards second colour
        """
        colour1 = wx.SystemSettings.GetColour(colour1) \
                  if isinstance(colour1, integer_types) else wx.Colour(colour1)
        colour2 = wx.SystemSettings.GetColour(colour2) \
                  if isinstance(colour2, integer_types) else wx.Colour(colour2)
        rgb1, rgb2 = tuple(colour1)[:3], tuple(colour2)[:3]
        delta  = tuple(a - b for a, b in zip(rgb1, rgb2))
        result = tuple(a - int(d * ratio) for a, d in zip(rgb1, delta))
        result = tuple(min(255, max(0, x)) for x in result)
        return wx.Colour(result)


    @classmethod
    def Diff(cls, colour1, colour2):
        """
        Returns difference between two colours, as wx.Colour of absolute deltas over channels.

        Arguments can be wx.Colour, RGB tuple, colour hex string, or wx.SystemSettings colour index.
        """
        colour1 = wx.SystemSettings.GetColour(colour1) \
                  if isinstance(colour1, integer_types) else wx.Colour(colour1)
        colour2 = wx.SystemSettings.GetColour(colour2) \
                  if isinstance(colour2, integer_types) else wx.Colour(colour2)
        rgb1, rgb2 = tuple(colour1)[:3], tuple(colour2)[:3]
        result = tuple(abs(a - b) for a, b in zip(rgb1, rgb2))
        return wx.Colour(result)


    @classmethod
    def IsDark(cls):
        """Returns whether display is in dark mode (heuristical judgement from system colours)."""
        try:              return wx.SystemSettings.GetAppearance().IsDark()
        except Exception: return sum(cls.Diff(wx.WHITE, wx.SYS_COLOUR_WINDOW)[:3]) > 3 * 175


    @classmethod
    def UpdateContainer(cls):
        """Updates configuration colours with current system theme values."""
        for name, colourid in cls.colourmap.items():
            setattr(cls.colourcontainer, name, cls.ColourHex(colourid))

        if cls.IsDark():
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


    @classmethod
    def Patch(cls, ctrl):
        """
        Ensures foreground and background system colours on control and its descendant controls.

        Explicitly sets background colour on ComboBox, SpinCtrl and TextCtrl,
        and foreground colour on wx.CheckBox and UltimateListCtrl header window
        (workaround for dark mode in Windows 10+).
        """
        if "nt" != os.name or sys.getwindowsversion() < (10, ): return

        PROPS = {wx.ComboBox: {"BackgroundColour": wx.SYS_COLOUR_WINDOW},
                 wx.SpinCtrl: {"BackgroundColour": wx.SYS_COLOUR_WINDOW},
                 wx.TextCtrl: {"BackgroundColour": wx.SYS_COLOUR_WINDOW},
                 wx.CheckBox: {"ForegroundColour": wx.SYS_COLOUR_BTNTEXT},
                 wx.lib.agw.ultimatelistctrl.UltimateListHeaderWindow:
                              {"ForegroundColour": wx.SYS_COLOUR_LISTBOXTEXT}, }
        for ctrl in [ctrl] + get_all_children(ctrl):
            for prop, colour in PROPS.get(type(ctrl), {}).items():
                if ctrl not in cls.ctrlprops or prop not in cls.ctrlprops[ctrl]:
                    cls.Manage(ctrl, prop, colour)



CallableManagerEvent, EVT_CALLABLE_MANAGER = wx.lib.newevent.NewCommandEvent()

class CallableManagerDialog(wx.Dialog):
    """
    Dialog for displaying and managing a list of callables.

    Posts all changes as EVT_CALLABLE_MANAGER, with ClientObject as the current list.
    """

    def __init__(self, parent, title, items, validator=callable, tester=None, alias="callable", body=""):
        """
        @param   items      list of {label, body, name, ?callable, ?namespace, ?active}
        @param   validator  function(target) returning bool or error message
                            for potential target value from compiled namespace
        @param   test       function(target, dialog) returning bool or error message
                            for test-invoking the target
        @param   alias      name for callable type, used in dialog texts
        @param   body       default body content for new items
        """
        wx.Dialog.__init__(self, parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self.items     = [dict(x) for x in items]
        self.validator = validator
        self.tester    = tester
        self.alias     = alias
        self.body      = body

        self.editmode  = False
        self.newmode   = False
        self.item      = self.items[0] if self.items else None
        self.state     = {}  # Current item edit state, as {namespace: {..}, error: ".."}

        panel = self.panel = wx.Panel(self, style=wx.BORDER_RAISED)
        splitter = wx.SplitterWindow(panel, style=wx.BORDER_NONE)
        panel_left  = wx.Panel(splitter)
        panel_right = wx.Panel(splitter)

        list_items  = wx.ListView(panel_left, style=wx.LC_REPORT | wx.LC_SINGLE_SEL |
                                                    wx.LC_NO_HEADER)
        button_up   = wx.Button(panel_left, label="Up")
        button_down = wx.Button(panel_left, label="Down")

        label_title = wx.StaticText(panel_right, label="Tit&le:")
        edit_title = wx.TextCtrl(panel_right)
        label_body = wx.StaticText(panel_right, label="&Body:")
        stc_body = wx.stc.StyledTextCtrl(panel_right)
        label_name = wx.StaticText(panel_right, label="Ta&rget:")
        combo_name = wx.ComboBox(panel_right, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        button_test = wx.Button(panel_right, label="&Test")
        label_active = wx.StaticText(panel_right, label="&Active:")
        cb_active    = wx.CheckBox(panel_right)

        label_error = wx.StaticText(panel_right, label="Error:")
        edit_error  = wx.TextCtrl(panel_right, style=wx.TE_MULTILINE | wx.TE_NO_VSCROLL |
                                                     wx.BORDER_NONE)

        button_compile = wx.Button(panel_right, label="&Compile")
        button_edit    = wx.Button(panel_right, label="&Edit")
        button_save    = wx.Button(panel_right, label="&Save")
        button_delete  = wx.Button(panel_right, label="Delete")
        button_cancel  = wx.Button(panel_right, label="Canc&el")

        button_new     = wx.Button(self, label="&New entry")
        button_close   = wx.Button(self, label="Close")

        self.Sizer        = wx.BoxSizer(wx.VERTICAL)
        panel.Sizer       = wx.BoxSizer(wx.VERTICAL)
        panel_left.Sizer  = wx.BoxSizer(wx.VERTICAL)
        panel_right.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_arrows      = wx.BoxSizer(wx.HORIZONTAL)
        sizer_form        = wx.GridBagSizer(hgap=5, vgap=5)
        sizer_test        = wx.BoxSizer(wx.HORIZONTAL)
        sizer_itembuttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons     = wx.BoxSizer(wx.HORIZONTAL)

        sizer_arrows.Add(button_up,   proportion=1)
        sizer_arrows.Add(button_down, proportion=1)

        sizer_test.Add(combo_name, proportion=1)
        sizer_test.Add(button_test)

        sizer_itembuttons.Add(button_compile)
        sizer_itembuttons.AddStretchSpacer()
        sizer_itembuttons.Add(button_edit,    flag=wx.LEFT, border=5)
        sizer_itembuttons.Add(button_save,    flag=wx.LEFT, border=5)
        sizer_itembuttons.Add(button_delete,  flag=wx.LEFT, border=5)
        sizer_itembuttons.Add(button_cancel,  flag=wx.LEFT, border=5)

        sizer_buttons.Add(button_new)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_close)

        panel_left.Sizer.Add(list_items, proportion=1, flag=wx.GROW)
        panel_left.Sizer.Add(sizer_arrows, flag=wx.GROW)

        sizer_form.Add(label_title,       pos=(0, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_form.Add(edit_title,        pos=(0, 1), flag=wx.GROW)
        sizer_form.Add(label_body,        pos=(1, 0))
        sizer_form.Add(stc_body,          pos=(1, 1), flag=wx.GROW)
        sizer_form.Add(label_name,        pos=(2, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_form.Add(sizer_test,        pos=(2, 1), flag=wx.GROW)
        sizer_form.Add(label_active,      pos=(3, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_form.Add(cb_active,         pos=(3, 1))
        sizer_form.Add(label_error,       pos=(4, 0))
        sizer_form.Add(edit_error,        pos=(4, 1), span=(2, 2), flag=wx.GROW)
        sizer_form.Add(sizer_itembuttons, pos=(6, 0), span=(1, 2), flag=wx.GROW)
        sizer_form.AddGrowableRow(1)
        sizer_form.AddGrowableCol(1)

        panel_right.Sizer.Add(sizer_form, proportion=1, flag=wx.ALL | wx.GROW, border=5)

        panel.Sizer.Add(splitter, proportion=1, flag=wx.GROW)
        self.Sizer.Add(panel, proportion=1, flag=wx.GROW)
        self.Sizer.Add(sizer_buttons, flag=wx.ALL | wx.GROW, border=5)

        splitter.SetMinimumPaneSize(150)
        splitter.SplitVertically(panel_left, panel_right, splitter.MinimumPaneSize)

        listfont = list_items.Font
        listfont.PointSize = int(1.5 * listfont.PointSize)
        list_items.Font = listfont
        list_items.AppendColumn("")
        edit_error.SetEditable(False)
        stc_body.SetTabWidth(4)
        stc_body.SetUseTabs(False)
        stc_body.SetWrapMode(wx.stc.STC_WRAP_WORD)
        stc_body.SetLexer(wx.stc.STC_LEX_PYTHON)
        stc_body.SetKeyWords(0, " ".join(keyword.kwlist))
        stc_body.SetMargins(0, 0)
        stc_body.SetMarginType(1, wx.stc.STC_MARGIN_NUMBER)
        ColourManager.SetShellStyles(stc_body)
        button_test.Show(bool(tester))

        label_title.ToolTip    = edit_title.ToolTip = "Title for %s; ampersand makes hotkey" % alias
        label_body.ToolTip     = stc_body.ToolTip   = "Python code to compile for %s" % alias
        label_active.ToolTip   = cb_active.ToolTip  = "Enable %s for use" % alias
        label_name.ToolTip     = combo_name.ToolTip = "Callable name from body to invoke as %s" % alias
        button_new.ToolTip     = "Enter new %s" % alias
        button_close.ToolTip   = "Close dialog"
        button_up.ToolTip      = "Move selected entry one step higher"
        button_down.ToolTip    = "Move selected entry one step higher"
        button_test.ToolTip    = "Invoke %s with content from popup" % alias
        button_compile.ToolTip = "Compile and verify code"
        button_edit.ToolTip    = "Edit current %s" % alias
        button_save.ToolTip    = "Save %s" % alias
        button_delete.ToolTip  = "Delete %s" % alias
        button_cancel.ToolTip  = "Discard changes"

        self.list_items     = list_items
        self.edit_title     = edit_title
        self.stc_body       = stc_body
        self.combo_name     = combo_name
        self.cb_active      = cb_active
        self.label_error    = label_error
        self.edit_error     = edit_error
        self.button_up      = button_up
        self.button_down    = button_down
        self.button_test    = button_test
        self.button_compile = button_compile
        self.button_edit    = button_edit
        self.button_save    = button_save
        self.button_delete  = button_delete
        self.button_cancel  = button_cancel
        self.button_new     = button_new
        self.button_close   = button_close

        wrap = lambda f, *a: lambda e: wx.CallAfter(f, *a)
        splitter.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED, wrap(self._UpdateUI))
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._OnSelectItem,           list_items)
        self.Bind(wx.stc.EVT_STC_MODIFIED,    wrap(self.EnsureMargin),      stc_body)
        self.Bind(wx.EVT_BUTTON,              wrap(self.Compile),           button_compile)
        self.Bind(wx.EVT_BUTTON,              wrap(self.Test),              button_test)
        self.Bind(wx.EVT_BUTTON,              wrap(self.SetEditmode, True), button_edit)
        self.Bind(wx.EVT_BUTTON,              self._OnCancelEdit,           button_cancel)
        self.Bind(wx.EVT_BUTTON,              self._OnSaveEdit,             button_save)
        self.Bind(wx.EVT_BUTTON,              self._OnDelete,               button_delete)
        self.Bind(wx.EVT_BUTTON,              self._OnNew,                  button_new)
        self.Bind(wx.EVT_BUTTON,              self._OnClose,                button_close)
        self.Bind(wx.EVT_BUTTON,              wrap(self.MoveItem, -1),      button_up)
        self.Bind(wx.EVT_BUTTON,              wrap(self.MoveItem, +1),      button_down)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,  self._OnSysColourChange)
        self.Bind(wx.EVT_CLOSE,               self._OnClose)
        self.SetEscapeId(button_close.Id)

        ColourManager.Manage(self,        "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(edit_error,  "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(label_error, "ForegroundColour", wx.SYS_COLOUR_HOTLIGHT)
        ColourManager.Manage(edit_error,  "ForegroundColour", wx.SYS_COLOUR_HOTLIGHT)

        for i, item in enumerate(self.items): list_items.InsertItem(i, item["title"])
        if self.items: list_items.Select(0)
        self.Populate()
        self.SetEditmode(False)

        self.Layout()
        self.Fit()
        self.Size = (700, 500)
        self.MinSize = (450, 350)
        self.CenterOnParent()
        self._UpdateUI()


    def Populate(self):
        """Populates dialog controls with current item."""
        item = self.item or {}
        readonly, self.stc_body.ReadOnly = self.stc_body.ReadOnly, False
        self.edit_title.Value = item.get("title", "")
        self.stc_body.Text    = item.get("body", "")
        self.cb_active.Value  = item.get("active") is not False
        self.label_error.Shown = False
        self.edit_error.Value = ""
        self.combo_name.SetItems([])
        self.stc_body.ReadOnly = readonly
        self.EnsureMargin()
        self.button_test.Enabled = self.item is not None
        if not self.newmode and self.item is not None: self.Compile()


    def GetChanges(self):
        """Returns dictionary of values changed in current item, if any."""
        result = {}
        if self.item.get("title", "") != self.edit_title.Value: result["title"] = self.edit_title.Value
        if self.item.get("body",  "") != self.stc_body.Text:    result["body"]  = self.stc_body.Text
        if self.item.get("name",  "") != self.combo_name.Value: result["name"]  = self.combo_name.Value
        if self.item.get("active", True) != self.cb_active.Value:
            result["active"] = self.cb_active.Value
        return result


    def Compile(self):
        """Compiles entered code, updates state and UI with results."""
        self.label_error.Shown = False
        self.edit_error.Value = ""
        ns, err, text = {}, None, self.stc_body.Text
        try: eval(compile(text, "", "exec"), None, ns)
        except Exception as e: ns, err = None, str(e)
        if ns: ns = {k: v for k, v in sorted(ns.items()) if self.validator(v) is True}
        if not ns and not err: err = "No suitable %s found in body." % self.alias
        selected = self.combo_name.Value if ns and self.combo_name.Value in ns else None

        self.combo_name.SetItems(list(ns or {}))
        self.label_error.Shown = bool(err)
        self.edit_error.Value = err or ""
        if selected: self.combo_name.SetSelection(self.combo_name.FindString(selected))
        elif ns: self.combo_name.SetSelection(0)
        self.label_error.ContainingSizer.Layout()

        self.state.update(namespace=ns or {}, error=err)


    def Test(self):
        """Compiles item if changed, and invokes external tester."""
        if not self.state or "body" in self.GetChanges():
            self.Compile()
        if "namespace" in self.state and self.combo_name.Value in self.state["namespace"]:
            target = self.state["namespace"][self.combo_name.Value]
            self.tester(target, self)


    def MoveItem(self, direction):
        """Moves item currently selected in itemlist one step higher or lower; posts event."""
        index = self.list_items.GetFirstSelected()
        if index < 0 or direction < 0 and not index \
        or direction > 0 and index == len(self.items) - 1:
            self.list_items.SetFocus()
            return
        index2 = index + (1 if direction > 0 else -1)
        self.list_items.SetItemText(index,  self.items[index2]["title"])
        self.list_items.SetItemText(index2, self.items[index ]["title"])
        self.items[index], self.items[index2] = self.items[index2], self.items[index]
        self.list_items.SetFocus()
        self.list_items.Select(index2)
        self._PostEvent()


    def SetEditmode(self, editmode=True):
        """Sets form controls read-only or not and toggles buttons."""
        self.editmode = editmode
        if not editmode: self.newmode = False
        self.edit_title.SetEditable(editmode)
        self.stc_body.ReadOnly  = not editmode
        self.combo_name.Enabled = editmode
        self.cb_active.Enabled  = editmode
        self.button_edit.Shown    = self.button_delete.Shown = not editmode
        self.button_compile.Shown = self.button_save.Shown   = self.button_cancel.Shown = editmode
        self.button_edit.Enabled  = self.button_delete.Enabled = not editmode and self.item is not None
        self.button_edit.ContainingSizer.Layout()


    def EnsureMargin(self):
        """Ensures code editor having margin wide enough for line numbers."""
        PADDING, CHARWIDTH = 4, 7
        linecount = len(self.stc_body.Text.splitlines()) + 1
        width = PADDING + CHARWIDTH * (1 + max(1, int(math.log10(linecount or 1))))
        self.stc_body.SetMarginWidth(1, width)


    def _CheckUnsaved(self):
        """Returns true if form has unsaved changes and user prompted to cancel in popup."""
        if not self.editmode or not self.GetChanges(): return False
        return wx.OK != wx.MessageBox("There are unsaved changes.\n\n"
                                      "Are you sure you want to discard them?",
                                      "Unsaved changes", wx.OK | wx.CANCEL)


    def _PostEvent(self):
        """Posts CallableManagerEvent with current content."""
        evt = CallableManagerEvent(self.Id)
        evt.SetEventObject(self)
        evt.SetClientObject([copy.copy(x) for x in self.items])
        wx.PostEvent(self.Parent, evt)


    def _UpdateUI(self):
        """Sizes itemlist columns to fit."""
        w = self.list_items.Size[0] - self.list_items.GetWindowBorderSize()[0]
        self.list_items.SetColumnWidth(0, w)


    def _OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        ColourManager.SetShellStyles(self.stc_body)


    def _OnSelectItem(self, event):
        """Handler for activating an item entry, populates form."""
        if self._CheckUnsaved() \
        or self.item in self.items and self.items.index(self.item) == event.Index: return
        self.item = self.items[event.Index]
        self.state.clear()
        self.newmode = False
        self.Populate()
        self.SetEditmode(False)


    def _OnNew(self, event):
        """Handler for clicking the new button, opens blank form if not already."""
        if self.newmode or self._CheckUnsaved():
            if self.newmode: self.edit_title.SetFocus()
            return
        self.SetEditmode(True)
        self.newmode = True
        self.item = {"body": (self.body + "\n") if self.body else ""}
        self.state.clear()
        self.Populate()
        if self.list_items.GetFirstSelected() >= 0:
            self.list_items.Select(self.list_items.GetFirstSelected(), False)
        self.edit_title.SetFocus()


    def _OnSaveEdit(self, event):
        """Handler for saving changes, posts event if changed, and exits editmode."""
        changes = self.GetChanges()
        if not changes.get("title") and not self.item.get("title"):
            self.edit_title.SetFocus()
            return wx.MessageBox("Title is mandatory.", "Unsaved changes", wx.ICON_WARNING | wx.OK)
        if changes:
            self.Compile()
            if self.state["error"] and wx.OK != wx.MessageBox(
                "Are you sure you want to save invalid state?\n\nError: %s" % self.state["error"],
                "Unsaved changes", wx.ICON_WARNING | wx.OK | wx.CANCEL
            ): return

            self.item.update(changes, **self.GetChanges())
            if self.item.get("active") is not False: self.item.pop("active", None)
            if self.item.get("name") in self.state["namespace"]:
                self.item["target"] = self.state["namespace"][self.item["name"]]

            if self.newmode:
                self.items.append(self.item)
                self.list_items.InsertItem(len(self.items) - 1, self.item["title"])
                self.list_items.Select(len(self.items) - 1)
            elif "title" in changes:
                idx = self.items.index(self.item)
                self.list_items.SetItemText(idx, self.item["title"])
            self._UpdateUI()

            self._PostEvent()
        self.SetEditmode(False)


    def _OnCancelEdit(self, event):
        """Handler for cancelling editmode, confirms unsaved changes."""
        if self._CheckUnsaved(): return
        if self.newmode: self.item = None
        self.newmode = False
        self.Populate()
        self.SetEditmode(False)


    def _OnDelete(self, event):
        """Handler for deleting item, asks for confirmation and posts event."""
        if wx.OK != wx.MessageBox("Are you sure you want to delete this item?", "Delete",
                                  wx.OK | wx.CANCEL): return
        self.list_items.DeleteItem(self.items.index(self.item))
        self.items.remove(self.item)
        self.state.clear()
        self.item = None
        self.Populate()
        self.SetEditmode(False)
        self._PostEvent()


    def _OnClose(self, event):
        """Handler for closing dialog, confirms unsaved changes."""
        if self._CheckUnsaved(): return
        self.EndModal(wx.ID_OK) if self.IsModal() else self.Hide()



class FileBrowseButton(wx.lib.filebrowsebutton.FileBrowseButton):
    """FileBrowseButton using a cached file dialog."""

    def __init__ (self, parent, *args, **kwargs):
        super(FileBrowseButton, self).__init__(parent, *args, **kwargs)
        self.dialog = None

    def OnBrowse (self, event=None):
        """Opens file dialog, forwards selection to callback, if any."""
        self.dialog = self.dialog or wx.FileDialog(self, message=self.dialogTitle,
                                                   wildcard=self.fileMask, style=self.fileMode)

        dlg, current = self.dialog, self.GetValue()
        if current != get_dialog_path(dlg):
            root, tail = os.path.split(current)
            if os.path.isdir(current):
                dlg.Directory, dlg.Filename = current, ""
            elif os.path.isdir(root):
                dlg.Directory, dlg.Filename = root, tail
            else:
                dlg.Directory, dlg.Filename = self.startDirectory, ""

        if dlg.ShowModal() == wx.ID_OK:
            self.SetValue(get_dialog_path(dlg))



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



class FilterEntryDialog(wx.Dialog):
    """
    Dialog allowing to set filter values on a single item.
    """


    def __init__(self, parent=None, item=None, title="Filter", message="",
                 filter_menu=(), filter_hint=None,
                 style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER | wx.FRAME_FLOAT_ON_PARENT |
                       wx.APPLY):
        """
        @param   item         item to manage,
                              as {name, ?hidden, ?filtered, ?exact, ?inverted, ?value}
        @param   message      message to show on dialog if any
        @param   filter_menu  list of menu choices for filter value, as [{label, value, ?disabled}],
                              "value" optionally being callback(item)
                              or a list/tuple of nested submenu choices
        @param   filter_hint  hint text displayed for empty filter value,
                              optionally as callback(item)
        @param   style        dialog style flags; dialog will have Apply-button if wx.APPLY included
                              (see SetApplyCallback)
        """
        apply, style = (style & wx.APPLY), (style ^ wx.APPLY if style & wx.APPLY else style)
        wx.Dialog.__init__(self, parent, title=title, style=style)

        self._item    = {} # {name, label, hidden, filtered, filter}
        self._ctrls   = {} # {name: wx.Control}
        self._message = "" # text for optional wx.StaticText
        self._apply       = True # whether to show Apply-button
        self._apply_cb    = None # callback(item) registered for Apply-button
        self._filter_menu = []   # [{label, value}]
        self._filter_hint = None # value or callable(item)

        self._item = dict(name=item["name"], value=item.get("value", ""),
                          exact=bool(item.get("exact")), inverted=bool(item.get("inverted")),
                          filtered=bool(item.get("filtered")))
        self._message = message or ""
        self._apply   = apply
        self._filter_menu = [dict(label=x["label"], value=x["value"],
                             disabled=bool(x.get("disabled"))) for x in filter_menu]
        self._filter_hint = filter_hint

        self._Build()
        self._Bind()
        self.Fit()
        self._Refresh()
        self.MinSize = self.Size = max(350, self.Size.Width), self.Size.Height
        if self._item["filtered"] and not self._ctrls["edit_filter"].Hint:
            self._ctrls["edit_filter"].SetFocus()


    def GetItem(self):
        """Returns the item, with current choices for flags and filter values."""
        return dict(self._item)
    Item = property(GetItem)


    def SetApplyCallback(self, callback):
        """Sets callback function(item) invoked on clicking Apply-button."""
        if callback is not None and not callable(callback):
            raise ValueError("Invalid callback %r" % callback)
        self._apply_cb = callback


    def _Build(self):
        """Creates dialog controls."""
        sizer_main = wx.BoxSizer(wx.VERTICAL)
        sizer_item = wx.BoxSizer(wx.HORIZONTAL)

        name = self._item["name"]
        check_filter = wx.CheckBox(self, label=self._message)
        edit_filter  = HintedTextCtrl(self, escape=False)
        button_menu  = wx.Button(self, label="..", size=(BUTTON_MIN_WIDTH, ) * 2) \
                       if self._filter_menu else None
        check_exact  = wx.CheckBox(self, label="&EXACT")
        check_invert = wx.CheckBox(self, label="&NOT")

        check_filter.ToolTip = "Enable filter for %r" % name
        edit_filter.ToolTip  = "Filter value for %r" % name
        if button_menu:
            button_menu.ToolTip = "Open options menu"
        check_exact.ToolTip  = "Match entered filter value exactly as is, " \
                               "do not use partial case-insensitive match"
        check_invert.ToolTip = "Revert filter for column, matching where value is different"

        sizer_item.Add(check_filter, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5) \
            if not self._message else None
        sizer_item.Add(edit_filter,  flag=wx.GROW, proportion=1)
        sizer_item.Add(button_menu,  flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=5) \
            if button_menu else None
        sizer_item.Add(check_exact,  flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer_item.Add(check_invert, flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL, border=5)

        self._ctrls["check_filter"] = check_filter
        self._ctrls["edit_filter" ] = edit_filter
        self._ctrls["check_exact"]  = check_exact
        self._ctrls["check_invert"] = check_invert
        if button_menu:
            self._ctrls["button_menu"] = button_menu

        buttonflags = wx.OK | wx.CANCEL | (wx.APPLY if self._apply else 0)
        sizer_buttons = self.CreateStdDialogButtonSizer(buttonflags)

        sizer_main.Add(check_filter, flag=wx.GROW | wx.ALL ^ wx.BOTTOM, border=5) \
            if self._message else None
        sizer_main.Add(sizer_item, flag=wx.GROW | wx.ALL, border=10, proportion=1)
        sizer_main.Add(sizer_buttons, flag=wx.GROW | wx.ALL ^ wx.TOP, border=10)

        self.Sizer = sizer_main


    def _Bind(self):
        """Binds control handlers."""
        self.Bind(wx.EVT_CHECKBOX,   self._OnToggleFiltered, self._ctrls["check_filter"])
        self.Bind(wx.EVT_CHECKBOX,   self._OnToggleExact,    self._ctrls["check_exact"])
        self.Bind(wx.EVT_CHECKBOX,   self._OnToggleInverted, self._ctrls["check_invert"])
        self.Bind(wx.EVT_TEXT_ENTER, self._OnChangeFilter,   self._ctrls["edit_filter"])
        if self._filter_menu:
            self.Bind(wx.EVT_BUTTON, self._OnOpenFilterOptions, self._ctrls["button_menu"])
        if self._apply:
            self.Bind(wx.EVT_BUTTON, self._OnApply, id=wx.ID_APPLY)


    def _Refresh(self):
        """Enables-disables-populates controls according to current settings."""
        filter_text = self._item["value"]
        if filter_text is not None: filter_text = text_type(filter_text)
        self._ctrls["check_filter"].Value = self._item["filtered"]
        self._ctrls["edit_filter" ].Value = filter_text
        self._ctrls["edit_filter" ].Enable(self._item["filtered"])
        self._ctrls["check_exact" ].Enable(self._item["filtered"])
        self._ctrls["check_exact" ].Value = self._item["exact"]
        self._ctrls["check_invert"].Enable(self._item["filtered"])
        self._ctrls["check_invert"].Value = self._item["inverted"]
        if self._filter_menu:
            self._ctrls["button_menu"].Enable(self._item["filtered"])
        if self._filter_hint:
            hint = self._filter_hint if self._item["filtered"] else ""
            self._ctrls["edit_filter"].Hint = hint(self._item) if callable(hint) else hint


    def _OnApply(self, event):
        """Handler for clicking Apply-button, invokes registered apply-callback if any."""
        if callable(self._apply_cb): self._apply_cb(self.GetItem())


    def _OnToggleFiltered(self, event):
        """Handler for toggling item filtered on/off, updates state and refreshes display."""
        self._item["filtered"] = not self._item["filtered"]
        self._Refresh()
        if self._item["filtered"] and not self._ctrls["edit_filter"].Hint:
            self._ctrls["edit_filter"].SetFocus()
            self._ctrls["edit_filter"].SelectNone()


    def _OnToggleExact(self, event):
        """Handler for toggling item filter exact on/off, updates state and refreshes display."""
        self._item["exact"] = not self._item["exact"]
        self._Refresh()


    def _OnToggleInverted(self, event):
        """Handler for toggling item filter inverted on/off, updates state and refreshes display."""
        self._item["inverted"] = not self._item["inverted"]
        self._Refresh()


    def _OnChangeFilter(self, event):
        """Handler for editing filter text, refreshes filter hint if any."""
        self._item["value"] = event.EventObject.Value
        if self._filter_hint:
            hint = self._filter_hint if self._item["filtered"] else ""
            self._ctrls["edit_filter"].Hint = hint(self._item) if callable(hint) else ""


    def _OnOpenFilterOptions(self, event):
        """Handler for clicking filter options button, opens popup menu."""

        def populate_menu(menu, menu_opts):
            for opts in menu_opts:
                value = opts["value"]
                if value and isinstance(value, (list, tuple)) \
                and all(isinstance(x, dict) and "label" in x and "value" in x for x in value):
                    submenu = wx.Menu()
                    menuitem = menu.Append(wx.ID_ANY, opts["label"], submenu)
                    if opts.get("disabled"): menuitem.Enable(False)
                    else: populate_menu(submenu, value)
                    continue # for opts

                menuitem = wx.MenuItem(menu, -1, opts["label"])
                menu.Append(menuitem)
                if opts.get("disabled"): menuitem.Enable(False)
                on_menu = functools.partial(self._OnSetFilterOption, value=value)
                rootmenu.Bind(wx.EVT_MENU, on_menu, menuitem)

        rootmenu = wx.Menu()
        populate_menu(rootmenu, self._filter_menu)
        event.EventObject.PopupMenu(rootmenu, tuple(event.EventObject.Size))


    def _OnSetFilterOption(self, event, value):
        """Handler for filter options menu item, applies value."""
        value2 = value(self._item) if callable(value) else value
        self._item["value"] = value2 if value2 is None else text_type(value2)
        self._Refresh()



class FindReplaceDialog(wx.Dialog):
    """
    Dialog allowing to search and replace in wx controls.

    Automatically hides itself when parent gets hidden, and re-shows itself when parent is restored.

    Supported controls: wx.TextCtrl, wx.stc.StyledTextCtrl, wx.grid.Grid.
    """

    """Search text autocomplete history shared across dialog instances."""
    FIND_TEXTS = []

    """Replace text autocomplete history shared across dialog instances."""
    REPLACE_TEXTS = []

    """Colour set to find control background if search text not found."""
    COLOUR_NOTFOUND = "pink"


    def __init__(self, parent=None, target=None, title="Find and replace", findonly=False,
                 style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER | wx.FRAME_FLOAT_ON_PARENT):
        """
        @param   target    wx control being searched
        @param   title     dialog title, defaults to "Find" if findonly
        @param   findonly  whether dialog has no replace functionality
        """
        if findonly and title == "Find and replace": title = "Find"
        wx.Dialog.__init__(self, parent, title=title, style=style)

        self._flags = {
            "case"     : False,  # Search is case-sensitive
            "findonly" : False,  # Search controls only, no replace (static flag)
            "hex"      : False,  # Hex editor controls for search and replace texts
            "multiline": False,  # Multi-line controls for searcn and replace texts
            "regex"    : False,  # Search text interpreted as regex expression
            "reverse"  : False,  # Search performed backward from current position
            "shared"   : False,  # Search and replace text autocomplete history shared globally
            "word"     : False,  # Search matches whole words only
        }
        self._ctrls      = {}     # {name: wx.Control}
        self._sizers     = {}     # {name: wx.Sizer}
        self._status     = {}     # {action, found, wrapped, replaced, reverse, searching}
        self._target     = None   # wx control being searched
        self._synchidden = False  # Whether dialog was hidden when parent was hidden
        self._shownonce  = False  # Whether dialog has been shown at least once
        self._pattern    = None   # re.Pattern from last search
        self._match      = None   # re.Match from last search
        self._matchspan  = None   # (start, end) of last match in target text
        self._matchpos   = None   # grid (row, col) of last match; same as _matchspan if text control
        self._text       = None   # Text value of target control from last search

        self._flags["findonly"] = bool(findonly)
        self.SetTarget(target)

        self.MinSize = (450, -1)
        self._Build()
        self._Bind()
        self._Refresh()
        self.Fit()
        self.MinSize = (450, self.Size.Height)
        self._ctrls["hex_find"].MinSize = self._ctrls["text_find"].Size
        self._ctrls["status"].MaxSize = (450 - self._ctrls["button_multi"].Size.Width - 30, -1)


    def Show(self, show=True):
        """Shhows or hides the dialog."""
        self._synchidden = False
        if show:
            self._LoadSharedHistory()
            self._RefreshStatus()
            self._shownonce = True
        wx.Dialog.Show(self, show=show)


    def GetTarget(self):
        """Returns text component being searched."""
        return self._target
    def SetTarget(self, target):
        """Sets text component being searched, raises error if unsupported type."""
        if target is self._target: return
        if not isinstance(target, (wx.TextCtrl, wx.stc.StyledTextCtrl, wx.grid.Grid, type(None))):
            raise Exception("Unsupported target type: %r" % type(target))
        self._target    = target
        if not self._ctrls: return  # Still constructing
        self._pattern   = None
        self._match     = None
        self._matchspan = None
        self._matchpos  = None
        self._status.clear()
        self._RefreshStatus()
    Target = property(GetTarget, SetTarget)


    def EnsureVisible(self):
        """Moves dialog upwards if beyond screen bottom edge."""
        display = wx.Display(self)
        if not display.ClientArea.Contains(self.Rect):
            delta = display.ClientArea.Bottom - self.Rect.Bottom
            self.SetPosition((self.Position.x, self.Position.y + delta))


    def IsFindOnly(self):
        """Returns whether dialog is find-only, without replace."""
        return self._flags["findonly"]
    FindOnly = property(IsFindOnly)


    def IsSharedHistory(self):
        """Returns whether search and replace text autocomplete history is shared across dialogs."""
        return self._flags["shared"]
    def SetSharedHistory(self, enabled=True):
        """Toggles searching backward from current position."""
        if bool(enabled) == self._flags["shared"]: return
        self._flags["shared"] = bool(enabled)
        if enabled:
            self._ctrls["text_find"].SetChoices(self.FIND_TEXTS)
            if not self._flags["findonly"]:
                self._ctrls["text_repl"].DROPDOWN_CLEAR_TEXT = "Clear replace history"
                self._ctrls["text_repl"].SetChoices(self.REPLACE_TEXTS)
    SharedHistory = property(IsSharedHistory, SetSharedHistory)


    def IsShownOnce(self):
        """Returns whether dialog has been shown at least once."""
        return self._shownonce
    ShownOnce = property(IsShownOnce)


    def IsCase(self):
        """Returns whether case-sensitive search."""
        return self._flags["case"]
    def SetCase(self, enabled=True):
        """Toggles case-sensitive search."""
        self._SetFlag("case", enabled)
    Case = property(IsCase, SetCase)


    def IsWholeWords(self):
        """Returns whether matching whole words only."""
        return self._flags["word"]
    def SetWholeWords(self, enabled=True):
        """Toggles whether matching whole words only."""
        self._SetFlag("word", enabled)
    WholeWords = property(IsWholeWords, SetWholeWords)


    def IsRegex(self):
        """Returns whether regular expression search."""
        return self._flags["regex"]
    def SetRegex(self, enabled=True):
        """Toggles regular expression search."""
        self._SetFlag("regex", enabled)
    Regex = property(IsRegex, SetRegex)


    def IsHex(self):
        """Returns whether hexadecimal search."""
        return self._flags["hex"]
    def SetHex(self, enabled=True):
        """Toggles hexadecimal search."""
        self._SetFlag("hex", enabled)
    Hex = property(IsHex, SetHex)


    def IsMultiline(self):
        """Returns whether multi-line text mode."""
        return self._flags["multiline"]
    def SetMultiline(self, enabled=True):
        """Toggles multi-line text mode."""
        self._SetFlag("multiline", enabled)
    Multiline = property(IsMultiline, SetMultiline)


    def IsReverse(self):
        """Returns whether searching backward from current position."""
        return self._flags["reverse"]
    def SetReverse(self, enabled=True):
        """Toggles searching backward from current position."""
        self._SetFlag("reverse", enabled)
    Reverse = property(IsReverse, SetReverse)


    def GetFindChoices(self):
        """Returns the list of auto-complete choices for search text."""
        return self._ctrls["text_find"].GetChoices()
    def SetFindChoices(self, choices):
        """Sets the list of auto-complete choices for search text."""
        return self._ctrls["text_find"].SetChoices(choices)
    FindChoices = property(GetFindChoices, SetFindChoices)


    def GetReplaceChoices(self):
        """Returns the list of auto-complete choices for search text."""
        return self._ctrls["text_repl"].GetChoices()
    def SetReplaceChoices(self, choices):
        """Sets the list of auto-complete choices for replacement text."""
        return self._ctrls["text_repl"].SetChoices(choices)
    ReplaceChoices = property(GetReplaceChoices, SetReplaceChoices)


    def _Build(self):
        """Creates dialog controls."""
        repl = not self._flags["findonly"]
        label_find    = wx.StaticText(self, label="F&ind what:",    name="find_label")
        label_repl    = wx.StaticText(self, label="Re&place with:", name="repl_label")
        label_findbig = wx.StaticText(self, label="F&ind what:",    name="findbig_label")
        label_replbig = wx.StaticText(self, label="Re&place with:", name="replbig_label")
        label_status  = wx.StaticText(self)

        text_find = TextCtrlAutoComplete(self, name="find")
        text_repl = TextCtrlAutoComplete(self, name="repl")
        hex_find  = HexTextCtrl(self, name="find")
        hex_repl  = HexTextCtrl(self, name="repl")

        text_findbig = wx.TextCtrl(self, style=wx.TE_MULTILINE, name="findbig")
        text_replbig = wx.TextCtrl(self, style=wx.TE_MULTILINE, name="replbig")
        hex_findbig  = HexTextCtrl(self, name="findbig", addressed=True)
        hex_replbig  = HexTextCtrl(self, name="replbig", addressed=True)

        check_case  = wx.CheckBox(self, label="Match &case")
        check_regex = wx.CheckBox(self, label="Regular e&xpression")
        check_hex   = wx.CheckBox(self, label="&Hexadecimal")
        check_word  = wx.CheckBox(self, label="Match &whole words only")
        check_rev   = wx.CheckBox(self, label="Search &upwards")

        button_find    = wx.Button(self, label="&Find next")
        button_prev    = wx.Button(self, label="&Previous")
        button_repl    = wx.Button(self, label="&Replace")
        button_replall = wx.Button(self, label="Replace &all")
        button_count   = wx.Button(self, label="Cou&nt")
        button_cancel  = wx.Button(self, label="Cancel")
        button_multi   = wx.ToggleButton(self, label="Multi-&line")

        check_case .ToolTip = "Find case-sensitive matches only"
        check_regex.ToolTip = "Find using a regular expression (Python style regex)"
        check_hex  .ToolTip = "Enter text in hexadecimal codes"
        check_rev  .ToolTip = "Search backward from current position"

        button_count.ToolTip = "Count number of occurrences"
        button_multi.ToolTip = "Toggle multi-line controls"

        text_findbig.MinSize = text_replbig.MinSize = (-1, 5*text_findbig.GetTextExtent("X").Height)
        hex_findbig.MinSize  = hex_replbig.MinSize  = (-1, 5*hex_findbig .GetTextExtent("X").Height)
        if self._flags["shared"]:
            if repl: text_repl.DROPDOWN_CLEAR_TEXT = "Clear replace history"
            text_find.SetChoices(self.FIND_TEXTS), repl and text_repl.SetChoices(self.REPLACE_TEXTS)

        ColourManager.Manage(label_status, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)

        self.SetAffirmativeId(button_find.Id)
        self.SetEscapeId(button_cancel.Id)
        button_find.SetDefault()

        self.Sizer      = wx.BoxSizer(wx.VERTICAL)
        sizer_padding   = wx.BoxSizer(wx.VERTICAL)
        sizer_grid      = wx.GridBagSizer(vgap=5, hgap=5)
        sizer_findedits = wx.BoxSizer(wx.VERTICAL)
        sizer_repledits = wx.BoxSizer(wx.VERTICAL) if repl else None
        sizer_flags     = wx.GridBagSizer(vgap=5, hgap=5)
        sizer_bigedits  = wx.BoxSizer(wx.VERTICAL)

        sizer_findedits.Add(text_find, flag=wx.GROW)
        sizer_findedits.Add(hex_find,  flag=wx.GROW)
        sizer_repledits.Add(text_repl, flag=wx.GROW) if repl else None
        sizer_repledits.Add(hex_repl,  flag=wx.GROW) if repl else None

        sizer_flags.Add(check_case,  pos=(0, 0))
        sizer_flags.Add(check_regex, pos=(1, 0))
        sizer_flags.Add(check_hex,   pos=(2, 0))
        sizer_flags.Add(check_word,  pos=(0, 1))
        sizer_flags.Add(check_rev,   pos=(1, 1)) if repl else None

        sizer_bigedits.Add(label_findbig, flag=wx.BOTTOM,          border=3)
        sizer_bigedits.Add(text_findbig,  flag=wx.GROW)
        sizer_bigedits.Add(hex_findbig,   flag=wx.GROW)
        sizer_bigedits.Add(label_replbig, flag=wx.TOP | wx.BOTTOM, border=3) if repl else None
        sizer_bigedits.Add(text_replbig,  flag=wx.GROW)                      if repl else None
        sizer_bigedits.Add(hex_replbig,   flag=wx.GROW)                      if repl else None

        sizer_grid.Add(label_find,      pos=(0, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer_grid.Add(sizer_findedits, pos=(0, 1), flag=wx.GROW)
        sizer_grid.Add(button_find,     pos=(0, 2))
        sizer_grid.Add(label_repl,      pos=(1, 0), flag=wx.ALIGN_CENTER_VERTICAL) if repl else None
        sizer_grid.Add(sizer_repledits, pos=(1, 1), flag=wx.GROW)                  if repl else None
        sizer_grid.Add(button_repl,     pos=(1, 2))                                if repl else None
        sizer_grid.Add(button_prev,     pos=(1, 2))                            if not repl else None
        sizer_grid.Add(sizer_flags,     pos=(1 + repl, 0), span=(3, 2), border=3, flag=wx.TOP)
        sizer_grid.Add(button_replall,  pos=(1 + repl, 2))                         if repl else None
        sizer_grid.Add(button_count,    pos=(2 + repl, 2))
        sizer_grid.Add(button_cancel,   pos=(3 + repl, 2))
        sizer_grid.Add(label_status,    pos=(4 + repl, 0), span=(1, 2), flag=wx.ALIGN_BOTTOM)
        sizer_grid.Add(button_multi,    pos=(4 + repl, 2))
        sizer_grid.Add(sizer_bigedits,  pos=(5 + repl, 0), span=(1, 3), flag=wx.GROW)

        sizer_grid.AddGrowableCol(1)
        sizer_grid.AddGrowableRow(5 + repl)
        sizer_padding.Add(sizer_grid, border=5, flag=wx.LEFT | wx.GROW)
        self.Sizer.Add(sizer_padding, border=5, flag=wx.ALL | wx.GROW)

        repl_ctrls = dict(label_repl=label_repl,       label_replbig=label_replbig,
                          text_repl=text_repl,         hex_repl=hex_repl,
                          text_replbig=text_replbig,   hex_replbig=hex_replbig,
                          check_rev=check_rev,
                          button_repl=button_repl,     button_replall=button_replall)
        findonly_ctrls = dict(button_prev=button_prev)

        self._sizers.update(grid=sizer_grid, bigedits=sizer_bigedits)
        self._ctrls.update(repl_ctrls if repl else findonly_ctrls,
                           label_find=label_find,        label_findbig=label_findbig,
                           status=label_status,          text_find=text_find,
                           hex_find=hex_find,            text_findbig=text_findbig,
                           hex_findbig=hex_findbig,      check_case=check_case,
                           check_word=check_word,        check_regex=check_regex,
                           check_hex=check_hex,          button_find=button_find,
                           button_count=button_count,    button_cancel=button_cancel,
                           button_multi=button_multi)
        for x in findonly_ctrls.values() if repl else repl_ctrls.values():
            x.Destroy()


    def _Bind(self):
        """Binds control and dialog event and shortcut handlers."""
        repl = not self._flags["findonly"]
        on_toggle = lambda f, f2=None: (lambda event: (f(event.EventObject.Value), f2 and f2()))
        on_edit   = lambda e: self._RefreshStatus()
        self.Bind(wx.EVT_CHECKBOX, on_toggle(self.SetCase),       self._ctrls["check_case"])
        self.Bind(wx.EVT_CHECKBOX, on_toggle(self.SetWholeWords), self._ctrls["check_word"])
        self.Bind(wx.EVT_CHECKBOX, on_toggle(self.SetRegex),      self._ctrls["check_regex"])
        self.Bind(wx.EVT_CHECKBOX, on_toggle(self.SetHex),        self._ctrls["check_hex"])
        self.Bind(wx.EVT_CHECKBOX, on_toggle(self.SetReverse),    self._ctrls["check_rev"]) if repl else None

        self.Bind(wx.EVT_BUTTON, self._OnFind,       self._ctrls["button_find"])
        self.Bind(wx.EVT_BUTTON, self._OnPrevious,   self._ctrls["button_prev"]) if not repl else None
        self.Bind(wx.EVT_BUTTON, self._OnReplace,    self._ctrls["button_repl"])     if repl else None
        self.Bind(wx.EVT_BUTTON, self._OnReplaceAll, self._ctrls["button_replall"])  if repl else None
        self.Bind(wx.EVT_BUTTON, self._OnCount,      self._ctrls["button_count"])
        self.Bind(wx.EVT_BUTTON, self._OnClose,      self._ctrls["button_cancel"])

        self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS, self._OnClearHistory, self._ctrls["text_find"])
        self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS, self._OnClearHistory, self._ctrls["text_repl"]) if repl else None

        self.Bind(wx.EVT_TEXT, on_edit, self._ctrls["text_find"])
        self.Bind(wx.EVT_TEXT, on_edit, self._ctrls["hex_find"])
        self.Bind(wx.EVT_TEXT, on_edit, self._ctrls["text_findbig"])
        self.Bind(wx.EVT_TEXT, on_edit, self._ctrls["hex_findbig"])

        self.Bind(wx.EVT_TOGGLEBUTTON, on_toggle(self.SetMultiline, self.EnsureVisible), self._ctrls["button_multi"])

        self.Bind(wx.EVT_SET_FOCUS, lambda e: self._LoadSharedHistory())
        self.Bind(wx.EVT_WINDOW_DESTROY, self._OnDestroy) if self.Parent else None
        parent_ptr = self.Parent  # Hide dialog if any parent gets hidden
        while parent_ptr is not None:
            parent_ptr.Bind(wx.EVT_SHOW, self._OnShowParent)
            parent_ptr = parent_ptr.Parent


    def _Refresh(self):
        """Enables-disables-shows-hides controls according to current settings."""
        repl = not self._flags["findonly"]
        focus_ctrl = self.FindFocus()
        did_multiline = (self._flags["multiline"] == self._ctrls["label_find"].Enabled)
        did_hex = any(self._ctrls[k].Shown and self._ctrls[k].Enabled
                      for k in ("text_find", "text_findbig")) == self._flags["hex"]
        name_find,  name_repl  = (self._GetCtrlName(replace, visible=True) for replace in (False, True))
        name_find2, name_repl2 = (self._GetCtrlName(replace) for replace in (False, True))
        self.Freeze()
        # Enable/disable single-line text controls for multiline flag
        self._ctrls["label_find"].Enable(not self._flags["multiline"])
        self._ctrls["label_repl"].Enable(not self._flags["multiline"]) if repl else None
        self._ctrls["text_find"] .Enable(not self._flags["multiline"])
        self._ctrls["text_repl"] .Enable(not self._flags["multiline"]) if repl else None
        self._ctrls["hex_find"]  .Enable(not self._flags["multiline"])
        self._ctrls["hex_repl"]  .Enable(not self._flags["multiline"]) if repl else None
        # Show/hide single-line text/hex controls for hex flag
        self._ctrls["text_find"].Show(not self._flags["hex"])
        self._ctrls["text_repl"].Show(not self._flags["hex"]) if repl else None
        self._ctrls["hex_find"] .Show(self._flags["hex"])
        self._ctrls["hex_repl"] .Show(self._flags["hex"])     if repl else None
        # Show/hide multi-line controls for multiline flag, and text/hex controls for hex flag
        self._ctrls["label_findbig"].Show(self._flags["multiline"])
        self._ctrls["label_replbig"].Show(self._flags["multiline"]) if repl else None
        self._ctrls["text_findbig"] .Show(self._flags["multiline"] and not self._flags["hex"])
        self._ctrls["text_replbig"] .Show(self._flags["multiline"] and not self._flags["hex"]) if repl else None
        self._ctrls["hex_findbig"]  .Show(self._flags["multiline"] and self._flags["hex"])
        self._ctrls["hex_replbig"]  .Show(self._flags["multiline"] and self._flags["hex"])     if repl else None
        # Enable/disable and populate case and regex checkboxes for hex flag
        self._ctrls["check_case"] .Enable(not self._flags["hex"])
        self._ctrls["check_regex"].Enable(not self._flags["hex"])
        self._ctrls["check_word"] .Enable(not self._flags["regex"])
        self._ctrls["check_case"] .SetValue(False if self._flags["hex"]   else self._flags["case"])
        self._ctrls["check_regex"].SetValue(False if self._flags["hex"]   else self._flags["regex"])
        self._ctrls["check_word"] .SetValue(False if self._flags["regex"] else self._flags["word"])
        self.Layout()
        # Heighten/shorten dialog for multiline flag if freshly toggled
        if did_multiline:
            direction = (1 if self._flags["multiline"] else -1)
            height = self._sizers["bigedits"].Size.Height + self._sizers["grid"].VGap
            self.Size = (self.Size.Width, self.Size.Height + direction * height)
            prevsize = self.Size
            if direction > 0: self.Fit()
            self.Size = (prevsize.Width, -1) if direction > 0 else (-1, self.MinSize.Height)
        if did_multiline or did_hex:
            for n1, n2 in [(name_find, name_find2), (name_repl, name_repl2)]:
                if n2 in self._ctrls and self._ctrls[n1].Value:
                    self._ctrls[n2].Value = self._ctrls[n1].Value
                    if "hex" not in n2: self._ctrls[n2].SelectAll()
        if focus_ctrl is self._ctrls.get(name_find): self._ctrls[name_find2].SetFocus()
        if focus_ctrl is self._ctrls.get(name_repl): self._ctrls[name_repl2].SetFocus()
        self._RefreshStatus()
        self.Thaw()
        self.Refresh()


    def _GetCtrlName(self, replace=False, visible=False):
        """Returns the name of current find or replace text component."""
        tpl = "%s_repl%s" if replace else "%s_find%s"
        if visible:
            shown = lambda *names: any(n in self._ctrls and self._ctrls[n].Shown for n in names)
            return tpl % ("hex" if shown("hex_find",    "hex_findbig")  else "text",
                          "big" if shown("hex_findbig", "text_findbig") else "")
        else:
            return tpl % ("hex" if self._flags["hex"]       else "text",
                          "big" if self._flags["multiline"] else "")


    def _MakeFindRegex(self):
        """Returns search text and flags as re.Pattern, None if no text, raises on regex error."""
        text = self._ctrls[self._GetCtrlName(visible=True)].Value
        if not text: return None
        flags = (0 if self._flags["case"] else re.IGNORECASE)
        if not self._flags["regex"]: text = re.escape(text)
        if self._flags["word"] and not self._flags["hex"] and not self._flags["regex"]:
            text = r"\b%s\b" % text
        return re.compile(text, flags)


    def _SetFlag(self, name, enabled=True):
        """Toggles flag and refreshes dialog."""
        if bool(self._flags[name]) == bool(enabled): return
        self._flags[name] = bool(enabled)
        self._Refresh()


    def _OnDestroy(self, event):
        """Handler for destroying dialog, unbinds EVT_SHOW from parents."""
        parent_ptr = self.Parent
        while parent_ptr is not None:
            parent_ptr.Unbind(wx.EVT_SHOW, handler=self._OnShowParent)
            parent_ptr = parent_ptr.Parent


    def _OnShowParent(self, event):
        """Handler for hiding a parent, hides dialog if shown."""
        event.Skip()
        if not event.Show and self.Shown:
            self._synchidden = True
            self.Hide()
        elif event.Show and not self.Shown and self._synchidden:
            self.Show()


    def _OnClearHistory(self, event):
        """Handler for clearing autocomplete history in search or replace texts."""
        kind = "search" if event.EventObject is self._ctrls["text_find"] else "replace"
        if wx.OK != wx.MessageBox("Clear %s history?" % kind, "Clear history", wx.OK | wx.CANCEL):
            return
        event.EventObject.SetChoices([])
        event.EventObject.ShowDropDown(False)
        event.EventObject.Value = ""
        (self.FIND_TEXTS if "search" == kind else self.REPLACE_TEXTS)[:] = []


    def _OnFind(self, event):
        """Handler for searching and selecting next match."""
        if not self._IsSearchable(): return
        self._RefreshStatus()
        try: pattern = self._MakeFindRegex()
        except Exception as e:
            wx.MessageBox("Invalid regular expression.\n\n%s" % e, self.Title, wx.ICON_ERROR)
        else: pattern and self._DoFind(pattern, reverse=self._flags["reverse"])


    def _OnPrevious(self, event):
        """Handler for searching and selecting previous match."""
        if not self._IsSearchable(): return
        self._RefreshStatus()
        try: pattern = self._MakeFindRegex()
        except Exception as e:
            wx.MessageBox("Invalid regular expression.\n\n%s" % e, self.Title, wx.ICON_ERROR)
        else:
            pattern and self._DoFind(pattern, reverse=True)


    def _OnReplace(self, event):
        """Handler for searching and replacing current or new match."""
        if not self._IsSearchable(): return
        self._RefreshStatus()
        try: pattern = self._MakeFindRegex()
        except Exception as e:
            wx.MessageBox("Invalid regular expression.\n\n%s" % e, self.Title, wx.ICON_ERROR)
        else: pattern and self._DoReplace(pattern)


    def _OnReplaceAll(self, event):
        """Handler for searching and replacing all matches."""
        if not self._IsSearchable(): return
        self._RefreshStatus()
        try: pattern = self._MakeFindRegex()
        except Exception as e:
            wx.MessageBox("Invalid regular expression.\n\n%s" % e, self.Title, wx.ICON_ERROR)
        else: pattern and self._DoReplaceAll(pattern)


    def _OnCount(self, event):
        """Handler for counting all occurrences, pops up dialog with result."""
        if not self._IsSearchable(): return
        self._RefreshStatus()
        try: pattern = self._MakeFindRegex()
        except Exception as e:
            wx.MessageBox("Invalid regular expression.\n\n%s" % e, self.Title, wx.ICON_ERROR)
        else:
            if not pattern: return
            count = self._DoCount(pattern)
            self._RefreshStatus()
            wx.MessageBox("Found %s occurrence%s." % (count, "" if 1 == count else "s"), self.Title)


    def _OnClose(self, event):
        """Handler for closing dialog, hides window."""
        self.Hide()


    def _DoFind(self, pattern, reverse=False):
        """Searches and selects next match."""
        self._RefreshStatus(searching=True)
        self._FindMatch(pattern, reverse)
        self._RefreshStatus(action="find", reverse=reverse)
        self._SelectMatch()
        self._StoreHistory()


    def _DoReplace(self, pattern):
        """Searches and replaces current or new match, selects next match."""
        self._RefreshStatus(searching=True)
        kwargs = dict(pattern=pattern, reverse=self._flags["reverse"])
        found = self._IsAtMatch(pattern)
        if found:  # Replace selection if selected by last search
            self._ReplaceMatch()
            kwargs.update(startspan=self._matchspan, startpos=self._matchpos)
        if self._FindMatch(**kwargs): found = True # Find and select next match, if any
        self._RefreshStatus(action="replace", found=found, reverse=self._flags["reverse"])
        self._SelectMatch()
        self._StoreHistory()


    def _DoReplaceAll(self, pattern):
        """Searches and replaces all matches for pattern."""
        self._RefreshStatus(searching=True)
        self._match = None
        kwargs = dict(reverse=False, wrap=False)
        kwargs["startpos" if isinstance(self._target, wx.grid.Grid) else "startspan"] = (0, 0)
        while self._FindMatch(pattern, **kwargs):
            self._ReplaceMatch()
            kwargs.update(startspan=self._matchspan, startpos=self._matchpos)
        self._RefreshStatus(action="replace_all", found=len(kwargs) > 3)
        self._StoreHistory()


    def _DoCount(self, pattern):
        """Returns count of all occurrences of pattern in target."""
        self._RefreshStatus(searching=True)
        self._match = None
        count, kwargs = 0, dict(reverse=False, wrap=False)
        kwargs["startpos" if isinstance(self._target, wx.grid.Grid) else "startspan"] = (0, 0)
        while self._FindMatch(pattern, **kwargs):
            kwargs.update(startspan=self._matchspan, startpos=self._matchpos)
            count += 1
        return count


    def _SelectMatch(self):
        """Selects current match in target control, or deselects current selection if no match."""
        if not self._match:
            if not isinstance(self._target, wx.grid.Grid):
                self._target.SetSelection(*self._target.GetSelection()[-1:] * 2)
            return
        if isinstance(self._target, wx.grid.Grid):
            self._target.GoToCell(*self._matchpos)
        else:
            span = self._GetSpanForTextCtrl(self._matchspan)
            self._target.ShowPosition(span[0]) # Try to make whole selection visible
            self._target.ShowPosition(span[1])
            self._target.SetSelection(*span)


    def _ReplaceMatch(self):
        """Replaces current match in target control with entered text."""
        text = self._ctrls[self._GetCtrlName(replace=True)].Value
        match, span, pos = self._match, self._matchspan, self._matchpos
        if self._flags["regex"] and (match.groups() or match.groupdict()) \
        and re.search(r"(\\\d)|(\\g<.+>)", text):
            refs, repls = {}, []  # Replace all backrefs like \1 in one fell swoop
            for k, v in match.groupdict().items() or enumerate(match.groups(), 1):
                repls.append("\\g<%s>" % k) # \g<INDEX> and \g<NAME>
                refs["\\g<%s>" % k] = v
                if isinstance(k, int):
                    repls.append("\\%s" % k) # \INDEX
                    refs["\\%s" % k] = v
            text = re.sub("|".join(map(re.escape, repls)), lambda m: refs[m.group(0)], text)

        if isinstance(self._target, wx.grid.Grid):
            v1 = self._target.GetCellValue(pos)
            v2 = v1[:span[0]] + text + v1[span[1]:]
            self._target.SetCellValue(pos[0], pos[1], v2)
            evt = wx.grid.GridEvent(-1, wx.grid.wxEVT_GRID_CELL_CHANGED, self._target, *pos)
            wx.PostEvent(self._target, evt)
            self._matchspan = (span[0], span[1] + len(v2) - len(v1))
        else:
            span, span0 = self._GetSpanForTextCtrl(self._matchspan), self._matchspan
            self._target.Replace(span[0], span[1], text)
            self._matchspan = (span0[0], span0[1] + len(text) - (span0[1] - span0[0]))
        self._status["replaced"] = self._status.get("replaced", 0) + 1


    def _FindMatch(self, pattern, reverse=False, startspan=None, startpos=None, wrap=True):
        """
        Searches target, advances inner search state, returns whether match was found.

        @param   reverse    whether searching backward
        @param   startspan  (start, end) of text span to continue from
        @param   startpos   (row, col) of target grid position to start from if not current
        @param   wrap       wrap search around if not found from current position
        """
        direction = -1 if reverse else 1

        def get_match(text):
            match = None
            for match in pattern.finditer(text) if reverse else (): pass
            return match if reverse else pattern.search(text)

        if isinstance(self._target, wx.grid.Grid):
            if startspan or startpos or self._IsAtMatch(pattern):  # Continue in remaining cell text
                mydirection = 0 if startpos and not startspan else direction
                text, span, pos = self._GetFromTarget(mydirection, startspan or self._matchspan,
                                                      startpos or self._matchpos)
            else:  # Start search from current cell
                text, span, pos = self._GetFromTarget(direction=0)
            match, wrapped, spanpos_prev = None, (False if pos else None), (span, pos)
            while pos or (wrap and wrapped is False):  # Wrap immediately if at grid edge
                if pos:
                    match = get_match(text)
                    if match: break  # while pos
                    text, span, pos = self._GetFromTarget(direction, startpos=pos)  # Continue search
                if not pos and (wrap and not wrapped):  # Wrap search around if not found this side
                    (text, span, pos), wrapped = self._GetFromTarget(direction, wrap=True), True
                    self._status.update(wrapped=True)
                if spanpos_prev == (span, pos): break  # while pos
                spanpos_prev = (span, pos)
            fulltext = self._target.GetCellValue(pos) if pos else None
        else:
            fulltext = self._target.Value
            if not startspan: startspan = self._matchspan if self._IsAtMatch(pattern) else None
            text, pos, span = self._GetFromTarget(direction, startspan)
            match = get_match(text) if span[0] != span[1] else None
            if not match and wrap and text != fulltext:  # Wrap search around if not found this side
                text, pos, span = self._GetFromTarget(direction, startspan, wrap=True)
                match = get_match(text)
                self._status.update(wrapped=True)

        matchspan = (span[0] + match.start(), span[0] + match.end()) if match else None
        matchpos = pos if isinstance(self._target, wx.grid.Grid) else matchspan
        self._match, self._matchspan, self._matchpos = match, matchspan, matchpos
        self._pattern, self._text = pattern, fulltext
        self._status.update(found=bool(match))
        return bool(match)


    def _GetFromTarget(self, direction=1, startspan=None, startpos=None, wrap=False):
        """
        Returns target text to search, and text position.

        @param   direction  1 for forward, -1 for backward, 0 for current grid cell
        @param   startspan  (start, end) of text span to continue from
        @param   startpos   target grid position to start from if not current, as (row, col)
        @param   wrap       start from other end in direction of given or current position

        @return             (text, span, pos); text as full or remaining side in target;
                            span as (text start, text end), cell text if grid;
                            pos as (row, col) if grid, same as span if text

        """
        def ensure_rows(end=False):  # Tries to populate more or all rows in grid, returns row count
            seekable = next((c for c in (self._target, self._target.Table)
                             if callable(getattr(c, "SeekAhead", None))), None)
            try: seekable and seekable.SeekAhead(end=end)  # Support components like SQLiteGridBase
            except Exception: pass
            return self._target.Table.RowsCount

        def move_pos(pos, direction):  # Returns next grid cell in direction, can wrap to next row
            MAXROW, MAXCOL = ROWS, COLS
            row2, col2 = pos[0], pos[1] + direction
            if col2 < 0 or col2 > MAXCOL - 1:
                row2, col2 = row2 + (direction or 1), MAXCOL - 1 if direction < 0 else 0
            if row2 < 0 or row2 > MAXROW - 1: MAXROW = ensure_rows(direction < 0)
            return None if row2 < 0 or row2 > MAXROW - 1 else (row2, col2)

        def ensure_pos(pos, direction=0):  # Returns next visible grid cell position, or None
            if not ROWS or not any(self._target.IsColShown(x) for x in range(COLS)): return None
            if direction: pos = move_pos(pos, direction)
            while pos and not self._target.IsColShown(pos[1]):
                pos = move_pos(pos, direction or 1)
            return pos

        text = pos = span = None

        if isinstance(self._target, wx.grid.Grid):
            ROWS, COLS = self._target.Table.RowsCount, self._target.Table.ColsCount
            startpos = startpos or (self._target.GridCursorRow, self._target.GridCursorCol)
            if wrap:
                if direction < 0: ROWS = ensure_rows(end=True)
                startpos = (ROWS - 1, COLS - 1) if direction < 0 else (0, 0)
            elif not startspan or startspan[0] == startspan[1]:  # 0-length match: advance
                startpos, startspan = ensure_pos(startpos, direction), None
            if startpos:
                text = self._target.GetCellValue(startpos)
                span, pos = (0, len(text)), startpos
                if startspan:
                    span = (0, startspan[0]) if direction < 0 else (startspan[1], len(text))
                    if startspan[0] == startspan[1] and not (direction < 0):
                        span = (startspan[1] + 1, len(text))  # 0-length match: advance
                    text = text[span[0]:span[1]]
        else:
            text = self._target.Value
            mystartspan = startspan or [self._target.InsertionPoint] * 2
            if (direction < 0 and not wrap) or (direction > 0 and wrap):
                span = (0, mystartspan[0] if direction < 0 else len(text))
            else: # Going backward and wrapping, or forward and not wrapping
                advance = self._match and startspan and startspan[0] == startspan[1] # 0-length match
                span = ((0 if direction < 0 else mystartspan[1]) + bool(advance), len(text))
            if span != (0, len(text)):
                text = text[span[0]:span[1]]
            pos = span
        return text, span, pos


    def _GetSpanForTextCtrl(self, span):
        """Returns given text span for target text control, usable for SetSelection() et al."""
        if not isinstance(self._target, wx.stc.StyledTextCtrl) \
        or len(self._target.Text) == len(self._target.TextRaw):
            return span
        # Workaround for StyledTextCtrl text indexes being for raw bytes not unicode
        unichars = self._target.Value[:span[1]]
        rawchars = [x.encode("utf-8") for x in unichars]
        rawfrom = sum(map(len, rawchars[:span[0]]))
        rawto   = rawfrom + sum(map(len, rawchars[span[0]:span[1]]))
        return (rawfrom, rawto)


    def _IsAtMatch(self, pattern):
        """Returns whether current target selection is at last match."""
        result = False
        if self._matchpos:
            if isinstance(self._target, wx.grid.Grid):
                text, pos = None, (self._target.GridCursorRow, self._target.GridCursorCol)
                if self._target.IsColShown(self._matchpos[1]): text = self._target.GetCellValue(pos)
                result = pattern == self._pattern and text == self._text and pos == self._matchpos
            else:
                text, pos = self._target.Value, self._target.GetSelection()
                result = pattern == self._pattern and text == self._text and \
                         pos == self._GetSpanForTextCtrl(self._matchspan)
        return result


    def _IsSearchable(self):
        """Returns whether target exists and is searchable (enabled, and has content if grid)."""
        return True if self._target and self._target.Enabled else False


    def _RefreshStatus(self, **status):
        """Sets find / replace status colour and text to find control and status label."""
        self._status.update(status)
        ok = True if "action" not in status else (self._status.get("found") or self._status.get("replaced"))
        colour = ColourManager.ColourHex(wx.SYS_COLOUR_WINDOW) if ok else self.COLOUR_NOTFOUND
        for ctrl in map(self._ctrls.get, ("text_find", "hex_find", "text_findbig", "hex_findbig")):
            if not ctrl.Shown or not ctrl.Enabled: continue # for ctrl
            if isinstance(ctrl, wx.TextCtrl):
                ctrl.SetBackgroundColour(colour)
            else:
                ctrl.SetStyleSpecs(background=colour)
            ctrl.Refresh()
            break # for ctrl
        status1 = self._ctrls["status"].Label
        status2 = ""
        if status:
            texts = []
            if self._status.get("replaced") and "replace_all" == self._status.get("action"):
                texts.append("Replaced %(replaced)s occurrences" % self._status)
            elif self._status.get("found") and not self._status.get("replaced") \
            and isinstance(self._target, wx.grid.Grid):
                gridpos = "%s, %s" % tuple(x + 1 for x in self._matchpos)
                textpos_nums = (self._matchspan[0] + 1, )
                if self.Regex and self._matchspan[1] - self._matchspan[0] > 1:
                    textpos_nums += self._matchspan[1:]  # Show full span for regex if length > 1
                textpos = "-".join(map(str, textpos_nums))
                texts.append("Matched in grid cell (%s), text position %s" % (gridpos, textpos))
            if "replaced" not in self._status \
            and self._status.get("wrapped") and self._status.get("found"):
                texts.append("Search wrapped around to %s" % \
                             ("end" if self._status.get("reverse") else "beginning"))
            if not texts and not ok: texts.append("Nothing found")
            elif self._status.get("searching"): texts.append("Searching..")
            status2 = ".\n".join(texts) + ("." if len(texts) > 1 else "")
        self._status.clear()
        if status1 != status2:
            self._ctrls["status"].ToolTip = self._ctrls["status"].Label = status2
            self._ctrls["status"].Wrap(self._ctrls["status"].MaxSize.Width)
            self.Layout()
            wx.SafeYield()


    def _StoreHistory(self):
        """
        Adds current search and replace values to autocomplete history, updates shared if enabled.
        """
        names  = [self._GetCtrlName(replace) for replace in (False, True)]
        values = [self._ctrls[n].Value if n in self._ctrls else None for n in names]
        for name, value in zip(("text_find", "text_repl"), values):
            if not value or name not in self._ctrls: continue  # for
            choices = self._ctrls[name].GetChoices()
            choices0 = choices[:]
            if value in choices and value != choices[0]: choices.remove(value)
            if value not in choices: choices.insert(0, value)
            if choices == choices0: continue  # for
            self._ctrls[name].SetChoices(choices)
            if self._flags["shared"]:
                (self.FIND_TEXTS if "text_find" == name else self.REPLACE_TEXTS)[:] = choices


    def _LoadSharedHistory(self):
        """Populates search and replace text control autocomplete from shared history if enabled."""
        if not self._flags["shared"]: return
        for n, tt in zip(("text_find", "text_repl"), (self.FIND_TEXTS, self.REPLACE_TEXTS)):
            if n in self._ctrls and len(self._ctrls[n].Choices) != len(tt):
                self._ctrls[n].SetChoices(tt)



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
                      or callable(dialog) doing required change and returning field name;
                      name may be a sequence of names as subpath
       ?tb:           [{type, ?help, ?toggle, ?on, ?bmp}] for SQLiteTextCtrl component,
                      adds toolbar, supported toolbar buttons "numbers", "wrap",
                      "copy", "paste", "open" and "save", plus "sep" for separator
       ?format:       function(value) for formatting ComboBox/ListBox items
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
    @param   format    function(value) for formatting ComboBox/ListBox items
    """

    WIDTH = 640 if "linux" in sys.platform else 440
    HEIGHT_FOOTER = 100 if "linux" in sys.platform else 65


    def __init__(self, parent, title, props=None, data=None, edit=None, autocomp=None,
                 onclose=None, footer=None, format=None):
        wx.Dialog.__init__(self, parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self._ignore_change = False
        self._editmode = bool(edit) if edit is not None else True
        self._comps    = collections.defaultdict(list) # {(path): [wx component, ]}
        self._autocomp = autocomp
        self._onclose  = onclose
        self._footer   = dict(footer) if footer and footer.get("populate") else None
        self._format   = format if callable(format) else lambda x: x
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
        FRAMEH = get_window_height(self, exclude=splitter or panel_wrap)
        FOOTERH = self.HEIGHT_FOOTER if panel_footer else 0
        self.Size = self.MinSize = (self.WIDTH, FRAMEH + FOOTERH + panel_wrap.VirtualSize[1])
        if splitter:
            splitter.SetSashPosition(splitter.Size[1] - 65)
        self.CenterOnParent()
        ColourManager.Patch(self)


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
            if isinstance(x, collections_abc.Iterable) and not isinstance(x, string_types):
                for k, v in enumerate(x):
                    if isinstance(x, collections_abc.Mapping): k, v = v, x[v]
                    callback(v)
                    walk(v, callback)

        if props is not None:
            memo = {} # copy-module produces invalid result for wx.Bitmap, and errors for wx.Window
            walk(props, lambda v: memo.update({id(v): v})
                                               if callable(v) or isinstance(v, wx.Object) else None)
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
        if sizer.Cols > 1 and not sizer.IsColGrowable(sizer.Cols - 2):
            sizer.AddGrowableCol(sizer.Cols - 2, proportion=1)
        if len(self._comps) == 1 and not sizer.IsRowGrowable(0) and self._editmode:
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
        """Returns field from props; name can be a sequence of names as subpath."""
        names = list(name) if isinstance(name, (list, tuple)) else [name]
        fields, path = self._props, list(path) + names
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


    def _GetFormat(self, field):
        """Returns function for formatting field values."""
        if "format" in field:
            return field["format"] if field["format"] else lambda x: x
        return self._format


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
                GRW = 0 if isinstance(c, (wx.CheckBox, wx.ComboBox)) else wx.GROW
                sizer.Add(c, border=brd, pos=(self._rows, col), span=(1, colspan), flag=BRD | GRW)
                col += colspan

        self._rows += 1
        for f in field.get("children") or (): self._AddField(f, fpath)


    def _AddFooter(self, parent, footer):
        """Adds footer component to dialog, returns footer panel."""
        panel = wx.Panel(parent)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        label, tb, ctrl = None, None, None
        accname = "footer_%s" % NewId()

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
                listbox.SetItems(list(map(self._GetFormat(field), vv)))
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
                        c.SetItems(list(map(self._GetFormat(field), choices)))
                        for j, x in enumerate(choices): c.SetClientData(j, x)
                        value = self._GetFormat(field)(value) if value else value
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
            ctrl = field["component"](parent, traversable=True, style=wx.BORDER_SUNKEN, name=accname)

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
                    ctrl.SetWordWrap(False)

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
                v = self._GetValue(field, path)
                tstyle = wx.TE_MULTILINE if v and "\n" in v else 0
                ctrl = wx.TextCtrl(parent, style=tstyle)

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
        elif isinstance(ctrl, wx.ListBox):  events = [wx.EVT_LISTBOX_DCLICK]
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
        if isinstance(src, wx.ComboBox) and not field.get("choicesedit") and src.HasClientData():
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
            linkpath = (path + tuple(name[:-1])) if isinstance(name, (list, tuple)) else path
            if linkfield: self._PopulateField(linkfield, linkpath)


    def _OnAddToList(self, field, path, event):
        """Handler from adding items from listbox on the left to the right."""
        indexes = []

        listbox1, listbox2 = (x for x in self._comps[path + (field["name"], )]
                              if isinstance(x, wx.ListBox))
        if isinstance(event.EventObject, wx.ListBox):
            indexes.append(event.GetSelection())
        else: # Helper button
            indexes.extend(listbox1.GetSelections())
            if not indexes and listbox1.GetCount(): indexes.append(0)
        selecteds = list(map(listbox1.GetClientData, indexes))

        if field.get("exclusive"):
            for i in indexes[::-1]: listbox1.Delete(i)
        listbox2.AppendItems(list(map(self._GetFormat(field), selecteds)))
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
        else: # Helper button
            indexes.extend(listbox2.GetSelections())
            if not indexes and listbox2.GetCount(): indexes.append(0)

        for i in indexes[::-1]: listbox2.Delete(i)
        items2 = list(map(listbox2.GetClientData, range(listbox2.Count)))
        if field.get("exclusive"):
            allchoices, format = self._GetChoices(field, path), self._GetFormat(field)
            listbox1.SetItems([format(x) for x in allchoices if x not in items2])
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

        listbox2.SetItems(list(map(self._GetFormat(field), items)))
        for j, x in enumerate(items): listbox2.SetClientData(j, x)
        for i in indexes: listbox2.Select(i + direction)
        self._SetValue(field, items, path)


    def _OnToggleField(self, field, path, ctrl, event=None):
        """Handler for toggling a field (and subfields) on/off, updates display."""
        fpath = path + (field["name"], )
        ctrls = [] # [(field, path, ctrl)]
        for c in self._comps.get(fpath, []):
            ctrls.append((field, path, c))
        if field.get("togglename") and field["togglename"].get("name"):
            for c in self._comps.get(fpath + (field["togglename"]["name"], ), []):
                if c not in (x for _, _, x in ctrls):
                    ctrls.append((field["togglename"], fpath, c))
        neststack = [(fpath, field["children"])] if field.get("children") else []
        while neststack:
            npath, children = neststack.pop(0)
            for f in children:
                for c in self._comps.get(npath + (f["name"], ), []):
                    if c not in (x for _, _, x in ctrls):
                        ctrls.append((f, npath, c))
                if f.get("children"):
                    neststack.append((npath + (f["name"], ), f["children"]))

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
        if on and self._editmode and ("text" == field.get("type")
             or path and field == self._GetField(path[-1], path[:-1]).get("togglename")
        ):
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
            linkpath = (path + tuple(name[:-1])) if isinstance(name, (list, tuple)) else path
            if linkfield: self._PopulateField(linkfield, linkpath)
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
        ctrl.SetWordWrap(event.IsChecked())


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
        """
        Constructor.

        @param   parent  parent window
        @param   label   button label
        @param   note    button note text
        @param   bmp     button icon
        @param   id      button wx identifier
        @param   pos     button position
        @param   size    button default size
        @param   style   alignment flags for button content
                         (left-right for horizontal, center for vertical),
                         plus optional wx.BORDER_RAISED
                         for permanent 3D-border and default cursor,
                         plus any flags for wx.Panel
        @param   name    control name
        """
        wx.Panel.__init__(self, parent, id, pos, size,
                          style & ~wx.BORDER_RAISED | wx.FULL_REPAINT_ON_RESIZE, name)
        self._label = label
        self._note = note
        self._bmp = bmp
        self._bmp_disabled = bmp
        if bmp is not None and bmp.IsOk():
            img = bmp.ConvertToImage().ConvertToGreyscale()
            self._bmp_disabled = wx.Bitmap(img) if img.IsOk() else bmp
        self._hover = False # Whether button is being mouse hovered
        self._press = False # Whether button is being mouse pressed
        self._style = style
        self._wrapped = True
        self._enabled = True
        self._size = self.Size

        # Wrapped texts for both label and note
        self._text_label = None
        self._text_note = None
        # (width, height, lineheight) for wrapped texts in current DC
        self._extent_label = None
        self._extent_note = None


        self._cursor_hover = None if wx.BORDER_RAISED & self._style else wx.Cursor(wx.CURSOR_HAND)

        self.Bind(wx.EVT_MOUSE_EVENTS,       self.OnMouseEvent)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.OnMouseCaptureLostEvent)
        self.Bind(wx.EVT_PAINT,              self.OnPaint)
        self.Bind(wx.EVT_SIZE,               self.OnSize)
        self.Bind(wx.EVT_SET_FOCUS,          self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnFocus)
        self.Bind(wx.EVT_ERASE_BACKGROUND,   self.OnEraseBackground)
        self.Bind(wx.EVT_KEY_DOWN,           self.OnKeyDown)
        self.Bind(wx.EVT_CHAR_HOOK,          self.OnChar)

        if not wx.BORDER_RAISED & self._style: self.SetCursor(self._cursor_hover)
        ColourManager.Manage(self, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        self.UpdateButton()


    def GetMinSize(self):
        return self.DoGetBestSize()
    MinSize = property(GetMinSize, wx.Panel.SetMinSize)


    def GetMinWidth(self):
        return self.DoGetBestSize().Width
    MinWidth = property(GetMinWidth)


    def GetMinHeight(self):
        return self.DoGetBestSize().Height
    MinHeight = property(GetMinHeight)


    def DoGetBestSize(self):
        w, h = 10, 10
        if any(self._extent_label or ()) or any(self._extent_note or ()):
            w += 10 + max(ext[0] for ext in (self._extent_label, self._extent_note) if ext)
        if self._bmp:
            bw, bh = (x + 10 for x in self._bmp.Size)
            w, h = w + bw, h + bh
        if any(self._extent_label or ()):
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
        if (self._style & wx.ALIGN_RIGHT):
            x = width - 10 - self._bmp.Size.width
        elif (self._style & wx.ALIGN_CENTER_HORIZONTAL):
            x = 10 + (width - self.DoGetBestSize().width) // 2
        if (self._style & wx.ALIGN_BOTTOM):
            y = height - self.DoGetBestSize().height + 10
        elif (self._style & wx.ALIGN_CENTER_VERTICAL):
            y = (height - self.DoGetBestSize().height + 10) // 2

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

        if self._press or (is_focused and any(get_key_state(x) for x in KEYS.SPACE)):
            # Button is being clicked with mouse: create sunken effect
            colours = [(128, 128, 128)] * 2
            lines   = [(1, 1, width - 2, 1), (1, 1, 1, height - 2)]
            dc.DrawLineList(lines, [PEN(wx.Colour(*c)) for c in colours])
            x += 1; y += 1
        elif wx.BORDER_RAISED & self._style:
            # Draw 3D border
            colours = [ColourManager.ColourHex(x) for x in (
                wx.SYS_COLOUR_3DHILIGHT, wx.SYS_COLOUR_3DLIGHT,
                wx.SYS_COLOUR_3DSHADOW,  wx.SYS_COLOUR_3DDKSHADOW
            )]
            lines, pencolours = [], []
            lines  = [(0, 0, 0, height - 1), (0, 0, width - 1, 0)]
            lines += [(1, 1, 1, height - 2), (1, 1, width - 2, 1)]
            lines += [(1, height - 2, width - 2, height - 2), (width - 2, 1, width - 2, height - 2)]
            lines += [(0, height - 1, width - 1, height - 1), (width - 1, 0, width - 1, height - 1)]
            dc.DrawLineList(lines, sum(([PEN(wx.Colour(c))]*2 for c in colours), []))
        elif self._hover and self.IsThisEnabled():
            # Button is being hovered with mouse: create raised effect
            colours  = [(255, 255, 255)] * 2
            if sum(ColourManager.Diff(self.BackgroundColour, wx.WHITE)[:3]) < 15:
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
            dc.DrawBitmap(bmp, x, y, useMask=True)

        if self._style & wx.ALIGN_RIGHT:
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
                h += dc.GetTextExtent(line)[1]
                text_label += chars + "\n"
        dc.DrawText(text_label, x, y)

        # Draw note
        _, label_h = dc.GetMultiLineTextExtent(self._text_label)
        y += label_h + 10
        dc.Font = self.Font
        dc.DrawText(self._text_note, x, y)


    def GetWrapped(self):
        """Returns current text wrap setting."""
        return self._wrapped
    def SetWrapped(self, on=True):
        """
        Enables or disables wrap mode, wrapping button texts to size if enabled,
        or sizing button to unwrapped texts.
        """
        on = bool(on)
        if on != self._wrapped:
            self._wrapped = on
            self.UpdateButton()
    Wrapped = property(GetWrapped, SetWrapped)


    def WrapTexts(self):
        """Wraps button texts to current control size if wrap mode enabled."""
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
        if self._wrapped:
            x = 10 + self._bmp.Size.width + 10
            self._text_note = WORDWRAP(self._text_note, width - 10 - x, dc)
            dc.Font = wx.Font(dc.Font.PointSize, dc.Font.Family, dc.Font.Style,
                              wx.FONTWEIGHT_BOLD, faceName=dc.Font.FaceName)
            self._text_label = WORDWRAP(self._text_label, width - 10 - x, dc)
        self._extent_label = dc.GetMultiLineTextExtent(self._text_label)
        self._extent_note = dc.GetMultiLineTextExtent(self._text_note)


    def UpdateButton(self):
        """Wraps texts accordug to current settings and triggers button layout."""
        exts = self._extent_label, self._extent_note
        self.WrapTexts()
        if not self._wrapped and exts != (self._extent_label, self._extent_note):
            self.Size = self.MinSize = self.DoGetBestSize()
        self.Refresh()
        self.InvalidateBestSize()
        wx.CallAfter(lambda: self.Parent and self.Parent.Layout())


    def OnPaint(self, event):
        """Handler for paint event, calls Draw()."""
        dc = wx.BufferedPaintDC(self)
        self.Draw(dc)


    def OnSize(self, event):
        """Handler for size event, resizes texts and repaints control."""
        event.Skip()
        if event.Size != self._size:
            self._size = event.Size
            wx.CallAfter(lambda: self and self.UpdateButton())


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
            self.UpdateButton()
    Label = property(GetLabel, SetLabel)


    def SetNote(self, note):
        if note != self._note:
            self._note = note
            self.UpdateButton()
    def GetNote(self):
        return self._note
    Note = property(GetNote, SetNote)



class Patch(object):
    """Monkey-patches wx API for general compatibility over different versions."""

    _PATCHED = False

    @staticmethod
    def patch_wx(art=None):
        """
        Patches wx object methods to smooth over version and setup differences.

        In wheel-built wxPython in Ubuntu22, floats are no longer auto-converted to ints
        in core wx object method calls like wx.Colour().

        @param   art  image overrides for wx.ArtProvider, as {image ID: wx.Bitmap}
        """
        if Patch._PATCHED: return

        if not hasattr(wx.stc.StyledTextCtrl, "SetMarginCount"):  # Since wx 3.1.1
            wx.stc.StyledTextCtrl.SetMarginCount = lambda *a, **kw: None

        if not hasattr(wx.stc.StyledTextCtrl, "GetSelectionEmpty"):  # Not in Py2
            def GetSelectionEmpty(self):
                return all(self.GetSelectionNStart(i) == self.GetSelectionNEnd(i)
                           for i in range(self.GetSelections()))
            wx.stc.StyledTextCtrl.GetSelectionEmpty = GetSelectionEmpty

        # Some versions have StartStyling(start), others StartStyling(start, mask)
        STC__StartStyling = wx.stc.StyledTextCtrl.StartStyling
        def StartStyling__Patched(self, *args, **kwargs):
            try: return STC__StartStyling(self, *args, **kwargs)
            except TypeError: return STC__StartStyling(self, *(args + (255, )), **kwargs)
        wx.stc.StyledTextCtrl.StartStyling = StartStyling__Patched

        if wx.VERSION >= (4, 2):
            # Previously, ToolBitmapSize was set to largest, and smaller bitmaps were padded
            ToolBar__Realize = wx.ToolBar.Realize
            def Realize__Patched(self):
                sz = tuple(self.GetToolBitmapSize())
                for i in range(self.GetToolsCount()):
                    t = self.GetToolByPos(i)
                    for b in filter(bool, (t.NormalBitmap, t.DisabledBitmap)):
                        sz = max(sz[0], b.Width), max(sz[1], b.Height)
                self.SetToolBitmapSize(sz)
                for i in range(self.GetToolsCount()):
                    t = self.GetToolByPos(i)
                    if t.NormalBitmap:   t.NormalBitmap   = resize_img(t.NormalBitmap,   sz)
                    if t.DisabledBitmap: t.DisabledBitmap = resize_img(t.DisabledBitmap, sz)
                return ToolBar__Realize(self)
            wx.ToolBar.Realize = Realize__Patched

            def resize_bitmaps(func):
                """Returns function pass-through wrapper, resizing any Bitmap arguments."""
                def inner(self, *args, **kwargs):
                    sz = self.GetToolBitmapSize()
                    args = [resize_img(v, sz) if v and isinstance(v, wx.Bitmap) else v for v in args]
                    kwargs = {k: resize_img(v, sz) if v and isinstance(v, wx.Bitmap) else v
                              for k, v in kwargs.items()}
                    return func(self, *args, **kwargs)
                return functools.update_wrapper(inner, func)
            wx.ToolBar.SetToolNormalBitmap   = resize_bitmaps(wx.ToolBar.SetToolNormalBitmap)
            wx.ToolBar.SetToolDisabledBitmap = resize_bitmaps(wx.ToolBar.SetToolDisabledBitmap)

        if wx.VERSION[:3] == (4, 1, 1) and "linux" in sys.platform:
            # wxPython 4.1.1 on Linux crashes with FlatNotebook agwStyle FNB_VC8
            FlatNotebook__init = wx.lib.agw.flatnotebook.FlatNotebook.__init__
            def FlatNotebook__Patched(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                                      size=wx.DefaultSize, style=0, agwStyle=0, name="FlatNotebook"):
                if agwStyle & wx.lib.agw.flatnotebook.FNB_VC8:
                    agwStyle ^= wx.lib.agw.flatnotebook.FNB_VC8
                FlatNotebook__init(self, parent, id, pos, size, style, agwStyle, name)
            wx.lib.agw.flatnotebook.FlatNotebook.__init__ = FlatNotebook__Patched

        if wx.VERSION >= (4, 2) and art:
            # Patch wx.ArtProvider.GetBitmap to return given bitmaps for overridden images instead
            ArtProvider__GetBitmap = wx.ArtProvider.GetBitmap
            def GetBitmap__Patched(id, client=wx.ART_OTHER, size=wx.DefaultSize):
                if id in art and size == art[id].Size:
                    return art[id]
                return ArtProvider__GetBitmap(id, client, size)
            wx.ArtProvider.GetBitmap = GetBitmap__Patched

        Patch._PATCHED = True

        # In some setups, float->int autoconversion is not done for Python/C sip objects
        try: wx.Rect(1.1, 2.2, 3.3, 4.4)
        except Exception: pass
        else: return

        def defloatify(func):
            """Returns function pass-through wrapper, converting any float arguments to int."""
            cast = lambda v: int(v) if isinstance(v, float) else v
            make = lambda v: type(v)(cast(x) for x in v) if isinstance(v, (list, tuple)) else cast(v)
            def inner(*args, **kwargs):
                args = [make(v) for v in args]
                kwargs = {k: make(v) for k, v in kwargs.items()}
                return func(*args, **kwargs)
            return functools.update_wrapper(inner, func)

        wx.Colour.__init__              = defloatify(wx.Colour.__init__)
        wx.Font.__init__                = defloatify(wx.Font.__init__)
        wx.Point.__init__               = defloatify(wx.Point.__init__)
        wx.Rect.__init__                = defloatify(wx.Rect.__init__)
        wx.Size.__init__                = defloatify(wx.Size.__init__)
        wx.adv.PseudoDC.TranslateId     = defloatify(wx.adv.PseudoDC.TranslateId)
        wx.adv.PseudoDC.SetIdBounds     = defloatify(wx.adv.PseudoDC.SetIdBounds)
        wx.ImageList.Draw               = defloatify(wx.ImageList.Draw)
        wx.BufferedPaintDC.DrawText     = defloatify(wx.BufferedPaintDC.DrawText)
        wx.BufferedPaintDC.DrawBitmap   = defloatify(wx.BufferedPaintDC.DrawBitmap)
        wx.MemoryDC.DrawText            = defloatify(wx.MemoryDC.DrawText)
        wx.MemoryDC.DrawBitmap          = defloatify(wx.MemoryDC.DrawBitmap)
        wx.PaintDC.DrawText             = defloatify(wx.PaintDC.DrawText)
        wx.PaintDC.DrawBitmap           = defloatify(wx.PaintDC.DrawBitmap)
        wx.Rect.Contains                = defloatify(wx.Rect.Contains)
        wx.Rect.Offset                  = defloatify(wx.Rect.Offset)
        wx.Rect.Union                   = defloatify(wx.Rect.Union)
        wx.ScrolledWindow.Scroll        = defloatify(wx.ScrolledWindow.Scroll)
        wx.ScrolledWindow.SetScrollbars = defloatify(wx.ScrolledWindow.SetScrollbars)



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
        else:
            truelinesmax = self.ManagedChild.GetNumberOfLines()
            while self.ManagedChild.GetLineLength(linesmax + 1) >= 0 and linesmax < truelinesmax - 1:
                linesmax += 1
                t = self.ManagedChild.GetLineText(linesmax)
                widthmax = max(widthmax, self.ManagedChild.GetTextExtent(t)[0])
        if hasattr(self.ManagedChild, "DoGetBorderSize"): # Depends on wx version and OS
            borderw, borderh = self.ManagedChild.DoGetBorderSize()
        else: borderw, borderh = (x / 2. for x in self.ManagedChild.GetWindowBorderSize())
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

    SORT_ARROW_DOWN = wx.lib.embeddedimage.PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAEhJ"
        "REFUOI1jZGRiZqAEMFGke9QABgYGBgYWdIH///7+J6SJkYmZEacLkCUJacZqAD5DsInTLhDR"
        "bcPlKrwugGnCFy6Mo3mBAQChDgRlP4RC7wAAAABJRU5ErkJggg==")

    ## Item styles as {style name: {option name: values to set or callable(self) returning values to set}}
    STYLES = {
        None:     {"ItemFont":             lambda self: self.Font,
                   "ItemTextColour":       lambda self: self.ForegroundColour,
                   "ItemBackgroundColour": lambda self: self.BackgroundColour}, # None is default style
        "active": {"ItemFont":             lambda self: self.Font.Bold()},
    }


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
        self._id_styles = {}    # {item_id: style name if any}
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
        id_copy = NewId()
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


    def GetTopRow(self):
        """Returns top row data dictionary, or None if no top row."""
        return copy.deepcopy(self._top_row)
    def SetTopRow(self, data, imageIds=()):
        """
        Adds special top row to list, not subject to sorting or filtering.

        @param   data      item data dictionary
        @param   imageIds  list of indexes for the images associated to top row
        """
        self._top_row = copy.deepcopy(data)
        if imageIds: self._id_images[0] = self._ConvertImageIds(imageIds)
        else: self._id_images.pop(0, None)
        self._PopulateTopRow()
        wx.CallAfter(self.AutoSizeColumns)


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
            self._id_rows += [(item_id, copy.deepcopy(r))]
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
            data, columns = copy.deepcopy(data), [c[0] for c in self._columns]
            for i, col_name in enumerate(columns):
                col_value = self._formatters[col_name](data, col_name)

                if imageIds and not i: self.InsertImageStringItem(index, col_value, imageIds)
                elif not i: self.InsertStringItem(index, col_value)
                else: self.SetStringItem(index, i, col_value)
            self.SetItemData(index, item_id)
            self.itemDataMap[item_id] = [data[c] for c in columns]
            self._data_map[item_id] = data
            self._ApplyItemStyle(index, None)
        self._id_rows.insert(index - bool(self._top_row), (item_id, data))
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

        @return   item index, or NOT_FOUND
        """
        for i in range(self.GetItemCount()):
            if self.GetItemText(i) == text: return i
        return wx.NOT_FOUND


    def RefreshRows(self):
        """
        Clears the list and inserts all unfiltered rows, auto-sizing the columns;
        retains scroll position.
        """
        selected_idxs, selected_items, selected = [], [], self.GetFirstSelected()
        while selected >= 0:
            selected_idxs.append(selected)
            selected_items.append((selected, self.GetItemText(selected)))
            selected = self.GetNextSelected(selected)

        self.Freeze()
        try:
            scrollpos = self._mainWin.GetScrollPos(wx.VERTICAL)
            wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
            self._PopulateTopRow()
            self._PopulateRows(selected_items)
            if scrollpos:
                pixelh = self._mainWin.VirtualSize.Height - self._mainWin.Size.Height
                scrollh = self.GetScrollRange(wx.VERTICAL) 
                scrollh -= self._mainWin.GetScrollPageSize(wx.VERTICAL)
                pixels_per_scroll = pixelh / scrollh
                self.ScrollList(0, (scrollpos + 1) * pixels_per_scroll)
        finally: self.Thaw()


    def RefreshRow(self, index, data=None):
        """
        Refreshes row with specified index from item data.

        @param   data  optional dictionary to update current data with
        """
        if not self.GetItemCount(): return
        if index < 0: index = index % self.GetItemCount()
        if index == 0 and self._top_row: item = self._top_row
        else: item = self._data_map.get(self.GetItemData(index))
        if not item: return
        if data: item.update(copy.deepcopy(data))

        for i, col_name in enumerate([c[0] for c in self._columns]):
            col_value = self._formatters[col_name](item, col_name)
            self.SetStringItem(index, i, col_value)
        self._ApplyItemStyle(index, self.GetItemStyle(index))


    def AutoSizeColumns(self, expand_main=True):
        """
        Autosizes all columns to fit current content.

        @param   expand_main  whether first column gets sized to all remaining space
        """
        if not self: return
        widths = []
        get_width = lambda t: self.GetTextExtent(t)[0]
        col_start = 1 if expand_main else 0
        for col_index, (col_name, col_label) in enumerate(self._columns[col_start:], col_start):
            header_width = get_width(col_label + "  ") + self.COL_PADDING # "  " sort space
            texts = [self.GetItem(i, col_index).GetText() for i in range(self.GetItemCount())]
            widths.append(max(header_width, max(get_width(t) for t in texts)))
        if self._col_maxwidth > 0:
            widths = [min(w, self._col_maxwidth) for w in widths]

        if expand_main: # First column to maximum remaining from other columns and scrollbar
            main_width = self.Size[0] - sum(widths) - 5 # Space for padding
            if self.GetScrollRange(wx.VERTICAL) > 1:
                main_width -= self.GetScrollThumb(wx.VERTICAL) # Space for scrollbar
            widths.insert(0, main_width)

        for col_index, width in enumerate(widths):
            self.SetColumnWidth(col_index, width)
            self._col_widths[col_index] = width


    def Select(self, idx, on=True):
        """Selects/deselects an item; changes current item if selected."""
        wx.lib.agw.ultimatelistctrl.UltimateListCtrl.Select(self, idx, on)
        if on: self._mainWin.ChangeCurrent(idx)


    def CenterOnItem(self, idx):
        """Scrolls to center view on item, if currently not visible."""
        pixelh = self._mainWin.VirtualSize.Height - self._mainWin.Size.Height
        scrollh = self.GetScrollRange(wx.VERTICAL) 
        scrollh -= self._mainWin.GetScrollPageSize(wx.VERTICAL)
        pixels_per_scroll = pixelh / scrollh
        row_height = self.GetUserLineHeight()
        count_per_page = self._mainWin.Size.Height / row_height
        scrollpos = self._mainWin.GetScrollPos(wx.VERTICAL)
        first_visible_pixel = pixels_per_scroll * scrollpos

        first_visible = int(first_visible_pixel / row_height)
        last_visible = int(first_visible + count_per_page)
        if first_visible <= idx <= last_visible: return

        y1 = (scrollpos + 1) * pixels_per_scroll
        y2 = (idx - count_per_page // 2) * row_height
        self.ScrollList(0, -y1)
        self.ScrollList(0, y2)
        self.Update()


    def DeleteItem(self, index):
        """Deletes the row at the specified index."""
        item_id = self.GetItemData(index)
        data = self._data_map.get(item_id)
        del self._data_map[item_id]
        self._id_rows.remove((item_id, data))
        self._id_images.pop(item_id, None)
        self._id_styles.pop(item_id, None)
        return wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteItem(self, index)


    def DeleteAllItems(self):
        """Deletes all items data and clears the list."""
        self.itemDataMap = {}
        self._data_map = {}
        self._id_rows = []
        self._id_styles = {}
        for item_id in self._id_images:
            if item_id >= 0: self._id_images.pop(item_id)
        self.Freeze()
        try:
            result = wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
            self._PopulateTopRow()
        finally: self.Thaw()
        return result


    def GetItemCountFull(self):
        """Returns the full row count, including top row and items hidden by filter."""
        return len(self._id_rows) + bool(self._top_row)


    def GetItemTextFull(self, idx):
        """Returns item text by index, including top row and items hidden by filter."""
        rows = ([(0, self._top_row)] if self._top_row else []) + self._id_rows
        data, col_name = rows[idx][-1], self._columns[0][0]
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
        return copy.deepcopy(self._data_map.get(self.GetItemData(index)))


    def GetItemStyle(self, index):
        """Returns style name for item, or None if no style applied."""
        return self._id_styles.get(self.GetItemData(index))
    def SetItemStyle(self, index, name):
        """Sets style on item, or clears current style if None. Redraws item if style changed."""
        if name is not None and name not in self.STYLES:
            raise ValueError("Unknown item style: %r" % (name, ))
        item_id = self.GetItemData(index)
        if self._id_styles.get(item_id) == name: return
        self._id_styles[item_id] = name
        self._ApplyItemStyle(index, name)


    def GetItemStyleByText(self, text):
        """
        Returns style for item with given primary label, or None if no style applied.

        Ignores current filter if any.
        """
        col_name = self._columns[0][0]
        rows = self._id_rows + ([(0, self._top_row)] if self._top_row else [])
        item_id = next(d for d, r in rows if self._formatters[col_name](r, col_name) == text)
        return self._id_styles.get(item_id)
    def SetItemStyleByText(self, text, style):
        """
        Sets style on item with given primary label, or clears current style if None.

        Ignores current filter if any. Redraws item if style changed and item displayed.
        """
        if style is not None and style not in self.STYLES:
            raise ValueError("Unknown item style: %r" % (style, ))
        col_name = self._columns[0][0]
        rows = self._id_rows + ([(0, self._top_row)] if self._top_row else [])
        item_id = next(d for d, r in rows if self._formatters[col_name](r, col_name) == text)
        if self._id_styles.get(item_id) == style: return
        self._id_styles[item_id] = style
        if item_id not in self._data_map: return
        index = next(i for i in range(self.GetItemCount()) if item_id == self.GetItemData(i))
        self._ApplyItemStyle(index, style)


    def SetItemMappedDataByText(self, text, data):
        """Updates the data dictionary mapped to the item with given primary label."""
        col_name = self._columns[0][0]
        rows = self._id_rows + ([(0, self._top_row)] if self._top_row else [])
        row = next((r for _, r in rows if self._formatters[col_name](r, col_name) == text), None)
        if row: row.update(copy.deepcopy(data))


    def GetListCtrl(self):
        """Required by ColumnSorterMixin."""
        return self


    def SortListItems(self, col=-1, ascending=1):
        """Sorts the list items on demand."""
        selected_ids, selected = [], self.GetFirstSelected()
        while selected >= 0:
            selected_ids.append(self.GetItemData(selected))
            selected = self.GetNextSelected(selected)

        wx.lib.mixins.listctrl.ColumnSorterMixin.SortListItems(self, col, ascending)

        if selected_ids: # Re-select the previously selected items
            idindx = dict((self.GetItemData(i), i) for i in range(self.GetItemCount()))
            for i in selected_ids: self.Select(idindx[i]) if i in idindx else None


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
        if event.GetIndex() is None: return
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
        styles    = list(map(self.GetItemStyle,      selecteds))
        image_ids = list(map(self._id_images.get,    map(self.GetItemData, selecteds)))

        self.Freeze()
        try:
            for x in selecteds[::-1]: self.DeleteItem(x)
            for i, (data, style, imageIds) in enumerate(zip(datas, styles, image_ids)):
                imageIds0 = self._ConvertImageIds(imageIds, reverse=True)
                self.InsertRow(idx + i, data, imageIds0)
                self.SetItemStyle(idx + i, style)
                self.Select(idx + i)
            self._drag_start = None
        finally: self.Thaw()


    def OnDragStart(self, event):
        """Handler for dragging items in the list, cancels dragging."""
        if self.GetSortState()[0] < 0 and (not self._top_row or event.GetIndex()):
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


    def _ApplyItemStyle(self, index, name):
        """Applies given style on item."""
        fullstyle = dict(self.STYLES[None], **self.STYLES[name])
        for k, v in fullstyle.items():
            if callable(v): v = v(self)
            getattr(self, "Set%s" % k)(index, *v if isinstance(v, (list, tuple)) else [v])


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
        if 0 in self._id_images:
            self.InsertImageStringItem(0, col_value, self._id_images[0])
        else: self.InsertStringItem(0, col_value)
        for i, col_name in enumerate(columns[1:], 1):
            col_value = self._formatters[col_name](self._top_row, col_name)
            self.SetStringItem(0, i, col_value)
        self._ApplyItemStyle(0, self.GetItemStyle(0))


    def _PopulateRows(self, selected_items=()):
        """Populates all rows, restoring previous selecteds if any"""
        # To map list item data ID to row, ListCtrl allows only integer per row
        row_data_map = {} # {item_id: {row dict}, }
        item_data_map = {} # {item_id: [row values], }
        index = self.GetItemCount()
        for item_id, row in self._id_rows:
            if not self._RowMatchesFilter(row): continue # for item_id, row
            col_name = self._columns[0][0]
            col_value = self._formatters[col_name](row, col_name)
            if item_id in self._id_images:
                self.InsertImageStringItem(index, col_value, self._id_images[item_id])
            else: self.InsertStringItem(index, col_value)

            self.SetItemData(index, item_id)
            item_data_map[item_id] = {0: row[col_name]}
            row_data_map[item_id] = row
            col_index = 1 # First was already inserted
            for col_name, col_label in self._columns[col_index:]:
                col_value = self._formatters[col_name](row, col_name)
                self.SetStringItem(index, col_index, col_value)
                item_data_map[item_id][col_index] = row.get(col_name)
                col_index += 1
            self._ApplyItemStyle(index, self.GetItemStyle(index))
            index += 1
        self._data_map = row_data_map
        self.itemDataMap = item_data_map

        if self._col_widths:
            for col, width in self._col_widths.items():
                self.SetColumnWidth(col, width)
        else:
            self.AutoSizeColumns()
        if self.GetSortState()[0] >= 0:
            self.SortListItems(*self.GetSortState())

        if selected_items: # Re-select the previously selected items
            idindx   = dict((self.GetItemData(i), i) for i in range(self.GetItemCount()))
            textindx = dict((self.GetItemText(i), i) for i in range(self.GetItemCount()))
            for item_id, item_text in selected_items:
                index = textindx.get(item_text, idindx.get(item_id))
                if index is not None: self.Select(index)


    def _RowMatchesFilter(self, row):
        """Returns whether the row dict matches the current filter."""
        result = True
        if self._filter:
            result = False
            patterns = list(map(re.escape, self._filter.split()))
            matches = set()
            for col_name, col_label in self._columns:
                col_value = self._formatters[col_name](row, col_name)
                matches.update(p for p in patterns if re.search(p, col_value, re.I | re.U))
                if len(matches) == len(patterns):
                    result = True
                    break # for col_name
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

    """SQLite keywords, reserved or context-specific."""
    KEYWORDS = list(map(text_type, sorted([
        "ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ALWAYS", "ANALYZE",
        "AND", "AS", "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN",
        "BY", "CASCADE", "CASE", "CAST", "CHECK", "COLLATE", "COLUMN", "COMMIT",
        "CONFLICT", "CONSTRAINT", "CREATE", "CROSS", "CURRENT", "CURRENT_DATE",
        "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT", "DEFERRABLE",
        "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DO", "DROP", "EACH",
        "ELSE", "END", "ESCAPE", "EXCEPT", "EXCLUDE", "EXCLUSIVE", "EXISTS",
        "EXPLAIN", "FAIL", "FILTER", "FIRST", "FOLLOWING", "FOR", "FOREIGN", "FROM",
        "FULL", "GENERATED", "GLOB", "GROUP", "GROUPS", "HAVING", "IF", "IGNORE",
        "IMMEDIATE", "IN", "INDEX", "INDEXED", "INITIALLY", "INNER", "INSERT",
        "INSTEAD", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "KEY", "LAST",
        "LEFT", "LIKE", "LIMIT", "MATCH", "MATERIALIZED", "NATURAL", "NO", "NOT",
        "NOTHING", "NOTNULL", "NULL", "NULLS", "OF", "OFFSET", "ON", "OR", "ORDER",
        "OTHERS", "OUTER", "OVER", "PARTITION", "PLAN", "PRAGMA", "PRECEDING",
        "PRIMARY", "QUERY", "RAISE", "RANGE", "RECURSIVE", "REFERENCES", "REGEXP",
        "REINDEX", "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RETURNING", "RIGHT",
        "ROLLBACK", "ROW", "ROWS", "SAVEPOINT", "SELECT", "SET", "TABLE", "TEMP",
        "TEMPORARY", "THEN", "TIES", "TO", "TRANSACTION", "TRIGGER", "UNBOUNDED",
        "UNION", "UNIQUE", "UPDATE", "USING", "VACUUM", "VALUES", "VIEW", "VIRTUAL",
        "WHEN", "WHERE", "WINDOW", "WITH", "WITHOUT",
        "BINARY", "NOCASE", "ROWID", "RTRIM", "STRICT", # Keywords only in some context
    ])))
    """SQLite data types."""
    TYPEWORDS = list(map(text_type, sorted([
        "ANY",
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
        self.linenumbers     = kwargs.pop("linenumbers", False)
        self.wordwrap        = kwargs.pop("wordwrap", True)

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
        self.last_change = time.time() # Timestamp of last text change
        self.scrollwidth_interval = 0  # Milliseconds to wait before updating scroll width
        self.scrollwidth_timer = None  # wx.Timer for updating scroll width on delay

        self.SetLexer(wx.stc.STC_LEX_SQL)
        self.SetMarginCount(1)
        self.SetMarginCursor(0, wx.stc.STC_CURSORARROW)
        self.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(0, 25) if self.linenumbers else None
        self.SetMarginWidth(1, 0) # Get rid of marker margin
        self.SetTabWidth(4)
        # Keywords must be lowercase, required by StyledTextCtrl
        self.SetKeyWords(0, u" ".join(self.KEYWORDS + self.TYPEWORDS).lower())
        self.AutoCompStops(self.AUTOCOMP_STOPS)
        self.SetWrapMode(wx.stc.STC_WRAP_WORD if self.wordwrap else wx.stc.STC_WRAP_NONE)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(True)
        self.AutoCompSetIgnoreCase(True)
        self.SetScrollWidthTracking(True) # Ensures scroll width is never less than required
        self.UpdateScrollWidth()

        self.SetStyleSpecs()

        self.Bind(wx.EVT_KEY_DOWN,           self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,          self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnKillFocus)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,       self.OnZoom)
        self.Bind(wx.stc.EVT_STC_CHANGE,     self.OnChange)
        if self.caretline_focus: self.SetCaretLineVisible(False)
        if self.traversable: self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)
        if self.wheelable is False: self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        fgcolour, bgcolour, highcolour = (ColourManager.ColourHex(x) for x in
            (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW if self.Enabled else wx.SYS_COLOUR_BTNFACE,
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
        result = super(SQLiteTextCtrl, self).Enable(enable)
        self.SetStyleSpecs()
        return result


    def LoadFile(self, filename):
        """Loads the file contents into editor, retaining undo history."""
        with open(filename, "rb") as f: text = f.read()
        if b"\r\n" in text: self.SetEOLMode(wx.stc.STC_EOL_CRLF)
        elif b"\n" in text: self.SetEOLMode(wx.stc.STC_EOL_LF)
        self.SetText(text)


    def UpdateScrollWidth(self, force=False):
        """
        Updates horizontal scroll width, delaying action by scroll width tracking interval, if any.

        @param   force  whether to update immediately, regardless of interval
        """
        if not force and self.scrollwidth_timer or self.WordWrap: return

        def action():
            if not self: return
            self.scrollwidth_timer = None
            if not TRACKING: self.SetScrollWidthTracking(True)
            self.SetScrollWidth(1)
            if self.HasFocus(): self.EnsureCaretVisible()
            if not TRACKING: wx.CallLater(1, lambda: self and self.SetScrollWidthTracking(False))

        INTERVAL, TRACKING = self.scrollwidth_interval, self.GetScrollWidthTracking()
        overtime = False if force or not INTERVAL else (time.time() - self.last_change > INTERVAL)
        self.scrollwidth_timer, _ = None, self.scrollwidth_timer and self.scrollwidth_timer.Stop()
        if force or not INTERVAL or overtime: action()
        else: self.scrollwidth_timer = wx.CallLater(INTERVAL, action)


    def GetScrollWidthTrackingInterval(self):
        """Returns milliseconds the control waits before updating scroll width after text change."""
        return self.scrollwidth_interval
    def SetScrollWidthTrackingInterval(self, interval):
        """Sets milliseconds to wait before updating scroll width after text change."""
        self.scrollwidth_interval = max(0, interval or 0)
        if self.scrollwidth_timer: self.UpdateScrollWidth(force=True)
    ScrollWidthTrackingInterval = property(GetScrollWidthTrackingInterval,
                                           SetScrollWidthTrackingInterval)


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


    def HasLineNumbers(self):
        """Returns whether control shows line numbers."""
        return self.linenumbers


    def SetLineNumbers(self, show=True):
        """Sets whether control shows line numbers."""
        self.linenumbers = bool(show)
        w = max(25, 5 + 10 * int(math.log(self.LineCount, 10))) if show else 0
        self.SetMarginWidth(0, w)
    LineNumbers = property(HasLineNumbers, SetLineNumbers)


    def HasWordWrap(self):
        """Returns whether control wraps text."""
        return self.wordwrap


    def SetWordWrap(self, wrap=True):
        """Sets whether control wraps text."""
        self.wordwrap = bool(wrap)
        self.SetWrapMode(wx.stc.STC_WRAP_WORD if wrap else wx.stc.STC_WRAP_NONE)
        if not wrap: self.UpdateScrollWidth()
    WordWrap = property(HasWordWrap, SetWordWrap)


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


    def OnChange(self, event):
        """Updates horizontal scroll width and marks change timestamp."""
        event.Skip()
        if self.ScrollWidthTracking: self.UpdateScrollWidth()
        self.last_change = time.time()


    def OnChar(self, event):
        """Goes to next/previous control on Tab/Shift+Tab,swallows Enter."""
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

    def __init__(self, ctrl):
        """Takes snapshot of current control state for do."""
        super(HexByteCommand, self).__init__(canUndo=True)
        self._ctrl   = ctrl
        self._done   = False
        self._state1 = ctrl._GetValueState()
        self._state1["Selection"] = ctrl.GetSelection()
        self._state2 = None

    def Store(self):
        """
        Takes snapshot of current control state for undo, stores command in command processor;
        updates mirror if any.
        """
        self._state2 = self._ctrl._GetValueState()
        self._state2["Selection"] = self._ctrl.GetSelection()
        self._ctrl._undoredo.Store(self)
        self._done = True
        self._UpdateMirror(self._state2)

    def Submit(self, *new_value, **kwargs):
        """
        Takes snapshot of current control state for undo, or uses value argument for new state,
        stores command in command processor and carries out do; optionally updates mirror if any.

        @param   new_value  single value for new state if not using control state
        @param   mirror     optional keyword argument to update mirror control
        """
        self._state2 = self._ctrl._GetValueState(*new_value)
        self._state2["Selection"] = (0, 0) if new_value else self._ctrl.GetSelection()
        self._ctrl._undoredo.Submit(self)
        self._done = True
        if kwargs.get("mirror"): self._UpdateMirror(self._state2)

    def Do(self, mirror=False):
        """Applies control do-action (wx.Command override)."""
        result = self._Apply(self._state2)
        if self._done and result and self._ctrl.Mirror and mirror:
            self._ctrl.Mirror.Redo()
        return result

    def Undo(self, mirror=False):
        """Applies control undo-action (wx.Command override)."""
        result = self._Apply(self._state1)
        if result and self._ctrl.Mirror and mirror:
            self._ctrl.Mirror.Undo()
        return result

    def _Apply(self, state):
        """Populates control with state, returns False if control invalid else True."""
        if not self._ctrl: return False
        line_index = self._ctrl.FirstVisibleLine
        for k in state:
            if "Selection" != k: setattr(self._ctrl, k, state[k])
        self._ctrl.Freeze()
        try:
            self._ctrl._Populate()
            self._ctrl.SetSelection(*state["Selection"])
            self._ctrl.ChooseCaretX() # Update sticky column for vertical movement
            self._ctrl.SetFirstVisibleLine(line_index)
            self._ctrl.EnsureCaretVisible()
        finally: self._ctrl.Thaw()
        return True

    def _UpdateMirror(self, state):
        """Updates linked control, if any."""
        if not self._ctrl.Mirror: return
        mirrorcmd = HexByteCommand(self._ctrl.Mirror)
        mirrorcmd._state2 = {k: state[k][:] for k in ("_bytes", "_bytes0", "Selection")}
        mirrorcmd._ctrl._undoredo.Submit(mirrorcmd)
        mirrorcmd._done = True


class HexByteCommandProcessor(wx.CommandProcessor):
    """Command processor for mirrored hex and byte controls."""

    def __init__(self, ctrl, maxCommands=-1):
        super(HexByteCommandProcessor, self).__init__(maxCommands)
        self._ctrl = ctrl

    def Redo(self, mirror=False):
        """Redoes the current command (wx.CommandProcessor override)."""
        result = super(HexByteCommandProcessor, self).Redo()
        if result and mirror and self._ctrl.Mirror:
            self._ctrl.Mirror.Redo(mirror=False)
        return result

    def Undo(self, mirror=False):
        """Undoes the last command executed (wx.CommandProcessor override)."""
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
                   wx.WXK_NUMPAD9: 9}

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
        """
        @param   addressed     show content in lines of 16 bytes with address margin (default False)
        @param   show_changes  highlight changes from value given in SetValue() (default False)
        """
        addressed = bool(kwargs.pop("addressed", False))
        show_changes = bool(kwargs.pop("show_changes", False))
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self._addressed    = addressed     # Whether margin and fixed line width
        self._show_changes = show_changes  # Whether changes from first value are highlighted
        self._fixed        = False         # Fixed-length value
        self._type         = str           # Value type: str, unicode, int, float, long
        self._bytes0       = []            # [byte or None, ]
        self._bytes        = bytearray()
        self._mirror       = None # Linked control
        self._undoredo     = HexByteCommandProcessor(self)

        self.SetStyleSpecs()
        char_width = self.TextWidth(0, "X")

        self.SetEOLMode(wx.stc.STC_EOL_LF) if addressed else None
        self.SetWrapMode(wx.stc.STC_WRAP_CHAR if addressed else wx.stc.STC_WRAP_NONE)
        self.SetCaretLineBackAlpha(20)
        self.SetCaretLineVisible(False)

        if addressed:
            self.SetMarginCount(2)
            self.SetMarginType(0, wx.stc.STC_MARGIN_TEXT)
            self.SetMarginWidth(0, char_width * 9 + 5)
            self.SetMarginWidth(1, 2)
            self.SetMarginCursor(0, wx.stc.STC_CURSORARROW)
            self.SetMargins(3, 0)
        else:
            self.SetMarginCount(0)
            self.SetMarginLeft(0)
            self.SetUseHorizontalScrollBar(False)
            self.SetUseVerticalScrollBar(False)

        self.SetOvertype(True)
        if addressed:
            self.SetUseTabs(False)
            w = char_width * self.WIDTH * 3 + self.GetMarginWidth(0) + \
                sum(max(x, 0) for x in self.GetMargins()) + \
                max(0, wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X))
            self.MinSize = self.MaxSize = w, -1
        else:
            self.MinSize = self.MaxSize = -1, 20

        self.Bind(wx.EVT_KEY_DOWN,                self.OnKeyDown)
        self.Bind(wx.EVT_CHAR_HOOK,               self.OnChar)
        self.Bind(wx.EVT_SET_FOCUS,               self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,              self.OnKillFocus)
        self.Bind(wx.EVT_MOUSE_EVENTS,            self.OnMouse)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,      self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,            self.OnZoom)
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_COPY,  self.OnCopy) \
            if hasattr(wx.stc, "EVT_STC_CLIPBOARD_COPY") else None
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_PASTE, self.OnPaste) \
            if hasattr(wx.stc, "EVT_STC_CLIPBOARD_PASTE") else None
        self.Bind(wx.stc.EVT_STC_START_DRAG,      lambda e: e.SetString(""))


    def SetStyleSpecs(self, background=None):
        """Sets STC style colours from system settings, using given background if any."""
        if not self: return
        bg_code = wx.SYS_COLOUR_WINDOW if self.Enabled else wx.SYS_COLOUR_BTNFACE
        fgcolour = ColourManager.ColourHex(wx.SYS_COLOUR_BTNTEXT)
        bgcolour = ColourManager.ColourHex(bg_code)
        textbgcolour = background or bgcolour

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, textbgcolour, fgcolour))
        self.StyleClearAll() # Apply the new default style to all styles

        self.StyleSetSpec(self.STYLE_CHANGED, "fore:%s" % self.COLOUR_CHANGED)
        self.StyleSetSpec(self.STYLE_MARGIN,  "back:%s" % bgcolour)


    def Enable(self, enable=True):
        """Enables or disables the control, updating display."""
        if self.Enabled == enable: return False
        result = super(HexTextCtrl, self).Enable(enable)
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
        elif self._type is   float:          v = struct.unpack(">d", v)[0]
        elif self._type is text_type:
            try: v = v.decode("utf-8")
            except Exception: v = v.decode("latin1")
        return v

    def SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        self._QueueEvents()
        byte_pos = self.Selection[0]
        self._SetValue(value)
        self._undoredo.ClearCommands()
        self._Populate()
        self._ApplyPositions(byte_pos)
        self.EnsureCaretVisible()

    Value = property(GetValue, SetValue)


    def GetOriginalBytes(self): return list(self._bytes0)
    OriginalBytes = property(GetOriginalBytes)


    def UpdateValue(self, value, mirror=False):
        """Update current content as typed value (string or number)."""
        self._QueueEvents()
        byte_pos = self.Selection[0]
        HexByteCommand(self).Submit(value, mirror=mirror)
        self._ApplyPositions(byte_pos)
        self.EnsureCaretVisible()


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
        return self._PosOut(sself.CurrentPos)
    def SetCurrentPos(self, caret):
        return super(HexTextCtrl, self).SetCurrentPos(self._PosIn(caret))
    CurrentPos = property(GetCurrentPos, SetCurrentPos)


    def GetSelection(self):
        """Returns the current byte selection span, as (from_, to_)."""
        text_from, text_to = super(HexTextCtrl, self).GetSelection()
        adjust = 1 if text_from != text_to else 0 # Ensure selection
        byte_from, byte_to = self._PosOut(text_from), self._PosOut(text_to + adjust)
        return byte_from, byte_to
    def SetSelection(self, from_, to_):
        """Selects the bytes from first position up to but not including second."""
        adjust = -1 if from_ != to_ else 0 # Pull back to omit trailing space
        return super(HexTextCtrl, self).SetSelection(self._PosIn(from_), self._PosIn(to_) + adjust)
    Selection = property(GetSelection)


    def GetShowChanges(self):
        """Returns whether changes from value given in SetValue() are highlighted."""
        return self._show_changes
    def SetShowChanges(self, show_changes):
        """Sets whether changes from value given in SetValue() are highlighted; restyles text."""
        self._show_changes = bool(show_changes)
        self._Restyle()
    ShowChanges = property(GetShowChanges, SetShowChanges)


    def GetHex(self):
        """Returns current content as hex-encoded string with spaces and newlines."""
        return super(HexTextCtrl, self).Text


    def InsertInto(self, text):
        """Inserts string at current insertion point, interpreted as hex text if possible."""
        pos = self.InsertionPoint
        if self._fixed and not self._bytes: return # NULL number
        if pos == self.GetLastPosition() and self._fixed: pass

        self._QueueEvents()

        cmd = HexByteCommand(self)
        selection = self.GetSelection()
        if selection[0] != selection[1] and not self._fixed:
            del self._bytes [selection[0]:selection[1]]
            del self._bytes0[selection[0]:selection[1]]

        value = self._AdaptValue(text)
        try: v = bytearray.fromhex(value.decode("latin1")) # Interpret as hex text if possible
        except Exception: v = bytearray(value) # Fall back to raw bytes
        bpos = pos // 3 + (pos == self.GetLastPosition())
        maxlen = min(len(v), len(self._bytes) - bpos) if self._fixed else len(v)
        v = v[:maxlen]

        if self._show_changes and bpos + maxlen > len(self._bytes):
            self._bytes0.extend([None] * (bpos + maxlen - len(self._bytes)))
        if self.Overtype:
            self._bytes[bpos:bpos + maxlen] = v
        else:
            self._bytes [bpos:bpos] = v
            if self._show_changes:
                self._bytes0[bpos:bpos] = [None] * len(v)

        self._Populate()
        self.SetSelection(selection[0] + len(v), selection[0] + len(v))
        self.EnsureCaretVisible()
        cmd.Store()


    def Replace(self, from_, to_, value):
        """
        Replaces the bytes starting at the first position up to (but not including)
        the byte at the last position with the given value.
        """
        if self._fixed and not self._bytes: return # NULL number
        if from_ >= len(self._bytes): return # Out of bounds

        self._QueueEvents()

        cmd = HexByteCommand(self)
        v = bytearray(self._AdaptValue(value))
        to_ = min(to_, len(self._bytes))
        overflow = len(v) - (to_ - from_)

        if self._fixed:
            if overflow > 0: # Erase overflow
                v = v[:len(self._bytes) - from_]
            elif overflow < 0: # Pad underflow with 0-bytes
                v += bytearray([0] * min(len(self._bytes) - from_, abs(overflow)))
        elif self._show_changes:
            if overflow > 0:
                self._bytes0[to_:to_] = [None] * overflow
            elif overflow < 0:
                del self._bytes0[to_ + overflow:to_]
        self._bytes[from_:to_] = v

        self._Populate()
        self.SetSelection(to_, to_)
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


    def MirrorSelection(self):
        """Sets selection or cursor position from mirrored control, if any."""
        if not self._mirror: return

        byte_selection = self._mirror.Selection
        if byte_selection[0] != byte_selection[1]:
            self.SetSelection(*byte_selection)
            return

        byte_pos = byte_selection[0]
        text_pos_shift = 0

        if self._addressed:
            mirrorbase = super(type(self._mirror), self._mirror)
            mirror_text_pos = mirrorbase.CurrentPos
            line_start = mirrorbase.PositionFromLine(mirrorbase.LineFromPosition(mirror_text_pos))
            mirror_pos_in_line = mirror_text_pos - line_start
            if mirror_pos_in_line >= self._mirror.WIDTH:  # At line end
                text_pos_shift = -1 # Move back from line to previous line end

        self._ApplyPositions(byte_pos, text_pos_shift=text_pos_shift)


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


    def OnCopy(self, event):
        """Handler for clipboard copy event, updates bytes and fixes content if cutting."""

        def fix_content(cmd, byte_selection, line_index):
            if not self or not self.GetSelectionEmpty(): return

            if not self._fixed:
                del self._bytes[byte_selection[0]:byte_selection[1]]
                if self._show_changes:
                    del self._bytes0[byte_selection[0]:byte_selection[1]]
            self._Populate()
            self._ApplyPositions(byte_selection[0])
            self.SetFirstVisibleLine(line_index)
            cmd.Store()

        cmd = HexByteCommand(self)
        wx.CallAfter(fix_content, cmd, self.Selection, self.FirstVisibleLine)
        self._QueueEvents()


    def OnPaste(self, event):
        """Handles paste event."""
        text = event.String
        event.SetString("") # Cancel default paste
        self.InsertInto(text)


    def OnChar(self, event):
        """Handler for keypress, performs undo-redo-paste; cancels event if not acceptable key."""

        if event.CmdDown() and not event.AltDown() and not event.ShiftDown() \
        and ord("Z") == event.KeyCode:
            self.Undo(mirror=True)
            return

        if event.CmdDown() and not event.AltDown() and (not event.ShiftDown() \
        and ord("Y") == event.KeyCode) or (event.ShiftDown() and ord("Z") == event.KeyCode):
            self.Redo(mirror=True)
            return

        if event.CmdDown() and not event.AltDown() and not event.ShiftDown() \
        and event.KeyCode == ord("X"): # Cut
            if self.GetSelectionEmpty(): pass
            elif hasattr(wx.stc, "EVT_STC_CLIPBOARD_COPY"):
                event.Skip() # Allow default handling
            else:
                byte_pos1, byte_pos2 = self.Selection
                content = bytes(self._bytes[byte_pos1:byte_pos2])
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(content))
                    wx.TheClipboard.Close()
                if not self._fixed:
                    self.InsertInto("")
                elif sys.version_info < (3, ): # Uncancelable in Py2
                    wx.CallAfter(self._Populate)

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

        if event.HasModifiers():
            event.Skip()
        else:
            is_enter_or_space = event.KeyCode in KEYS.ENTER + KEYS.SPACE
            is_hex = unichr(event.UnicodeKey) in self.MASK
            is_numpad = event.KeyCode in self.NUMPAD_NUMS
            is_cmd_or_nav = event.KeyCode in KEYS.NAVIGATION + KEYS.COMMAND
            if not is_enter_or_space and (is_numpad or is_hex or is_cmd_or_nav):
                event.Skip()


    def OnKeyDown(self, event):
        """Handler for key down, performs navigation and text insertion."""
        self._QueueEvents()

        if event.KeyCode in KEYS.LEFT + KEYS.RIGHT:
            self._OnKeyDownLeftRight(event)

        elif event.KeyCode in KEYS.UP + KEYS.DOWN + KEYS.PAGEUP + KEYS.PAGEDOWN:
            if self._addressed:
                self._OnKeyDownVertical(event)

        elif event.KeyCode in KEYS.END and not event.CmdDown():
            if event.ShiftDown():
                self.LineEndExtend()
            else:
                text_pos2 = self.GetLineEndPosition(self.CurrentLine)
                super(HexTextCtrl, self).SetSelection(text_pos2, text_pos2)
            if not self._addressed:
                self.EnsureCaretVisible()

        elif event.KeyCode in KEYS.DELETE + KEYS.BACKSPACE:
            self._OnKeyDownDeleteBackspace(event)

        elif not event.HasModifiers() \
        and (unichr(event.UnicodeKey) in self.MASK or event.KeyCode in self.NUMPAD_NUMS) \
        and (not event.ShiftDown() or unichr(event.UnicodeKey) not in string.digits):
            self._OnKeyDownHex(event)

        elif event.KeyCode in KEYS.INSERT and not event.HasAnyModifiers():
            if not self._fixed: event.Skip() # Disallow changing overtype if length fixed

        elif event.KeyCode in KEYS.TAB:
            if not self._mirror: # Allow normal tab navigation if stand-alone control
                direction = wx.NavigationKeyEvent.IsBackward if event.ShiftDown() \
                            else wx.NavigationKeyEvent.IsForward
                self.Parent.NavigateIn(direction)

        else:
            event.Skip()


    def OnMouse(self, event):
        """Handler for mouse event, moves caret to word boundary."""
        event.Skip()
        after_mouse_click = event.LeftUp() or event.RightUp()
        if after_mouse_click or event.LinesPerAction:
            self._QueueEvents(after_mouse_click)


    def _OnKeyDownLeftRight(self, event):
        """Handler for pressing left/right arrow keys."""
        if not self._bytes: return

        sself = super(HexTextCtrl, self)
        direction = -1 if event.KeyCode in KEYS.LEFT else 1
        pos_in_line = self._GetPositionInLine()
        pos_in_triplet = pos_in_line % 3
        has_selection = not self.GetSelectionEmpty()
        is_beyond_content = (sself.SelectionEnd == self.GetLastPosition())
        is_beyond_line_content = self._addressed and pos_in_line >= self.WIDTH * 3 - 1
        byte_selection = self.GetSelection()

        if event.ShiftDown(): # Select text
            active_side = 1 if sself.Anchor <= sself.CurrentPos else 0 # Left-to-right vs reverse
            if not has_selection:
                active_side = 0 if direction < 0 else 1

            byte_selection2 = list(byte_selection)
            byte_selection2[active_side] += direction
            if not has_selection and direction < 0:
                if pos_in_triplet == 1: # At second digit of byte: select this only
                    byte_selection2 = [byte_selection[0], byte_selection[0] + 1]

            anchor2, currentpos2 = byte_selection2[::1 if active_side == 1 else -1]
            self._ApplyPositions(currentpos2, anchor2)
        else: # Move cursor
            byte_pos = self.CurrentPos
            adjust = direction
            if has_selection:
                if direction < 0:
                    byte_pos = byte_selection[0] # Go back to selection front
                else: # direction > 0
                    byte_pos = byte_selection[1] # Go forward to selection end
                pos_in_line = (byte_pos % self.WIDTH if self._addressed else byte_pos) * 3
                pos_in_triplet = 0
                is_beyond_content = False
                is_beyond_line_content = pos_in_line >= self.WIDTH * 3 - 1
                adjust = 0

            byte_pos2 = byte_pos + direction
            text_pos_shift = 0

            if pos_in_triplet == 1 and direction < 0: # At second digit of byte: remain at byte
                adjust = 0
            elif is_beyond_line_content and direction > 0: # At line end: already on next byte
                adjust = 0
            elif direction < 0 and byte_selection[1] - byte_selection[0] == 1: # Single byte selected
                if is_beyond_content or is_beyond_line_content: # Shift to last byte in line
                    adjust = -1
                elif sself.Anchor <= sself.CurrentPos: # Left-to-right selection
                    adjust = 0 # Remain at single selected byte

            if event.CmdDown(): # Allow single digit movement as Ctrl-Left or Ctrl-Right
                if direction > 0:
                    if pos_in_triplet == 0:
                        adjust = 0 # Remain at current byte
                        text_pos_shift = 1 # To second digit in current byte
                else: # direction < 0
                    if pos_in_triplet == 0:
                        adjust = direction
                        text_pos_shift = 1 # To second digit in previous byte
                    elif is_beyond_content or is_beyond_line_content:
                        text_pos_shift = 1 # To second digit in last byte of line

            byte_pos2 = byte_pos + adjust
            self._ApplyPositions(byte_pos2, text_pos_shift=text_pos_shift)

        self.EnsureCaretVisible()


    def _OnKeyDownVertical(self, event):
        """Handler for pressing up/down or pageup/pagedown keys."""
        if not self._bytes or not self._addressed: return

        STEP = self.WIDTH if event.KeyCode in KEYS.UP + KEYS.DOWN else \
               self.WIDTH * max(1, self.LinesOnScreen()) # PAGEUP / PAGEDOWN
        sself = super(HexTextCtrl, self)
        direction = -1 if event.KeyCode in KEYS.UP + KEYS.PAGEUP else 1
        line_index = self.CurrentLine
        pos_in_line = self._GetPositionInLine()
        pos_in_triplet = pos_in_line % 3
        has_selection = not self.GetSelectionEmpty()
        is_beyond_content = (sself.SelectionEnd == self.GetLastPosition())
        is_beyond_line_content = self._addressed and pos_in_line >= self.WIDTH * 3 - 1
        byte_selection = self.GetSelection()

        if event.ShiftDown(): # Select text
            active_side = 1 if sself.Anchor <= sself.CurrentPos else 0 # Left-to-right vs reverse
            if not has_selection:
                active_side = 0 if direction < 0 else 1

            byte_selection2 = list(byte_selection)
            byte_selection2[active_side] += direction * STEP
            if not has_selection and direction < 0:
                if pos_in_triplet == 1: # At second digit of byte: select this additionally
                    byte_selection2[1] += 1

            anchor2, currentpos2 = byte_selection2[::1 if active_side == 1 else -1]
            self._ApplyPositions(currentpos2, anchor2)
        else: # Move cursor
            byte_pos = self.CurrentPos
            if has_selection:
                pos_in_line = (byte_pos % self.WIDTH) * 3
                pos_in_triplet = 0
                is_beyond_content = False
                is_beyond_line_content = pos_in_line >= self.WIDTH * 3 - 1
                line_index = self.LineFromPosition(byte_pos * 3)

            byte_pos2 = byte_pos + direction * STEP
            text_pos_shift = 0

            if pos_in_triplet == 1:
                text_pos_shift = 1 # Push forward one char to remain on byte second digit

            line_index2 = line_index + direction * STEP // self.WIDTH
            if line_index2 < 0 or line_index2 >= len(self._bytes) // self.WIDTH: # Over edge
                line_index2 = max(0, min(byte_pos2, len(self._bytes) - 1)) // self.WIDTH
                byte_pos2 = line_index2 * self.WIDTH + pos_in_line // 3 # Keep in same column
                if is_beyond_content or is_beyond_line_content:
                    byte_pos2 += 1 # Move to very last byte, or first byte in next line
                if is_beyond_line_content:
                    text_pos_shift = -1 # Pull back one char to remain at end of line
            elif is_beyond_line_content:
                if direction < 0 or direction > 0 and line_index2 < self.LineCount - 1:
                    text_pos_shift = -1 # Pull back one char to remain at end of line

            self._ApplyPositions(byte_pos2, text_pos_shift=text_pos_shift)

        if event.KeyCode in KEYS.PAGEUP + KEYS.PAGEDOWN:
            self.ScrollPages(direction)
        else:
            self.EnsureCaretVisible()


    def _OnKeyDownDeleteBackspace(self, event):
        """Handler for pressing Delete or Backspace."""
        if self._fixed or not self._bytes: return

        cmd = HexByteCommand(self)
        selection = self.GetSelection()
        if selection[0] != selection[1]:
            del self._bytes [selection[0]:selection[1]]
            if self._show_changes:
                del self._bytes0[selection[0]:selection[1]]
            self.SetSelection(selection[0], selection[0])
            cmd.Submit(mirror=True)
            return

        sself = super(HexTextCtrl, self)
        direction = -1 if event.KeyCode in KEYS.BACKSPACE else 1
        text_pos = sself.CurrentPos
        pos_in_line = self._GetPositionInLine(text_pos)
        line_index = self.LineFromPosition(text_pos)
        is_beyond_content = (sself.SelectionEnd == self.GetLastPosition())

        if text_pos == 0 and direction < 0 or is_beyond_content and direction > 0:
            return # Backspacing at start or deleting at end

        byte_pos, pos_in_triplet = self.CurrentPos, pos_in_line % 3
        if is_beyond_content:
            byte_pos = min(byte_pos, len(self._bytes) - 1)
            pos_in_triplet = 0
        elif direction < 0 and pos_in_triplet == 0:
            byte_pos -= 1 # Backspacing over previous byte
        elif self._addressed and pos_in_line >= self.WIDTH * 3 - 1:
            if direction < 0: # Backspace at line end: apply on last byte of cursor line
                byte_pos -= 1
            pos_in_triplet = 0
        del self._bytes[byte_pos]
        if self._show_changes:
            del self._bytes0[byte_pos]

        needs_reflow = line_index < self.LineCount - 1 or (pos_in_line == 0 and direction < 0)
        if needs_reflow:
            initial_visible_line = self.FirstVisibleLine
            self._Populate()
            self.SetFirstVisibleLine(initial_visible_line)
            text_pos2 = self._PosIn(byte_pos)
            sself.SetEmptySelection(text_pos2)
        else: # Last line and not backspacing from first byte: change in-place
            remove_from = text_pos
            if pos_in_triplet:
                remove_from -= 1 # Include first digit of byte
            elif direction < 0 and self.GetSelectionEmpty(): # Drop preceding triple
                remove_from -= 3
            if direction > 0 and byte_pos >= len(self._bytes) - 1:
                remove_from -= 1 # Drop trailing space
            remove_until = min(sself.Length, remove_from + 3)
            sself.Replace(remove_from, remove_until, "")
            self._Remargin()
        self.EnsureCaretVisible()
        cmd.Store()


    def _OnKeyDownHex(self, event):
        """Handler for pressing hex input keys."""
        if self._fixed and not self._bytes: return # NULL value

        cmd = HexByteCommand(self)

        selection = self.GetSelection() # Byte positions
        has_selection = (selection[0] != selection[1])
        is_replacing_selection = has_selection and not self._fixed
        if is_replacing_selection:
            del self._bytes [selection[0]:selection[1]]
            if self._show_changes:
                del self._bytes0[selection[0]:selection[1]]

        sself = super(HexTextCtrl, self)
        byte_pos = self.CurrentPos
        text_pos = sself.CurrentPos
        is_beyond_content = (sself.SelectionEnd == self.GetLastPosition())
        pos_in_triplet = 0 # Position index in byte triplet "XY "
        if self._fixed: # Ensure valid start position
            if has_selection or is_beyond_content:
                byte_pos = selection[0] if has_selection else len(self._bytes) - 1
                text_pos = byte_pos * 3 # Ensure position from first digit of byte
            else:
                pos_in_triplet = self._GetPositionInLine(text_pos) % 3
            is_beyond_content = False
        elif is_replacing_selection: # Reset positions to former selection start
            byte_pos = selection[0]
            text_pos = byte_pos * 3
        else:
            pos_in_line = self._GetPositionInLine(text_pos)
            pos_in_triplet = self._GetPositionInLine(text_pos) % 3

        if is_beyond_content: # At very end of free content: add new byte
            if self._bytes:
                byte_pos, text_pos = len(self._bytes), len(self._bytes) * 3
            self._bytes.append(0)
            if self._show_changes: self._bytes0.append(None)
            pos_in_triplet = 0
        elif pos_in_triplet != 1: # At first digit of byte or at addressed line end
            text_pos = byte_pos * 3 # Ensure text pos from byte actual start pos
            pos_in_triplet = 0 # Set text pos to byte actual start pos
            if not self.Overtype: # Insert new byte at current position
                self._bytes.insert(byte_pos, 0)
                if self._show_changes: self._bytes0.insert(byte_pos, None)
        byte_pos = min(byte_pos, len(self._bytes) - 1)

        byte = self._bytes[byte_pos]
        input_number = self.NUMPAD_NUMS[event.KeyCode] if event.KeyCode in self.NUMPAD_NUMS \
                       else int(unichr(event.UnicodeKey), 16)
        if pos_in_triplet == 0: # Write first digit in byte
            digit1, digit2 = input_number, byte & 0x0F
        else: # Write second digit in byte
            digit1, digit2 = byte >> 4, input_number
        byte = digit1 * 16 + digit2
        self._bytes[byte_pos] = byte

        is_inserting_new = is_beyond_content or (pos_in_triplet == 0 and not self.Overtype)
        if is_replacing_selection or is_inserting_new: # Needs reflow: repopulate everything
            initial_visible_line = self.FirstVisibleLine
            self._Populate()
            self.SetFirstVisibleLine(initial_visible_line)
        else: # Overwrite current text with new value for byte
            byte_start_pos = text_pos - pos_in_triplet
            sself.Replace(byte_start_pos, byte_start_pos + 2, "%02X" % byte)
            if self._show_changes:
                style = self.STYLE_CHANGED
                if self._bytes[byte_pos] == self._bytes0[byte_pos]: style = 0
                self.StartStyling(byte_start_pos)
                self.SetStyling(2, style)
        text_pos2 = text_pos + 1 + bool(pos_in_triplet) # Go to next digit, possibly next byte
        self.GotoPos(text_pos2)
        cmd.Store()


    def _AdaptValue(self, value):
        """Returns the value as bytes() for hex representation."""
        is_long, is_int = is_fixed_long(value), isinstance(value, int) and is_fixed(value)
        if is_long:                    v = struct.pack(">q", value)
        elif is_int:                   v = struct.pack(">l", value)
        elif isinstance(value, float): v = struct.pack(">d", value)
        elif value is None:            v = b""
        elif isinstance(value, text_type):
            try: v = value.encode("latin1")
            except Exception: v = value.encode("utf-8")
        else: v = value
        if not isinstance(v, bytes):
            v = str(v).encode("latin1")
        return v


    def _ApplyPositions(self, currentpos, anchor=None, text_pos_shift=0):
        """
        Sets new cursor position or new selection, ensuring proper edge indexes in text.

        @param   currentpos      cursor byte position to set
        @param   anchor          selection anchor byte position to set if not same as cursor
        @param   text_pos_shift  number of characters to shift final cursor position by
        """
        sself = super(HexTextCtrl, self)
        if anchor is None: anchor = currentpos
        text_selection = [self._PosIn(x) for x in (anchor, currentpos)]
        pos_in_triplets = [self._GetPositionInLine(x) % 3 for x in text_selection]
        if currentpos == anchor: # No selection
            if pos_in_triplets[0] == 2: # At space between bytes: move forward to next byte
                text_selection = [text_selection[0] + 1] * 2
            if text_pos_shift:
                text_selection = [x + text_pos_shift for x in text_selection]
            sself.SetEmptySelection(text_selection[0])
            return

        anchor_side, caret_side = (0, 1)
        if anchor <= currentpos: # Selection from left to right
            if pos_in_triplets[anchor_side] == 1: # At second digit of byte: back to first
                text_selection[anchor_side] -= 1
            elif pos_in_triplets[anchor_side] == 2: # At space beyond byte: forward to next byte
                text_selection[anchor_side] += 1
            if pos_in_triplets[caret_side] == 0: # At start of next byte: back to end of previous
                text_selection[caret_side] -= 1
            elif pos_in_triplets[caret_side] == 1: # At second digit of byte: forward to whole byte
                text_selection[caret_side] += 1
        else:
            if pos_in_triplets[anchor_side] == 0: # At start of next byte: back to end of previous
                text_selection[anchor_side] -= 1
            elif pos_in_triplets[anchor_side] == 1: # At second digit of byte: forward to whole byte
                text_selection[anchor_side] += 1
            if pos_in_triplets[caret_side] == 1: # At second digit of byte: back to whole byte
                text_selection[caret_side] -= 1
            elif pos_in_triplets[caret_side] == 2: # At space beyond byte: forward to next byte
                text_selection[caret_side] += 1
        text_selection = [max(0, min(x, len(self._bytes) * 3)) for x in text_selection]

        if anchor <= currentpos: # Selection from left to right
            sself.SetSelection(*text_selection)
        else:
            sself.SetAnchor(text_selection[anchor_side])
            sself.SetCurrentPos(text_selection[caret_side])


    def _PosIn(self, byte_pos):
        """Returns text position for byte position."""
        return byte_pos * 3
    def _PosOut(self, text_pos):
        """Returns byte position for text position."""
        pos_in_line = self._GetPositionInLine(text_pos)
        adjust = 0
        if text_pos >= self.GetLastPosition() \
        or self._addressed and pos_in_line >= self.WIDTH * 3 - 1:
            adjust = 1 # Caret can be at line end: interpret as being on next byte
        return (text_pos + adjust) // 3


    def _Populate(self):
        """Sets current content to widget."""
        lines, hexlify = [], binascii.hexlify
        if sys.version_info < (3, 8): # Support sep-parameter
            hexlify = lambda data, sep: sep.join(b"%02X" % c for c in data)
        if self._addressed:
            for i in range(0, len(self._bytes), self.WIDTH):
                lines.append(hexlify(self._bytes[i:i + self.WIDTH], b" ").decode("latin1").upper())
        else:
            lines.append(hexlify(self._bytes, b" ").decode("latin1").upper())
        super(HexTextCtrl, self).ChangeValue("\n".join(lines))
        self._Restyle()
        self._Remargin()
        if self._fixed and not self.Overtype: self.SetOvertype(True)


    def _Restyle(self):
        """Restyles current content according to changed state."""
        if not self._show_changes: return
        eventmask0, _ = self.GetModEventMask(), self.SetModEventMask(0)
        try:
            self.StartStyling(0)
            self.SetStyling(super(HexTextCtrl, self).Length, 0)
            ranges, currange = [], None
            for i, c in enumerate(self._bytes):
                if c == self._bytes0[i]: currange = None
                elif currange:           currange[-1] += 1
                else:                    currange = [i, 1]; ranges.append(currange)
            for i, length in ranges:
                self.StartStyling(i * 3)
                self.SetStyling(length * 3 - 1, self.STYLE_CHANGED)
        finally: self.SetModEventMask(eventmask0)


    def _Remargin(self):
        """Rebuilds hex address margin."""
        if not self._addressed: return
        eventmask0, _ = self.GetModEventMask(), self.SetModEventMask(0)
        try:
            sself = super(HexTextCtrl, self)
            self.MarginTextClearAll()
            for line in range(self.LineCount):
                self.MarginSetStyle(line, self.STYLE_MARGIN)
                self.MarginSetText (line, " %08X " % line)
        finally: self.SetModEventMask(eventmask0)


    def _GetPositionInLine(self, pos=None):
        """Returns position in line for global text position; current position if not given."""
        if pos is None: pos = super(HexTextCtrl, self).CurrentPos
        line_start_pos = self.PositionFromLine(self.LineFromPosition(pos)) if self._addressed else 0
        return pos - line_start_pos


    def _GetValueState(self, *value):
        """Returns value type and data dict, from current content or given value."""
        if not value:
            return {"_bytes": self._bytes[:], "_bytes0": self._bytes0[:],
                    "_fixed": self._fixed, "_type": self._type}

        value = value[0]
        if isinstance(value, bool): value = int(value)
        bytesvalue = self._AdaptValue(value)
        bytes0 = self._bytes0[:]
        diff = len(bytesvalue) - len(bytes0)
        if diff > 0:   bytes0.extend([None] * diff)
        elif diff < 0: del bytes0[abs(diff):]

        state = {
            "_bytes":  bytearray(bytesvalue),
            "_bytes0": bytes0,
            "_fixed":  is_fixed(value) or value is None,
            "_type":   type(value) if is_fixed(value) or isinstance(value, string_types) else str,
        }
        return state


    def _SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        if isinstance(value, bool): value = int(value)
        v = self._AdaptValue(value)

        self._type     = type(value) if is_fixed(value) or isinstance(value, string_types) else str
        self._fixed    = is_fixed(value) or value is None
        self._bytes[:] = v
        if self._show_changes:
            self._bytes0[:] = [x if isinstance(x, int) else ord(x) for x in v]
        if self._fixed and not self.Overtype: self.SetOvertype(True)


    def _QueueEvents(self, after_mouse_click=False):
        """Raises CaretPositionEvent or LinePositionEvent or SelectionEvent if changed after."""
        sself = super(HexTextCtrl, self)
        text_selection1 = sself.GetSelection()
        byte_pos1, firstline1 = self.CurrentPos, self.FirstVisibleLine

        def adjust_selection(): # Ensures valid position or byte selection
            text_selection2, notselected2 = sself.GetSelection(), self.GetSelectionEmpty()
            new_selection = list(text_selection2)
            left_pos_in_line, right_pos_in_line = map(self._GetPositionInLine, text_selection2)
            pos_in_left_triplet = left_pos_in_line % 3
            pos_in_right_triplet = right_pos_in_line % 3

            starts_beyond_content = (left_pos_in_line >= self.WIDTH * 3 - 1)
            any_byte_selected = (text_selection2[1] - text_selection2[0]) > 1
            if self._addressed and starts_beyond_content and not any_byte_selected:
                if sself.Anchor < sself.CurrentPos and pos_in_right_triplet == 0:
                    # Left to right over linefeed: move to first byte of next line
                    new_pos = self._PosIn(self.CurrentPos)
                else: # Move to line end
                    new_pos = text_selection2[0] - max(0, pos_in_left_triplet - 2)
                new_selection = [new_pos] * 2 # Set to line end
            elif notselected2 and pos_in_left_triplet == pos_in_left_triplet == 1:
                pass # At second digit of byte: allow
            elif pos_in_left_triplet == 1: # At second digit of byte
                new_selection[0] -= 1 # Move back to first digit
            elif pos_in_left_triplet == 2: # At space between bytes
                new_selection[0] += 1 # Move to first digit of next byte

            if notselected2:
                new_selection[1] = new_selection[0]
            elif new_selection[0] != new_selection[1]:
                if pos_in_right_triplet == 0: # At first digit of next byte
                    new_selection[1] -= 1 # Move back before trailing space
                elif pos_in_right_triplet == 1: # At second digit of byte
                    new_selection[1] += 1 # Move forward to byte end

            if new_selection != list(text_selection2):
                if new_selection[0] == new_selection[1]:
                    sself.SetEmptySelection(new_selection[0])
                else:
                    step = 1 if sself.Anchor < sself.CurrentPos else -1 # Left-to-right vs reverse
                    new_anchor, new_currentpos = new_selection[::step]
                    sself.SetAnchor(new_anchor)
                    sself.SetCurrentPos(new_currentpos)

        def after():
            if not self: return

            if after_mouse_click: adjust_selection()

            text_selection2 = sself.GetSelection()
            byte_pos2, firstline2 = self.CurrentPos, self.FirstVisibleLine
            if after_mouse_click or byte_pos1 != byte_pos2: # Notify of new position
                evt = CaretPositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(byte_pos2)
                wx.PostEvent(self, evt)
            elif firstline1 != firstline2: # Notify of scroll change
                evt = LinePositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(firstline2)
                wx.PostEvent(self, evt)
            if after_mouse_click or text_selection1 != text_selection2: # Notify of selection change
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
        """
        @param   show_changes  highlight changes from value given in SetValue() (default False)
        """
        show_changes = bool(kwargs.pop("show_changes", False))
        wx.stc.StyledTextCtrl.__init__(self, *args, **kwargs)

        self._show_changes = show_changes  # Whether changes from first value are highlighted
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
        self.SetMarginWidth(1, 0) # Py2 workaround

        self.SetStyleSpecs()
        self.SetOvertype(True)
        self.SetUseTabs(False)
        w = self.TextWidth(0, "X") * (self.WIDTH + 2) + max(0, wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X))
        self.Size = self.MinSize = self.MaxSize = w, -1

        self.Bind(wx.EVT_CHAR,                    self.OnChar)
        self.Bind(wx.EVT_KEY_DOWN,                self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS,               self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS,              self.OnKillFocus)
        self.Bind(wx.EVT_MOUSE_EVENTS,            self.OnMouse)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,      self.OnSysColourChange)
        self.Bind(wx.stc.EVT_STC_ZOOM,            self.OnZoom)
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_COPY,  self.OnCopy) \
            if hasattr(wx.stc, "EVT_STC_CLIPBOARD_COPY") else None
        self.Bind(wx.stc.EVT_STC_CLIPBOARD_PASTE, self.OnPaste) \
            if hasattr(wx.stc, "EVT_STC_CLIPBOARD_PASTE") else None
        self.Bind(wx.stc.EVT_STC_START_DRAG,      lambda e: e.SetString(""))


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        if not self: return
        fgcolour, bgcolour = (ColourManager.ColourHex(x) for x in
            (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW if self.Enabled else wx.SYS_COLOUR_BTNFACE)
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
        result = super(ByteTextCtrl, self).Enable(enable)
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
        elif self._type is   float:          v = struct.unpack(">d", v)[0]
        elif self._type is text_type:
            try: v = v.decode("utf-8")
            except Exception: v = v.decode("latin1")
        return v

    def SetValue(self, value):
        """Set current content as typed value (string or number), clears undo."""
        self.Freeze()
        try:
            text_pos = self.GetSelection()[0]
            self._SetValue(value)
            self._Populate()
            self._undoredo.ClearCommands()
            self.GotoPos(text_pos)
            self.ChooseCaretX() # Update sticky column for vertical movement
        finally: self.Thaw()

    Value = property(GetValue, SetValue)


    def GetOriginalBytes(self): return list(self._bytes0)
    OriginalBytes = property(GetOriginalBytes)


    def UpdateValue(self, value, mirror=False):
        """Update current content as typed value (string or number), retaining history."""
        self.Freeze()
        try:
            text_pos = self.GetSelection()[0]
            HexByteCommand(self).Submit(value, mirror=mirror)
            self.GotoPos(text_pos)
            self.ChooseCaretX() # Update sticky column for vertical movement
        finally: self.Thaw()


    def GetAnchor(self):
        return self._PosOut(super(ByteTextCtrl, self).Anchor)
    def SetAnchor(self, anchor):
        super(ByteTextCtrl, self).SetAnchor(self._PosIn(anchor))
    Anchor = property(GetAnchor, SetAnchor)


    def GetCurrentPos(self):
        return self._PosOut(super(ByteTextCtrl, self).CurrentPos)
    def SetCurrentPos(self, caret):
        super(ByteTextCtrl, self).SetCurrentPos(self._PosIn(caret))
        self.ChooseCaretX() # Update sticky column for vertical movement
    CurrentPos = property(GetCurrentPos, SetCurrentPos)


    def GetSelection(self):
        """Returns the current byte selection span, as (from_, to_)."""
        from_, to_ = super(ByteTextCtrl, self).GetSelection()
        return self._PosOut(from_), self._PosOut(to_)
    def SetSelection(self, from_, to_):
        """Sets the current byte selection span."""
        text_from, text_to = self._PosIn(from_), self._PosIn(to_)
        if from_ != to_:
            if to_ and not to_ % self.WIDTH: # Until line end: deselect linefeed
                text_to -= 1
        super(ByteTextCtrl, self).SetSelection(text_from, text_to)
        self.ChooseCaretX() # Update sticky column for vertical movement
    Selection = property(GetSelection)


    def GetShowChanges(self):
        """Returns whether changes from value given in SetValue() are highlighted."""
        return self._show_changes
    def SetShowChanges(self, show_changes):
        """Sets whether changes from value given in SetValue() are highlighted; restyles text."""
        self._show_changes = bool(show_changes)
        self._Restyle()
    ShowChanges = property(GetShowChanges, SetShowChanges)


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


    def MirrorSelection(self):
        """Sets selection or cursor position from mirrored control, if any."""
        if not self._mirror: return

        byte_selection = self._mirror.Selection
        if byte_selection[0] != byte_selection[1]:
            self.SetSelection(*byte_selection)
            self.ChooseCaretX() # Update sticky column for vertical movement
            return

        byte_pos = byte_selection[0]
        do_shift = False

        if self._mirror._addressed:
            mirrorbase = super(type(self._mirror), self._mirror)
            mirror_text_pos = mirrorbase.CurrentPos
            line_start = mirrorbase.PositionFromLine(mirrorbase.LineFromPosition(mirror_text_pos))
            mirror_pos_in_line = mirror_text_pos - line_start
            if mirror_pos_in_line >= self._mirror.WIDTH * 3 - 1:  # At line end
                do_shift = True # Move back from line start to previous line end

        self.SetSelection(byte_pos, byte_pos)
        if do_shift:
            self.CharLeft()
        self.ChooseCaretX() # Update sticky column for vertical movement


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
            if self._show_changes:
                del self._bytes0[selection[0]:selection[1]]

        pos = selection[0]
        v = self._AdaptValue(text)
        maxlen = min(len(v), self.Length - pos) if self._fixed else len(v)
        v = v[:maxlen]

        if self._show_changes and pos + maxlen > len(self._bytes):
            self._bytes0.extend([None] * (pos + maxlen - len(self._bytes)))
        if self.Overtype:
            self._bytes[pos:pos + maxlen] = v
        else:
            self._bytes [pos:pos] = v
            if self._show_changes:
                self._bytes0[pos:pos] = [None] * len(v)

        first_line = self.FirstVisibleLine
        self.Freeze()
        try:
            self._Populate()
            self.SetFirstVisibleLine(first_line)
            self.GotoPos(self._PosIn(selection[0] + len(v)))
            self.EnsureCaretVisible()
            self.ChooseCaretX() # Update sticky column for vertical movement
        finally: self.Thaw()
        cmd.Store()


    def OnCopy(self, event):
        """Handler for clipboard copy event, updates bytes if cutting."""

        def fix_content(cmd, byte_selection, first_line):
            if not self: return
            if not self.GetSelectionEmpty(): return # Not cut if selection still on

            if not self._fixed:
                del self._bytes[byte_selection[0]:byte_selection[1]]
                if self._show_changes:
                    del self._bytes0[byte_selection[0]:byte_selection[1]]
            self._Populate()
            self.SetFirstVisibleLine(first_line)
            self.GotoPos(self._PosIn(byte_selection[0]))
            self.EnsureCaretVisible()
            self.ChooseCaretX() # Update sticky column for vertical movement
            cmd.Store()

        byte_pos1, byte_pos2 = self.Selection
        content = self._bytes[byte_pos1:byte_pos2].decode("utf-8", errors="replace")
        event.SetString(content)
        cmd = HexByteCommand(self)
        # No way to differentiate copy from cut, other than checking later if content changed
        wx.CallAfter(fix_content, cmd, (byte_pos1, byte_pos2), self.FirstVisibleLine)
        self._QueueEvents()


    def OnPaste(self, event):
        """Handles paste event."""
        text = event.String
        event.SetString("") # Cancel default paste
        self.InsertInto(text)


    def OnChar(self, event):
        """Handler for character input, displays printable character."""
        if self._fixed and not self._bytes: return # NULL number

        if event.CmdDown() or event.AltDown(): return

        self._QueueEvents()
        cmd = HexByteCommand(self)
        byte_selection = self.GetSelection()
        if self._fixed:
            self.SetSelection(byte_selection[0], byte_selection[0]) # Discard selection
        elif byte_selection[0] != byte_selection[1]:
            del self._bytes [byte_selection[0]:byte_selection[1]]
            if self._show_changes:
                del self._bytes0[byte_selection[0]:byte_selection[1]]
            self.DeleteBack()

        sself = super(ByteTextCtrl, self)
        if not event.UnicodeKey:
            event.Skip()
        elif sself.CurrentPos != self.GetLastPosition() or not self._fixed:
            text_pos, byte_pos = sself.CurrentPos, byte_selection[0]
            pos_in_line = text_pos - self.PositionFromLine(self.LineFromPosition(text_pos))

            if byte_pos >= len(self._bytes) or text_pos >= self.GetLastPosition():
                self._bytes.append(0)
                if self._show_changes: self._bytes0.append(None)
            elif not self.Overtype:
                self._bytes.insert(byte_pos, 0)
                if self._show_changes: self._bytes0.insert(byte_pos, None)

            if event.KeyCode == self._bytes[byte_pos] \
            and (byte_selection[0] == byte_selection[1] or self._fixed):
                self.GotoPos(self._PosIn(byte_pos + 1))
                self.ChooseCaretX() # Update sticky column for vertical movement
                return

            self._bytes[byte_pos] = event.KeyCode
            self.Freeze()
            try:
                if self.Overtype and text_pos < self.GetLastPosition():
                    if not self._fixed and pos_in_line >= self.WIDTH:
                        text_pos += 1
                    char = re.sub("[^\x20-\x7e]", ".", chr(event.KeyCode)) # Display non-ASCII as dots
                    self.Replace(text_pos, text_pos + 1, char)
                    if self._show_changes:
                        style = self.STYLE_CHANGED
                        if self._bytes0[byte_pos] == self._bytes[byte_pos]: style = 0
                        self.StartStyling(text_pos)
                        self.SetStyling(1, style)
                else: self._Populate()
                self.GotoPos(self._PosIn(byte_pos + 1))
            finally: self.Thaw()
        self.ChooseCaretX() # Update sticky column for vertical movement
        cmd.Store()


    def OnKeyDown(self, event):
        """Handler for key down, fires position change events."""
        is_cmd, is_alt, is_shift = event.CmdDown(), event.AltDown(), event.ShiftDown()

        if is_cmd and not is_alt and not is_shift \
        and ord("Z") == event.KeyCode:
            self.Undo(mirror=True)

        elif is_cmd and not is_alt \
        and (not is_shift and ord("Y") == event.KeyCode or is_shift and ord("Z") == event.KeyCode):
            self.Redo(mirror=True)

        elif is_cmd and not is_alt and not is_shift \
        and event.KeyCode in KEYS.INSERT + (ord("C"), ): # Copy
            if self.GetSelectionEmpty(): pass
            elif hasattr(wx.stc, "EVT_STC_CLIPBOARD_COPY"):
                event.Skip() # Allow default handling
            else:
                byte_pos1, byte_pos2 = self.Selection
                content = self._bytes[byte_pos1:byte_pos2].decode("utf-8", errors="replace")
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(content))
                    wx.TheClipboard.Close()

        elif is_cmd and not is_alt and not is_shift \
        and event.KeyCode == ord("X"): # Cut
            if self.GetSelectionEmpty(): pass
            elif hasattr(wx.stc, "EVT_STC_CLIPBOARD_COPY"):
                event.Skip() # Allow default handling
            else:
                byte_pos1, byte_pos2 = self.Selection
                content = bytes(self._bytes[byte_pos1:byte_pos2])
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(content))
                    wx.TheClipboard.Close()
                if not self._fixed:
                    self.InsertInto("")
                elif sys.version_info < (3, ): # Uncancelable in Py2
                    wx.CallAfter(self._Populate)

        elif is_cmd and not is_alt and not is_shift and ord("V") == event.KeyCode \
        or not is_cmd and not is_alt and is_shift and event.KeyCode in KEYS.INSERT:
            text = None
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                    o = wx.TextDataObject()
                    wx.TheClipboard.GetData(o)
                    text = o.Text
                wx.TheClipboard.Close()
            if text is not None: self.InsertInto(text)

        elif event.KeyCode in KEYS.INSERT and not event.HasAnyModifiers():
            if not self._fixed:
                event.Skip() # Disallow changing overtype for fixed-length content

        elif event.KeyCode in KEYS.ARROW + KEYS.PAGING + KEYS.HOME + KEYS.END:
            self._QueueEvents()
            accept = True
            if event.KeyCode in KEYS.UP   and self.CurrentLine == 0 \
            or event.KeyCode in KEYS.DOWN and self.CurrentLine == self.LineCount - 1:
                accept = False # Do not jump to front or end from first or last line
            if accept:
                event.Skip()
                self.ChooseCaretX() # Update sticky column for vertical movement

        elif event.KeyCode in KEYS.DELETE + KEYS.BACKSPACE:
            if not self._fixed:
                self._OnKeyDownDeleteBackspace(event)

        elif event.KeyCode in KEYS.ENTER + KEYS.TAB: pass

        else:
            self._QueueEvents()
            event.Skip()


    def OnMouse(self, event):
        """Handler for mouse event, fires position change events."""
        self._QueueEvents()
        event.Skip()


    def _OnKeyDownDeleteBackspace(self, event):
        """Handler for pressing Delete or Backspace."""
        self._QueueEvents()

        cmd = HexByteCommand(self)
        byte_selection = list(self.GetSelection())
        if byte_selection[0] != byte_selection[1]:
            del self._bytes [byte_selection[0]:byte_selection[1]]
            if self._show_changes:
                del self._bytes0[byte_selection[0]:byte_selection[1]]
            self.GotoPos(self._PosIn(byte_selection[0]))
            cmd.Submit(mirror=True)
            return

        sself = super(ByteTextCtrl, self)
        text_pos    = sself.CurrentPos
        line_index  = self.LineFromPosition(text_pos)
        pos_in_line = text_pos - self.PositionFromLine(line_index)
        direction   = -1 if event.KeyCode in KEYS.BACKSPACE else 1

        if not self._bytes or text_pos == 0 and direction < 0 \
        or text_pos == self.GetLastPosition() and direction > 0:
            return

        byte_pos = self.CurrentPos - (1 if direction < 0 else 0)
        del self._bytes[byte_pos]
        if self._show_changes:
            del self._bytes0[byte_pos]

        if line_index == self.LineCount - 1 and (direction > 0 or pos_in_line > 0):
            # Last line and not backspacing from first byte
            delete_from = max(text_pos - 1 if direction < 0 else text_pos, 0)
            self.Remove(delete_from, delete_from + 1)
        else:
            self.Freeze()
            try:
                initial_visible_line = self.FirstVisibleLine
                self._Populate()
                self.SetFirstVisibleLine(initial_visible_line)
                text_pos2 = self._PosIn(byte_pos)
                self.GotoPos(text_pos2)
            finally: self.Thaw()
        self.ChooseCaretX() # Update sticky column for vertical movement
        cmd.Store()


    def _AdaptValue(self, value):
        """Returns the value as str for byte representation."""
        is_long, is_int = is_fixed_long(value), isinstance(value, int) and is_fixed(value)
        if is_long:                    v = struct.pack(">q", value)
        elif is_int:                   v = struct.pack(">l", value)
        elif isinstance(value, float): v = struct.pack(">d", value)
        elif value is None:            v = b""
        elif isinstance(value, text_type):
            try: v = value.encode("latin1")
            except Exception: v = value.encode("utf-8")
        else: v = value
        if not isinstance(v, bytes):
            v = str(v).encode("latin1")
        return v


    def _PosIn(self, byte_pos):
        line, linepos = divmod(byte_pos, self.WIDTH)
        return line * (self.WIDTH + 1) + linepos
    def _PosOut(self, text_pos):
        return text_pos - self.LineFromPosition(text_pos)


    def _Populate(self):
        """Sets current content to widget."""
        chars = re.sub("[^\x20-\x7e]", ".", bytes(self._bytes).decode("latin1"))
        lines = [chars[i:i + self.WIDTH] for i in range(0, len(self._bytes), self.WIDTH)]
        fulltext = "\n".join(lines)
        if super(ByteTextCtrl, self).Text != fulltext:
            super(ByteTextCtrl, self).ChangeValue(fulltext)
        self._Restyle()
        if self._fixed and not self.Overtype: self.SetOvertype(True)


    def _Restyle(self):
        """Restyles current content according to changed state."""
        if not self._show_changes: return
        eventmask0, _ = self.GetModEventMask(), self.SetModEventMask(0)
        try:
            self.StartStyling(0)
            self.SetStyling(super(ByteTextCtrl, self).Length, 0)
            ranges, currange = [], None
            for i, c in enumerate(self._bytes):
                if c == self._bytes0[i]: currange = None
                elif currange:           currange[-1] += 1
                else:                    currange = [i, 1]; ranges.append(currange)
            for i, length in ranges:
                self.StartStyling(i // self.WIDTH + i)
                self.SetStyling(length // self.WIDTH + length, self.STYLE_CHANGED)
        finally: self.SetModEventMask(eventmask0)


    def _GetValueState(self, *value):
        """Returns value type and data dict, from current content or given value."""
        if not value:
            return {"_bytes": self._bytes[:], "_bytes0": self._bytes0[:],
                    "_fixed": self._fixed, "_type": self._type}

        value = value[0]
        if isinstance(value, bool): value = int(value)
        bytesvalue = self._AdaptValue(value)
        bytes0 = self._bytes0[:]
        if self._show_changes:
            diff = len(bytesvalue) - len(bytes0)
            if diff > 0:   bytes0.extend([None] * diff)
            elif diff < 0: del bytes0[abs(diff):]

        state = {
            "_bytes":  bytearray(bytesvalue),
            "_bytes0": bytes0,
            "_fixed":  is_fixed(value) or value is None,
            "_type":   type(value) if is_fixed(value) or isinstance(value, string_types) else str,
        }
        return state


    def _SetValue(self, value, noreset=False):
        """Set current content as typed value (string or number)."""
        if isinstance(value, bool): value = int(value)
        v = self._AdaptValue(value)

        self._bytes[:] = v
        if not noreset:
            self._type  = type(value) if is_fixed(value) or isinstance(value, string_types) else str
            self._fixed = is_fixed(value) or value is None
            if self._show_changes:
                self._bytes0[:] = [x if isinstance(x, int) else ord(x) for x in v]
        if self._fixed and not self.Overtype: self.SetOvertype(True)


    def _QueueEvents(self):
        """Raises CaretPositionEvent or LinePositionEvent or SelectionEvent if changed after."""

        sself = super(ByteTextCtrl, self)
        text_pos, firstline = sself.CurrentPos, self.FirstVisibleLine
        text_selection = self.GetSelectionEmpty(), sself.GetSelection()

        def after():
            if not self: return

            if text_pos != sself.CurrentPos:
                evt = CaretPositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.CurrentPos)
                wx.PostEvent(self, evt)
            elif firstline != self.FirstVisibleLine:
                evt = LinePositionEvent(self.Id)
                evt.SetEventObject(self)
                evt.SetInt(self.FirstVisibleLine)
                wx.PostEvent(self, evt)

            if text_selection != sself.GetSelection():
                evt = SelectionEvent(self.Id)
                evt.SetEventObject(self)
                wx.PostEvent(self, evt)
        wx.CallAfter(after)



class ItemFilterDialog(wx.Dialog):
    """
    Dialog allowing to set hidden-flag or filter values on a range of items.
    """


    def __init__(self, parent=None, items=(), title="Filter items", filter_menu=(),
                 filter_hint=None,
                 style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER | wx.FRAME_FLOAT_ON_PARENT |
                       wx.APPLY):
        """
        @param   items        list of items to manage,
                              as [{name, ?label, ?hidden, ?exact, ?filtered, ?inverted, ?value}]
        @param   filter_menu  list of menu choices for filter values, as [{label, value, ?disabled}],
                              "value" optionally being callback(item, index)
                              or a list/tuple of nested submenu choices
        @param   filter_hint  hint text displayed for empty filter value,
                              optionally as callback(item, index)
        @param   style        dialog style flags; dialog will have Apply-button if wx.APPLY included
                              (see SetApplyCallback)
        """
        apply, style = (style & wx.APPLY), (style ^ wx.APPLY if style & wx.APPLY else style)
        wx.Dialog.__init__(self, parent, title=title, style=style)

        self._items  = {} # [{name, label, hidden, filtered, filter}]
        self._ctrls  = {} # {name or (row, name): wx.Control}
        self._apply       = True # whether to show Apply-button
        self._apply_cb    = None # callback(item) registered for Apply-button
        self._filter_menu = []    # [{label, value}]
        self._filter_hint = None  # value or callable(item)

        self._items = [dict(name=x["name"], value=x.get("value", ""),
                            exact=bool(x.get("exact")), inverted=bool(x.get("inverted")),
                            hidden=bool(x.get("hidden")), filtered=bool(x.get("filtered")),
                            label=x.get("label", x["name"])) for x in items]
        self._apply = apply
        self._filter_menu = [dict(label=x["label"], value=x["value"],
                                  disabled=bool(x.get("disabled"))) for x in filter_menu]
        self._filter_hint = filter_hint

        self._Build()
        self._Bind()
        self._SizeToFit()
        self._AlignColumns()
        self._Refresh()
        ColourManager.Patch(self)


    def GetItems(self):
        """Returns the list of items, with current choices for flags and filter values."""
        return [dict(x) for x in self._items]
    Items = property(GetItems)


    def SetApplyCallback(self, callback):
        """Sets callback function(item) invoked on clicking Apply-button."""
        if callback is not None and not callable(callback):
            raise ValueError("Invalid callback %r" % callback)
        self._apply_cb = callback


    def _Build(self):
        """Creates dialog controls."""
        check_show_all   = wx.CheckBox(self, label="&Show all")
        check_filter_all = wx.CheckBox(self, label="&Filter all")

        container = wx.ScrolledWindow(self)

        check_show_all.ToolTip   = "Toggle all items shown or hidden"
        check_filter_all.ToolTip = "Enable filters for all"
        check_show_all.Value   = all(not x["hidden"] for x in self._items)
        check_filter_all.Value = all(x["filtered"] for x in self._items)
        container.SetScrollRate(0, 20)

        sizer_main = wx.BoxSizer(wx.VERTICAL)
        sizer_header = wx.GridBagSizer()
        sizer_grid = wx.GridBagSizer()

        for i, item in enumerate(self._items):
            name, label = item["name"], item["label"]
            check_name   = wx.CheckBox(container)
            label_name   = wx.StaticText(container, label=label, style=wx.ST_ELLIPSIZE_END)
            check_filter = wx.CheckBox(container)
            edit_filter  = HintedTextCtrl(container, escape=False)
            button_menu  = wx.Button(container, label="..", size=(BUTTON_MIN_WIDTH, ) * 2) \
                           if self._filter_menu else None
            check_exact  = wx.CheckBox(container, label="EXACT")
            check_invert = wx.CheckBox(container, label="NOT")

            label_name.MinSize = ( 20, -1)
            label_name.MaxSize = (250, -1)
            check_name.ToolTip   = "Show or hide %r" % name
            label_name.ToolTip   = "Show or hide %r" % name
            check_filter.ToolTip = "Enable filter for %r" % name
            edit_filter.ToolTip  = "Filter value for %r" % name
            if button_menu:
                button_menu.ToolTip = "Open options menu"
            check_exact.ToolTip  = "Match entered filter value exactly as is, "\
                                   "do not use partial case-insensitive match"
            check_invert.ToolTip = "Revert filter for column, matching where value is different"

            sizer_grid.Add(check_name,   pos=(i, 0), flag=wx.ALIGN_CENTER_VERTICAL)
            sizer_grid.Add(label_name,   pos=(i, 1), flag=wx.ALIGN_CENTER_VERTICAL | wx.GROW)
            sizer_grid.Add(check_filter, pos=(i, 2), flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
            sizer_grid.Add(edit_filter,  pos=(i, 3), flag=wx.GROW)
            sizer_grid.Add(button_menu,  pos=(i, 4), flag=wx.GROW) if button_menu else None
            sizer_grid.Add(check_exact,  pos=(i, 4 + bool(button_menu)), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
            sizer_grid.Add(check_invert, pos=(i, 5 + bool(button_menu)), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)

            self._ctrls[(i, "check_name"  )] = check_name
            self._ctrls[(i, "label_name"  )] = label_name
            self._ctrls[(i, "check_filter")] = check_filter
            self._ctrls[(i, "edit_filter" )] = edit_filter
            self._ctrls[(i, "check_exact" )] = check_exact
            self._ctrls[(i, "check_invert")] = check_invert
            if button_menu:
                self._ctrls[(i, "button_menu")] = button_menu

        buttonflags = wx.OK | wx.CANCEL | (wx.APPLY if self._apply else 0)
        sizer_buttons = self.CreateStdDialogButtonSizer(buttonflags)

        sizer_header.Add(check_show_all,   pos=(0, 0))
        sizer_header.Add(check_filter_all, pos=(0, 1), flag=wx.LEFT)
        sizer_main.Add(sizer_header,  flag=wx.GROW | wx.ALL, border=10)
        sizer_main.Add(container,     flag=wx.GROW | wx.LEFT | wx.RIGHT, border=10, proportion=1)
        sizer_main.Add(sizer_buttons, flag=wx.GROW | wx.ALL, border=10)

        sizer_grid.HGap, sizer_grid.VGap = 5, 5
        sizer_grid.AddGrowableCol(1)
        sizer_grid.AddGrowableCol(3)

        self.Sizer = sizer_main
        container.Sizer = sizer_grid
        self._ctrls.update(check_show_all=check_show_all, check_filter_all=check_filter_all,
                           container=container)


    def _Bind(self):
        """Binds control and dialog event handlers."""
        self.Bind(wx.EVT_CHECKBOX, self._OnToggleAllShown,    self._ctrls["check_show_all"])
        self.Bind(wx.EVT_CHECKBOX, self._OnToggleAllFiltered, self._ctrls["check_filter_all"])
        self.Bind(wx.EVT_SIZE, lambda e: (e.Skip(), wx.CallAfter(self._AlignColumns)))
        if self._apply:
            self.Bind(wx.EVT_BUTTON, self._OnApply, id=wx.ID_APPLY)
        for i in range(len(self._items)):
            on_toggle_show   = functools.partial(self._OnToggleItemShown,    index=i)
            on_toggle_filter = functools.partial(self._OnToggleItemFiltered, index=i)
            on_toggle_exact  = functools.partial(self._OnToggleItemExact,    index=i)
            on_toggle_invert = functools.partial(self._OnToggleItemInverted, index=i)
            on_edit_filter   = functools.partial(self._OnChangeItemFilter,   index=i)
            self._ctrls[(i, "label_name")].Bind(wx.EVT_LEFT_UP, on_toggle_show)
            self.Bind(wx.EVT_CHECKBOX,   on_toggle_show,   self._ctrls[(i, "check_name")])
            self.Bind(wx.EVT_CHECKBOX,   on_toggle_filter, self._ctrls[(i, "check_filter")])
            self.Bind(wx.EVT_CHECKBOX,   on_toggle_exact,  self._ctrls[(i, "check_exact")])
            self.Bind(wx.EVT_CHECKBOX,   on_toggle_invert, self._ctrls[(i, "check_invert")])
            self.Bind(wx.EVT_TEXT_ENTER, on_edit_filter,   self._ctrls[(i, "edit_filter")])
            if self._filter_menu:
                on_filter_menu = functools.partial(self._OnOpenItemFilterOptions, index=i)
                self.Bind(wx.EVT_BUTTON, on_filter_menu, self._ctrls[(i, "button_menu")])


    def _SizeToFit(self):
        """Resizes dialog window to reasonable width and height."""
        self.Fit()
        container = self._ctrls["container"]
        MINH = get_window_height(self, exclude=container)
        ITMH = max(x.Size.Height for x in map(container.Sizer.GetItem, range(container.Sizer.Cols)))
        self.MinSize = (450, MINH + ITMH)
        self.MaxSize = (600, -1)
        if self.Size.Height > 400:
            self.Size = (self.Size.Width, 400)
        elif container.VirtualSize.Height > container.Size.Height:
            h = MINH + ITMH
            while h < 240: h += ITMH
            h = min(h, MINH + container.VirtualSize.Height)
            self.Size = (self.Size.Width, h)
        self.MaxSize = (-1, -1)


    def _AlignColumns(self):
        """Aligns header columns with item columns."""
        container = self._ctrls["container"]
        NAMESW = sum(container.Sizer.ColWidths[:2]) + 2 * container.Sizer.HGap
        sizer_header = self.Sizer.GetItem(0).Sizer
        sizer_header.GetItem(1).Border = NAMESW - sizer_header.GetItem(0).Size.Width
        self.Layout()


    def _Refresh(self, index=None):
        """Enables-disables-populates all or specific items according to current settings."""
        self.Freeze()
        try:
            items = enumerate(self._items) if index is None else [(index, self._items[index])]
            for i, item in items:
                item_shown, item_filtered = not item["hidden"], item["filtered"]
                filter_text = "" if item["value"] is None else text_type(item["value"])
                fgcolour = wx.SYS_COLOUR_WINDOWTEXT if item_shown else wx.SYS_COLOUR_GRAYTEXT
                ColourManager.Manage(self._ctrls[(i, "label_name")], "ForegroundColour", fgcolour)
                self._ctrls[(i, "check_name"  )].Value = item_shown
                self._ctrls[(i, "check_filter")].Value = item_filtered
                self._ctrls[(i, "edit_filter" )].Value = filter_text
                self._ctrls[(i, "edit_filter" )].Enable(item_filtered)
                self._ctrls[(i, "check_exact" )].Enable(item_filtered)
                self._ctrls[(i, "check_exact" )].Value = item["exact"]
                self._ctrls[(i, "check_invert")].Enable(item_filtered)
                self._ctrls[(i, "check_invert")].Value = item["inverted"]
                if self._filter_menu:
                    self._ctrls[(i, "button_menu")].Enable(item_filtered)
                if self._filter_hint:
                    hint = self._filter_hint if item_filtered else ""
                    self._ctrls[(i, "edit_filter")].Hint = hint(item, i) if callable(hint) else hint
        finally: self.Thaw()


    def _OnToggleAllShown(self, event):
        """Handler for toggling all items shown on/off, updates state and refreshes display."""
        for item in self._items: item["hidden"] = not event.IsChecked()
        self._Refresh()


    def _OnToggleAllFiltered(self, event):
        """Handler for toggling all items filtered on/off, updates state and refreshes display."""
        for item in self._items: item["filtered"] = event.IsChecked()
        self._Refresh()


    def _OnApply(self, event):
        """Handler for clicking Apply-button, invokes registered apply-callback if any."""
        if callable(self._apply_cb): self._apply_cb(self.GetItems())


    def _OnToggleItemShown(self, event, index):
        """Handler for toggling item shown on/off, updates state and refreshes display."""
        self._items[index]["hidden"] = not self._items[index]["hidden"]
        self._Refresh(index)


    def _OnToggleItemFiltered(self, event, index):
        """Handler for toggling item filtered on/off, updates state and refreshes display."""
        self._items[index]["filtered"] = not self._items[index]["filtered"]
        self._Refresh(index)
        if self._items[index]["filtered"] and not self._ctrls[(index, "edit_filter")].Hint:
            self._ctrls[(index, "edit_filter")].SetFocus()
            self._ctrls[(index, "edit_filter")].SelectNone()


    def _OnToggleItemExact(self, event, index):
        """Handler for toggling item filter exact on/off, updates state and refreshes display."""
        self._items[index]["exact"] = not self._items[index]["exact"]
        self._Refresh(index)


    def _OnToggleItemInverted(self, event, index):
        """Handler for toggling item filter inverted on/off, updates state and refreshes display."""
        self._items[index]["inverted"] = not self._items[index]["inverted"]
        self._Refresh(index)


    def _OnChangeItemFilter(self, event, index):
        """Handler for editing filter text, refreshes filter hint if any."""
        item = self._items[index]
        item["value"] = event.EventObject.Value
        if self._filter_hint:
            hint = self._filter_hint if item["filtered"] else ""
            self._ctrls[(index, "edit_filter")].Hint = hint(item, index) if callable(hint) else hint


    def _OnOpenItemFilterOptions(self, event, index):
        """Handler for clicking filter options button, opens popup menu."""

        def populate_menu(menu, menu_opts):
            for opts in menu_opts:
                value = opts["value"]
                if isinstance(value, (list, tuple)) \
                and all(isinstance(x, dict) and "label" in x and "value" in x for x in value):
                    submenu = wx.Menu()
                    menuitem = menu.Append(wx.ID_ANY, opts["label"], submenu)
                    if opts.get("disabled"): menuitem.Enable(False)
                    else: populate_menu(submenu, value)
                    continue # for opts

                menuitem = wx.MenuItem(menu, -1, opts["label"])
                menu.Append(menuitem)
                if opts.get("disabled"): menuitem.Enable(False)
                on_menu = functools.partial(self._OnSetItemFilterOption, index=index, value=value)
                rootmenu.Bind(wx.EVT_MENU, on_menu, menuitem)

        rootmenu = wx.Menu()
        populate_menu(rootmenu, self._filter_menu)
        event.EventObject.PopupMenu(rootmenu, tuple(event.EventObject.Size))


    def _OnSetItemFilterOption(self, event, index, value):
        """Handler for filter options menu item, applies value."""
        value2 = value(self._items[index], index) if callable(value) else value
        self._items[index]["value"] = value2 if value2 is None else text_type(value2)
        self._Refresh(index)



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

        self.SetLexer(wx.stc.STC_LEX_JSON) if hasattr(wx.stc, "STC_LEX_JSON") else None
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
        fgcolour, bgcolour, highcolour = (ColourManager.ColourHex(x) for x in
            (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW if self.Enabled else wx.SYS_COLOUR_BTNFACE,
             wx.SYS_COLOUR_HOTLIGHT)
        )

        self.SetCaretForeground(fgcolour)
        self.SetCaretLineBackground("#00FFFF")
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT,
                          "face:%s,back:%s,fore:%s" % (self.FONT_FACE, bgcolour, fgcolour))
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT, "fore:%s" % highcolour)
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD, "fore:#FF0000")
        self.StyleClearAll() # Apply the new default style to all styles
        if not hasattr(wx.stc, "STC_JSON_DEFAULT"): return # Py2

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
        result = super(JSONTextCtrl, self).Enable(enable)
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
        if not hasattr(wx.stc, "STC_JSON_OPERATOR"): return # Py2

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
            if tab not in self._tabs: return
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
        p = wx.Panel(self, size=(0, 0))
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
            self.Bind(wx.EVT_WINDOW_DESTROY,        self.OnDestroy, self)
        self.Bind(wx.EVT_SET_FOCUS,                 self.OnFocus, self)
        self.Bind(wx.EVT_KILL_FOCUS,                self.OnFocus, self)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,        self.OnSysColourChange)


    def OnDestroy(self, event):
        """Handler for window destruction, unbinds handlers from parents."""
        gp = self
        while gp is not None:
            gp.Unbind(wx.EVT_MOVE, gp, handler=self.OnSizedOrMoved)
            gp.Unbind(wx.EVT_SIZE, gp, handler=self.OnSizedOrMoved)
            gp = gp.GetParent()


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
            event.SetEventObject(self)
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


    def GetChoices(self):
        """Returns the choices available in the dropdown list."""
        return self._choices[:]
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
                self._listbox.SetItemTextColour(len(choices) - 1, self._clear_colour)

            itemheight = self._listbox.GetItemRect(0)[-1] if choices else 0
            itemcount = min(len(choices), self.DROPDOWN_COUNT_PER_PAGE)
            # Leave room vertically for border and padding.
            size = wx.Size(self.Size.width - 3, itemheight * itemcount + 5)
            self._listbox.Size = self._listwindow.Size = size
            # Leave room for vertical scrollbar
            self._listbox.SetColumnWidth(0, size.width - 16)
            self._listbox.SetScrollbar(wx.HORIZONTAL, 0, 0, 0)
    Choices = property(GetChoices, SetChoices)


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


    def _OnEditChar(self, event):
        """Handler for keypress in label edit control, stops editing on Enter or Escape."""
        keycode = event.GetKeyCode()
        if keycode in KEYS.ENTER and not event.ShiftDown():
            event.EventObject.AcceptChanges()
            wx.CallAfter(event.EventObject.Finish)
        elif keycode in KEYS.ESCAPE:
            wx.CallAfter(event.EventObject.StopEditing)
        else:
            event.Skip()


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
        if wx.VERSION >= (4, 1) and "linux" in sys.platform:
            # Workaround for wxPython issue #1938 on crashing in Linux
            ctrl.Unbind(wx.EVT_CHAR, source=ctrl, handler=ctrl.OnChar)
            ctrl.Bind(wx.EVT_CHAR, self._OnEditChar)
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
        fgcolour, bgcolour, highcolour, graycolour = (ColourManager.ColourHex(x) for x in
            (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW if self.Enabled else wx.SYS_COLOUR_BTNFACE,
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
        result = super(YAMLTextCtrl, self).Enable(enable)
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


def center_in_window(dialog, window):
    """Centers dialog in given window."""
    x = window.ScreenPosition[0] + (window.Size[0] - dialog.Size[0]) // 2
    y = window.ScreenPosition[1] + max(0, (window.Size[1] - dialog.Size[1]) // 2)
    dialog.SetPosition((x, y))


def cmp(x, y):
    """Return negative if x<y, zero if x==y, positive if x>y."""
    if x == y: return 0
    if x is None: return -1
    if y is None: return +1
    try:
        return -1 if x < y else +1
    except TypeError:
        return -1 if str(x) < str(y) else +1


def get_all_children(ctrl):
    """Returns a list of all nested children of given wx component."""
    result, stack = [], [ctrl]
    while stack:
        ctrl = stack.pop(0)
        for child in ctrl.GetChildren() if hasattr(ctrl, "GetChildren") else []:
            result.append(child)
            stack.append(child)
    return result


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


def get_key_state(keycode):
    """Returns true if specified key is currently down."""
    try: return wx.GetKeyState(keycode)
    except Exception: return False  # wx3 can raise for non-modifier keys in non-X11 backends


def get_tool_rect(toolbar, id_tool):
    """
    Returns position and size of a horizontal toolbar tool by ID. No support for stretchable space.
    """
    HAS_LABELS = toolbar.WindowStyleFlag & wx.TB_HORZ_TEXT
    HAS_ICONS = not toolbar.WindowStyleFlag & wx.TB_NOICONS
    BORDER       = max(0, wx.SystemSettings.GetMetric(wx.SYS_BORDER_X)) if "nt" == os.name else 4
    PAD_BMP      = 2 if "nt" == os.name else (2 if HAS_LABELS else 3)
    PAD_BMP_JUST = 2 if "nt" == os.name else 7
    PAD_CTRL     = 3 if "nt" == os.name else 0
    PAD_EXTRA    = 1 if "nt" == os.name else 0
    PAD_LABEL    = 5 if "nt" == os.name else 12
    PAD_SEP      = 3 if "nt" == os.name else 7
    W_GAP        = 0 if "nt" == os.name else 1
    W_LEAD       = 0 if "nt" == os.name else 4
    W_SEP        = 2 if "nt" == os.name else 1
    W_LABEL_MIN  = (5 if HAS_LABELS else 1) if "nt" == os.name else 0

    def get_inter(tool, index): # Return horizontal padding in front of tool
        width = PAD_SEP if tool.IsSeparator() else PAD_CTRL if tool.IsControl() else 0
        if not index: width += W_LEAD
        else:
            if toolbar.GetToolByPos(index - 1).IsSeparator(): width += PAD_SEP
            elif tool.IsButton(): width += W_GAP
        if tool.IsSeparator() and "nt" != os.name:
            if not index or toolbar.GetToolByPos(index - 1).IsSeparator(): width -= 1
        return width

    def get_width(tool): # Return pixel width of tool
        if tool.IsSeparator(): return W_SEP
        if tool.IsControl():   return tool.Control.Size.Width

        pad_bmp = PAD_BMP_JUST if HAS_LABELS and not tool.Label else PAD_BMP
        w = 2 * BORDER
        if HAS_ICONS: w += pad_bmp + toolbar.ToolBitmapSize.Width
        if HAS_LABELS and tool.Label:
            w += 2 * PAD_LABEL + toolbar.GetTextExtent(wx.StripMenuCodes(tool.Label))[0] + PAD_EXTRA
            if not HAS_ICONS: w += 3
        else:
            w += W_LABEL_MIN + pad_bmp
        return w

    myindex = toolbar.GetToolPos(id_tool)
    mytool  = toolbar.GetToolByPos(myindex)
    result  = wx.Rect(0, 0, get_width(mytool), toolbar.Size.Height)
    for index in range(myindex):
        tool = toolbar.GetToolByPos(index)
        result.X += get_inter(tool, index) + get_width(tool)
    result.X += get_inter(mytool, myindex)
    if result.X > toolbar.Size.Width:
        result.X = toolbar.Size.Width - get_width(mytool)
    return result


def get_window_height(window, exclude=()):
    """
    Returns minimum height of given window, including frame and content.

    @param   exclude  wx objects to exclude from height calculations in window's vertical BoxSizer
    """
    metric_source = window.Parent.TopLevelParent if window.Parent else window
    METRICS = (wx.SYS_CAPTION_Y, wx.SYS_FRAMESIZE_Y, wx.SYS_WINDOWMIN_Y)
    CAPTION, FRAME, MIN = [max(0, wx.SystemSettings.GetMetric(x, metric_source)) for x in METRICS]
    height = max(2 * FRAME + CAPTION, MIN) # Metric availability varies with platforms and versions
    if exclude and isinstance(window.Sizer, wx.BoxSizer) \
    and wx.VERTICAL == window.Sizer.Orientation:
        if isinstance(exclude, wx.Object): exclude = [exclude]
        for szitem in map(window.Sizer.GetItem, range(window.Sizer.ItemCount)):
            if not any(x and x in exclude for x in (szitem.Window, szitem.Sizer)):
                height += szitem.Size.Height
    elif window.Sizer:
        height += window.Sizer.Size.Height
    return height


def is_fixed(value):
    """Returns whether value is fixed-size (float, or 32/64-bit integer)."""
    return isinstance(value, float) or isinstance(value, integer_types) and -2**63 <= value < 2**63


def is_fixed_long(value, bytevalue=None):
    """
    Returns whether value is integer between 32 and 64 bits.
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


def make_dialog_filter(formats=(), names=None, noun="file", group=False, merge=False, blank=False):
    """
    Returns text for wx file dialog wildcard with given formats.

    Format name is taken from given names dictionary, or generated as "EXT noun".

    @param   formats  file formats like ["csv", "txt"], any leading dots will be stripped;
                      may contain nested collections like ["bmp", ("jpg", "jpeg"), "png"]
    @param   names    dictionary with format names if any, as {format: informative name}
    @param   noun     general noun for files, used in generated names
    @param   group    whether to include an initial entry for all given formats, as "All nouns|*.*"
    @param   merge    whether to merge all formats under a single entry instead
    @param   blank    whether to include a final entry for all files, as "All files|*.*"
    @return           text like "CSV spreadsheet (*.csv)|*.csv|Text document (*.txt)|*.txt"
    """
    entries = []
    formats = [[y.lstrip(".") for y in ([x] if isinstance(x, string_types) else x)] for x in formats]
    if not names: names = {}
    if merge and formats:
        exts = ";".join("*." + y for x in formats for y in x)
        entry = "%s%s (%s)|%s" % (noun[0].upper(), noun[1:], exts, exts)
        entries.append(entry)
        formats = []
    if group and formats:
        entry = "All {0}s ({1})|{1}".format(noun, ";".join("*." + y for x in formats for y in x))
        entries.append(entry)
    for fmts in formats:
        exts = ";".join("*." + x for x in fmts)
        fmt = fmts[0]
        name = names.get(fmt) or "%s %s" % (fmt.upper(), noun)
        entry = "%s%s (%s)|%s" % (name[0].upper(), name[1:], exts, exts)
        entries.append(entry)
    if blank:
        entry = "All files|*.*"
        entries.append(entry)
    return "|".join(entries)


def resize_img(img, size, aspect_ratio=True, bg=(-1, -1, -1)):
    """Returns a resized wx.Image or wx.Bitmap, centered in free space if any."""
    if not img or not size or list(size) == list(img.GetSize()): return img

    result = img if isinstance(img, wx.Image) else img.ConvertToImage()
    size1, size2 = list(result.GetSize()), list(size)
    align_pos = None
    if size1[0] < size[0] and size1[1] < size[1]:
        size2 = tuple(size1)
        align_pos = [(a - b) // 2 for a, b in zip(size, size2)]
    elif aspect_ratio:
        ratio = size1[0] / float(size1[1]) if size1[1] else 0.0
        size2[ratio > 1] = int(size2[ratio > 1] * (ratio if ratio < 1 else 1 / ratio))
        align_pos = [(a - b) // 2 for a, b in zip(size, size2)]
    if size1[0] > size[0] or size1[1] > size[1]:
        if result is img: result = result.Copy()
        result.Rescale(*size2)
    if align_pos:
        if result is img: result = result.Copy()
        result.Resize(size, align_pos, *bg)
    return result.ConvertToBitmap() if isinstance(img, wx.Bitmap) else result


def set_dialog_filter(dialog, idx=-1, ext=None, exts=()):
    """
    Sets filter index in FileDialog, replaces extension in current filename.

    Smooths over issue in Linux where setting filter index
    retains previous extension in default filename.

    @param   dialog      FileDialog instance
    @param   idx         index to set
    @param   ext         alternative to idx: file extension to set index at.
                         If exts not given, tries to detect index from dialog wildcard.
    @param   exts        list of file extensions to get index for `ext` from
    """
    # Wildcard is like "JSON data (*.json)|*.json|YAML data (*.yaml)|*.yaml|"
    exts = exts or [x[2:] for x in dialog.Wildcard.split("|")[1::2] if x.startswith("*.")]
    idx = exts.index(ext) if ext and ext in exts else idx
    if idx >= 0:
        dialog.SetFilterIndex(idx)
        ext = exts[idx] if not ext and idx < len(exts) else ext or ""
        base, extnow = os.path.splitext(dialog.Filename)
        if extnow != "." + ext:
            dialog.Filename = "%s.%s" % (base, ext)
