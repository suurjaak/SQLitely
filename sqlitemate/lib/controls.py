# -*- coding: utf-8 -*-
"""
Stand-alone GUI components for wx:

- BusyPanel(wx.Window):
  Primitive hover panel with a message that stays in the center of parent
  window.

- ColourManager(object):
  Updates managed component colours on Windows system colour change.

- EntryDialog(wx.Dialog):
  Non-modal text entry dialog with auto-complete dropdown, appears in lower
  right corner.

- NonModalOKDialog(wx.Dialog):
  A simple non-modal dialog with an OK button, stays on top of parent.

- NoteButton(wx.PyPanel, wx.Button):
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

- TabbedHtmlWindow(wx.PyPanel):
  wx.html.HtmlWindow with tabs for different content pages.
    
- TextCtrlAutoComplete(wx.TextCtrl):
  A text control with autocomplete using a dropdown list of choices. During
  typing, the first matching choice is appended to textbox value, with the
  appended text auto-selected.
  If wx.PopupWindow is not available (Mac), behaves like a common TextCtrl.
  Based on TextCtrlAutoComplete by Michele Petrazzo, from a post
  on 09.02.2006 in wxPython-users thread "TextCtrlAutoComplete",
  http://wxpython-users.1045709.n5.nabble.com/TextCtrlAutoComplete-td2348906.html

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.01.2012
@modified    29.08.2019
------------------------------------------------------------------------------
"""
import collections
import copy
import locale
import os
import re

import wx
import wx.html
import wx.lib.agw.flatnotebook
import wx.lib.agw.gradientbutton
try: # ShapedButton requires PIL, might not be installed
    import wx.lib.agw.shapedbutton
except Exception: pass 
import wx.lib.agw.ultimatelistctrl
import wx.lib.embeddedimage
import wx.lib.mixins.listctrl
import wx.lib.newevent
import wx.lib.wordwrap
import wx.stc


# Convenience methods for creating a wx.Brush and wx.Pen or returning cached.
BRUSH = lambda c, s=wx.SOLID: wx.TheBrushList.FindOrCreateBrush(c, s)
PEN = lambda c, w=1, s=wx.SOLID: wx.ThePenList.FindOrCreatePen(c, w, s)


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
        label = self._label = wx.StaticText(parent=self, label=label)
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
        @param   darkcolourmap    colours changed if dark background
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
        """Returns system colour as HTML colour hex string."""
        return wx.SystemSettings.GetColour(idx).GetAsString(wx.C2S_HTML_SYNTAX)


    @classmethod
    def GetColour(cls, colour):
        return wx.NamedColour(getattr(cls.colourcontainer, colour)) \
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



