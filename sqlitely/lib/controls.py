# -*- coding: utf-8 -*-
"""
Stand-alone GUI components for wx:

- BusyPanel(wx.Window):
  Primitive hover panel with a message that stays in the center of parent
  window.

- ColourManager(object):
  Updates managed component colours on Windows system colour change.

- FormDialog(wx.Dialog):
  Dialog for displaying a complex editable form.

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

- ScrollingHtmlWindow(wx.html.HtmlWindow):
  HtmlWindow that remembers its scroll position on resize and append.

- SearchCtrl(wx.TextCtrl):
  Simple search control, with search description.

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

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.01.2012
@modified    18.11.2019
------------------------------------------------------------------------------
"""
import collections
import copy
import functools
import locale
import os
import re

import wx
import wx.html
import wx.lib.agw.flatnotebook
import wx.lib.agw.gradientbutton
import wx.lib.agw.labelbook
try: # ShapedButton requires PIL, might not be installed
    import wx.lib.agw.shapedbutton
except Exception: pass
import wx.lib.agw.ultimatelistctrl
import wx.lib.embeddedimage
import wx.lib.gizmos
import wx.lib.mixins.listctrl
import wx.lib.newevent
import wx.lib.wordwrap
import wx.stc


# Convenience methods for creating a wx.Brush and wx.Pen or returning cached.
BRUSH = lambda c, s=wx.BRUSHSTYLE_SOLID: wx.TheBrushList.FindOrCreateBrush(c, s)
PEN = lambda c, w=1, s=wx.PENSTYLE_SOLID: wx.ThePenList.FindOrCreatePen(c, w, s)


