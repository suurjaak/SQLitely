# -*- coding: utf-8 -*-
"""
Schema diagram layout logic.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     29.08.2019
@modified    26.08.2023
------------------------------------------------------------------------------
"""
import base64
from collections import defaultdict
import copy
import io
import logging
import math
import os

from PIL import Image, ImageColor, ImageFont
import six
try:
    import wx
    import wx.adv
except ImportError: wx = None

from . lib.vendor import step
from . lib import util
try: from . lib import controls
except ImportError: controls = None
from . import images
from . import templates


class MyColour(object):
    """Simple partial stand-in for wx.Colour."""

    C2S_HTML_SYNTAX = 4

    def __init__(self, *args, **kwargs):
        """
        Constructs a colour with integer components.

        @param   args  () or (red, green, blue, alpha=255) or (colRGB as 32-bit int) or (colour)
        """
        self._r =  -1
        self._g =  -1
        self._b =  -1
        self._a = 255

        cast = lambda x: int(x) % 256

        def init_blank(): pass
        def init_none(*a, **kw):
            if (len(a) + len(kw)) != 1 or None not in a + tuple(kw.values()):
                raise TypeError("value is not None")
        def init_rgba(red, green, blue, alpha=255):
            self._r, self._g, self._b, self._a = map(cast, (red, green, blue, alpha))
        def init_colrgb(colRGB):
            self.SetRGB(colRGB)
        def init_colour(colour):
            init_rgba(*list(colour))
        def init_colourstr(colour):
            init_rgba(*ImageColor.getrgb(colour))


        errs = []
        for ctor in (init_blank, init_none, init_rgba, init_colrgb, init_colour, init_colourstr):
            try: ctor(*args, **kwargs)
            except Exception as e: errs.append(e)
            else: del errs[:]; break # for ctor
        if errs:
            raise TypeError("Colour(): arguments did not match any overloaded call\n%s" %
                            "\n".join("  overload %s: %s" % (i + 1, e) for i, e in enumerate(errs)))

    def Get(self, includeAlpha=True):
        """Returns the RGB intensity values as a tuple, optionally the alpha value as well."""
        return (self._r, self._g, self._b, self._a) if includeAlpha else (self._r, self._g, self._b)

    def GetAsString(self, flags=C2S_HTML_SYNTAX):
        """Returns colour as HTML-compatible string like "#FFFFFF"."""
        if not flags & self.C2S_HTML_SYNTAX:
            raise NotImplementedError("Only C2S_HTML_SYNTAX is supported.")
        return "#" + "".join("%0X" % x for x in self[:3])

    def IsOk(self):
        """Returns whether the colour object is valid (initialised with RGB values)."""
        return self._r >= 0 and self._g >= 0 and self._b >= 0

    def SetRGB(self, colRGB):
        """
        Sets the RGB colour values from a single 32 bit value.

        The argument should be of the form 0x00BBGGRR and 0xAABBGGRR respectively,
        where 0xRR 0xGG 0xBB are the values of the red, green and blue components.

        Notice the right-to-left order of components!
        """
        rgb = colRGB % 256**3
        self._r = rgb % 256
        self._g = (rgb % 256**2) >> 8
        self._b = rgb >> 16

    def SetRGBA(self, colRGBA):
        """
        Sets the RGBA colour values from a single 32 bit value.

        The argument should be of the form 0xAABBGGRR,
        where 0xRR 0xGG 0xBB 0xAA are the values of the red, green, blue and alpha components.

        Notice the right-to-left order of components!
        """
        self._a = colRGBA >> 24
        self.SetRGB(colRGBA)

    def __eq__(self, other):
        if isinstance(other, (MyColour, list, tuple)) and len(other) == len(self):
            return self.Get() == tuple(other)
        return False

    def __bool__(self):
        return self.IsOk()

    __nonzero__ = __bool__ # Py2

    def __len__(self):
        return 4

    def __getitem__(self, idx):
        return self.Get()[idx]

    def __str__(self):
        return str(self.Get())

    def __repr__(self):
        return "Colour" + str(self.Get())

Colour = wx.Colour if wx else MyColour


logger = logging.getLogger(__name__)