class NonModalOKDialog(wx.Dialog):
    """A simple non-modal dialog with an OK button, stays on top of parent."""

    def __init__(self, parent, title, message):
        wx.Dialog.__init__(self, parent=parent, title=title,
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
        self.Close()
        event.Skip()



class EntryDialog(wx.Dialog):
    """
    Non-modal text entry dialog with auto-complete dropdown, appears in lower
    right corner.
    Fires a wx.EVT_COMMAND_ENTER event on pressing Enter or button.
    """
    HIDE_TIMEOUT = 1500 # Milliseconds to wait for hiding after losing focus

    def __init__(self, parent, title, label="", value="", emptyvalue="", tooltip="", choices=[]):
        """
        @param   title       dialog window title
        @param   label       label before text entry, if any
        @param   value       default value of text entry
        @param   emptyvalue  gray text shown in text box if empty and unfocused
        @param   tooltip     tooltip shown for enter button
        """
        style = wx.CAPTION | wx.CLOSE_BOX | wx.STAY_ON_TOP
        wx.Dialog.__init__(self, parent=parent, title=title, style=style)
        self._hider = None # Hider callback wx.Timer

        if label:
            label_text = self._label = wx.StaticText(self, label=label)
        text = self._text = TextCtrlAutoComplete(
            self, description=emptyvalue, size=(200, -1),
            style=wx.TE_PROCESS_ENTER)
        tb = wx.ToolBar(parent=self, style=wx.TB_FLAT | wx.TB_NODIVIDER)

        text.Value = value
        text.SetChoices(choices)
        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR,
                                       (16, 16))
        tb.SetToolBitmapSize(bmp.Size)
        tb.AddLabelTool(wx.ID_FIND, "", bitmap=bmp, shortHelp=tooltip)
        tb.Realize()

        self.Bind(wx.EVT_ACTIVATE, self._OnActivate, self)
        text.Bind(wx.EVT_KEY_DOWN, self._OnKeyDown)
        self.Bind(wx.EVT_TEXT_ENTER, self._OnSearch, text)
        self.Bind(wx.EVT_TOOL, self._OnSearch, id=wx.ID_FIND)
        self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS, self._OnClearChoices, text)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_top = wx.BoxSizer(wx.HORIZONTAL)
        if label:
            sizer_top.Add(label_text, flag=wx.ALIGN_CENTER_VERTICAL |
                          wx.LEFT, border=5)
        sizer_top.Add(text, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=5)
        sizer_top.Add(tb, flag=wx.LEFT | wx.RIGHT |
                      wx.ALIGN_CENTER_VERTICAL, border=5)
        self.Sizer.Add(sizer_top, flag=wx.GROW | wx.TOP | wx.BOTTOM, border=5)
        self.Fit()
        x, y, w, h = wx.GetClientDisplayRect()
        self.Position = (x + w - self.Size.width, y + h - self.Size.height)
        self._pos_last = self.Position
        self._displayrect_last = (x, y, w, h)



    def Show(self, show=True):
        """Shows or hides the window, and raises it if shown."""
        if show:
            x, y, w, h = wx.GetClientDisplayRect()
            if (x, y, w, h) != self._displayrect_last:     # Display size has
                self.Position = (x + w - self.Size.width,  # changed, move to
                                 y + h - self.Size.height) # screen corner.
                self._displayrect_last = (x, y, w, h)
            self.Raise()
            self._text.SetFocus()
        wx.Dialog.Show(self, show)


    def GetValue(self):
        """Returns the text box value."""
        return self._text.Value
    def SetValue(self, value):
        """Sets the text box value."""
        self._text.Value = value
    Value = property(GetValue, SetValue)


    def SetChoices(self, choices):
        """Sets the auto-complete choices for text box."""
        self._text.SetChoices(choices)


    def _OnActivate(self, event):
        if not (event.Active or self._hider):
            self._hider = wx.CallLater(self.HIDE_TIMEOUT, self.Hide)
        elif event.Active and self._hider: # Kill the hiding timeout, if any
            self._hider.Stop()
            self._hider = None


    def _OnKeyDown(self, event):
        if wx.WXK_ESCAPE == event.KeyCode and not self._text.IsDropDownShown():
            self.Hide()
        event.Skip()


    def _OnSearch(self, event):
        findevent = wx.CommandEvent(wx.wxEVT_COMMAND_ENTER, self.GetId())
        wx.PostEvent(self, findevent)


    def _OnClearChoices(self, event):
        choice = wx.MessageBox("Clear search history?", self.Title,
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if wx.OK == choice:
            self._text.SetChoices([])



class NoteButton(wx.PyPanel, wx.Button):
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
        @param   
        """
        wx.PyPanel.__init__(self, parent, id, pos, size,
                            style | wx.FULL_REPAINT_ON_RESIZE, name)
        self._label = label
        self._note = note
        self._bmp = bmp
        self._bmp_disabled = bmp
        if bmp is not None and bmp.IsOk():
            img = bmp.ConvertToImage().ConvertToGreyscale()
            self._bmp_disabled = wx.BitmapFromImage(img) if img.IsOk() else bmp
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

        self._cursor_hover   = wx.StockCursor(wx.CURSOR_HAND)
        self._cursor_default = wx.StockCursor(wx.CURSOR_DEFAULT)

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
        w = 100 if self.Size.width < 100 else self.Size.width
        h = 40 if self.Size.height < 40 else self.Size.height
        if self._extent_label:    
            h1 = 10 + self._bmp.Size.height + 10
            h2 = 10 + self._extent_label[1] + 10 + self._extent_note[1] + 10
            h  = max(h1, h2)
        size = wx.Size(w, h)

        return size


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

            # Draw focus marquee.
            if not NoteButton.BMP_MARQUEE:
                NoteButton.BMP_MARQUEE = wx.EmptyBitmap(2, 2)
                dc_bmp = wx.MemoryDC()
                dc_bmp.SelectObject(NoteButton.BMP_MARQUEE)
                dc_bmp.Background = wx.Brush(self.BackgroundColour)
                dc_bmp.Clear()
                dc_bmp.Pen = wx.Pen(self.ForegroundColour)
                dc_bmp.DrawPointList([(0, 1), (1, 0)])
                dc_bmp.SelectObject(wx.NullBitmap)
            if hasattr(wx.Pen, "Stipple"):
                pen = PEN(dc.TextForeground, 1, wx.STIPPLE)
                pen.Stipple, dc.Pen = NoteButton.BMP_MARQUEE, pen
                dc.DrawRectangle(4, 4, width - 8, height - 8)
            else:
                brush = BRUSH(dc.TextForeground)
                brush.SetStipple(NoteButton.BMP_MARQUEE)
                dc.Brush = brush
                dc.Pen = wx.TRANSPARENT_PEN
                dc.DrawRectangle(4, 4, width - 8, height - 8)
                dc.Brush = BRUSH(self.BackgroundColour)
                dc.DrawRectangle(5, 5, width - 10, height - 10)
            dc.Pen = PEN(dc.TextForeground)

        if self._press or (is_focused and wx.GetKeyState(wx.WXK_SPACE)):
            # Button is being clicked with mouse: create sunken effect.
            colours = [(128, 128, 128)] * 2
            lines   = [(1, 1, width - 2, 1), (1, 1, 1, height - 2)]
            dc.DrawLineList(lines, [PEN(wx.Colour(*c)) for c in colours])
            x += 1; y += 1
        elif self._hover and self.IsThisEnabled():
            # Button is being hovered with mouse: create raised effect.
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
                          wx.FONTWEIGHT_BOLD, face=dc.Font.FaceName)
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
                            chars += line[i] # Double ampersand: add as one.
                    if i < len(line):
                        chars += line[i]
                    i += 1
                h += self._extent_label[2]
                text_label += chars + "\n"
        dc.DrawText(text_label, x, y)

        # Draw note
        _, label_h, _ = dc.GetMultiLineTextExtent(self._text_label)
        y += label_h + 10
        dc.Font = self.Font
        dc.DrawText(self._text_note, x, y)


    def WrapTexts(self):
        """Wraps button texts to current control size."""
        width, height = self.Size
        label = self._label
        self._text_label = label
        self._text_note = self._note
        WORDWRAP = wx.lib.wordwrap.wordwrap
        if width > 20 and height > 20:
            dc = wx.ClientDC(self)
        else: # Not properly sized yet: assume a reasonably fitting size
            dc, width, height = wx.MemoryDC(), 500, 100
            dc.SelectObject(wx.EmptyBitmap(500, 100))
        dc.Font = self.Font
        x = 10 + self._bmp.Size.width + 10
        self._text_note = WORDWRAP(self._text_note, width - 10 - x, dc)
        dc.Font = wx.Font(dc.Font.PointSize, dc.Font.Family, dc.Font.Style,
                          wx.FONTWEIGHT_BOLD, face=dc.Font.FaceName)
        self._text_label = WORDWRAP(self._text_label, width - 10 - x, dc)
        self._extent_label = dc.GetMultiLineTextExtent(self._text_label)
        self._extent_note = dc.GetMultiLineTextExtent(self._text_note)


    def OnPaint(self, event):
        """Handler for paint event, calls """
        dc = wx.BufferedPaintDC(self)
        self.Draw(dc)


    def OnSize(self, event):
        """Handler for size event, resizes texts and repaints control."""
        if event.Size != self._size:
            self._size = event.Size
            wx.CallAfter(lambda: self and (self.WrapTexts(), self.Refresh(),
                         self.InvalidateBestSize(), self.Parent.Layout()))
        event.Skip()


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
        if skip:
            event.Skip()


    def OnMouseEvent(self, event):
        """
        Mouse handler, creates hover/press border effects and fires button
        event on click.
        """
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
        event.Skip()


    def OnMouseCaptureLostEvent(self, event):
        """Handles MouseCaptureLostEvent, updating control UI if needed."""
        self._hover = self._press = False


    def ShouldInheritColours(self):
        return True


    def InheritsBackgroundColour(self):
        return True


    def Enable(self, enable=True):
        """
        Enable or disable this control for user input, returns True if the
        control state was changed.
        """
        self._enabled = enable
        result = wx.PyPanel.Enable(self, enable)
        if result:
            self.Refresh()
        return result


    def IsThisEnabled(self):
        """Returns the internal enabled state, independent of parent state."""
        if hasattr(wx.PyPanel, "IsThisEnabled"):
            result = wx.PyPanel.IsThisEnabled(self)
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
        wx.Dialog.__init__(self, parent=parent, title=title, style=style)
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
        wx.Dialog.__init__(self, parent=parent, title=title,
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.RESIZE_BORDER)
        self.properties = [] # [(name, type, orig_val, default, label, ctrl), ]

        panelwrap = wx.Panel(self)
        panel = self.panel = wx.lib.scrolledpanel.ScrolledPanel(panelwrap)

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
        ctrl.ToolTipString = label.ToolTipString = "Value of type %s%s." % (
            typeclass.__name__,
            "" if default is None else ", default %s" % repr(default))
        tip.ForegroundColour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        tipfont, tipfont.PixelSize = tip.Font, (0, 9)
        tip.Font = tipfont
        for x in (label, tip): x.Bind(wx.EVT_LEFT_UP, label_handler)

        self.sizer_items.Add(label, pos=(row, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        self.sizer_items.Add(ctrl, pos=(row, 1), flag=ctrl_flag)
        self.sizer_items.Add(tip, pos=(row + 1, 0), span=(1, 2),
                             flag=wx.BOTTOM, border=3)
        self.properties.append((name, typeclass, value, default, label, ctrl))


    def Realize(self):
        """Lays out the properties, to be called when adding is completed."""
        self.panel.SetupScrolling(scroll_x=False)
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
        event.Skip() # Allow event to propagate wx handler


    def _OnScroll(self, event=None):
        """
        Handler for scrolling the window, stores scroll position
        (HtmlWindow loses it on resize).
        """
        p, r = self.GetScrollPos, self.GetScrollRange
        self._last_scroll_pos   = [p(x) for x in (wx.HORIZONTAL, wx.VERTICAL)]
        self._last_scroll_range = [r(x) for x in (wx.HORIZONTAL, wx.VERTICAL)]
        if event: event.Skip() # Allow event to propagate wx handler


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
        self.Freeze()
        p, r, s = self.GetScrollPos, self.GetScrollRange, self.GetScrollPageSize
        pos, rng, size = (x(wx.VERTICAL) for x in [p, r, s])
        result = super(ScrollingHtmlWindow, self).AppendToPage(source)
        if size != s(wx.VERTICAL) or pos + size >= rng:
            pos = r(wx.VERTICAL) # Keep scroll at bottom edge
        self.Scroll(0, pos), self._OnScroll()
        self.Thaw()
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
        event.Skip() # Allow to propagate to parent, to show having focus


    def OnKeyDown(self, event):
        """Handler for keypress, empties text on escape."""
        if event.KeyCode in [wx.WXK_ESCAPE] and self.Value:
            self.Value = ""
            wx.PostEvent(self, wx.CommandEvent(wx.wxEVT_COMMAND_TEXT_ENTER))
        event.Skip()


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
        id_copy = wx.NewId()
        entries = [(wx.ACCEL_CTRL, x, id_copy)
                   for x in (ord("C"), wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT)]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))
        self.Bind(wx.EVT_MENU, self.OnCopy, id=id_copy)
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnSort)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_DRAG,  self.OnDragStart)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_END_DRAG,    self.OnDragStop)
        self.Bind(wx.lib.agw.ultimatelistctrl.EVT_LIST_BEGIN_RDRAG, self.OnDragCancel)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)


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
        self._col_widths.clear()
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

        if self._RowMatchesFilter(data):
            columns = [c[0] for c in self._columns]
            for i, col_name in enumerate(columns):
                col_value = self._formatters[col_name](data, col_name)

                if imageIds and not i: self.InsertImageStringItem(index, col_value, imageIds)
                elif not i: self.InsertStringItem(index, col_value)
                else: self.SetStringItem(index, i, col_value)
                col_width = self.GetTextExtent(col_value)[0] + self.COL_PADDING
                if col_width > self._col_widths.get(i, 0):
                    self._col_widths[i] = col_width
                    self.SetColumnWidth(i, col_width)
            self.SetItemData(index, item_id)
            self.itemDataMap[item_id] = [data[c] for c in columns]
            self._data_map[item_id] = data
            self.SetItemTextColour(index, self.ForegroundColour)
            self.SetItemBackgroundColour(index, self.BackgroundColour)
        self._id_rows.append((item_id, data))
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
            if force_refresh:
                self._col_widths.clear()
            self._filter = value
            if self._id_rows:
                self.RefreshRows()


    def RefreshRows(self):
        """
        Clears the list and inserts all unfiltered rows, auto-sizing the 
        columns.
        """
        selected_ids, selected = [], self.GetFirstSelected()
        while selected >= 0:
            selected_ids.append(self.GetItemData(selected))
            selected = self.GetNextSelected(selected)

        self.Freeze()
        wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
        self._PopulateTopRow()
            
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
            if not self._RowMatchesFilter(row):
                continue # continue for index, (item_id, row) in enumerate(..)
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

        self.Thaw()


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
        result = wx.lib.agw.ultimatelistctrl.UltimateListCtrl.DeleteAllItems(self)
        self._PopulateTopRow()
        self.Thaw()
        return result


    def GetItemCountFull(self):
        """Returns the full row count, including items hidden by filter."""
        return len(self._id_rows)


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
        if start and start != stop:
            item_id, data = self.GetItemData(start), self.GetItemMappedData(start)
            imageIds = self._id_images.get(item_id) or ()
            idx = stop if start > stop or stop == self.GetItemCount() - 1 \
                  else stop - 1
            self.DeleteItem(start)
            self.InsertRow(idx, data, self._ConvertImageIds(imageIds, False))
            self.Select(idx)
        self._drag_start = None


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
        try:
            wx.CallAfter(self.Children[0].DragFinish, HackEvent())
        except: raise


    def _CreateImageList(self):
        """
        Creates image list for the control, populated with sort arrow images.
        Arrow colours are adjusted for system foreground colours if necessary.
        """
        il = wx.lib.agw.ultimatelistctrl.PyImageList(*self.SORT_ARROW_UP.Bitmap.Size)
        fgcolour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
        defrgb, myrgb = "\x00" * 3, "".join(map(chr, fgcolour.Get()))

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
                width -= 16 # Space for scrollbar
            self.SetColumnWidth(0, width)
        if self.GetItemCount() == 1: wx.CallAfter(resize)


    def _RowMatchesFilter(self, row):
        """Returns whether the row dict matches the current filter."""
        result = True
        if self._filter:
            result = False
            patterns = map(re.escape, self._filter.split())
            for col_name, col_label in self._columns:
                col_value = self._formatters[col_name](row, col_name)
                if all(re.search(p, col_value, re.I) for p in patterns):
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
    """A StyledTextCtrl configured for SQLite syntax highlighting."""

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
    FONT_FACE = "Courier New" if os.name == "nt" else "Courier"
    """String length from which autocomplete starts."""
    AUTOCOMP_LEN = 2

    def __init__(self, *args, **kwargs):
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
        self.Bind(wx.EVT_KILL_FOCUS,         self.OnKillFocus)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)


    def SetStyleSpecs(self):
        """Sets STC style colours."""
        fgcolour, bgcolour, highcolour = (
            wx.SystemSettings.GetColour(x).GetAsString(wx.C2S_HTML_SYNTAX)
            for x in (wx.SYS_COLOUR_BTNTEXT, wx.SYS_COLOUR_WINDOW,
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
        self.autocomps_added.update(map(unicode, words))
        # A case-insensitive autocomp has to be sorted, will not work
        # properly otherwise. UserList would support arbitrarily sorting.
        self.autocomps_total = sorted(
            list(self.autocomps_added) + map(unicode, self.KEYWORDS), cmp=self.stricmp
        )


    def AutoCompAddSubWords(self, word, subwords):
        """
        Adds more subwords used in autocompletion, will be shown after the word
        and a dot.
        """
        word, subwords = unicode(word), map(unicode, subwords)
        if word not in self.autocomps_added:
            self.AutoCompAddWords([word])
        if subwords:
            word_key = word.upper()
            if word_key not in self.autocomps_subwords:
                self.autocomps_subwords[word_key] = set()
            self.autocomps_subwords[word_key].update(subwords)


    def OnKillFocus(self, event):
        """Handler for control losing focus, hides autocomplete."""
        self.AutoCompCancel()



    def OnSysColourChange(self, event):
        """Handler for system colour change, updates STC styling."""
        event.Skip()
        self.SetStyleSpecs()


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
                    for last_word in re.findall("(\\w+)$", line_text):
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

class TabbedHtmlWindow(wx.PyPanel):
    """
    HtmlWindow with tabs for different content pages.
    """

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.html.HW_DEFAULT_STYLE,
                 name=wx.html.HtmlWindowNameStr):
        wx.PyPanel.__init__(self, parent, pos=pos, size=size, style=style)
        # [{"title", "content", "id", "info", "scrollpos", "scrollrange"}]
        self._tabs = []
        self._default_page = ""      # Content shown on the blank page
        self._delete_callback = None # Function called after deleting a tab
        ColourManager.Manage(self, "BackgroundColour", wx.SYS_COLOUR_WINDOW)

        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = self._notebook = wx.lib.agw.flatnotebook.FlatNotebook(
            parent=self, size=(-1, 27),
            agwStyle=wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                     wx.lib.agw.flatnotebook.FNB_MOUSE_MIDDLE_CLOSES_TABS |
                     wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS |
                     wx.lib.agw.flatnotebook.FNB_VC8)
        self._html = wx.html.HtmlWindow(parent=self, style=style, name=name)

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
        for name in ["GetTabAreaColour", "SetTabAreaColour"]:
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
        event.Skip() # Allow event to propagate to wx handler



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
                # Default empty tab has no closing X: remove X from tab style
                style = nb.GetAGWWindowStyleFlag()
                style ^= wx.lib.agw.flatnotebook.FNB_X_ON_TAB
                nb.SetAGWWindowStyleFlag(style)
            else:
                index = min(nb.GetSelection(), nb.GetPageCount() - 2)
                self.SetActiveTab(index)
            if self._delete_callback:
                self._delete_callback(tab)


    def _CreateTab(self, index, title):
        """Creates a new tab in the tab container at specified index."""
        p = wx.Panel(parent=self, size=(0,0)) 
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
            # Default empty tab had no closing X: add X to tab style
            style = self._notebook.GetAGWWindowStyleFlag()
            style |= wx.lib.agw.flatnotebook.FNB_X_ON_TAB
            self._notebook.SetAGWWindowStyleFlag(style)

        self._html.Freeze()
        self._SetPage(tab["content"])
        self._html.Thaw()


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
                self._SetPage(tab["content"])
                self._html.Scroll(*tab["scrollpos"])
                self._html.Thaw()


    def SetActiveTab(self, index):
        """Sets active the tab at the specified index."""
        tab = self._tabs[index]
        self._notebook.SetSelection(index)
        self._html.Freeze()
        self._SetPage(tab["content"])
        self._html.Scroll(*tab["scrollpos"])
        self._html.Thaw()


    def SetActiveTabByID(self, id):
        """Sets active the tab with the specified ID."""
        tab = next((x for x in self._tabs if x["id"] == id), None)
        index = self._tabs.index(tab)
        self._notebook.SetSelection(index)
        self._html.Freeze()
        self._SetPage(tab["content"])
        self._html.Scroll(*tab["scrollpos"])
        self._html.Thaw()


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
            self._cursor_action_hover = wx.StockCursor(wx.CURSOR_HAND)
            self._cursor_default      = wx.StockCursor(wx.CURSOR_DEFAULT)

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
        if self:
            self.ShowDropDown(False)
        event.Skip()


    def OnClickDown(self, event):
        """
        Handler for clicking and holding left mouse button, remembers click
        position.
        """
        self._lastinsertionpoint = self.GetInsertionPoint()
        event.Skip()


    def OnClickUp(self, event):
        """
        Handler for releasing left mouse button, toggles dropdown list
        visibility on/off if clicking same spot in textbox.
        """
        if (self.GetInsertionPoint() == self._lastinsertionpoint):
            self.ShowDropDown(not self._listwindow.Shown)
        event.Skip()


    def OnListItemSelected(self, event):
        """
        Handler for selecting an item in the dropdown list, sets its value to
        textbox.
        """
        self.SetValueFromSelected()
        event.Skip()


    def OnFocus(self, event):
        """
        Handler for focusing/unfocusing the control, shows/hides description.
        """
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
        event.Skip() # Allow to propagate to parent, to show having focus


    def OnMouse(self, event):
        """
        Handler for mouse events, changes cursor to pointer if hovering over
        action item like "Clear history".
        """
        index, flag = self._listbox.HitTest(event.GetPosition())
        if index == self._listbox.ItemCount - 1:
            if self._cursor != self._cursor_action_hover:
                self._cursor = self._cursor_action_hover
                self._listbox.SetCursor(self._cursor_action_hover)
        elif self._cursor == self._cursor_action_hover:
            self._cursor = self._cursor_default
            self._listbox.SetCursor(self._cursor_default)
        event.Skip()


    def OnKeyDown(self, event):
        """Handler for any keypress, changes dropdown items."""
        if not self._choices:
            return event.Skip()

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
        if skip:
            event.Skip()


    def OnText(self, event):
        """
        Handler for changing textbox value, auto-completes the text and selects
        matching item in dropdown list, if any.
        """
        if self._ignore_textchange:
            self._ignore_textchange = self._skip_autocomplete = False
            event.Skip()
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
        event.Skip()


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
                self._listbox.InsertStringItem(i, text)
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
            x, y = self.ClientToScreenXY(0, height - 2)
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