class BusyPanel(wx.Window):
    """
    Primitive hover panel with a message that stays in the center of parent
    window.
    """
    FOREGROUND_COLOUR = wx.WHITE
    BACKGROUND_COLOUR = wx.Colour(110, 110, 110, 255)

    def __init__(self, parent, label):
        wx.Window.__init__(self, parent)
        self.Hide()
        sizer = self.Sizer = wx.BoxSizer(wx.VERTICAL)
        label = self._label = wx.StaticText(self, label=label)
        self.BackgroundColour = self.BACKGROUND_COLOUR
        label.ForegroundColour = self.FOREGROUND_COLOUR
        sizer.Add(label, border=15, flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        self.Fit()
        self.Layout()
        self.CenterOnParent()
        self.Show()
        parent.Refresh()
        wx.YieldIfNeeded()


    def Close(self):
        try:
            self.Hide()
            self.Parent.Refresh()
            self.Destroy()
        except Exception: pass



class ColourManager(object):
    """
    Updates managed component colours on Windows system colour change.
    """
    colourcontainer   = None
    colourmap         = {} # {colour name in container: wx.SYS_COLOUR_XYZ}
    darkcolourmap     = {} # {colour name in container: wx.SYS_COLOUR_XYZ}
    darkoriginals     = {} # {colour name in container: original value}
    # {ctrl: (prop name: colour name in container)}
    ctrls             = collections.defaultdict(dict)


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
        if "nt" != os.name: return

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
        cls.ctrls[ctrl][prop] = colour
        cls.UpdateControlColour(ctrl, prop, colour)


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
        return wx.Colour(getattr(cls.colourcontainer, colour)) \
               if isinstance(colour, basestring) \
               else wx.SystemSettings.GetColour(colour)


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
        for ctrl, props in cls.ctrls.items():
            if not ctrl: # Component destroyed
                cls.ctrls.pop(ctrl)
                continue # for ctrl, props

            for prop, colour in props.items():
                cls.UpdateControlColour(ctrl, prop, colour)


    @classmethod
    def UpdateControlColour(cls, ctrl, prop, colour):
        """Sets control property or invokes "Set" + prop."""
        mycolour = cls.GetColour(colour)
        if hasattr(ctrl, prop):
            setattr(ctrl, prop, mycolour)
        elif hasattr(ctrl, "Set" + prop):
            getattr(ctrl, "Set" + prop)(mycolour)



class FormDialog(wx.Dialog):
    """
    Dialog for displaying a complex editable form.
    Uses ComboBox for fields with choices.
    Uses two ListBoxes for list fields.

    @param   props  [{
       name:          field name
       ?type:         (bool | list | anything) if field has direct content,
                      or callback(dialog, field, panel, data) making controls
       ?label:        field label if not using name
       ?help:         field tooltip
       ?path:         [data path, if, more, complex, nesting]
       ?choices:      [value, ] or callback(field, path, data) returning list
       ?choicesedit   true if value not limited to given choices
       ?component     specific wx component to use
       ?toggle:       if true, field is toggle-able and children hidden when off
       ?children:     [{field}, ]
       ?link:         "name" of linked field, cleared and repopulated on change
       ?tb:           [{type, ?help}] for SQLiteTextCtrl component, adds toolbar,
                      supported toolbar buttons "open" and "paste"
    }]
    @param   autocomp  list of words to add to SQLiteTextCtrl autocomplete
    """

    def __init__(self, parent, title, props=None, data=None, edit=None, autocomp=None):
        wx.Dialog.__init__(self, parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self._ignore_change = False
        self._editmode = True
        self._comps    = collections.defaultdict(list) # {(path): [wx component, ]}
        self._autocomp = autocomp
        self._toggles  = {} # {(path): wx.CheckBox, }
        self._props    = []
        self._data     = {}
        self._rows     = 0

        panel_wrap  = wx.ScrolledWindow(self)
        panel_items = self._panel = wx.Panel(panel_wrap)
        panel_wrap.SetScrollRate(0, 20)

        button_save   = wx.Button(self, label="OK",     id=wx.OK)
        button_cancel = wx.Button(self, label="Cancel", id=wx.CANCEL)

        button_save.SetDefault()
        self.SetEscapeId(wx.CANCEL)
        self.Bind(wx.EVT_BUTTON, self._OnClose, button_save)

        self.Sizer        = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons     = wx.BoxSizer(wx.HORIZONTAL)
        panel_wrap.Sizer  = wx.BoxSizer(wx.VERTICAL)
        panel_items.Sizer = wx.GridBagSizer(hgap=5, vgap=0)

        panel_items.Sizer.SetEmptyCellSize((0, 0))
        panel_wrap.Sizer.Add(panel_items, border=10, proportion=1, flag=wx.RIGHT | wx.GROW)

        sizer_buttons.Add(button_save,   border=10, flag=wx.LEFT)
        sizer_buttons.Add(button_cancel, border=10, flag=wx.LEFT)

        self.Sizer.Add(panel_wrap, border=15, proportion=1, flag=wx.LEFT | wx.TOP | wx.GROW)
        self.Sizer.Add(sizer_buttons, border=5, flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)

        for x in self, panel_wrap, panel_items:
            ColourManager.Manage(x, "ForegroundColour", wx.SYS_COLOUR_BTNTEXT)
            ColourManager.Manage(x, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)
        self.Populate(props, data, edit)

        if self._editmode:
            self.MinSize = (440, panel_items.Size[1] + 80)
        else:
            self.MinSize = (440, panel_items.Size[1] + 10)
            self.SetEscapeId(wx.OK)
            self.Fit()
            button_cancel.Hide()
        self.CenterOnParent()


    def Populate(self, props, data, edit=None):
        """
        Clears current content, if any, adds controls to dialog,
        and populates with data.
        """
        self._ignore_change = True
        self._props = copy.deepcopy(props or [])
        self._data  = copy.deepcopy(data  or {})
        if edit is not None: self._editmode = edit
        self._rows  = 0

        while self._panel.Sizer.Children: self._panel.Sizer.Remove(0)
        for c in self._panel.Children: c.Destroy()
        self._toggles.clear()
        self._comps.clear()

        for f in self._props: self._AddField(f)

        for f in self._props: self._PopulateField(f)
        self._panel.Sizer.AddGrowableCol(6, 1)
        if len(self._comps) == 1: self._panel.Sizer.AddGrowableRow(0, 1)
        self._ignore_change = False
        self.Layout()


    def GetData(self):
        """Returns the current data values."""
        result = copy.deepcopy(self._data)
        for p in sorted(self._toggles, key=len, reverse=True):
            if not self._toggles[p].Value:
                ptr = result
                for x in p[:-1]: ptr = ptr.get(x) or {}
                ptr.pop(p[-1], None)
        return result


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


    def _DelValue(self, field, path=()):
        """Deletes field data value."""
        ptr = self._data
        path = field.get("path") or path
        for x in path: ptr = ptr.get(x, {})
        ptr.pop(field["name"], None)


    def _GetField(self, name, path=()):
        """Returns field from props."""
        fields, path = self._props, list(path) + [name]
        while fields:
            for f in fields:
                if [f["name"]] == path: return f
                if f["name"] == path[0] and f.get("children"):
                    fields, path = f["children"], path[1:]
                    break # for f


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


    def _AddField(self, field, path=()):
        """Adds field controls to dialog."""
        callback = field["type"] if callable(field.get("type")) \
                   and field["type"] not in (bool, list) else None
        if not callback and not self._editmode and self._GetValue(field, path) is None: return
        MAXCOL = 8
        parent, sizer = self._panel, self._panel.Sizer
        level, fpath = len(path), path + (field["name"], )

        col = 0
        if field.get("toggle") and self._editmode:
            toggle = wx.CheckBox(parent, label=field["label"] if "label" in field else field["name"])
            if field.get("help"): toggle.ToolTip = field["help"]
            sizer.Add(toggle, border=5, pos=(self._rows, level), span=(1, 2), flag=wx.TOP | wx.BOTTOM)
            self._comps[fpath].append(toggle)
            self._toggles[tuple(field.get("path") or fpath)] = toggle
            self._BindHandler(self._OnToggleField, toggle, field, path, toggle)
            col += 2
        elif field.get("toggle"):
            # Show ordinary label in view mode, checkbox goes very gray
            label = wx.StaticText(parent, label=field["label"] if "label" in field else field["name"])
            if field.get("help"): label.ToolTip = field["help"]
            sizer.Add(label, border=5, pos=(self._rows, level), span=(1, 2), flag=wx.TOP | wx.BOTTOM)
            col += 2

        if callback: callback(self, field, parent, self._data)
        elif not field.get("toggle") or any(field.get(x) for x in ["type", "choices", "component"]):
            ctrls = self._MakeControls(field, path)
            for i, c in enumerate(ctrls):
                colspan = 2 if isinstance(c, wx.StaticText) else MAXCOL - level - col
                brd, BRD = (5, wx.BOTTOM) if isinstance(c, wx.CheckBox) else (0, 0)
                sizer.Add(c, border=brd, pos=(self._rows, level + col), span=(1, colspan), flag=BRD | wx.GROW)
                col += colspan

        self._rows += 1
        for f in field.get("children") or (): self._AddField(f, fpath)


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
            listbox1, listbox2 = (x for x in ctrls if isinstance(x, wx.ListBox))
            listbox1.SetItems([x for x in choices if x not in value])
            listbox2.SetItems(value or [])
            listbox1.Enable(self._editmode)
            listbox2.Enable(self._editmode)
            for c in ctrls:
                if isinstance(c, wx.Button): c.Enable(self._editmode)
        else:
            for i, c in enumerate(ctrls):
                if not i and isinstance(c, wx.CheckBox) and field.get("toggle"):
                    c.Value = (value is not None)
                    self._OnToggleField(field, path, c)
                    c.Enable(self._editmode)
                    continue # for i, c
                if isinstance(c, wx.stc.StyledTextCtrl):
                    c.SetText(value or "")
                    if self._autocomp and isinstance(c, SQLiteTextCtrl):
                        c.AutoCompClearAdded()
                        c.AutoCompAddWords(self._autocomp)
                elif isinstance(c, wx.CheckBox): c.Value = bool(value)
                else:
                    if isinstance(c, wx.ComboBox): c.SetItems(choices)
                    if isinstance(value, (list, tuple)): value = "".join(value)
                    c.Value = "" if value is None else value

                if isinstance(c, wx.TextCtrl): c.SetEditable(self._editmode)
                else: c.Enable(self._editmode)

        for f in field.get("children") or (): self._PopulateField(f, fpath)


    def _MakeControls(self, field, path=()):
        """Returns a list of wx components for field."""
        result = []
        parent, sizer, ctrl = self._panel, self._panel.Sizer, None
        fpath = path + (field["name"], )
        label = field["label"] if "label" in field else field["name"]
        accname = "ctrl_%s" % self._rows # Associating label click with control

        if list is field.get("type"):
            if not field.get("toggle") and field.get("type") not in (bool, list):
                result.append(wx.StaticText(parent, label=label, name=accname + "_label"))

            sizer_f = wx.BoxSizer(wx.VERTICAL)
            sizer_l = wx.BoxSizer(wx.HORIZONTAL)
            sizer_b1 = wx.BoxSizer(wx.VERTICAL)
            sizer_b2 = wx.BoxSizer(wx.VERTICAL)
            ctrl1 = wx.ListBox(parent, style=wx.LB_EXTENDED)
            b1    = wx.Button(parent, label=">", size=(30, -1))
            b2    = wx.Button(parent, label="<", size=(30, -1))
            ctrl2 = wx.ListBox(parent, style=wx.LB_EXTENDED)
            b3    = wx.Button(parent, label=u"\u2191", size=(20, -1))
            b4    = wx.Button(parent, label=u"\u2193", size=(20, -1))

            b1.ToolTip = "Add selected from left to right"
            b2.ToolTip = "Remove selected from right"
            b3.ToolTip = "Move selected items higher"
            b4.ToolTip = "Move selected items lower"
            ctrl1.SetName(accname)
            ctrl1.MinSize = ctrl2.MinSize = (150, 100)
            if field.get("help"): ctrl1.ToolTip = field["help"]

            sizer_b1.Add(b1); sizer_b1.Add(b2)
            sizer_b2.Add(b3); sizer_b2.Add(b4)
            sizer_l.Add(ctrl1, proportion=1)
            sizer_l.Add(sizer_b1, flag=wx.ALIGN_CENTER_VERTICAL);
            sizer_l.Add(ctrl2, proportion=1)
            sizer_l.Add(sizer_b2, flag=wx.ALIGN_CENTER_VERTICAL);

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
            # Special case, add toolbar buttons to STC
            sizer_top = wx.BoxSizer(wx.HORIZONTAL)
            sizer_stc = wx.BoxSizer(wx.VERTICAL)

            mylabel = wx.StaticText(parent, label=label, name=accname + "_label")
            tb = wx.ToolBar(parent, style=wx.TB_FLAT | wx.TB_NODIVIDER)
            ctrl = field["component"](parent)

            OPTS = {"open":  {"id": wx.ID_OPEN,  "bmp": wx.ART_FILE_OPEN, "handler": self._OnOpenFile},
                    "paste": {"id": wx.ID_PASTE, "bmp": wx.ART_PASTE,     "handler": self._OnPaste}, }
            for prop in field["tb"]:
                opts = OPTS[prop["type"]]
                bmp = wx.ArtProvider.GetBitmap(opts["bmp"], wx.ART_TOOLBAR, (16, 16))
                tb.SetToolBitmapSize(bmp.Size)
                tb.AddLabelTool(opts["id"], "", bitmap=bmp, shortHelp=prop.get("help", ""))
                tb.Bind(wx.EVT_TOOL, functools.partial(opts["handler"], field, path), id=opts["id"])
            tb.Realize()
            ctrl.SetName(accname)

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
                ctrl = wx.CheckBox(parent, label=label) if self._editmode \
                       else wx.StaticText(parent, label=label)
            elif "choices" in field:
                style = wx.CB_DROPDOWN | (0 if field.get("choicesedit") else wx.CB_READONLY)
                ctrl = wx.ComboBox(parent, style=style)
            else:
                ctrl = wx.TextCtrl(parent)

            result.append(ctrl)
            self._BindHandler(self._OnChange, ctrl, field, path)

        for i, x in enumerate(result):
            if not isinstance(x, wx.Window): continue # for i, x
            self._comps[fpath].append(x)
            if not i: continue # for i, x
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
        value = event.EventObject.Value
        if isinstance(value, basestring) \
        and (not isinstance(event.EventObject, wx.stc.StyledTextCtrl)
        or not value.strip()): value = value.strip()
        self._SetValue(field, value, path)
        if field.get("link"):
            linkfield = self._GetField(field["link"], path)
            self._DelValue(linkfield, path)
            self._PopulateField(linkfield, path)


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
        selecteds = map(listbox1.GetString, indexes)

        for i in indexes[::-1]: listbox1.Delete(i)
        listbox2.AppendItems(selecteds)
        self._SetValue(field, listbox2.GetItems(), path)


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
        items2 = listbox2.GetItems()
        allchoices = self._GetChoices(field, path)
        listbox1.SetItems([x for x in allchoices if x not in items2])
        self._SetValue(field, items2, path)


    def _OnMoveInList(self, field, path, direction, event):
        """Handler for moving selected items up/down within listbox."""
        _, listbox2 = (x for x in self._comps[path + (field["name"], )]
                       if isinstance(x, wx.ListBox))
        indexes = listbox2.GetSelections()
        selecteds, items = map(listbox2.GetString, indexes), listbox2.GetItems()

        if not indexes or direction < 0 and not indexes[0] \
        or direction > 0 and indexes[-1] == len(items) - 1: return

        for i in range(len(items))[::-direction]:
            if i not in indexes: continue # for i
            i2 = i + direction
            items[i], items[i2] = items[i2], items[i]

        listbox2.SetItems(items)
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
        for f in field.get("children", []):
            for c in self._comps.get(fpath + (f["name"], ), []):
                ctrls.append((f, fpath, c))

        on = event.EventObject.Value if event else ctrl.Value
        for f, p, c in ctrls:
            # Never hide field-level toggle itself
            if isinstance(c, wx.CheckBox) and f.get("toggle") and p == path:
                continue # for f, p, c

            fon = on
            # Hide field children that are toggled off
            if not isinstance(c, wx.CheckBox) and f.get("toggle") \
            and p != path and self._GetValue(f, p) is None:
                fon = False

            c.Show(fon)
        if on and self._GetValue(field, path) is None:
            self._SetValue(field, {} if field.get("children") else "", path)
        self.Layout()


    def _OnOpenFile(self, field, path, event=None):
        """Handler for opening file dialog and loading file contents to STC field."""
        dialog = wx.FileDialog(
            self, message="Open file", defaultFile="",
            wildcard="SQL file (*.sql)|*.sql|All files|*.*",
            style=wx.FD_FILE_MUST_EXIST | wx.FD_OPEN | wx.RESIZE_BORDER
        )
        if wx.ID_OK != dialog.ShowModal(): return
        fpath = path + (field["name"], )
        ctrl = self._comps[fpath][0]
        filename = dialog.GetPath()
        ctrl.LoadFile(filename)
        self._SetValue(field, ctrl.GetText(), path)


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
        self.Hide()
        self.IsModal() and self.EndModal(event.GetId())



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

        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseEvent)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.OnMouseCaptureLostEvent)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_SET_FOCUS, self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnFocus)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)

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
            x = 10 + (width - self.DoGetBestSize().width) / 2

        dc.Font = self.Font
        dc.Brush = BRUSH(self.BackgroundColour)
        if self.IsThisEnabled():
            dc.TextForeground = self.ForegroundColour
        else:
            graycolour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
            dc.TextForeground = graycolour
        dc.Pen = PEN(dc.TextForeground)
        dc.Clear()

        is_focused = (self.FindFocus() == self)

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
            draw_focus = (self._label or self._note) or self._press or \
                         (is_focused and wx.GetKeyState(wx.WXK_SPACE))
            if draw_focus and hasattr(wx.Pen, "Stipple"):
                pen = PEN(dc.TextForeground, 1, wx.PENSTYLE_STIPPLE)
                pen.Stipple, dc.Pen = NoteButton.BMP_MARQUEE, pen
                dc.DrawRectangle(4, 4, width - 8, height - 8)
            elif draw_focus:
                brush = BRUSH(dc.TextForeground)
                brush.SetStipple(NoteButton.BMP_MARQUEE)
                dc.Brush = brush
                dc.Pen = wx.TRANSPARENT_PEN
                dc.DrawRectangle(4, 4, width - 8, height - 8)
                dc.Brush = BRUSH(self.BackgroundColour)
                dc.DrawRectangle(5, 5, width - 10, height - 10)
            dc.Pen = PEN(dc.TextForeground)

        if self._press or (is_focused and wx.GetKeyState(wx.WXK_SPACE)):
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
            dc.Pen = wx.Pen(self.ForegroundColour)
            for line in self._text_label.split("\n"):
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
        """Refreshes display if pressing space."""
        if not event.AltDown() and event.UnicodeKey in [wx.WXK_SPACE]:
            self.Refresh()


    def OnKeyUp(self, event):
        """Fires button event on releasing space or enter."""
        skip = True
        if not event.AltDown():
            key = event.UnicodeKey
            if key in [wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
                button_event = wx.PyCommandEvent(wx.EVT_BUTTON.typeId, self.Id)
                button_event.EventObject = self
                wx.PostEvent(self, button_event)
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
    Enabled = property(Enable, IsEnabled)


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
                 style=wx.CAPTION | wx.CLOSE_BOX | wx.FRAME_FLOAT_ON_PARENT):
        wx.Dialog.__init__(self, parent, title=title, style=style)
        self._is_cancelled = False

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel = self._panel = wx.Panel(self)
        sizer = self._panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        label = self._label_message = wx.StaticText(panel, label=message)
        sizer.Add(label, border=2*8, flag=wx.LEFT | wx.TOP)
        gauge = self._gauge = wx.Gauge(panel, range=maximum, size=(300,-1),
                              style=wx.GA_HORIZONTAL | wx.PD_SMOOTH)
        sizer.Add(gauge, border=2*8, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.GROW)
        gauge.Value = 0
        if cancel:
            self._button_cancel = wx.Button(self._panel, id=wx.ID_CANCEL)
            sizer.Add(self._button_cancel, border=8,
                      flag=wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL)
            self.Bind(wx.EVT_BUTTON, self.OnCancel, self._button_cancel)
            self.Bind(wx.EVT_CLOSE, self.OnCancel)
        else:
            sizer.Add((8, 8))

        self.Sizer.Add(panel, flag=wx.GROW)
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
            self._label_message.Label = message
        self._gauge.Value = value
        self.Refresh()
        return not self._is_cancelled


    def OnCancel(self, event):
        """
        Handler for cancelling the dialog, hides the window.
        """
        self._is_cancelled = True
        self.Hide()


    def SetGaugeForegroundColour(self, colour):
        self._gauge.ForegroundColour = colour



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

        button_save = wx.Button(panelwrap, label="Save")
        button_reset = wx.Button(panelwrap, label="Restore defaults")
        button_cancel = wx.Button(panelwrap, label="Cancel", id=wx.CANCEL)

        self.Bind(wx.EVT_BUTTON, self._OnSave, button_save)
        self.Bind(wx.EVT_BUTTON, self._OnReset, button_reset)
        self.Bind(wx.EVT_BUTTON, self._OnCancel, button_cancel)

        button_save.SetDefault()
        self.SetEscapeId(wx.CANCEL)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        panelwrap.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_items = self.sizer_items = wx.GridBagSizer(hgap=5, vgap=1)

        panel.Sizer.Add(sizer_items, proportion=1, border=5, flag=wx.GROW | wx.RIGHT)
        panelwrap.Sizer.Add(panel, proportion=1, border=10, flag=wx.GROW | wx.ALL)
        for b in (button_save, button_reset, button_cancel):
            sizer_buttons.Add(b, border=10, flag=wx.LEFT)
        panelwrap.Sizer.Add(sizer_buttons, border=10, flag=wx.ALL | wx.ALIGN_RIGHT)
        self.Sizer.Add(panelwrap, proportion=1, flag=wx.GROW)

        self.MinSize, self.Size = (320, 180), (420, 420)
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def AddProperty(self, name, value, help="", default=None, typeclass=unicode):
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
        tip = wx.StaticText(self.panel, label=help)

        ctrl.Value = self._GetValueForCtrl(value, typeclass)
        ctrl.ToolTip = label.ToolTip = "Value of type %s%s." % (
            typeclass.__name__,
            "" if default is None else ", default %s" % repr(default))
        tip.ForegroundColour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        tipfont, tipfont.PixelSize = tip.Font, (0, 9)
        tip.Font = tipfont
        tip.Wrap(self.panel.Size[0] - 20)
        for x in (label, tip): x.Bind(wx.EVT_LEFT_UP, label_handler)

        self.sizer_items.Add(label, pos=(row, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        self.sizer_items.Add(ctrl, pos=(row, 1), flag=ctrl_flag)
        self.sizer_items.Add(tip, pos=(row + 1, 0), span=(1, 2),
                             flag=wx.BOTTOM, border=3)
        self.properties.append((name, typeclass, value, default, label, ctrl))


    def Realize(self):
        """Lays out the properties, to be called when adding is completed."""
        self.panel.SetScrollRate(20, 20)
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
        if all_ok:
            self.Hide()
            self.IsModal() and self.EndModal(wx.ID_OK)
        else:
            self.Refresh()


    def _OnReset(self, event):
        """Handler for clicking reset, restores default values if available."""
        for name, typeclass, orig, default, label, ctrl in self.properties:
            if default is not None:
                ctrl.Value = self._GetValueForCtrl(default, typeclass)
            if self.COLOUR_ERROR == ctrl.ForegroundColour:
                label.ForegroundColour = ctrl.ForegroundColour = self.ForegroundColour
        self.Refresh()


    def _OnCancel(self, event):
        """Handler for clicking cancel, hides the dialog."""
        self.Hide()
        self.IsModal() and self.EndModal(wx.ID_CANCEL)


    def _GetValueForType(self, value, typeclass):
        """Returns value in type expected, or None on failure."""
        try:
            result = typeclass(value)
            isinstance(result, basestring) and result.strip()[0] # Reject empty
            return result
        except Exception:
            return None


    def _GetValueForCtrl(self, value, typeclass):
        """Returns the value in type suitable for appropriate wx control."""
        value = tuple(value) if isinstance(value, list) else value
        return "" if value is None else value \
               if isinstance(value, (basestring, bool)) else unicode(value)



class ScrollingHtmlWindow(wx.html.HtmlWindow):
    """
    HtmlWindow that remembers its scroll position on resize and append.
    """

    def __init__(self, *args, **kwargs):
        wx.html.HtmlWindow.__init__(self, *args, **kwargs)
        self.Bind(wx.EVT_SCROLLWIN, self._OnScroll)
        self.Bind(wx.EVT_SIZE, self._OnSize)
        self._last_scroll_pos = [0, 0]
        self._last_scroll_range = [0, 1]


    def _OnSize(self, event):
        """
        Handler for sizing the HtmlWindow, sets new scroll position based
        previously stored one (HtmlWindow loses its scroll position on resize).
        """
        event.Skip() # Allow event to propagate wx handler
        for i in range(2):
            orient = wx.VERTICAL if i else wx.HORIZONTAL
            # Division can be > 1 on first resizings, bound it to 1.
            pos, rng = self._last_scroll_pos[i], self._last_scroll_range[i]
            ratio = pos / float(rng) if rng else 0.0
            ratio = min(1, pos / float(rng) if rng else 0.0)
            self._last_scroll_pos[i] = ratio * self.GetScrollRange(orient)
        try:
            # Execute scroll later as something resets it after this handler
            wx.CallLater(50, lambda:
                self.Scroll(*self._last_scroll_pos) if self else None)
        except Exception:
            pass # CallLater fails if not called from the main thread


    def _OnScroll(self, event=None):
        """
        Handler for scrolling the window, stores scroll position
        (HtmlWindow loses it on resize).
        """
        if event: event.Skip() # Allow event to propagate wx handler
        p, r = self.GetScrollPos, self.GetScrollRange
        self._last_scroll_pos   = [p(x) for x in (wx.HORIZONTAL, wx.VERTICAL)]
        self._last_scroll_range = [r(x) for x in (wx.HORIZONTAL, wx.VERTICAL)]


    def Scroll(self, x, y):
        """Scrolls the window so the view start is at the given point."""
        self._last_scroll_pos = [x, y]
        return super(ScrollingHtmlWindow, self).Scroll(x, y)


    def SetPage(self, source):
        """Sets the source of a page and displays it."""
        self._last_scroll_pos, self._last_scroll_range = [0, 0], [0, 1]
        return super(ScrollingHtmlWindow, self).SetPage(source)


    def AppendToPage(self, source):
        """
        Appends HTML fragment to currently displayed text, refreshes the window
        and restores scroll position.
        """
        p, r, s = self.GetScrollPos, self.GetScrollRange, self.GetScrollPageSize
        self.Freeze()
        try:
            pos, rng, size = (x(wx.VERTICAL) for x in [p, r, s])
            result = super(ScrollingHtmlWindow, self).AppendToPage(source)
            if size != s(wx.VERTICAL) or pos + size >= rng:
                pos = r(wx.VERTICAL) # Keep scroll at bottom edge
            self.Scroll(0, pos), self._OnScroll()
        finally: self.Thaw()
        return result



class SearchCtrl(wx.TextCtrl):
    """
    A text control with search description.
    Fires EVT_TEXT_ENTER event on text change.
    """


    def __init__(self, parent, description="", **kwargs):
        """
        @param   description  description text shown if nothing entered yet
        """
        wx.TextCtrl.__init__(self, parent, **kwargs)
        self._text_colour = self._desc_colour = None
        ColourManager.Manage(self, "_text_colour", wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(self, "_desc_colour", wx.SYS_COLOUR_GRAYTEXT)

        self._description = description
        self._description_on = False # Is textbox filled with description?
        self._ignore_change  = False # Ignore text change in event handlers
        if not self.Value:
            self.Value = self._description
            self.SetForegroundColour(self._desc_colour)
            self._description_on = True

        self.Bind(wx.EVT_SET_FOCUS,          self.OnFocus,        self)
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnFocus,        self)
        self.Bind(wx.EVT_KEY_DOWN,           self.OnKeyDown,      self)
        self.Bind(wx.EVT_TEXT,               self.OnText,         self)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)


    def OnFocus(self, event):
        """
        Handler for focusing/unfocusing the control, shows/hides description.
        """
        event.Skip() # Allow to propagate to parent, to show having focus
        self._ignore_change = True
        if self and self.FindFocus() == self:
            if self._description_on:
                self.Value = ""
            self.SelectAll()
        elif self:
            if self._description and not self.Value:
                # Control has been unfocused, set and colour description
                wx.TextCtrl.SetValue(self, self._description)
                self.SetForegroundColour(self._desc_colour)
                self._description_on = True
        self._ignore_change = False


    def OnKeyDown(self, event):
        """Handler for keypress, empties text on escape."""
        event.Skip()
        if event.KeyCode in [wx.WXK_ESCAPE] and self.Value:
            self.Value = ""
            wx.PostEvent(self, wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER))


    def OnText(self, event):
        """Handler for text change, fires TEXT_ENTER event."""
        if self._ignore_change: return
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER)
        evt.String = self.Value
        wx.PostEvent(self, evt)


    def OnSysColourChange(self, event):
        """Handler for system colour change, updates text colour."""
        event.Skip()
        colour = self._desc_colour if self._description_on else self._text_colour
        self.SetForegroundColour(colour)


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
        return wx.TextCtrl.SetValue(self, value)
    Value = property(GetValue, SetValue)



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
        frmt = lambda: lambda r, c: "" if r.get(c) is None else unicode(r[c])
        self._formatters = collections.defaultdict(frmt)
        id_copy = wx.NewIdRef().Id
        entries = [(wx.ACCEL_CTRL, x, id_copy)
                   for x in (ord("C"), wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT)]
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
        return len(self._id_rows)


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
        sortstate = self.GetSortState()

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

        datas     = map(self.GetItemMappedData, selecteds)
        image_ids = map(self._id_images.get, map(self.GetItemData, selecteds))

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
        try: wx.CallAfter(self.Children[0].DragFinish, HackEvent())
        except: raise


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
                    dy = (idindx[item_id] - self.GetCountPerPage() / 2) * lh
                    self.ScrollList(0, dy)


    def _RowMatchesFilter(self, row):
        """Returns whether the row dict matches the current filter."""
        result = True
        if self._filter:
            result = False
            patterns = map(re.escape, self._filter.split())
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
        if isinstance(item1, unicode) and isinstance(item2, unicode):
            cmpVal = locale.strcoll(item1.lower(), item2.lower())
        elif isinstance(item1, str) or isinstance(item2, str):
            items = item1.lower(), item2.lower()
            cmpVal = locale.strcoll(*map(unicode, items))
        else:
            if item1 is None:
                cmpVal = -1
            elif item2 is None:
                cmpVal = 1
            else:
                cmpVal = cmp(item1, item2)

        # If items are equal, pick something else to make the sort value unique
        if cmpVal == 0:
            cmpVal = apply(cmp, self.GetSecondarySortValues(col, key1, key2))

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
    KEYWORDS = map(unicode, sorted([
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
    ]))
    """SQLite data types."""
    TYPEWORDS = map(unicode, sorted([
        "BLOB",
        "INTEGER", "BIGINT", "INT", "INT2", "INT8", "MEDIUMINT", "SMALLINT",
                   "TINYINT", "UNSIGNED",
        "NUMERIC", "BOOLEAN", "DATE", "DATETIME", "DECIMAL",
        "TEXT", "CHARACTER", "CLOB", "NCHAR", "NVARCHAR", "VARCHAR", "VARYING",
        "REAL", "DOUBLE", "FLOAT", "PRECISION",
    ]))
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

        self.autocomps_added.update(map(unicode, words))
        # A case-insensitive autocomp has to be sorted, will not work
        # properly otherwise. UserList would support arbitrarily sorting.
        self.autocomps_total = sorted(list(self.autocomps_added) + 
                                      map(unicode, self.KEYWORDS),
                                      cmp=self.stricmp)


    def AutoCompAddSubWords(self, word, subwords):
        """
        Adds more subwords used in autocompletion, will be shown after the word
        and a dot.
        """
        subwords = [x for x in subwords if not self.SAFEBYTE_RGX.search(x)]
        if not subwords or self.SAFEBYTE_RGX.search(word): return

        word, subwords = unicode(word), map(unicode, subwords)
        if word not in self.autocomps_added:
            self.AutoCompAddWords([word])
        if subwords:
            word_key = word.upper()
            self.autocomps_subwords.setdefault(word_key, set())
            self.autocomps_subwords[word_key].update(subwords)


    def AutoCompClearAdded(self):
        """Clears words added in AutoCompAddWords and AutoCompAddSubWords."""
        self.autocomps_added &= set(["sqlite_master"])
        del self.autocomps_total[:]
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
        if self.AutoCompActive(): return event.Skip()
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) \
        and self.LinesOnScreen() < 2: return
        if wx.WXK_TAB != event.KeyCode: return event.Skip()

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
            if wx.WXK_SPACE == event.UnicodeKey and event.CmdDown():
                # Start autocomp when user presses Ctrl+Space
                do_autocomp = True
            elif not event.CmdDown():
                # Check if we have enough valid text to start autocomplete
                char = None
                try: # Not all keycodes can be chars
                    char = chr(event.UnicodeKey).decode("latin1")
                except Exception:
                    pass
                if char not in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, 10, 13] \
                and char is not None:
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
                            words = sorted(
                                self.autocomps_subwords[text], cmp=self.stricmp
                            )
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
        elif self.AutoCompActive() and wx.WXK_DELETE == event.KeyCode:
            self.AutoCompCancel()
        if skip: event.Skip()


    def stricmp(self, a, b):
        return cmp(a.lower(), b.lower())