class SchemaPlacement(object):
    """
    Schema diagram visual layout logic.

    Uses wx if available, falls back to PIL if not (export only as SVG, no bitmap).
    If using wx, the wx.App must be created first.
    """

    DEFAULT_COLOURS = {
        "Background":      Colour(255, 255, 255),
        "Foreground":      Colour(  0,   0,   0),
        "Border":          Colour(128, 128, 128),
        "DragForeground":  Colour(  0,   0, 128),
        "GradientEnd":     Colour(103, 103, 255),
        "Line":            Colour(  0,   0,   0),
    }

    MINW      = 100 # Item minimum width
    LINEH     =  15 # Item column line height
    HEADERP   =   5 # Vertical margin between header and columns
    HEADERH   =  20 # Item header height (header contains name)
    FOOTERH   =   5 # Item footer height
    BRADIUS   =   5 # Item rounded corner radius
    FMARGIN   =   2 # Focused item border margin
    CARDINALW =   7 # Horizontal width of cardinality crowfoot
    CARDINALH =   3 # Vertical step for cardinality crowfoot
    DASHSIDEW =   2 # Horizontal width of one side of parent relation dash
    LPAD      =  15 # Left padding
    HPAD      =  20 # Right and middle padding
    GPAD      =  30 # Padding between grid items
    MAX_TITLE =  50 # Item name max len
    MAX_TEXT  =  40 # Column name/type max len
    FONT_SIZE =   8 # Default font size
    FONT_FACE = "Verdana"
    FONT_SPAN = (1, 24)  # Minimum and maximum font size for zoom
    FONTS     = util.CaselessDict([(FONT_FACE, {"size": FONT_SIZE})], insertorder=True)
    STATSH    =  15      # Stats footer height
    FONT_STEP_STATS = -1 # Stats footer font size step from base font

    LAYOUT_GRID  = "grid"
    LAYOUT_GRAPH = "graph"

    SIZE_DEFAULT = (2000, 2000)

    ZOOM_STEP = 1. / FONT_SIZE
    ZOOM_MIN  = FONT_SPAN[0] / float(FONT_SIZE)
    ZOOM_MAX  = FONT_SPAN[1] / float(FONT_SIZE)
    ZOOM_DEFAULT = 1.0

    class GraphLayout(object):
        """
        """

        DEFAULT_EDGE_WEIGHT     =    1    # attraction for relations; 10 groups better but slower
        MAX_ITERATIONS          =  100    # maximum number of steps to stop at
        MIN_COMPLETION_DISTANCE =    0.1  # minimum change to stop at
        INERTIA                 =    0.1  # node speed inertia
        REPULSION               =  400    # repulsion between all nodes
        ATTRACTION              =    1    # attraction between connected nodes
        MAX_DISPLACE            =   10    # node displacement limit
        DO_FREEZE_BALANCE       = True    # whether unstable nodes are stabilized
        FREEZE_STRENGTH         =   80    # stabilization strength
        FREEZE_INERTIA          =    0.2  # stabilization inertia [0..1]
        GRAVITY                 =   50    # force of attraction to graph centre, smaller values push less connected nodes more outwards
        SPEED                   =    1    # convergence speed (>0)
        COOLING                 =    1.0  # dampens force if >0
        DO_OUTBOUND_ATTRACTION  = True    # whether attraction is distributed along outbound links (pushes hubs to center)


        @classmethod
        def layout(cls, items, links, bounds, viewport, progress=None):
            """
            Calculates item positions using a force-directed graph.

            @param   items     [{"name", "x", "y", "size"}, ]
            @param   links     [(name1, name2), (..)]
            @param   bounds    graph bounds as (x, y, width, height)
            @param   viewport  preferred viewport within bounds, as (x, y, width, height)
            @param   progress  callback function(iteration), returning whether to stop calculations
            @return            [{"name", "x", "y", "size"}, ]
            """

            def intersects(n1, n2):
                (w1, h1), (w2, h2) = n1["size"], n2["size"]
                x1, y1 = max(n1["x"], n2["x"]), max(n1["y"], n2["y"])
                x2, y2 = min(n1["x"] + w1, n2["x"] + w2), min(n1["y"] + h1, n2["y"] + h2)
                return x1 < x2 and y1 < y2


            def repulsor(n1, n2, c):
                xdist, ydist = n1["x"] - n2["x"], n1["y"] - n2["y"]
                dist = math.sqrt(xdist ** 2 + ydist ** 2) - n1["span"] - n2["span"]

                if not xdist and not ydist:
                    if not n1["fixed"]:
                        n1["dx"] += 0.01 * c
                        n1["dy"] += 0.01 * c
                    if not n2["fixed"]:
                        n2["dx"] -= 0.01 * c
                        n2["dy"] -= 0.01 * c
                    return

                f = 0.001 * c / dist if dist > 0 else -c
                if intersects(n1, n2): f *= 100
                if not n1["fixed"]:
                    n1["dx"] += xdist / dist * f
                    n1["dy"] += ydist / dist * f
                if not n2["fixed"]:
                    n2["dx"] -= xdist / dist * f
                    n2["dy"] -= ydist / dist * f


            def attractor(n1, n2, c):
                xdist, ydist = n1["x"] - n2["x"], n1["y"] - n2["y"]
                dist = math.sqrt(xdist ** 2 + ydist ** 2) - n1["span"] - n2["span"]
                if not dist: return

                f = 0.01 * -c * dist
                if not n1["fixed"]:
                    n1["dx"] += xdist / dist * f
                    n1["dy"] += ydist / dist * f
                if not n2["fixed"]:
                    n2["dx"] -= xdist / dist * f
                    n2["dy"] -= ydist / dist * f


            def iteration(nodes, links):
                """Performs one iteration, returns maximum distance shifted."""
                result = 0

                for n, o in nodes.items():
                    o.update(dx0=o["dx"], dx=o["dx"] * cls.INERTIA,
                             dy0=o["dy"], dy=o["dy"] * cls.INERTIA)
                nodelist = list(nodes.values())

                # repulsion
                for i, n1 in enumerate(nodelist):
                    for n2 in nodelist[i+1:]:
                        c = cls.REPULSION * (1 + n1["cardinality"]) * (1 + n2["cardinality"])
                        repulsor(n1, n2, c)

                # attraction
                for name1, name2 in links:
                    n1, n2 = nodes[name1], nodes[name2]
                    bonus = 100 if n1["fixed"] or n2["fixed"] else 1
                    bonus *= cls.DEFAULT_EDGE_WEIGHT
                    c = bonus * cls.ATTRACTION / (1. + n1["cardinality"] * cls.DO_OUTBOUND_ATTRACTION)
                    attractor(n1, n2, c)

                # gravity
                for n in nodelist:
                    if n["fixed"]: continue # for n
                    d = 0.0001 + math.sqrt(node["x"] ** 2 + node["y"] ** 2)
                    gf = 0.0001 * cls.GRAVITY * d
                    n["dx"] -= gf * n["x"] / d
                    n["dy"] -= gf * n["y"] / d

                # speed
                for n in nodelist:
                    if n["fixed"]: continue # for n
                    n["dx"] *= cls.SPEED * (10 if cls.DO_FREEZE_BALANCE else 1)
                    n["dy"] *= cls.SPEED * (10 if cls.DO_FREEZE_BALANCE else 1)

                # apply forces
                for n in nodelist:
                    if node["fixed"]: continue # for n

                    d = 0.0001 + math.sqrt(n["dx"] ** 2 + n["dy"] ** 2)
                    if cls.DO_FREEZE_BALANCE:
                        ddist = math.sqrt((n["dx0"] - n["dx"]) ** 2 + (n["dy0"] - n["dy"]) ** 2)
                        n["freeze"] = cls.FREEZE_INERTIA * n["freeze"] + \
                                      (1 - cls.FREEZE_INERTIA) * 0.1 * cls.FREEZE_STRENGTH * math.sqrt(ddist)
                        ratio = min(d / (d * (1 + n["freeze"])), cls.MAX_DISPLACE / d)
                    else:
                        ratio = min(1, cls.MAX_DISPLACE / d)

                    n["dx"], n["dy"] = n["dx"] * ratio / cls.COOLING, n["dy"] * ratio / cls.COOLING
                    x, y = n["x"] + n["dx"], n["y"] + n["dy"]

                    # Bounce back from edges
                    if x < bounds[0]: n["dx"] = bounds[0] - n["x"]
                    elif x + n["size"][0] > bounds[0] + bounds[2]:
                        n["dx"] = bounds[2] - n["size"][0] - n["x"]
                    if y < bounds[1]: n["dy"] = bounds[1] - n["y"]
                    elif y + n["size"][1] > bounds[1] + bounds[3]:
                        n["dy"] = bounds[3] - n["size"][1] - n["y"]

                    n["x"], n["y"] = n["x"] + n["dx"], n["y"] + n["dy"]
                    result = max(result, abs(n["dx"]), abs(n["dy"]))

                return result


            nodes = util.CaselessDict() # {name: {id, size, dx, dy, freeze, fixed, cardinality}, }

            for o in items:
                node = {"x": 0, "y": 0, "size": o["size"], "name": o["name"],
                        "dx": 0, "dy": 0, "freeze": 0, "cardinality": 0, "fixed": False}
                node["span"] = math.sqrt(o["size"][0] ** 2 + o["size"][1] ** 2) / 2.5
                nodes[o["name"]] = node

            for name1, name2 in links:
                if name1 != name2:
                    for n in name1, name2: nodes[n]["cardinality"] += 1

            # Start with all items in center
            center = viewport[0] + viewport[2] / 2, viewport[1] + viewport[3] / 2
            for n in nodes.values():
                x, y = (c - s/2 for c, s in zip(center, n["size"]))
                if not n["cardinality"]: x += 200 # Push solitary nodes out
                n["x"], n["y"] = x, y


            steps = 0
            while not callable(progress) or progress(iteration=steps):
                dist, steps = iteration(nodes, links), steps + 1
                if dist < cls.MIN_COMPLETION_DISTANCE or steps >= cls.MAX_ITERATIONS:
                    break # while
            return {n: {"x": o["x"], "y": o["y"]} for n, o in nodes.items()}


    def __init__(self, db, size=SIZE_DEFAULT):
        """
        @param   db    database.Database instance
        @param   size  total drawing area size, as (w, h)
        """
        self._db    = db
        self._ids   = {} # {DC ops ID: name or (name1, name2, (cols)) or None}
        # {name: {id, type, name, bmp, bmpsel, bmparea, hasmeta, stats, sql0, columns, keys, __id__}}
        self._objs  = util.CaselessDict()
        # {(name1, name2, (cols)): {id, pts, waylines, cardlines, cornerpts, textrect}}
        self._lines = util.CaselessDict()
        self._sels  = util.CaselessDict(insertorder=True) # {name selected: DC ops ID}
        # Bitmap cache, as {zoom: {item.__id__: {key: (imageobject, imageobject) or imageobject}},
        # with key as (sql, hasmeta, showcols, showkeys, shownulls, stats, dragrect),
        # image tuple as (standard bitmap, selected bitmap) and single image as dragrect highlight;
        # or {zoom: {PyEmdeddedImage: imageobject}} for scaled static images
        self._cache = defaultdict(lambda: defaultdict(dict))
        self._order = []   # Draw order [{obj dict}, ] selected items at end
        self._zoom  = 1.   # Zoom scale, 1 == 100%
        self._dc    = PseudoDC()
        self._size  = Size(size)

        self._dragrect    = None # Selection (x, y, w, h) currently being dragged
        self._dragrectabs = None # Selection being dragged, with non-negative dimensions
        self._dragrectid  = None # DC ops ID for selection rect
        self._use_cache   = True # Use self._cache for item bitmaps
        self._show_cols   = True
        self._show_keys   = False
        self._show_nulls  = False
        self._show_lines  = True
        self._show_labels = True
        self._show_stats  = False

        self._layout = {"layout": "grid", "active": True,
                        "grid": {"order": "name", "reverse": False, "vertical": True}}

        self._colour_bg     = self.DEFAULT_COLOURS["Background"]
        self._colour_fg     = self.DEFAULT_COLOURS["Foreground"]
        self._colour_border = self.DEFAULT_COLOURS["Border"]
        self._colour_line   = self.DEFAULT_COLOURS["Line"]
        self._colour_grad1  = self.DEFAULT_COLOURS["Background"]
        self._colour_grad2  = self.DEFAULT_COLOURS["GradientEnd"]
        self._colour_select = Colour(None)
        self._colour_dragfg = Colour(None)
        self._colour_dragbg = Colour(None)

        self._measurer = wx.MemoryDC() if wx else None

        self._font      = self.MakeFont(self.FONT_FACE, self.FONT_SIZE)
        self._font_bold = self.MakeFont(self.FONT_FACE, self.FONT_SIZE, bold=True)


    def Populate(self, opts=None):
        """
        Populates diagram from database, clearing any previous layout.

        @param   opts  diagram display options as returned from GetOptions()
        @return        (whether layout needs full reset, [name of item needing bitmap redraw, ])
        """
        objs0  = self._objs.values()
        sels0  = self._sels.copy()
        lines0 = self._lines.copy()
        rects0 = {o["name"]: self._dc.GetIdBounds(o["id"]) for o in objs0}
        maxid = max(o["id"] for o in objs0) if objs0 else 0

        self._ids  .clear()
        self._objs .clear()
        self._sels .clear()
        self._lines.clear()
        del self._order[:]
        for myid in self._ids: self._dc.ClearId(myid)
        for l0 in lines0.values(): self._dc.RemoveId(l0["id"])

        self.SetOptions(opts)

        opts, rects, fullbounds = opts or {}, {}, Rect()
        itemposes = util.CaselessDict(opts.get("items") or {})
        makeitems = []
        reset = any(o["__id__"] not in (x["__id__"] for x in self._db.schema.get(o["type"], {}).values())
                    for o in objs0) if self.LAYOUT_GRID == self.Layout else False
        keys = {} # {table: (pks, fks)}
        for name1 in self._db.schema.get("table", {}):
            keys[name1] = self._db.get_keys(name1, pks_only=True)
            for fk in keys[name1][1]:
                name2, rname = list(fk["table"])[0], ", ".join(fk["name"])
                if name2 not in self._db.schema["table"]: continue # for fk
                key = name1, name2, tuple(n.lower() for n in fk["name"])
                lid, maxid = (maxid + 1, ) * 2
                self._ids[lid] = key
                self._lines[key] = {"id": lid, "pts": [], "name": rname}
        for category in "table", "view":
            for name, opts in self._db.schema.get(category, {}).items():
                o0 = next((o for o in objs0 if o["__id__"] == opts["__id__"]), None)
                if o0: oid = o0["id"]
                else: oid = maxid = maxid + 1

                stats = self.MakeItemStatistics(opts)
                bmp, bmpsel = None, None
                if o0 and o0["sql0"] == opts["sql0"] \
                and self.HasItemBitmaps(o0, self._show_stats and stats):
                    bmp, bmpsel = self.GetItemBitmaps(o0, self._show_stats and stats)
                if o0 and o0["name"] in sels0: self._sels[name] = oid
                if name in itemposes and bmp:
                    rects[name] = Rect(Point(itemposes[name]), self.GetImageSize(bmp))
                elif o0 and bmp: rects[name] = rects0[o0["name"]]

                self._ids[oid] = name
                self._objs[name] = {"id": oid, "type": category, "name": name, "stats": stats,
                                    "__id__": opts["__id__"], "sql0": opts["sql0"],
                                    "hasmeta": bool(opts.get("meta")),
                                    "size_total": opts.get("size_total"), "count": opts.get("count"),
                                    "keys": keys.get(name, ((), ())),
                                    "columns": [dict(c)  for c in opts["columns"]],
                                    "bmp": bmp, "bmpsel": bmpsel, "bmparea": None}
                self._order.append(self._objs[name])
                if name in rects:
                    if o0 and not o0.get("meta"):
                        makeitems.append(name)  # Remake for fk icons
                    self._dc.SetIdBounds(oid, rects[name])
                    fullbounds.Union(rects[name])
                else:
                    makeitems.append(name)
                    if not o0 and self.Layout and name not in itemposes: reset = True

        # Nuke cache for objects no longer in schema
        for o0 in objs0:
            if not any(o0["__id__"] == o["__id__"] for o in self._order):
                self._dc.RemoveId(o0["id"])
                for cc in self._cache.values(): cc.pop(o0["__id__"], None)

        # Increase diagram virtual size if total item area is bigger
        area, vsize = self.GPAD * self.GPAD, self._size
        if reset: # Do a very rough calculation based on accumulated area
            for o in self._objs.values():
                osize = self.CalculateItemSize(o)[0]
                area += (osize.Width + self.GPAD) * (osize.Height + self.GPAD)
            while area > vsize[0] * vsize[1]:
                vsize = vsize[0], vsize[1] + 100
        for o in self._objs.values() if not reset else ():
            pos = itemposes.get(o["name"]) \
                  or next((r.TopLeft for r in [self._dc.GetIdBounds(o["id"])] if r), None)
            if not pos: continue  # for o
            size = self.CalculateItemSize(o)[0]
            rect = rects[o["name"]] = Rect(Point(pos), size)
            self._dc.SetIdBounds(o["id"], rect)
            fullbounds.Union(rect)

        if not reset and fullbounds:
            vsize = fullbounds.Right + 2 * self.BRADIUS, fullbounds.Bottom + 2 * self.BRADIUS
        if vsize[0] > self._size[0] or vsize[1] > self._size[1]:
            self._size = Size(vsize)

        if reset: self._dc.RemoveAll()
        self.CalculateLines(remake=True)

        return reset, makeitems


    def ClearCache(self):
        """Clears bitmap cache."""
        self._cache.clear()


    def ClearItems(self):
        """Clears all entities and relations from DC."""
        for oid in self._ids: self._dc.ClearId(oid)


    def ClearLines(self):
        """Clears all relation lines from DC."""
        for opts in self._lines.values(): self._dc.ClearId(opts["id"])


    def DrawToDC(self, dc, rect=None):
        """
        Draws current layout to wx.DC.

        @param   rect  if set, content outside the rect is not drawn
        """
        self._dc.DrawToDC(dc) if rect is None else self._dc.DrawToDCClipped(dc, rect)


    def MoveItem(self, name, dx, dy):
        """
        Shifts item by specified pixels on X and Y axis.

        @param   name  entity name or relation (childname, parentname, (fkname1, ))
        """
        oid = next((k for k, v in self._ids.items() if v == name), -1)
        self._dc.TranslateId(oid, dx, dy)


    def SelectItem(self, name, on=True):
        """
        Selects/deselects an item.

        @param   name  name of entity
        @param   on    true to select, false to deselect
        """
        if on and name not in self._sels:
            self._sels[name] = self._objs[name]["id"]
        elif not on and name in self._sels:
            self._sels.pop(name)


    def ChangeOrder(self, name, index):
        """
        Sets item with specified name to specified position in item order.

        @param   index  new index to set, may be negative
        """
        o = next((o for o in self._order if util.lceq(name, o["name"])), None)
        if o is None: return

        self._order.remove(o)
        index = min(len(self._order) - 1, max(-len(self._order), index))
        if index < 0: index = len(self._order) + index + 1
        self._order.insert(index, o)


    def SortItems(self, key, reverse=False):
        """
        Reorders items.

        @param   key      function of one argument returning item value to sort by,
                          or name of item attribute to sort by
        @param   reverse  xhether to sort in opposite order
        """
        sortkey = key if callable(key) else lambda o: o.get(key)
        self._order.sort(key=sortkey, reverse=reverse)


    """Returns current zoom level, 1 being 100% and .5 being 50%."""
    def GetZoom(self): return self._zoom
    def SetZoom(self, zoom):
        """
        Sets current zoom scale.

        @param   zoom     scale factor, will be constrained and stepped to valid min-max-step
        @return           whether zoom was changed
        """
        zoom = float(zoom) - zoom % self.ZOOM_STEP # Even out to allowed step
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        if self._zoom == zoom: return False

        zoom0 = self._zoom
        self._zoom = zoom

        self._font      = self.MakeFont(self.FONT_FACE, self.FONT_SIZE * zoom)
        self._font_bold = self.MakeFont(self.FONT_FACE, self.FONT_SIZE * zoom, bold=True)

        for k in ("MINW", "LINEH", "HEADERP", "HEADERH", "FOOTERH", "BRADIUS", "FMARGIN",
                  "CARDINALW", "CARDINALH", "DASHSIDEW", "LPAD", "HPAD", "GPAD", "STATSH"):
            # Scale instance constants from class constants
            v = getattr(self.__class__, k)
            setattr(self, k, int(math.ceil(v * zoom)))

        for o in self._order: # Scale all item bounds to new zoom
            r = self._dc.GetIdBounds(o["id"])
            pt = [v * zoom / zoom0 for v in r.TopLeft]
            sz, _, _, _ = self.CalculateItemSize(o)
            self._dc.SetIdBounds(o["id"], Rect(Point(pt), Size(sz)))

        return True
    Zoom = property(GetZoom, SetZoom)


    def GetOptions(self):
        """
        Returns all current diagram options, as
        {zoom: float, columns: bool, keycolumns: bool, lines: bool, labels: bool, statistics: bool,
         layout: {layout, active, ?grid: {order, reverse, vertical}}, items: {name: [x, y]}}.
        """
        pp = {o["name"]: list(self._dc.GetIdBounds(o["id"]).TopLeft) for o in self.Order}
        return {
            "zoom":    self._zoom,        
            "lines":   self._show_lines,  "labels":     self._show_labels, 
            "columns": self._show_cols,   "keycolumns": self._show_keys,
            "nulls":   self._show_nulls,  "statistics": self._show_stats,
            "items":   pp,                "layout": copy.deepcopy(self._layout),
        }
    def SetOptions(self, opts):
        """Sets all diagram options."""
        if not opts: return

        remake = False
        if "columns"    in opts and self._show_cols != bool(opts["columns"]):
            self._show_cols = not self._show_cols
            if self._show_cols: self._show_keys = False
            remake = True
        if "keycolumns" in opts and self._show_keys != bool(opts["keycolumns"]):
            self._show_keys = not self._show_keys
            if self._show_keys: self._show_cols = False
            remake = True
        if "nulls" in opts and self._show_nulls != bool(opts["nulls"]):
            self._show_nulls = not self._show_nulls
            remake = True
        if "lines"      in opts:
            self._show_lines = bool(opts["lines"])
            if not self._show_lines:
                for opts in self._lines.values(): self._dc.ClearId(opts["id"])
        if "labels" in opts: self._show_labels = bool(opts["labels"])
        if "statistics" in opts and bool(opts["statistics"]) != self._show_stats:
            self._show_stats = not self._show_stats
            remake = True
        if "zoom"     in opts:
            remake = self.SetZoom(opts["zoom"]) or remake

        if "layout" in opts:
            lopts = opts["layout"]
            if "layout" in lopts and lopts["layout"] in (self.LAYOUT_GRID, self.LAYOUT_GRAPH):
                self._layout["layout"] = lopts["layout"]
            if "active" in lopts: self._layout["active"] = bool(lopts["active"])
            for k, v in lopts.items():
                if isinstance(v, dict): self._layout.setdefault(k, {}).update(v)
        for name, (x, y) in (opts.get("items") or {}).items() if self._objs else ():
            o = self._objs.get(name)
            if not o:
                self.Layout = self._layout["layout"]
                break # for name, (x, y)
            r = self._dc.GetIdBounds(o["id"])
            if x != r.Left or y == r.Top:
                self._dc.TranslateId(o["id"], x - r.Left, y - r.Top)
                self._dc.SetIdBounds(o["id"], Rect(x, y, *r.Size))
    Options = property(GetOptions, SetOptions)


    def UpdateStatistics(self):
        """Updates local data structures with statistics data from database."""
        for o in self._objs.values():
            opts = self._db.schema[o["type"]].get(o["name"])
            if opts:
                for key in ("count", "size_total"):
                    if opts.get(key) is not None: o[key] = opts[key]
                o["stats"] = self.MakeItemStatistics(opts)


    def GetFullBounds(self, lines=False):
        """
        Returns the minimum rectangle containing all entities.

        @param   lines  include relation lines
        """
        oids = list(self._ids) if lines else [o["id"] for o in self._order]
        bounds, bounder = Rect(), self._dc.GetIdBounds
        if oids: bounds = sum(map(bounder, oids[1:]), bounder(oids[0]))
        bounds.Left, bounds.Top = max(0, bounds.Left), max(0, bounds.Top)
        return bounds


    def GetObjectBounds(self, name):
        """
        Returns object bounds as Rect.

        @param   name  entity name, or relation (childname, parentname, (fkname1, ))
        """
        oid = next((k for k, v in self._ids.items() if v == name), -1)
        return self._dc.GetIdBounds(oid)


    def MakeBitmap(self, zoom=None, selections=True, use_cache=True):
        """
        Returns diagram as image.

        @param   zoom        zoom level to use if not current
        @param   selections  whether currently selected items should be drawn as selected
        @param   use_cache   use bitmap caching
        """
        if wx: return self.MakeBitmap_wx(zoom, selections, use_cache)


    def MakeBitmap_wx(self, zoom=None, selections=True, use_cache=True):
        """
        Returns diagram as wx.Bitmap.

        @param   zoom        zoom level to use if not current
        @param   selections  whether currently selected items should be drawn as selected
        @param   use_cache   use bitmap caching
        """
        zoom0 = self._zoom
        lines0, sels0 = copy.deepcopy(self._lines), copy.deepcopy(self._sels)
        ids, bounder = list(self._ids), self._dc.GetIdBounds
        boundsmap0 = {myid: bounder(myid) for myid in ids}


        self._use_cache, use_cache0 = bool(use_cache), self._use_cache
        try:
            if not selections: self._sels.clear()

            if zoom is not None:
                zoom = float(zoom) - zoom % self.ZOOM_STEP # Even out to allowed step
                zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
                if self._zoom == zoom: zoom = None

            if zoom is not None: self.Zoom = zoom
            self.CalculateLines(remake=True)

            bounds = sum(map(bounder, ids[1:]), bounder(ids[0])) if ids else wx.Rect()

            MARGIN = int(math.ceil(10 * self._zoom))
            shift = [MARGIN - v for v in bounds.TopLeft]
            bmp = wx.Bitmap([v + 2 * MARGIN for v in bounds.Size])
            dc = wx.MemoryDC(bmp)
            dc.Background = controls.BRUSH(self.BackgroundColour)
            dc.Clear()
            dc.Font = self._font

            self.RecordLines(dc=dc, shift=shift)
            for o in (o for o in self._order if o["name"] not in self._sels):
                pos = [a + b for a, b in zip(self._dc.GetIdBounds(o["id"])[:2], shift)]
                obmp, _ = self.GetItemBitmaps(o)
                dc.DrawBitmap(obmp, pos, useMask=True)
            for name in self._sels:
                o = self._objs[name]
                pos = [a + b - 2 * self._zoom
                       for a, b in zip(self._dc.GetIdBounds(o["id"])[:2], shift)]
                _, obmp = self.GetItemBitmaps(o)
                dc.DrawBitmap(obmp, pos, useMask=True)
            dc.SelectObject(wx.NullBitmap)
            del dc

        finally:
            self._use_cache = use_cache0
            if zoom is not None: self.Zoom = zoom0
            self._lines.update(lines0)
            self._sels .update(sels0)
            for myid, mybounds in boundsmap0.items(): self._dc.SetIdBounds(myid, mybounds)

        return bmp


    def MakeTemplate(self, filetype, title=None, embed=False, selections=True):
        """
        Returns diagram as template content.

        @param   filetype    template type like "SVG"
        @param   title       specific title to set if not from database filename
        @param   embed       whether to omit full XML headers for embedding in HTML
        @param   selections  whether currently selected items should be drawn as selected
        """
        if "SVG" != filetype or not self._objs: return

        zoom0 = self._zoom
        lines0, sels0 = copy.deepcopy(self._lines), copy.deepcopy(self._sels)

        if not selections: self._sels.clear()

        if self._zoom != self.ZOOM_DEFAULT:
            self.SetZoom(self.ZOOM_DEFAULT)
            itembounds0 = {} # Remember current bounds, calculate for default zoom
            for name, o in self._objs.items():
                size, _, _, _ = self.CalculateItemSize(o)
                ibounds = itembounds0[name] = self._dc.GetIdBounds(o["id"])
                self._dc.SetIdBounds(o["id"], Rect(ibounds.Position, Size(size)))
            self.CalculateLines(remake=True)

        tpl = step.Template(templates.DIAGRAM_SVG, strip=False)
        if title is None:
            title = os.path.splitext(os.path.basename(self._db.name))[0] + " schema"
        ns = {"title": title, "items": [], "lines": self._lines if self._show_lines else {},
              "show_nulls": self._show_nulls, "show_labels": self._show_labels,
              "get_extent": self.GetTextExtent, "get_stats_texts": self.GetStatisticsTexts,
              "font_faces": copy.deepcopy(self.FONTS), "embed": embed,
              "fonts": {"normal": self._font, "bold": self._font_bold}}
        for o in self._objs.values():
            item = dict(o, bounds=self._dc.GetIdBounds(o["id"]))
            if not self._show_stats: item.pop("stats")
            item["columns"] = [c for c in item.get("columns", []) if self.IsColumnShown(item, c)]
            ns["items"].append(item)
        result = tpl.expand(ns)

        if zoom0 != self._zoom:
            for name, ibounds in itembounds0.items():
                self._dc.SetIdBounds(self._objs[name]["id"], ibounds)
            self.SetZoom(zoom0)
        self._lines.update(lines0)
        self._sels .update(sels0)

        return result


    def CalculateItemSize(self, opts, statistics=None):
        """
        Returns ((w, h), title, coltexts, colmax) for schema item with current settings.

        @param   statistics  {?size, ?rows, ?rows_maxunits} to use if not item current
        """
        statistics = (statistics or self.MakeItemStatistics(opts)) if self._show_stats else None
        w, h = self.MINW, self.HEADERH + self.FOOTERH

        # Measure title width
        title = util.ellipsize(util.unprint(opts["name"]), self.MAX_TITLE)
        extent = self.GetTextExtent(title, self._font_bold) # (w, h, descent, lead)
        w = max(w, extent[0] + extent[3] + 2 * self.HPAD)

        # Measure column text widths
        colmax = {"name": 0, "type": 0}
        coltexts = [] # [[name, type]]
        for c in opts.get("columns") or []:
            if not self.IsColumnShown(opts, c):
                continue  # for c
            coltexts.append([])
            for k in ["name", "type"]:
                t = util.ellipsize(util.unprint(c.get(k, "")), self.MAX_TEXT)
                coltexts[-1].append(t)
                if t: extent = self.GetTextExtent(t)
                if t: colmax[k] = max(colmax[k], extent[0] + extent[3])
        w = max(w, self.LPAD + 2 * self.HPAD + sum(colmax.values()))
        h += self.LINEH * len(coltexts) + self.HEADERP * bool(coltexts)
        if self._show_stats and opts["stats"]:
            h += self.STATSH - self.FOOTERH
            if not coltexts: h += self.FOOTERH

        # Measure statistics text widths
        if statistics:
            text1, text2 = self.GetStatisticsTexts(statistics, w)
            statswidth = sum(self.GetTextExtent(t)[0] for t in (text1, text2))
            if w - 2 * self.BRADIUS < statswidth:  # Add the difference rounded to upper 10
                w += int(math.ceil((statswidth - (w - 2 * self.BRADIUS)) / 10.) * 10)

        return Size(w, h), title, coltexts, colmax


    def CalculateLines(self, remake=False):
        """
        Calculates foreign relation line and text positions if showing lines is enabled.
        """
        if not self._show_lines: return

        lines = self._lines
        if self._sels and not remake:
            # Recalculate only lines from/to selected items, and lines to related items
            pairs, rels = set(), set() # {(name1, name2)}, {related item name}
            for name in self._sels:
                for (name1, name2, _) in self._lines:
                    if name in (name1, name2):
                        pairs.add((name1, name2))
                        if name2 not in self._sels: rels.add(name2)

            lines = util.CaselessDict()
            for (name1, name2, cols), opts in self._lines.items():
                if (name1, name2) in pairs or name2 in rels:
                    lines[(name1, name2, cols)] = opts


        # {name2: {False: [(name1, cols) at top], True: [(name1, cols) at bottom]}}
        vertslots = defaultdict(lambda: defaultdict(list))
        # {table name: {col name: col index on diagram with current settings}}
        tablecols = util.CaselessDict()
        for name, topts in self._db.schema["table"].items():
            tablecols[name] = util.CaselessDict()
            for c in topts["columns"]:
                if self.IsColumnShown(self._objs[name], c):
                    tablecols[name][c["name"]] = len(tablecols[name])

        # First pass: determine starting and ending Y
        for (name1, name2, cols), opts in lines.items():
            b1, b2 = (self._dc.GetIdBounds(o["id"])
                      for o in map(self._objs.get, (name1, name2)))

            idx = next((tablecols[name1].get(c, -1) for c in cols), -1)  # Column index in diagram item

            y1 = b1.Top + self.HEADERH // 2 + 2 if idx < 0 else \
                 b1.Top + self.HEADERH + self.HEADERP + (idx + 0.5) * self.LINEH
            y2 = b2.Top if y1 < b2.Top else b2.Bottom

            if b1.Contains(b2.Left + b2.Width // 2, y2):
                # Choose other side if within b1
                y2 = b2.Top if y1 >= b2.Top else b2.Bottom

            opts["pts"] = [[-1, y1], [-1, y2]]
            vertslots[name2][y2 == b2.Bottom].append((name1, cols))

        # Second pass: determine ending X
        get_opts = lambda name2, name1, cols: lines[(name1, name2, cols)]
        for name2 in vertslots:
            for slots in vertslots[name2].values():
                slots.sort(key=lambda x: -get_opts(name2, *x)["pts"][0][0])
                for i, (name1, cols) in enumerate(slots):
                    b2 = self._dc.GetIdBounds(self._objs[name2]["id"])
                    xstep = 2 * self.BRADIUS
                    while xstep > 1 and len(slots) * xstep > b2.Width - 2 * self.BRADIUS:
                        xstep -= 1
                    opts = get_opts(name2, name1, cols)
                    shift = 0 if len(slots) % 2 else 0.5
                    opts["pts"][1][0] = b2.Left + b2.Width // 2 + (len(slots) // 2 - i - shift) * xstep

        # Third pass: determine starting X
        for (name1, name2, cols), opts in lines.items():
            b1, b2 = (self._dc.GetIdBounds(o["id"])
                      for o in map(self._objs.get, (name1, name2)))

            use_left = b1.Left + b1.Width // 2 > opts["pts"][1][0]
            x1 = (b1.Left - 1) if use_left else (b1.Right + 1)
            if not (2 * self.CARDINALW < x1 < self._size.Width - 2 * self.CARDINALW):
                # Choose other side if too close to edge
                x1 = (b1.Left - 1) if not use_left else (b1.Right + 1)
            opts["pts"][0][0] = x1

        # Fourth pass: insert waypoints between starting and ending X-Y
        for (name1, name2, cols), opts in sorted(lines.items(),
                key=lambda x: any(n in self._sels for n in x[0][:2])):
            b1, b2 = (self._dc.GetIdBounds(o["id"])
                      for o in map(self._objs.get, (name1, name2)))

            pt1, pt2 = opts["pts"]
            slots = vertslots[name2][pt2[1] == b2.Bottom]
            idx = slots.index((name1, cols))

            # Make 1..3 waypoints between start and end points
            wpts = []
            if b1.Left - 2 * self.CARDINALW <= pt2[0] <= b1.Right + 2 * self.CARDINALW:
                # End point straight above or below start item
                b1_side = b1.Top if pt1[1] > pt2[1] else b1.Bottom
                ptm1 = [pt1[0] + 2 * self.CARDINALW * (-1 if pt1[0] <= b1.Left else 1), pt1[1]]
                ptm2 = [ptm1[0], pt2[1] + (b1_side - pt2[1]) // 2]

                if b2.Left < pt2[0] < b2.Right \
                and b2.Top - 2 * self.BRADIUS < ptm2[1] < b2.Bottom + 2 * self.BRADIUS:
                    ptm2 = [ptm2[0], (b2.Top if pt1[1] > b2.Top else b2.Bottom) + 2 * self.BRADIUS * (-1 if pt1[1] > b2.Top else 1)]

                ptm3 = [pt2[0], ptm2[1]]
                # (pt1.x +- cardinal step, pt1.y), (pt1.x +- cardinal step, halfway to pt2.y), (pt2x, halfway to pt2.y)
                wpts += [ptm1, ptm2, ptm3]
            else:
                ptm = [pt2[0], pt1[1]]
                if not  b2.Contains(ptm[0], ptm[1] - self.CARDINALW) \
                and not b2.Contains(ptm[0], ptm[1] + self.CARDINALW):
                    # Middle point not within end item: single waypoint (pt2.x, pt1.y)
                    wpts.append(ptm)
                else: # Middle point within end item
                    pt2_in_b2 = b2.Contains(pt2[0], pt2[1] + self.CARDINALW * (idx + 1))
                    b2_side   = b2.Left if pt1[0] < pt2[0] else b2.Right
                    ptm3 = [pt2[0], pt2[1] + self.CARDINALW * (idx + 1) * (-1 if pt2_in_b2 else 1)]

                    if b2.Contains(ptm3):
                        ptm3 = [ptm3[0], pt2[1] + self.CARDINALW * (idx + 1) * (+1 if pt2_in_b2 else -1)]

                    ptm2 = [pt1[0] + (b2_side - pt1[0]) // 2, ptm3[1]]
                    ptm1 = [ptm2[0], pt1[1]]
                    # (halfway to pt2.x, pt1.y), (halfway to pt2.x, pt2.y +- vertical step), (pt2.x, pt2.y +- vertical step)
                    wpts += [ptm1, ptm2, ptm3]
            opts["pts"][1:-1] = wpts

        # Fifth pass: calculate precise waypoints, cornerpoints, crowfoot points etc
        for (name1, name2, cols), opts in lines.items():
            pts = opts["pts"]
            cpts, clines, wlines, trect = [], [], [], []
            for i, wpt1 in enumerate(pts[:-1]):
                wpt2 = pts[i + 1]

                # Make rounded corners
                mywpt1, mywpt2 = wpt1[:], wpt2[:]
                axis = 0 if wpt1[0] != wpt2[0] else 1
                direction = 1 if wpt1[axis] < wpt2[axis] else -1
                if i: # Not first step: nudge start 1px further
                    nudge = 1 if direction > 0 else 0
                    mywpt1 = [wpt1[0] + (1 - axis) * nudge, wpt1[1] + axis * nudge]
                elif direction < 0: # First step going backward: nudge start 1px closer
                    mywpt1 = [mywpt1[0] + 1, mywpt1[1]]
                if i < len(pts) - 2: # Not last step: nudge end 1px closer
                    nudge = -1 if direction < 0 else 0
                    mywpt2 = [wpt2[0] - (1 - axis) * nudge, wpt2[1] - axis * nudge]
                elif mywpt2[1] < mywpt1[1]: # Last step to item bottom: nudge end 1px lower
                    mywpt2 = [mywpt2[0], mywpt2[1] + 1]
                if i: # Add smoothing point at corner between this and last step
                    wpt0 = pts[i - 1]
                    dx = -1 if not axis and direction < 0 else 0
                    dy = -1     if axis and direction < 0 else 0
                    cpt = [mywpt1[0] + axis       * (-1 if wpt0[0] < wpt1[0] else 1) + dx,
                           mywpt1[1] + (1 - axis) * (-1 if wpt0[1] < wpt1[1] else 1) + dy]
                    cpts.append(cpt)

                wlines.append((mywpt1, mywpt2))

            # Make cardinality crowfoot
            ptc0 = [pts[0][0] + self.CARDINALW * (-1 if pts[0][0] > pts[1][0] else 1), pts[0][1]]
            ptc1 = [pts[0][0], ptc0[1] - self.CARDINALH]
            ptc2 = [pts[0][0], ptc0[1] + self.CARDINALH]
            clines.extend([(ptc1, ptc0), (ptc2, ptc0)])

            # Make parent-item dash
            direction = 1 if pts[-1][1] > b2.Top else -1
            ptd1 = [pts[-1][0] - self.DASHSIDEW, pts[-1][1] + direction]
            ptd2 = [pts[-1][0] + self.DASHSIDEW + 1, ptd1[1]]
            clines.append((ptd1, ptd2))

            # Make foreign key label
            if opts["name"]:
                text = util.ellipsize(util.unprint(opts["name"]), self.MAX_TEXT)
                textent = self.GetTextExtent(text)
                tw, th = textent[0] + textent[3], textent[1] + textent[2]
                tpt1, tpt2 = next(pts[i:i+2] for i in range(len(pts) - 1)
                                  if pts[i][0] == pts[i+1][0])
                tx = tpt1[0] - tw // 2
                ty = min(tpt1[1], tpt2[1]) - th // 2 + abs(tpt1[1] - tpt2[1]) // 2
                trect = [tx, ty, tw, th]

            bounds = Rect()
            for pp in wlines: bounds.Union(Rect(*map(Point, pp)))
            for pp in clines: bounds.Union(Rect(*map(Point, pp)))
            if trect: bounds.Union(trect)
            self._dc.SetIdBounds(opts["id"], bounds)
            opts.update(waylines=wlines, cardlines=clines, cornerpts=cpts, textrect=trect)


    def PositionItemsGraph(self, viewport, progress=None):
        """
        Calculates item positions using a force-directed graph layout.

        @param   viewport  area to fit graph into
        @param   progress  callback function(step), if any, returning whether to stop calculations
        """

        nodes = [{"name": o["name"], "x": b.Left, "y": b.Top, "size": self.GetItemSize(o["name"])}
                 for o in self._objs.values() for b in [self._dc.GetIdBounds(o["id"])]]
        links = [(n1, n2) for n1, n2, opts in self._lines]
        bounds = [0, 0] + list(self._size)

        items = self.GraphLayout.layout(nodes, links, bounds, viewport, progress)
        for name, opts in items.items() if not progress or progress() else ():
            o = self._objs.get(name)
            if not o: continue # for

            bounds = self._dc.GetIdBounds(o["id"])
            dx, dy = opts["x"] - bounds.Left, opts["y"] - bounds.Top
            bounds.Offset(dx, dy)
            self._dc.TranslateId(o["id"], dx, dy)
            self._dc.SetIdBounds(o["id"], bounds)


    def PositionItemsGrid(self, viewport):
        """
        Calculates item positions using a simple grid layout.

        @param   viewport  area to fit grid into, on need expanded down if horizontal else right
        """
        MAXW = max(500 * self._zoom, viewport.Width)
        MAXH = max(500 * self._zoom, viewport.Height)

        def get_dx(rects, idx):
            """Returns starting X for column or row."""
            if self._layout["grid"]["vertical"]:
                result = 0
                for rr in filter(bool, rects[:idx]):
                    ww = [r.Width for r in rr]
                    median = sorted(ww)[len(rr) // 2]
                    result += max(w for w in ww if w < 1.5 * median)
            else:
                result = rects[idx][-1].Right if rects[idx] else 0
            return self.GPAD + result + (idx * self.GPAD if self._layout["grid"]["vertical"] else 0)

        def get_dy(rects, idx):
            """Returns starting Y for column or row."""
            if self._layout["grid"]["vertical"]:
                result = max(r.Bottom for r in rects[idx]) if rects[idx] else 0
            else:
                result = max(r.Bottom for r in rects[-2]) if len(rects) > 1 else 0
            return self.GPAD + result

        do_reverse = bool(self._layout["grid"]["reverse"])
        numval = lambda o: 0
        # Sort views always to the end
        catval = lambda c: c.upper() if do_reverse and util.lceq(c, "view") else c.lower()
        if "columns" == self._layout["grid"]["order"]:
            numval = lambda o: len(self._db.schema[o["type"]].get(o["name"], {}).get("columns", []))
        elif "rows" == self._layout["grid"]["order"]:
            numval = lambda o: self._db.schema[o["type"]].get(o["name"], {}).get("count", 0)
        elif "bytes" == self._layout["grid"]["order"]:
            statmap = util.CaselessDict({x["name"]: x["size_total"] for x in self._objs.values()
                                         if x.get("size_total") is not None})
            numval = lambda o: statmap.get(o["name"], 0)
        sortkey = lambda o: (catval(o["type"]), numval(o), o["name"].lower())
        items = sorted(self._order, key=sortkey, reverse=do_reverse)

        if self._layout["grid"]["vertical"]:
            col, colrects = 0, [[]] # [[col 0 rect 0, rect 1, ], ]
            for o in items:
                x, y = get_dx(colrects, col), get_dy(colrects, col)
                rect = Rect(x, y, *self.GetItemSize(o["name"]))

                xrect = next((r for r in colrects[-2][::-1] if r.Intersects(rect)),
                             None) if col else None # Overlapping rect in previous column
                while xrect or colrects[-1] and y + rect.Height > MAXH:

                    # Step lower or to next col if prev col has wide item
                    if xrect and xrect.Bottom + self.GPAD + rect.Height > MAXH:
                        col, colrects, y = col + 1, colrects + [[]], self.GPAD
                    elif xrect:
                        y = xrect.Bottom + self.GPAD

                    if colrects[-1] and y + rect.Height > MAXH:
                        col, colrects, y = col + 1, colrects + [[]], self.GPAD

                    rect = Rect(get_dx(colrects, col), y, *rect.Size)
                    xrect = next((r for r in colrects[-2][::-1] if r.Intersects(rect)),
                                 None) if col else None

                dcrect = Rect((viewport.Left + rect.Left, viewport.Top + rect.Top), rect.Size)
                self._dc.SetIdBounds(o["id"], dcrect)
                colrects[-1].append(rect)
        else:
            row, rowrects = 0, [[]] # [[row 0 rect 0, rect 1, ], ]
            for o in items:
                x, y = get_dx(rowrects, row), get_dy(rowrects, row)
                rect = Rect(x, y, *self.GetItemSize(o["name"]))

                if rowrects[-1] and x + rect.Width > MAXW:
                    row, rowrects, x = row + 1, rowrects + [[]], self.GPAD
                    rect = Rect(x, get_dy(rowrects, row), *rect.Size)

                dcrect = Rect((viewport.Left + rect.Left, viewport.Top + rect.Top), rect.Size)
                self._dc.SetIdBounds(o["id"], dcrect)
                rowrects[-1].append(rect)

        self.EnsureSize()


    def MakeItemStatistics(self, opts):
        """Returns {?size, ?rows, ?rows_maxunits} for schema item if stats enabled and available."""
        stats = {}
        if opts.get("size_total") is not None:
            stats["size"] = util.format_bytes(opts["size_total"])
        if opts.get("count") is not None:
            stats["rows"] = util.count(opts, unit="row")
            stats["rows_maxunits"] = util.plural("row", opts["count"], max_units=True)
        return stats


    def Draw(self, remake=False, remakelines=False, recalculate=False):
        """
        Draws everything, remaking item bitmaps and relation lines if specified,
        or recalculating all relation lines if specified,
        or recalculating only those relation lines connected to selected items if specified.
        """
        for o in self._order if remake or remakelines else ():
            r = self._dc.GetIdBounds(o["id"])
            self._dc.SetIdBounds(o["id"], Rect(r.TopLeft, self.GetItemSize(o["name"])))
        if not self._show_lines:
            for opts in self._lines.values(): self._dc.ClearId(opts["id"])
        self.RecordDragRect()
        self.RecordLines(remake=remake or remakelines, recalculate=recalculate)
        self.RecordItems()


    def Redraw(self, viewport, layout):
        """
        Redraws everything, remaking item bitmaps and applying layout.

        @param   viewport  area to fit diagram into
        @param   layout    layout to apply
        """
        self.UpdateStatistics()
        for o in self._order:
            bmps = self.GetItemBitmaps(o)
            if bmps: o["bmp"], o["bmpsel"] = bmps
        self.Layout = layout
        wrk = self.PositionItemsGrid if self.LAYOUT_GRID == self.Layout else self.PositionItemsGraph
        wrk(viewport)
        self.CalculateLines(remake=True)
        self.Draw()


    def RecordItems(self):
        """Records all schema items to DC."""
        for o in self._order:
            if o["name"] not in self._sels: self.RecordItem(o["name"])
        for o in self._order:
            if o["name"] in self._sels: self.RecordItem(o["name"])


    def RecordItem(self, name, bounds=None):
        """Records a single schema item to DC."""
        if name not in self._objs: return
        if wx: self.RecordItem_wx(name, bounds=bounds)


    def RecordItem_wx(self, name, bounds=None):
        """Records a single schema item to DC as wx.Bitmap."""
        o = self._objs[name]
        bounds = bounds or self._dc.GetIdBounds(o["id"])
        self._dc.RemoveId(o["id"])
        self._dc.SetId(o["id"])
        bmpname = ("bmparea" if self._dragrect else "bmpsel") if o["name"] in self._sels else "bmp"
        bmp = o[bmpname]
        if bmp is None:
            bmp = self.GetItemBitmaps(o, dragrect=name in self._sels)
            if isinstance(bmp, tuple):
                o["bmp"], o["bmpsel"] = bmp
                bmp = o[bmpname]
            else: o.update({bmpname: bmp})
        if not bounds:  # wx.Rect(0, 0, 0, 0): item not in DC yet
            bounds = wx.Rect(0, 0, *bmp.Size)
        pos = [a - (o["name"] in self._sels) * 2 * self._zoom for a in bounds.TopLeft]
        self._dc.DrawBitmap(bmp, pos, useMask=True)
        self._dc.SetIdBounds(o["id"], wx.Rect(bounds.TopLeft, bounds.BottomRight))
        self._dc.SetId(-1)


    def RecordDragRect(self):
        """Records selection rectangle currently being dragged."""
        if not self._dragrectid: return
        if wx: self.RecordDragRect_wx()


    def RecordDragRect_wx(self):
        """Records selection rectangle currently being dragged, using wx."""
        if not self._dragrectid: return

        self._dc.ClearId(self._dragrectid)
        self._dc.SetId(self._dragrectid)
        self._dc.SetPen(controls.PEN(self._colour_dragfg))
        self._dc.SetBrush(controls.BRUSH(self._colour_dragbg))
        #self._dc.SetBrush(wx.TRANSPARENT_BRUSH)

        self._dc.DrawRectangle(self._dragrectabs)
        self._dc.SetIdBounds(self._dragrectid, self._dragrectabs)
        self._dc.SetId(-1)


    def RecordLines(self, remake=False, recalculate=False, dc=None, shift=None):
        """
        Records foreign relation lines to DC if showing lines is enabled.

        @param   remake       whether to recalculate lines of not only selected items
        @param   recalculate  whether to recalculate lines of selected items
        @param   dc           wx.DC to use if not own PseudoDC
        @param   shift        line coordinate shift as (dx, dy) if any
        """
        if not self._show_lines: return
        if wx: self.RecordLines_wx(remake, recalculate, dc, shift)


    def RecordLines_wx(self, remake=False, recalculate=False, dc=None, shift=None):
        """
        Records foreign relation lines to DC if showing lines is enabled, using wx.

        @param   remake       whether to recalculate lines of not only selected items
        @param   recalculate  whether to recalculate lines of selected items
        @param   dc           wx.DC to use if not own PseudoDC
        @param   shift        line coordinate shift as (dx, dy) if any
        """
        if remake or recalculate: self.CalculateLines(remake)

        fadedcolour  = controls.ColourManager.Adjust(self.LineColour, self.BackgroundColour, 0.7)
        linepen      = controls.PEN(self.LineColour)
        linefadedpen = controls.PEN(fadedcolour)
        textbrush, textpen = controls.BRUSH(self.BackgroundColour), controls.PEN(self.BackgroundColour)
        textdragbrush = controls.BRUSH(self._colour_dragbg)
        textdragpen   = controls.PEN(self._colour_dragbg)
        cornerpen = controls.PEN(controls.ColourManager.Adjust(self.LineColour,  self.BackgroundColour))
        cornerfadedpen = controls.PEN(controls.ColourManager.Adjust(fadedcolour, self.BackgroundColour))

        adjust = (lambda *a: [a + b for a, b in zip(a, shift)]) if shift else lambda *a: a

        dc = dc or self._dc
        dc.SetFont(self._font)
        for (name1, name2, cols), opts in sorted(self._lines.items(),
                key=lambda x: any(n in self._sels for n in x[0][:2])):
            if not opts["pts"]: continue # for (name1, name2, cols)
            b1, b2 = (self._dc.GetIdBounds(o["id"])
                      for o in map(self._objs.get, (name1, name2)))

            if isinstance(dc, wx.adv.PseudoDC):
                dc.RemoveId(opts["id"])
                dc.SetId(opts["id"])

            lpen = linepen
            if self._dragrect and not any(self._dragrectabs.Contains(b) for b in (b1, b2)) \
            or self._sels and name1 not in self._sels and name2 not in self._sels:
                lpen = linefadedpen # Draw lines of not-focused items more faintly
            dc.SetPen(lpen)

            # Draw main lines
            for pt1, pt2 in opts["waylines"]: dc.DrawLine(adjust(*pt1), adjust(*pt2))

            # Draw cardinality crowfoot and parent-item dash
            for pt1, pt2 in opts["cardlines"]: dc.DrawLine(adjust(*pt1), adjust(*pt2))

            # Draw foreign key label
            if self._show_labels and opts["name"]:
                tname = util.ellipsize(util.unprint(opts["name"]), self.MAX_TEXT)
                tx, ty, tw, th = opts["textrect"]
                tbrush, tpen = textbrush, textpen
                if self._dragrect and self._dragrectabs.Contains((tx, ty, tw, th)):
                    tbrush, tpen = textdragbrush, textdragpen
                dc.SetBrush(tbrush)
                dc.SetPen(tpen)
                dc.DrawRectangle(adjust(tx, ty), (tw, th))
                dc.SetTextForeground(lpen.Colour)
                dc.DrawText(tname, adjust(tx, ty))

            # Draw inner rounded corners
            dc.SetPen(cornerfadedpen if lpen == linefadedpen else cornerpen)
            for cpt in opts["cornerpts"]: dc.DrawPoint(adjust(*cpt))

            if isinstance(dc, wx.adv.PseudoDC): dc.SetId(-1)


    def GetImageSize(self, obj):
        """Returns dimensions of given image object, as Size(w, h)."""
        if not callable(getattr(obj, "GetSize", None)) and hasattr(obj, "Image"):
            obj = obj.Image
        if callable(getattr(obj, "GetSize", None)):
            return obj.GetSize()
        if hasattr(obj, "size"):
            return Size(obj.size)
        return None


    def GetStaticBitmap(self, img):
        """Returns scaled bitmap of PyEmbeddedImage, cached if possible."""
        if wx:
            result = img.Bitmap
            if self._zoom != self.ZOOM_DEFAULT: result = self._cache[self._zoom][img]
            if not result:
                sz = [int(math.ceil(x * self._zoom)) for x in self.GetImageSize(img)]
                result = self._cache[self._zoom][img] = wx.Bitmap(img.Image.Scale(*sz))
        else:
            if img not in self._cache[self.ZOOM_DEFAULT]:
                img_pil = Image.open(io.BytesIO(base64.b64decode(img.data)))
                self._cache[self.ZOOM_DEFAULT][img] = img_pil
            result = self._cache[self._zoom][img]
            if not result:
                img_pil_default = self._cache[self.ZOOM_DEFAULT][img]
                sz = [int(math.ceil(x * self._zoom)) for x in self.GetImageSize(img_pil_default)]
                result = self._cache[self._zoom][img] = util.img_pil_resize(img_pil_default, sz)

        return result


    def GetStatisticsTexts(self, stats, width):
        """
        Returns final stats texts to show for item stats, as (rowstext, sizetext).

        @param   stats  item statistics dictionary
        @param   width  item width in pixels
        """
        stats = stats or {}
        stats_font = self.MakeFont(self.FONT_FACE, self.FONT_SIZE * self._zoom + self.FONT_STEP_STATS)
        text1, text2 = stats.get("rows", ""), stats.get("size", "")

        w1 = next(d[0] + d[3] for d in [self.GetTextExtent(text1, stats_font)]) if text1 else 0
        w2 = next(d[0] + d[3] for d in [self.GetTextExtent(text2, stats_font)]) if text2 else 0
        if w1 + w2 + 2 * self.BRADIUS > width:
            text1 = stats.get("rows_maxunits", text1) # Exact number does not fit: draw as "6.1M rows"
        return text1, text2


    def HasItemBitmaps(self, opts, statistics=None):
        """
        Returns whether schema item has cached bitmap for current view.

        @param   statistics  {?size, ?rows, ?rows_maxunits} to use if not item current
        """
        statistics = (statistics or self.MakeItemStatistics(opts)) if self._show_stats else None
        key1 = opts["__id__"]
        key2 = (opts["sql0"], bool(opts.get("meta") or opts.get("hasmeta")),
                self._show_cols, self._show_keys, self._show_nulls,
                str(statistics) if statistics else None, False)
        return key1 in self._cache[self._zoom] and key2 in self._cache[self._zoom][key1]


    def GetItemBitmaps(self, opts, statistics=None, dragrect=False):
        """
        Wrapper for MakeItemBitmaps(), using cache if possible.

        @param   statistics  {?size, ?rows, ?rows_maxunits} to use if not item current
        @param   dragrect    whether to return a single bitmap for drag rectangle highlight
        """
        if not self._use_cache: return self.MakeItemBitmaps(opts, statistics, dragrect)
        statistics = (statistics or self.MakeItemStatistics(opts)) if self._show_stats else None

        key1 = opts["__id__"]
        key2 = (opts["sql0"], bool(opts.get("meta") or opts.get("hasmeta")),
                self._show_cols, self._show_keys, self._show_nulls,
                str(statistics) if statistics else None, bool(dragrect))
        mycache = self._cache[self._zoom][key1]
        if key2 not in mycache:
            for cc in self._cache.values(): # Nuke any outdated bitmaps: SQL meta changed
                for k in list(cc.get(key1) or {}):
                    if k[:2] != key2[:2]: cc[key1].pop(k)

            mycache[key2] = self.MakeItemBitmaps(opts, statistics, dragrect)
        return mycache[key2]


    def SetItemBitmaps(self, name, **kwargs):
        """
        Sets item bitmaps.

        @param   name    item name
        @param   kwargs  supported keys: "bmp", "bmpsel" and "bmparea"
        """
        o = self._objs[name]
        for k in ("bmp", "bmpsel", "bmparea"):
            if k in kwargs: o[k] = kwargs[k]


    def MakeItemBitmaps(self, opts, statistics=None, dragrect=False):
        """
        Returns bitmaps representing a schema item like table.

        @param    opts        schema item
        @param    statistics  item statistics {?size, ?rows, ?rows_maxunits} if any
        @param    dragrect    whether to return a single bitmap for drag rectangle highlight
        @return               (default bitmap, focused bitmap) or bitmap inside drag rectangle
        """
        if wx: return self.MakeItemBitmaps_wx(opts, statistics, dragrect)


    def MakeItemBitmaps_wx(self, opts, statistics=None, dragrect=False):
        """
        Returns wx.Bitmaps representing a schema item like table.

        @param    opts         schema item
        @param    statistics  item statistics {?size, ?rows, ?rows_maxunits} if any
        @param    dragrect    whether to return a single bitmap for drag rectangle highlight
        @return               (default bitmap, focused bitmap) or bitmap inside drag rectangle
        """
        CRADIUS = self.BRADIUS if "table" == opts["type"] else 0

        (w, h), title, coltexts, colmax = self.CalculateItemSize(opts, statistics)
        collists, statslists = [[], []], [[], [], [], []] # [[text, ], [(x, y), ]]
        pks, fks = (sum((list(c["name"]) for c in v), []) for v in opts["keys"])

        # Populate column texts and coordinates
        for i, texts in enumerate(coltexts):
            for j, _ in enumerate(["name", "type"]):
                text = texts[j]
                if not text: continue # for j, k
                dx = self.LPAD + j * (colmax["name"] + self.HPAD)
                dy = self.HEADERH + self.HEADERP + i * self.LINEH
                collists[0].append(text); collists[1].append((dx, dy))

        # Populate statistics texts
        if statistics:
            stats_font = self.MakeFont(self.FONT_FACE, self.FONT_SIZE * self._zoom + self.FONT_STEP_STATS)
            dx, dy = self.BRADIUS, h - self.STATSH + 1
            text1, text2 = self.GetStatisticsTexts(statistics, w)
            if text1:
                statslists[0].append(text1); statslists[1].append((dx, dy))
            if text2:
                w2 = next(d[0] + d[3] for d in [self.GetTextExtent(text2, stats_font)])
                dx = w - w2 - self.BRADIUS
                statslists[2].append(text2); statslists[3].append((dx, dy))

        pkbmp, fkbmp, nbmp = None, None, self.GetStaticBitmap(images.DiagramNull)
        if pks: pkbmp = self.GetStaticBitmap(images.DiagramPK)
        if fks: fkbmp = self.GetStaticBitmap(images.DiagramFK)

        bmp = wx.Bitmap(w, h, depth=24)
        dc = wx.MemoryDC(bmp)
        dc.Background = wx.TRANSPARENT_BRUSH
        dc.Clear()
        bg, gradfrom = self.BackgroundColour, self.GradientStartColour
        if dragrect:
            bg = gradfrom = self._colour_dragbg

        # Fill with gradient, draw border
        dc.GradientFillLinear((0, 0, w, h), gradfrom, self.GradientEndColour)
        dc.Pen, dc.Brush = controls.PEN(self.BorderColour), wx.TRANSPARENT_BRUSH
        dc.DrawRoundedRectangle(0, 0, w, h, CRADIUS)

        if any(collists):
            # Empty out columns middle, draw header separator
            dc.Pen   = controls.PEN(bg)
            dc.Brush = controls.BRUSH(bg)
            dc.DrawRectangle(1, self.HEADERH, w - 2, self.HEADERP + self.LINEH * len(coltexts))
            dc.Pen, dc.Brush = controls.PEN(self.BorderColour), wx.TRANSPARENT_BRUSH
            dc.DrawLine(0, self.HEADERH, w, self.HEADERH)

        # Draw title
        dc.SetFont(self._font_bold)
        dc.TextForeground = self.ForegroundColour
        dc.DrawLabel(title, (0, 1, w, self.HEADERH), wx.ALIGN_CENTER)

        # Draw columns: name and type, and primary/foreign key icons
        dc.SetFont(self._font)
        dc.DrawTextList(collists[0], collists[1])
        for i, col in enumerate(opts.get("columns") or []):
            if not self.IsColumnShown(opts, col):
                continue  # for i, col
            dy = self.HEADERH + self.HEADERP + i * self.LINEH
            if col["name"] in pks:
                dc.DrawBitmap(pkbmp, 3 * max(self._zoom, 1), dy + 1, useMask=True)
            elif "notnull" not in col and self._show_nulls:
                dc.DrawBitmap(nbmp, 3 * max(self._zoom, 1), dy + 1, useMask=True)
            if col["name"] in fks:
                b, bw = fkbmp, fkbmp.Width
                dc.DrawBitmap(b, w - bw - 6 * self._zoom, dy + 1, useMask=True)

        # Draw statistics texts and separator
        if statistics:
            if any(collists):
                dc.DrawLine(0, h - self.STATSH, w, h - self.STATSH)
            dc.SetFont(stats_font)
        if statslists[0]:
            dc.DrawTextList(statslists[0], statslists[1])
        if statslists[2]:
            dc.TextForeground = self.BackgroundColour
            dc.DrawTextList(statslists[2], statslists[3])

        dc.SelectObject(wx.NullBitmap)
        del dc

        if CRADIUS:
            # Make transparency mask for excluding content outside rounded corners
            mbmp = wx.Bitmap(bmp.Size)
            mdc = wx.MemoryDC(mbmp)
            mdc.Background = wx.TRANSPARENT_BRUSH
            mdc.Clear()
            mdc.Pen, mdc.Brush = wx.WHITE_PEN, wx.WHITE_BRUSH
            mdc.DrawRoundedRectangle(0, 0, mbmp.Width, mbmp.Height, CRADIUS)
            mdc.SelectObject(wx.NullBitmap)
            del mdc
            bmp.SetMask(wx.Mask(mbmp, wx.TRANSPARENT_BRUSH.Colour))

            # Make transparency mask for excluding content outside rounded shadow corners
            sbmp = wx.Bitmap(w + 2 * self.FMARGIN, h + 2 * self.FMARGIN)
            sdc = wx.MemoryDC(sbmp)
            sdc.Background = wx.TRANSPARENT_BRUSH
            sdc.Clear()
            sdc.Pen, sdc.Brush = wx.WHITE_PEN, wx.WHITE_BRUSH
            sdc.DrawRoundedRectangle(0, 0, sbmp.Width, sbmp.Height, CRADIUS)
            del sdc

        # Make "selected" bitmap, with a surrounding shadow
        bmpsel = wx.Bitmap(w + 2 * self.FMARGIN, h + 2 * self.FMARGIN)
        fdc = wx.MemoryDC(bmpsel)
        fdc.Background = controls.BRUSH(self.SelectionColour)
        fdc.Clear()
        fdc.DrawBitmap(bmp, self.FMARGIN, self.FMARGIN, useMask=True)
        fdc.SelectObject(wx.NullBitmap)
        del fdc
        if CRADIUS: bmpsel.SetMask(wx.Mask(sbmp, wx.TRANSPARENT_BRUSH.Colour))

        return bmpsel if dragrect else (bmp, bmpsel)


    def IsColumnShown(self, opts, col):
        """
        Returns whether item column should be shown with current settings.

        @param   opts  entity data dictionary
        @param   col   column data dictionary
        """
        if self._show_keys:
            return any(col.get("name") in c["name"] for cc in opts["keys"] for c in cc)
        else: return self._show_cols


    def GetTextExtent(self, text, font=None):
        """
        Returns the dimensions of the specified text in the specified font.

        @param   text  text to measure, linefeeds are ignored
        @param   font  wx.Font or PIL.ImageFont, if not using default font
        @return        (width, height, descent, externalLeading) if wx available
                       else (width, height, 0, 0)
        """
        font = font or self._font
        if wx and isinstance(font, wx.Font):
            func, args = self._measurer.GetFullTextExtent, [text, font]
        else:
            func, args = font.getsize, [text]
        extent = util.memoize(func, *args, __key__="GetFullTextExtent")
        return (extent + (0, 0)) if 2 == len(extent) else extent


    def MakeFont(self, name, size, bold=False):
        """Returns a font with specified attributes; name is ignored if no wx."""
        bold = bool(bold)
        if wx:
            if not wx.Font.__hash__: wx.Font.__hash__ = lambda x: id(x)  # Py3 workaround
            weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
            font = util.memoize(wx.Font, size, wx.FONTFAMILY_MODERN,
                                wx.FONTSTYLE_NORMAL, weight, faceName=name)
        else:
            font, key = self.FONTS.get(name, {}).get((size, bold)), "boldpath" if bold else "path"

            for n, opts in self.FONTS.items() if font is None else (): # First pass: try loading from file
                if opts.get(key):
                    try: font = ImageFont.truetype(opts[key], size)
                    except Exception:
                        logger.exception("Error loading font %r (%s).", n, opts[key])
                    else: break # for n, opts

            for n, opts in self.FONTS.items() if font is None else (): # Second pass: try system font
                for filename in ("%s.ttf" % n, "%s.ttf" % n.lower(), "%s.TTF" % n.upper()):
                    try: font = ImageFont.truetype(filename, size)
                    except Exception:
                        logger.exception("Error loading font %r.", n)
                    else: break # for n, opts

            font = font or ImageFont.load_default()
            self.FONTS.setdefault(name, {}).setdefault("cache", {})[(size, bold)] = font

        return font


    def SetFonts(self, *fonts):
        """
        Sets fonts for diagram texts, as a prioritized list.

        @param   fonts  list of: name or (name, size) or ("name", size, ?ttf_normpath, ?ttf_boldpath)
        """
        success, ok = False, False
        self.FONTS.clear()
        for name in fonts:
            name, size, normpath, boldpath = (util.tuplefy(name) + (self.FONT_SIZE, None, None))[:4]

            if normpath and (not os.path.isfile(normpath) or not os.path.getsize(normpath)):
                normpath = None
            if boldpath and (not os.path.isfile(boldpath) or not os.path.getsize(boldpath)):
                boldpath = None

            self.FONTS[name] = {"size": size}
            if normpath: self.FONTS[name].update({"path":     normpath})
            if boldpath: self.FONTS[name].update({"boldpath": boldpath})

            if wx:
                if name.lower() not in [x.lower() for x in wx.FontEnumerator().GetFacenames()]:
                    for path in filter(bool, (normpath, boldpath)):
                        try: normpath and wx.Font.AddPrivateFont(normpath)
                        except Exception: logger.exception("Error adding font %r (%s).", name, path)
                ok = name.lower() in [x.lower() for x in wx.FontEnumerator().GetFacenames()]
            else:
                ok = bool(normpath and boldpath)

            if ok and not success:
                self.FONT_FACE = name
                self.FONT_SIZE = size
                success = True


    def EnsureSize(self):
        """Enlarge diagram area if less than current full bounds."""
        size2, bounds = Size(self._size), self.GetFullBounds(lines=True)
        if bounds and bounds.Right >= self._size[0]:
            size2[0] = bounds.Right + self.GPAD
        if bounds and bounds.Bottom >= self._size[1]:
            size2[1] = bounds.Bottom + self.GPAD
        if size2 != self._size: self._size = size2


    def GetItem(self, name):
        """Returns a schema item by name."""
        return self._objs[name].copy() if name in self._objs else None


    def GetItemSize(self, name):
        """Returns item bitmap size, calculated if bitmap not available."""
        o = self._objs[name]
        if self.HasItemBitmaps(o): return self.GetImageSize(self.GetItemBitmaps(o)[0])
        return self.CalculateItemSize(o)[0]


    def GetItems(self): return type(self._objs)((k, v.copy()) for k, v in self._objs.items())
    Items = property(GetItems)


    def GetLines(self): return type(self._lines)((k, v.copy()) for k, v in self._lines.items())
    Lines = property(GetLines)


    def GetOrder(self): return [o.copy() for o in self._order]
    Order = property(GetOrder)


    def GetLayout(self, active=True):
        """Returns current layout, by default active only."""
        return self._layout["layout"] if active and self._layout["active"] else None
    def SetLayout(self, layout, options=None):
        """
        Sets diagram layout style.

        @param   layout   one of LAYOUT_GRID, LAYOUT_GRAPH
        @param   options  options for grid layout as
                          {"order": "name", "reverse": False, "vertical": True},
                          updates current options
        """
        if layout in (self.LAYOUT_GRID, self.LAYOUT_GRAPH):
            self._layout["layout"] = layout
            self._layout["active"] = True
        if self.LAYOUT_GRID == self.Layout and options:
            self._layout[layout].update(options)
    Layout = property(GetLayout, SetLayout)


    def GetLayoutOptions(self, layout=None):
        """
        Returns current options for specified layout, e.g. {"order": "name"} for grid,
        or global layout options as {"layout": "grid", "active": True, "grid": {..}}.
        """
        return copy.deepcopy(self._layout if layout is None else self._layout.get(layout))


    def SetLayoutActive(self, active=True):
        """Sets current layout as active or inactive.."""
        self._layout["active"] = bool(active)


    def GetSelection(self):
        """Returns names of currently selected items."""
        return [o["name"] for o in self._order if o["name"] in self._sels]
    def SetSelection(self, names):
        """Sets current selection to specified names."""
        names = [] if names is None else names
        if len(names) == len(self._sels) and all(x in self._sels for x in names):
            return
        self._sels.clear()
        self._sels.update({self._objs[n]["name"]: self._objs[n]["id"] for n in names
                           if n in self._objs})
        for name in self._sels:
            self._order.remove(self._objs[name]); self._order.append(self._objs[name])
    Selection = property(GetSelection, SetSelection)


    def GetShowColumns(self):
        """Returns whether columns are shown."""
        return self._show_cols
    def SetShowColumns(self, show=True):
        """Sets showing columns on or off. Setting on will set ShowKeyColumns off."""
        show = bool(show)
        if show == self._show_cols: return
        self._show_cols = show
        if show: self._show_keys = False
    ShowColumns = property(GetShowColumns, SetShowColumns)


    def GetShowKeyColumns(self):
        """Returns whether only key columns are shown."""
        return self._show_keys
    def SetShowKeyColumns(self, show=True):
        """Sets showing only key columns on or off. Setting on will set ShowColumns off."""
        show = bool(show)
        if show == self._show_keys: return
        self._show_keys = show
        if show: self._show_cols = False
    ShowKeyColumns = property(GetShowKeyColumns, SetShowKeyColumns)


    def GetShowNulls(self):
        """Returns whether NULL column markers are shown."""
        return self._show_nulls
    def SetShowNulls(self, show=True):
        """Sets showing NULL column markers on or off."""
        self._show_nulls = bool(show)
    ShowNulls = property(GetShowNulls, SetShowNulls)


    def GetShowLines(self):
        """Returns whether foreign relation lines are shown."""
        return self._show_lines
    def SetShowLines(self, show=True):
        """Sets showing foreign relation lines on or off."""
        self._show_lines = bool(show)
    ShowLines = property(GetShowLines, SetShowLines)


    def GetShowLineLabels(self):
        """Returns whether foreign relation line labels are shown."""
        return self._show_labels
    def SetShowLineLabels(self, show=True):
        """Sets showing foreign relation line labels on or off."""
        self._show_labels = bool(show)
    ShowLineLabels = property(GetShowLineLabels, SetShowLineLabels)


    def GetShowStatistics(self):
        """Returns whether table statistics are shown."""
        return self._show_stats
    def SetShowStatistics(self, show=True):
        """Sets showing table statistics on or off."""
        self._show_stats = bool(show)
    ShowStatistics = property(GetShowStatistics, SetShowStatistics)


    def GetSize(self):       return Size(self._size)
    def SetSize(self, size): self._size = Size(size)
    Size = property(GetSize, SetSize)


    def GetDragRect(self):
        """Returns current drag rectangle, or None"""
        return None if self._dragrect is None else Rect(self._dragrect)
    def SetDragRect(self, rect):
        """Sets current drag rectangle, or clears if given None."""
        if rect is None:
            if self._dragrectid is not None: self._dc.RemoveId(self._dragrectid)
            self._dragrectid, self._dragrect, self._dragrectabs = None, None, None
        else:
            if not self._dragrectid:
                self._dragrectid = (max(self._ids) if self._ids else 0) + 1

            r = Rect(rect)
            r.Left = max(0, min(r.Left, self._size[0] - 1))
            r.Top  = max(0, min(r.Top,  self._size[1] - 1))
            if not (0 <= r.Left + r.Width <= self._size[0]):
                r.Width = (0 if r.Width < 0 else self._size[0]) - r.Left
            if not (0 <= r.Top + r.Height <= self._size[1]):
                r.Height = (0 if r.Height < 0 else self._size[1]) - r.Top
            self._dragrect = Rect(r)

            if r.Width  < 0: r = Rect(r.Left + r.Width, r.Top, -r.Width,  r.Height)
            if r.Height < 0: r = Rect(r.Left, r.Top + r.Height, r.Width, -r.Height)
            self._dragrectabs = r
    DragRect = property(GetDragRect, SetDragRect)


    def DragRectAbsolute(self):
        """Returns current drag rectangle in left-to-right coordinates, or None."""
        return None if self._dragrectabs is None else Rect(self._dragrectabs)
    DragRectAbsolute = property(DragRectAbsolute)


    def GetFont(self):       return self._font
    def SetFont(self, font): self._font = font
    Font = property(GetFont, SetFont)


    def GetBoldFont(self):       return self._font_bold
    def SetBoldFont(self, font): self._font_bold = font
    BoldFont = property(GetBoldFont, SetBoldFont)


    def GetBackgroundColour(self):         return self._colour_bg
    def SetBackgroundColour(self, colour): self._colour_bg = Colour(colour)
    BackgroundColour = property(GetBackgroundColour, SetBackgroundColour, doc=
    """Diagram background colour.""")


    def GetForegroundColour(self):         return self._colour_fg
    def SetForegroundColour(self, colour): self._colour_fg = Colour(colour)
    ForegroundColour = property(GetForegroundColour, SetForegroundColour, doc=
    """Diagram text colour.""")


    def GetBorderColour(self):         return self._colour_border
    def SetBorderColour(self, colour): self._colour_border = Colour(colour)
    BorderColour = property(GetBorderColour, SetBorderColour, doc=
    """Border colour of entity box.""")


    def GetLineColour(self):         return self._colour_line
    def SetLineColour(self, colour): self._colour_line = Colour(colour)
    LineColour = property(GetLineColour, SetLineColour, doc=
    """Line colour of entity relations.""")


    def GetSelectionColour(self):         return self._colour_select
    def SetSelectionColour(self, colour): self._colour_select = Colour(colour)
    SelectionColour = property(GetSelectionColour, SetSelectionColour, doc=
    """Colour of highlight border around selected entity box.""")


    def GetGradientStartColour(self):         return self._colour_grad1
    def SetGradientStartColour(self, colour): self._colour_grad1 = Colour(colour)
    GradientStartColour = property(GetGradientStartColour, SetGradientStartColour, doc=
    """Gradient start colour of entity title bar background.""")


    def GetGradientEndColour(self):         return self._colour_grad2
    def SetGradientEndColour(self, colour): self._colour_grad2 = Colour(colour)
    GradientEndColour = property(GetGradientEndColour, SetGradientEndColour, doc=
    """Gradient end colour of entity title bar background.""")


    def GetDragBackgroundColour(self):         return self._colour_dragbg
    def SetDragBackgroundColour(self, colour): self._colour_dragbg = Colour(colour)
    DragBackgroundColour = property(GetDragBackgroundColour, SetDragBackgroundColour, doc=
    """Fill colour of the mouse-dragging rectangle.""")


    def GetDragForegroundColour(self):         return self._colour_dragfg
    def SetDragForegroundColour(self, colour): self._colour_dragfg = Colour(colour)
    DragForegroundColour = property(GetDragForegroundColour, SetDragForegroundColour, doc=
    """Border colour of the mouse-dragging rectangle.""")


class MyPoint(object):
    """Simple stand-in for wx.Point."""

    def __init__(self, *args, **kwargs):
        """
        Constructs a point with integer coordinates.

        @param   args  () or (x, y) or (pt)
        """
        self._x = 0
        self._y = 0

        def init_blank():   pass
        def init_xy(x, y):  self._x, self._y = map(int, (x, y))
        def init_point(pt): self._x, self._y = map(int, pt)

        errs = []
        for ctor in (init_blank, init_xy, init_point):
            try: ctor(*args, **kwargs)
            except Exception as e: errs.append(e)
            else: del errs[:]; break # for ctor
        if errs:
            raise TypeError("Point(): arguments did not match any overloaded call\n%s" %
                            "\n".join("  overload %s: %s" % (i + 1, e) for i, e in enumerate(errs)))

    X = property((lambda self: self._x), (lambda self, val: setattr(self, "_x", int(val))))
    x = X

    Y = property((lambda self: self._y), (lambda self, val: setattr(self, "_y", int(val))))
    y = Y

    def Get(self):
        """Returns the x and y properties as a tuple."""
        return (self._x, self._y)

    def __eq__(self, other):
        if isinstance(other, (MyPoint, list, tuple)) and len(other) == len(self):
            return self.Get() == tuple(other)
        return False

    def __add__(self, val):
        if not isinstance(val, (MyPoint, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Point' and %r" % type(val).__name__)
        return type(self)(int(self._x + val[0]), int(self._y + val[1]))

    def __iadd__(self, val):
        if not isinstance(val, (MyPoint, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Point' and %r" % type(val).__name__)
        self._x += int(val[0])
        self._y += int(val[1])
        return self

    def __sub__(self, val):
        if not isinstance(val, (MyPoint, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Point' and %r" % type(val).__name__)
        return type(self)(int(self._x - val[0]), int(self._y - val[1]))

    def __isub__(self, val):
        if not isinstance(val, (MyPoint, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Point' and %r" % type(val).__name__)
        self._x -= int(val[0])
        self._y -= int(val[1])
        return self

    def __neg__(self):
        return type(self)(-self._x, -self._y)

    def __len__(self):
        return 2

    def __getitem__(self, idx):
        return self.Get()[idx]

    def __setitem__(self, idx, val):
        if   0 == idx: self._x = int(val)
        elif 1 == idx: self._y = int(val)
        else:          raise IndexError

    def __str__(self):
        return str(self.Get())

    def __repr__(self):
        return "Point" + str(self.Get())


class MyRect(object):
    """Simple stand-in for wx.Rect."""

    def __init__(self, *args, **kwargs):
        """
        Constructs a rectangle with integer coordinates.

        @param   args  () or (x, y, w, h) or (pos, size) or (size) or (topleft, bottomright)
        """
        self._x = 0
        self._y = 0
        self._w = 0
        self._h = 0

        def init_blank(): pass
        def init_xywh(x, y, w, h):
            self._x, self._y, self._w, self._h = map(int, (x, y, w, h))
        def init_corners(topLeft, bottomRight):
            for i, a in enumerate((topLeft, bottomRight), 1):
                if not isinstance(a, MyPoint):
                    raise TypeError("argument %s has unexpected type %r" % (i, type(a).__name__))
            self._x, self._y = map(int, topLeft)
            self._w, self._h = (int(b - a) for a, b in zip(topLeft, bottomRight))
        def init_pos_size(pos, size):
            (self._x, self._y), (self._w, self._h) = map(int, pos), map(int, size)
        def init_size(size):
            self._w, self._h = map(int, size)
        def init_rect(rect):
            init_xywh(*rect)

        errs = []
        for ctor in (init_blank, init_xywh, init_corners, init_pos_size, init_size, init_rect):
            try: ctor(*args, **kwargs)
            except Exception as e: errs.append(e)
            else: del errs[:]; break # for ctor
        if errs:
            raise TypeError("Rect(): arguments did not match any overloaded call\n%s" %
                            "\n".join("  overload %s: %s" % (i + 1, e) for i, e in enumerate(errs)))

    def Contains(self, *args):
        """
        Returns whether the given point is inside the rectangle (or on its boundary).

        @param   args  (x, y) or (pt) or (rect)
        """
        x, y = args if len(args) == 2 else \
               args[0].Position if isinstance(args[0], Rect) else args[0]
        return x >= self._x and y >= self._y and (y - self._y) < self._h and (x - self._x) < self._w

    def Deflate(self, *args):
        """
        Decreases the rectangle size.

        This method is the opposite from Inflate: Deflate(a, b) is equivalent to Inflate(-a, -b).

        @param   args  (dx, dy) or (size) or (rect)
        """
        x, y = args if len(args) == 2 else \
               args[0].Position if isinstance(args[0], Rect) else args[0]
        return self.Inflate(-x, -y)

    def Inflate(self, *args):
        """
        Increases the size of the rectangle.

        The left border is moved farther left and the right border is moved farther right by dx.
        The upper border is moved farther up and the bottom border is moved farther down by dy.
        If one or both of dx and dy are negative, the opposite happens:
        the rectangle size decreases in the respective direction.

        @param   args  (dx, dy) or (size) or (rect)
        """
        x, y = args if len(args) == 2 else \
               args[0].Position if isinstance(args[0], Rect) else args[0]

        if -2 * x > self._w:
            # Don't allow deflate to eat more width than we have,
            # a well-defined rectangle cannot have negative width.
            self._x += int(self._w / 2)
            self._w = 0
        else: # The inflate is valid.
            self._x -= int(x)
            self._w += int(2 * x)

        if -2 * y > self._h:
            # Don't allow deflate to eat more height than we have,
            # a well-defined rectangle cannot have negative height.
            self._y += int(self._h / 2)
            self._h = 0
        else: # The inflate is valid.
            self._y -= int(y)
            self._h += int(2 * y)

        return self

    def Intersect(self, rect):
        """
        Modifies this rectangle to contain the overlapping portion of this rectangle
        and the one passed in as parameter.
        """
        if not isinstance(rect, MyRect):
            raise TypeError("Intersect(): argument 1 has unexpected type %r" % type(rect).__name__)
        self *= rect
        return self

    def Intersects(self, rect):
        """
        Returns whether this rectangle has a non-empty intersection with the rectangle rect.
        """
        if not isinstance(rect, MyRect):
            raise TypeError("Intersects(): argument 1 has unexpected type %r" % type(rect).__name__)
        rect2 = self * rect
        return rect2.Width != 0

    def Offset(self, *args):
        """
        Moves the rectangle by the specified offset.

        @param   args  (x, y) or (pt)
        """
        x, y = args[0] if len(args) == 1 else args
        self._x, self._y = int(self._x + x), int(self._y + y)

    def Union(self, rect):
        """
        Modifies the rectangle to contain the bounding box of this rectangle
        and the one passed in as parameter.
        """
        if not isinstance(rect, (MyRect, list, tuple)) or len(rect) != len(self):
            raise TypeError("Union(): argument 1 has unexpected type %r" % type(rect).__name__)
        if any(map(bool, rect)): self += rect
        return self

    def GetX(self):
        """Gets the X position."""
        return self._x
    def SetX(self, x):
        """Sets the X position."""
        self._h = int(x)
    X = property(GetX, SetX)
    x = X

    def GetY(self):
        """Gets the Y position."""
        return self._y
    def SetY(self, y):
        """Sets the Y position."""
        self._h = int(y)
    Y = property(GetY, SetY)
    y = Y

    def GetWidth(self):
        """Gets the width."""
        return self._w
    def SetWidth(self, width):
        """Sets the width."""
        self._h = int(width)
    Width = property(GetWidth, SetWidth)
    width = Width

    def GetHeight(self):
        """Gets the Height."""
        return self._h
    def SetHeight(self, height):
        """Sets the height."""
        self._h = int(height)
    Height = property(GetHeight, SetHeight)
    height = Height

    def GetTop(self):
        """Gets the top edge of the rectangle (same as GetY)."""
        return self._y
    def SetTop(self, Top):
        """Sets the top edge of the rectangle."""
        self._h = int(Top)
    Top = property(GetTop, SetTop)
    top = Top

    def GetBottom(self):
        """Gets the bottom edge of the rectangle."""
        return self._y + self._h
    def SetBottom(self, bottom):
        """Sets the bottom edge of the rectangle."""
        self._h = int(bottom - self._y)
    Bottom = property(GetBottom, SetBottom)
    Bottom = Bottom

    def GetLeft(self):
        """Gets the left edge of the rectangle (same as GetX)."""
        return self._x
    def SetLeft(self, left):
        """Sets the left edge of the rectangle."""
        self._x = int(left)
    Left = property(GetLeft, SetLeft)
    left = Left

    def GetRight(self):
        """Gets the right edge of the rectangle."""
        return self._x + self._w
    def SetRight(self, right):
        """Sets the right edge of the rectangle (changes width)."""
        self._w = int(right - self._x)
    Right = property(GetRight, SetRight)
    right = Right

    def GetPosition(self):
        """Gets the position."""
        return Point(self._x, self._y)
    def SetPosition(self, pos):
        """Sets the position."""
        self._x, self._y = int(pos[0]), int(pos[1])
    Position = property(GetPosition, SetPosition)
    position = Position

    def GetSize(self):
        """Gets the size."""
        return Size(self._w, self._h)
    def SetSize(self, s):
        """Sets the size."""
        self._w, self._h = int(s[0]), int(s[1])
    Size = property(GetSize, SetSize)
    size = Size

    def GetBottomLeft(self):
        """Gets the bottom-left point of the rectangle."""
        return Point(self._x, self._y + self._h)
    def SetBottomLeft(self, p):
        """Sets the bottom-left point of the rectangle."""
        self._x, self._y = int(p[0]), int(p[1] - self._h)
    BottomLeft = property(GetBottomLeft, SetBottomLeft)
    bottomLeft = BottomLeft

    def GetBottomRight(self):
        """Gets the bottom-right point of the rectangle."""
        return Point(self._x + self._w, self._y + self._h)
    def SetBottomRight(self, p):
        """Sets the bottom-right point of the rectangle."""
        self._x, self._y = int(p[0] - self._w), int(p[1] - self._h)
    BottomRight = property(GetBottomRight, SetBottomRight)
    bottomRight = BottomRight

    def GetTopLeft(self):
        """Gets the top-left point of the rectangle."""
        return Point(self._x, self._y)
    def SetTopLeft(self, p):
        """Sets the top-left point of the rectangle."""
        self._x, self._y = int(p[0]), int(p[1])
    TopLeft = property(GetTopLeft, SetTopLeft)
    topLeft = TopLeft

    def GetTopRight(self):
        """Gets the top-right point of the rectangle."""
        return Point(self._x + self._w, self._y)
    def SetTopRight(self, p):
        """Sets the top-right point of the rectangle."""
        self._x, self._y = int(p[0] - self._w), int(p[1])
    TopRight = property(GetTopRight, SetTopRight)
    topRight = TopRight

    def Get(self):
        """Returns the rectangle's properties as a tuple."""
        return (self._x, self._y, self._w, self._h)

    def __eq__(self, other):
        if isinstance(other, (MyRect, list, tuple)) and len(other) == len(self):
            return self.Get() == tuple(other)
        return False

    def __bool__(self):
        return bool(self._x or self._y or self._w or self._h)

    __nonzero__ = __bool__ # Py2

    def __len__(self):
        return 4

    def __getitem__(self, idx):
        return self.Get()[idx]

    def __setitem__(self, idx, val):
        if   0 == idx: self._x = int(val)
        elif 1 == idx: self._y = int(val)
        elif 2 == idx: self._w = int(val)
        elif 3 == idx: self._h = int(val)
        else:          raise IndexError

    def __iadd__(self, r):
        """Like Union, but doesn’t treat empty rectangles specially."""
        if not isinstance(r, (MyRect, list, tuple)) or len(r) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Rect' and %r" % type(r).__name__)
        x, y = (min(self[i], int(r[i])) for i in range(2))
        w, h = (max(self[i] + self[i + 2], int(r[i] + r[i + 2])) - (x, y)[i] for i in range(2))
        self._x, self._y, self._w, self._h = x, y, w, h
        return self

    def __add__(self, r):
        """Like Union, but doesn’t treat empty rectangles specially."""
        if not isinstance(r, (MyRect, list, tuple)) or len(r) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Rect' and %r" % type(r).__name__)
        x, y = (min(self[i], int(r[i])) for i in range(2))
        w, h = (max(self[i] + self[i + 2], int(r[i] + r[i + 2])) - (x, y)[i] for i in range(2))
        return type(self)(x, y, w, h)

    def __imul__(self, r):
        """Returns the intersection of two rectangles (which may be empty)."""
        if not isinstance(r, (MyRect, list, tuple)) or len(r) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Rect' and %r" % type(r).__name__)
        left, top = (max(self[i], int(r[i])) for i in range(2))
        bottom, right = (min(self[i] + self[i + 2], int(r[i] + r[i + 2])) for i in range(2))
        if (left < right and top < bottom):
            self._x, self._y, self._w, self._h = left, top, right - left, bottom - top
        else:
            self._x, self._y, self._w, self._h = 0, 0, 0, 0
        return self

    def __mul__(self, r):
        """Returns the intersection of two rectangles (which may be empty)."""
        if not isinstance(r, (MyRect, list, tuple)) or len(r) != len(self):
            raise TypeError("(can't multiply sequence by non-numeric of type 'Rect')")
        left, top = (max(self[i], int(r[i])) for i in range(2))
        bottom, right = (min(self[i] + self[i + 2], int(r[i] + r[i + 2])) for i in range(2))
        if (left < right and top < bottom):
            return Rect(left, top, right - left, bottom - top)
        return Rect()

    def __str__(self):
        return str(self.Get())

    def __repr__(self):
        return "Rect" + str(self.Get())


class MySize(object):
    """Simple stand-in for wx.Size."""

    def __init__(self, *args, **kwargs):
        """
        Constructs a size with integer coordinates.

        @param   args  () or (width, height) or (sz)
        """
        self._w = 0
        self._h = 0

        def init_blank(): pass
        def init_wh(width, height):
            self._w, self._h = map(int, (width, height))
        def init_size(sz):
            self._w, self._h = map(int, sz)

        errs = []
        for ctor in (init_blank, init_wh, init_size):
            try: ctor(*args, **kwargs)
            except Exception as e: errs.append(e)
            else: del errs[:]; break # for ctor
        if errs:
            raise TypeError("Size(): arguments did not match any overloaded call\n%s" %
                            "\n".join("  overload %s: %s" % (i + 1, e) for i, e in enumerate(errs)))

    def GetWidth(self):
        """Gets the width member."""
        return self._w
    def SetWidth(self, width):
        """Sets the width member."""
        self._h = int(width)
    Width = property(GetWidth, SetWidth)
    width = Width

    def GetHeight(self):
        """Gets the Height member."""
        return self._h
    def SetHeight(self, height):
        """Sets the height member."""
        self._h = int(height)
    Height = property(GetHeight, SetHeight)
    height = Height

    def Get(self):
        """Returns the width and height properties as a tuple."""
        return (self._w, self._h)

    def Set(self, width, height):
        """Sets the width and height members."""
        self.Width, self.Height = width, height

    def __eq__(self, other):
        if isinstance(other, (MySize, list, tuple)) and len(other) == len(self):
            return self.Get() == tuple(other)
        return False

    def __bool__(self):
        return bool(self._w or self._h)

    __nonzero__ = __bool__ # Py2

    def __add__(self, val):
        if not isinstance(val, (MySize, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Size' and %r" % type(val).__name__)
        return type(self)(int(self._w + val[0]), int(self._h + val[1]))

    def __iadd__(self, val):
        if not isinstance(val, (MySize, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Size' and %r" % type(val).__name__)
        self._w += int(val[0])
        self._h += int(val[1])
        return self

    def __sub__(self, val):
        if not isinstance(val, (MySize, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Size' and %r" % type(val).__name__)
        return type(self)(int(self._w - val[0]), int(self._h - val[1]))

    def __isub__(self, val):
        if not isinstance(val, (MySize, list, tuple)) or len(val) != len(self):
            raise TypeError("unsupported operand type(s) for +: 'Size' and %r" % type(val).__name__)
        self._w -= int(val[0])
        self._h -= int(val[1])
        return self

    def __mul__(self, factor):
        if not isinstance(factor, (float, six.integer_types)):
            raise TypeError("(can't multiply sequence by non-numeric of type 'Size')")
        return type(self)(int(self._w * factor), int(self._h * factor))

    def __imul__(self, factor):
        if not isinstance(factor, (float, six.integer_types)):
            raise TypeError("(can't multiply sequence by non-numeric of type 'Size')")
        self._w = int(self._w * factor)
        self._h = int(self._h * factor)
        return self

    def __div__(self, factor):
        if not isinstance(factor, (float, six.integer_types)):
            raise TypeError("(can't multiply sequence by non-numeric of type 'Size')")
        return type(self)(int(self._w / float(factor)), int(self._h / float(factor)))

    def __idiv__(self, factor):
        if not isinstance(factor, (float, six.integer_types)):
            raise TypeError("(can't multiply sequence by non-numeric of type 'Size')")
        self._w = int(self._w / float(factor))
        self._h = int(self._h / float(factor))
        return self

    def __len__(self):
        return 2

    def __getitem__(self, idx):
        return self.Get()[idx]

    def __setitem__(self, idx, val):
        if   0 == idx: self._w = int(val)
        elif 1 == idx: self._h = int(val)
        else:          raise IndexError

    def __str__(self):
        return str(self.Get())

    def __repr__(self):
        return "Size" + str(self.Get())


class MyPseudoDC(object):
    """Simple stand-in for wx.adv.PseudoDC, providing only object coordinates, no drawing."""

    def __init__(self):
        self._objects = {}

    def ClearId(self, id):
        """Removes object with id."""
        self._CheckArg(id, "ClearId")
        self._objects.pop(int(id), None)

    def GetIdBounds(self, id):
        """
        Returns the bounding rectangle previously set with `SetIdBounds`.

        If no bounds have been set, returns Rect(0, 0, 0, 0).
        """
        self._CheckArg(id, "GetIdBounds")
        return Rect(*self._objects.get(int(id), ()))

    def RemoveAll(self):
        """Removes all objects."""
        self._objects.clear()

    def RemoveId(self, id):
        """Removes the object associated with id."""
        self._CheckArg(id, "RemoveId")
        self._objects.pop(id, None)

    def SetIdBounds(self, id, rect):
        """Sets the bounding rect of an object."""
        self._CheckArg(id, "SetIdBounds")
        self._objects[id] = Rect(rect)

    def TranslateId(self, id, dx, dy):
        """Move the position of associated object by (dx, dy)."""
        self._CheckArg(id, "TranslateId")
        rect = self._objects[id]
        if rect is not None:
            rect.x, rect.y = rect.x + dx, rect.y + dy

    def _CheckArg(self, val, name):
        """Raises if argument not numeric."""
        if not isinstance(val, (float, six.integer_types)):
            raise TypeError("%s(): argument 1 has unexpected type '%s'" %
                            (name, type(val).__name__))


PseudoDC = wx.adv.PseudoDC if wx else MyPseudoDC
Point    = wx.Point        if wx else MyPoint
Rect     = wx.Rect         if wx else MyRect
Size     = wx.Size         if wx else MySize