TabLeftDClickEvent, EVT_TAB_LEFT_DCLICK = wx.lib.newevent.NewEvent()

class TabbedHtmlWindow(wx.Panel):
    """
    HtmlWindow with tabs for different content pages.
    """

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.html.HW_DEFAULT_STYLE,
                 name=""):
        wx.Panel.__init__(self, parent, pos=pos, size=size, style=style)
        # [{"title", "content", "id", "info", "scrollpos", "scrollrange"}]
        self._tabs = []
        self._default_page = ""      # Content shown on the blank page
        self._delete_callback = None # Function called after deleting a tab
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_WINDOW)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = self._notebook = wx.lib.agw.flatnotebook.FlatNotebook(
            self, size=(-1, 27),
            agwStyle=wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_VC8)
        self._html = wx.html.HtmlWindow(self, style=style, name=name)

        self.Sizer.Add(notebook, flag=wx.GROW)
        self.Sizer.Add(self._html, proportion=1, flag=wx.GROW)

        self._html.Bind(wx.EVT_SIZE, self._OnSize)
        notebook.GetTabArea().Bind(wx.EVT_LEFT_DCLICK, self._OnLeftDClickTabArea)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._OnChangeTab)
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
        for name in ["DeletePage", "GetSelection", "GetTabAreaColour", "SetTabAreaColour"]:
            setattr(self, name, getattr(self._notebook, name))

        self._CreateTab(0, "") # Make default empty tab in notebook with no text
        self.Layout()


    def _OnLeftDClickTabArea(self, event):
        """Fires a TabLeftDClickEvent if a tab header was double-clicked."""
        area = self._notebook.GetTabArea()
        where, tab = area.HitTest(event.GetPosition())
        if wx.lib.agw.flatnotebook.FNB_TAB == where and tab < len(self._tabs):
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
                wx.CallLater(50, lambda:
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
            self.SetActiveTab(self._notebook.GetSelection())
            # Forward event to TabbedHtmlWindow listeners
            wx.PostEvent(self.GetEventHandler(), event)


    def _OnDropTab(self, event):
        """Handler for dropping a dragged tab."""
        new, old = event.GetSelection(), event.GetOldSelection()
        new = min(new, len(self._tabs) - 1) # Can go over the edge
        if self._tabs and new != old and new >= 0:
            self._tabs[old], self._tabs[new] = self._tabs[new], self._tabs[old]


    def _OnDeleteTab(self, event):
        """Handler for clicking in notebook to close a tab."""
        if not self._tabs:
            event.Veto() # User clicked to delete the default page, cancel
        else:
            nb = self._notebook
            tab = self._tabs[event.GetSelection()]
            self._tabs.remove(tab)
            if 1 == nb.GetPageCount(): # Was the only page,
                nb.SetPageText(0, "")  # reuse as default empty tab
                event.Veto()
                self._SetPage(self._default_page)
                # Hide dropdown selector, remove X from tab style.
                style = nb.GetAGWWindowStyleFlag()
                style ^= wx.lib.agw.flatnotebook.FNB_X_ON_TAB | \
                         wx.lib.agw.flatnotebook.FNB_DROPDOWN_TABS_LIST
                nb.SetAGWWindowStyleFlag(style)
            else:
                index = min(nb.GetSelection(), nb.GetPageCount() - 2)
                self.SetActiveTab(index)
            if self._delete_callback:
                self._delete_callback(tab)


    def _CreateTab(self, index, title):
        """Creates a new tab in the tab container at specified index."""
        p = wx.Panel(self, size=(0,0))
        p.Hide() # Dummy empty window as notebook needs something to hold
        self._notebook.InsertPage(index, page=p, text=title, select=True)


    def _SetPage(self, content):
        """Sets current HTML page content."""
        self._html.SetPage(content)
        ColourManager.Manage(self._html, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def SetDeleteCallback(self, callback):
        """Sets the function called after deleting a tab, with tab data."""
        self._delete_callback = callback


    def SetDefaultPage(self, content):
        self._default_page = content
        if not self._tabs:
            self._SetPage(self._default_page)


    def InsertTab(self, index, title, id, content, info):
        """
        Inserts a new tab with the specified title and content at the specified
        index, and activates the new tab.
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


    def GetTabDataByID(self, id):
        """Returns the data of the tab with the specified ID, or None."""
        result = next((x for x in self._tabs if x["id"] == id), None)
        return result


    def SetTabDataByID(self, id, title, content, info, new_id=None):
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


    def SetActiveTab(self, index):
        """Sets active the tab at the specified index."""
        tab = self._tabs[index]
        self._notebook.SetSelection(index)
        self._html.Freeze()
        try:
            self._SetPage(tab["content"])
            self._html.Scroll(*tab["scrollpos"])
        finally: self._html.Thaw()


    def SetActiveTabByID(self, id):
        """Sets active the tab with the specified ID."""
        tab = next((x for x in self._tabs if x["id"] == id), None)
        index = self._tabs.index(tab)
        self._notebook.SetSelection(index)
        self._html.Freeze()
        try:
            self._SetPage(tab["content"])
            self._html.Scroll(*tab["scrollpos"])
        finally: self._html.Thaw()


    def GetActiveTabData(self):
        """Returns all the data for the active tab."""
        if self._tabs:
            return self._tabs[self._notebook.GetSelection()]


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
        if self and self.FindFocus() == self:
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
        if event.KeyCode in [wx.WXK_DOWN, wx.WXK_UP]:
            if visible:
                step = 1 if (wx.WXK_UP != event.KeyCode) else -1
                itemcount = len(self._choices)
                selected_new = min(itemcount - 1, max(0, selected + step))
                self._listbox.Select(selected_new)
                ensured = selected_new + (0
                          if selected_new != len(self._choices) - 1 else 2)
                self._listbox.EnsureVisible(ensured)
            self.ShowDropDown()
            skip = False
        elif event.KeyCode in [wx.WXK_PAGEDOWN, wx.WXK_PAGEUP]:
            if visible:
                step = 1 if (wx.WXK_PAGEUP != event.KeyCode) else -1
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
        elif event.KeyCode in [wx.WXK_BACK, wx.WXK_DELETE]:
            self._skip_autocomplete = True
            self.ShowDropDown()
        if visible:
            if selected_new is not None: # Replace textbox value with new text
                self._ignore_textchange = True
                self.Value = self._listbox.GetItemText(selected_new)
                self.SetInsertionPointEnd()
            if wx.WXK_RETURN == event.KeyCode:
                self.ShowDropDown(False)
            if wx.WXK_ESCAPE == event.KeyCode:
                self.ShowDropDown(False)
                skip = False
        else:
            if wx.WXK_ESCAPE == event.KeyCode:
                if self._value_last != self.Value:
                    self.Value = self._value_last
                    self.SelectAll()
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
            if size.GetWidth() <> width:
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


    def FindAndActivateItem(self, match=None, expand=False, **kwargs):
        """
        Selects tree item where match returns true for item data, and invokes
        handlers registered for wx.EVT_TREE_ITEM_ACTIVATED. Expands all item
        parents.

        @param    match   callback(data associated with item): bool
                          or {key: value} to match in associated data dict
        @param    expand  expand matched item
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
            if expand: self.Expand(myitem)
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

    RootItem = property(lambda x: x.GetRootItem())


def YesNoMessageBox(message, caption, icon=wx.ICON_NONE, defaultno=False):
    """
    Opens a Yes/No messagebox that is closable by pressing Escape,
    returns dialog result.

    @param   icon       dialog icon to use, one of wx.ICON_XYZ
    @param   defaultno  True if No-button should be default
    """
    RES = {wx.ID_OK: wx.OK, wx.ID_CANCEL: wx.CANCEL}
    style = icon | wx.OK | wx.CANCEL | (wx.CANCEL_DEFAULT if defaultno else 0)
    dlg = wx.MessageDialog(None, message, caption, style)
    dlg.SetOKCancelLabels("&Yes", "&No")
    return wx.YES if wx.ID_OK == dlg.ShowModal() else wx.NO
