# -*- coding: utf-8 -*-
"""
Miscellaneous utility functions.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    20.12.2020
------------------------------------------------------------------------------
"""
import __builtin__
import collections
import contextlib
import copy
import ctypes
import datetime
import htmlentitydefs
import io
import locale
import math
import os
import platform
import re
import string
import struct
import subprocess
import sys
import threading
import time
import urllib
import warnings

from PIL import Image
import pytz
import wx


class CaselessDict(dict):
    """
    A case-insensitive dict for string keys, keys are returned in original case
    in case-insensitive order, unless insertorder given in constructor.
    Keys can be strings, or tuples of strings, or None.
    """

    def __init__(self, iterable=None, insertorder=False, **kwargs):
        self._data  = {} # {lowercase key: value}
        self._keys  = {} # {lowercase key: original key}
        self._order = [] if insertorder else None # [lowercase key]
        self.update(iterable, **kwargs)

    def clear(self):
        self._data.clear(), self._keys.clear()
        if self._order: del self._order[:]

    def copy(self):
        return type(self)(((k, self[k]) for k in self), self._order is not None)

    @staticmethod
    def fromkeys(S, v=None): return CaselessDict((k, v) for k in S)

    def get(self, key, value=None): return self[key] if key in self else value

    def has_key(self, key): return key in self

    def items(self): return [(k, self[k]) for k in self]

    def iteritems(self): return ((k, self[k]) for k in self)

    def iterkeys(self): return (k for k in self)

    def itervalues(self): return (self[k] for k in self)

    def keys(self): return list(self.__iter__())

    def pop(self, key, *args):
        if len(args) > 1:
            raise TypeError("pop expected at most 2 arguments, got %s" %
                            (len(args) + 1))
        if key in self:
            v, lc = self[key], self._(key)
            del self[key]
            if self._order and lc in self._order: self._order.remove(lc)
            return v
        elif args: return args[0]
        else: raise KeyError(key)

    def popitem(self):
        if not self: raise KeyError("popitem(): dictionary is empty")
        k = next(iter(self))
        v, lc = self[k], self._(k)
        del self[k]
        if self._order and lc in self._order: self._order.remove(lc)
        return k, v

    def setdefault(self, key, value=None):
        if key not in self: self[key] = value
        return self[key]

    def update(self, iterable=None, **kwargs):
        if callable(getattr(iterable, "keys", None)):
            iterable = [(k, iterable[k]) for k in iterable.keys()]
        for k, v in iterable or (): self[k] = v
        for k, v in kwargs.items(): self[k] = v

    def values(self): return [self[k] for k in self]

    def __bool__(self): return bool(self._data)

    def __contains__(self, key): return self._(key) in self._data

    def __eq__(self, other):
        return isinstance(other, type(self)) and \
               self._data == other._data and self._order == other._order

    def __ne__(self, other):
        return not (self == other)

    def __delitem__(self, key):
        lc = self._(key)
        del self._data[lc]
        del self._keys[lc]
        if self._order and lc in self._order: self._order.remove(lc)

    def __getitem__(self, key): return self._data[self._(key)]

    def __len__(self): return len(self._data)

    def __iter__(self):
        if self._order is not None:
            return iter(self._keys[k] for k in self._order)
        sortkey = lambda (a, b): a if isinstance(a, tuple) else (a, )
        return iter(x for _, x in sorted(self._keys.items(), key=sortkey))

    def __setitem__(self, key, value):
        lc, self._keys[lc], self._data[lc] = self._(key), key, value
        if self._order is not None and lc not in self._order:
            self._order.append(lc)

    def _(self, key):
        """Returns lowercased key value."""
        if key is None: return key
        if isinstance(key, basestring): return key.lower()
        return tuple(x.lower() if isinstance(x, basestring) else x for x in key)

    def __str__(self): return repr(self)

    def __repr__(self): return "%s(%s)" % (type(self).__name__, self.items())



class tzinfo_utc(datetime.tzinfo):
    """datetime.tzinfo class representing UTC timezone."""
    ZERO = datetime.timedelta(0)
    __reduce__ = object.__reduce__

    def utcoffset(self, dt): return self.ZERO
    def dst(self, dt):       return self.ZERO
    def tzname(self, dt):    return "UTC"
    def __ne__(self, other): return not self.__eq__(other)
    def __repr__(self):      return "%s()" % self.__class__.__name__
    def __eq__(self, other): return isinstance(other, self.__class__)
UTC = tzinfo_utc() # UTC timezone singleton



def hashable(x):
    """Returns whether object is hashable."""
    KNOWN = str, unicode, int, long, float, bool, type(None), \
            datetime.date, datetime.datetime, datetime.time
    if type(x) in KNOWN: return True
    if type(x) is tuple: return all(hashable(y) for y in x)
    if isinstance(x, (dict, list, set)): return False
    try: hash(x)
    except TypeError: return False
    return True


def memoize(*args, **kwargs):
    """
    Returns function result, cached if available, caches result otherwise.
    Returns deep copies if result is dict, list, set, or tuple.

    Acts as decorator if invoked with a single function argument or with 
    recognized keyword arguments; returning an outer decorator for the latter:

    @memoize
    def somefunction(a, b): ..

    @memoize(__nohash__=True)
    def otherfunction(a, b, unhashable): ..

    @param   args        (function, ?arg1, ..) or () if argumented decorator
    @param   __key__     cache root key to use if not function, must be hashable
    @param   __nohash__  whether arguments can be unhashable,
                         checks unhashable arguments by equality instead
    """
    func, root, nohash, ns = None, None, False, {}
    cache = getattr(memoize, "cache", None)
    nohashcache = getattr(memoize, "nohashcache", None)
    if cache is None:       # {root: {(args): value}}
        cache = collections.defaultdict(dict)
        setattr(memoize, "cache", cache)
    if nohashcache is None: # {root: {(args): [((unhashable args), value)]}}
        nohashcache = collections.defaultdict(lambda: collections.defaultdict(list))
        setattr(memoize, "nohashcache", nohashcache)


    NOCOPY = str, unicode, int, long, float, bool, type(None), \
             datetime.date, datetime.datetime, datetime.time
    def returner(v):
        if type(v) is tuple and all(type(x) in NOCOPY for x in v): return v
        return copy.deepcopy(v) if isinstance(v, (dict, list, set, tuple)) else v

    def decorate(func):
        ns["func"] = func
        if ns.get("root") is None: ns["root"] = func
        result = nohashget if nohash else hashget
        result.__module__ = func.__module__
        result.__name__ = func.__name__
        result.__doc__  = func.__doc__ or ""
        result.__doc__  += "\n\nDecorated with %s.memoize()." % __name__
        return result

    def outer(func): return decorate(func)

    def nohashget(*args, **kwargs):
        """
        Looks up by hashable args as far as possible,
        finishes with checking unhashables by equality.
        """
        key1, key2 = [], []
        for arg in args + sum(kwargs.items(), ()):
            (key1 if hashable(arg) else key2).append(arg)
        if not key2: return hashget(*args, **kwargs)

        tuples = nohashcache[ns["root"]][tuple(key1)]
        for mykey, value in tuples:
            for k1, k2 in zip(key2, mykey) if len(key2) == len(mykey) else ():
                if type(k1) is type(k2) and k1 == k2:
                    return returner(value)
        value = ns["func"](*args, **kwargs)
        tuples.append((key2, value))
        return returner(value)

    def hashget(*args, **kwargs):
        key = args + sum(kwargs.items(), ())
        mycache = cache[ns["root"]]
        if key not in mycache:
            mycache[key] = ns["func"](*args, **kwargs)
        return returner(mycache[key])


    as_outer = not args and ("__nohash__" in kwargs or "__key__" in kwargs)
    if "__nohash__" in kwargs: nohash = kwargs.pop("__nohash__")
    if "__key__"    in kwargs: root   = kwargs.pop("__key__")
    if as_outer and kwargs:
        raise TypeError("memoize() got an unexpected keyword argument '%s'" % 
                        next(iter(kwargs)))

    if not as_outer:
        func, args = args[0], args[1:]
        if root is None: root = func
    if func is not None: ns["func"] = func
    if root is not None: ns["root"] = root

    if as_outer: return outer # Argumented decorator
    elif not args and not kwargs: return decorate(func) # Plain decorator
    else: # Straight invocation
        if nohash: return nohashget(*args, **kwargs)
        else:
            key = args + sum(kwargs.items(), ())
            mycache = cache[root]
            if key not in mycache:
                mycache[key] = func(*args, **kwargs)
            return returner(mycache[key])


@memoize
def parse_datetime(s):
    """
    Tries to parse string as ISO8601 datetime, returns input on error.
    Supports "YYYY-MM-DD[ T]HH:MM(:SS)(.micros)?(Z|[+-]HH(:MM)?)?".
    """
    if not isinstance(s, basestring) or len(s) < 18: return s
    rgx = r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})(\.\d+)?(([+-]\d{2}(:?\d{2})?)|Z)?$"
    result, match = s, re.match(rgx, s)
    if match:
        _, micros, _, offset, _ = match.groups()
        minimal = re.sub(r"\D", "", s[:match.span(3)[0]] if offset else s)
        fmt = "%Y%m%d%H%M%S" + ("%f" if micros else "")
        try:
            result = datetime.datetime.strptime(minimal, fmt)
            if offset: # Support timezones like 'Z' or '+03:00'
                hh, mm = map(int, [offset[1:3], offset[4:]])
                delta = datetime.timedelta(hours=hh, minutes=mm)
                if offset.startswith("-"): delta = -delta
                z = pytz.tzinfo.StaticTzInfo()
                z._utcoffset, z._tzname, z.zone = delta, offset, offset
                result = z.localize(result)
        except ValueError: pass
    return result


@memoize
def parse_date(s):
    """
    Tries to parse string as date, returns input on error.
    Supports "YYYY-MM-DD", "YYYY.MM.DD", "YYYY/MM/DD", "YYYYMMDD",
    "DD.MM.YYYY", "DD/MM/YYYY", and "DD-MM-YYYY".
    """
    if not isinstance(s, basestring) or len(s) < 8: return s
    rgxs = [r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$",
            r"^(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})$",
            r"^(?P<year>\d{4})\/(?P<month>\d{2})\/(?P<day>\d{2})$",
            r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})$",
            r"^(?P<day>\d{2})\/(?P<month>\d{2})\/(?P<year>\d{4})$",
            r"^(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})$"]
    for r in rgxs:
        m = re.match(r, s)
        if not m: continue # for r
        year, month, day = (m.group(x) for x in ("year", "month", "day"))
        try: s = datetime.date(*map(int, (year, month, day)))
        except Exception: pass
        break # for r
    return s


@memoize
def parse_time(s):
    """
    Tries to parse string as time, returns input on error.
    Supports "HH:MM(:SS)?(.micros)?(Z|[+-]HH(:MM)?)?".
    """
    if not isinstance(s, basestring) or len(s) < 18: return s
    rgx = r"^\d{2}:\d{2}(:\d{2})?(\.\d+)?(([+-]\d{2}(:?\d{2})?)|Z)?$"
    result, match = s, re.match(rgx, s)
    if match:
        seconds, micros, _, offset, _ = match.groups()
        minimal = re.sub(r"\D", "", s[:match.span(3)[0]] if offset else s)
        fmt = "%H%M" + ("%S" if seconds else "") + ("%f" if micros else "")
        try:
            result = datetime.datetime.strptime(minimal, fmt).time()
            if offset: # Support timezones like 'Z' or '+03:00'
                hh, mm = map(int, [offset[1:3], offset[4:]])
                delta = datetime.timedelta(hours=hh, minutes=mm)
                if offset.startswith("-"): delta = -delta
                z = pytz.tzinfo.StaticTzInfo()
                z._utcoffset, z._tzname, z.zone = delta, offset, offset
                result = z.localize(result)
        except ValueError: pass
    return result


def wx_image_to_pil(image):
    """Returns PIL.Image for wx.Image."""
    (w, h), data = image.GetSize(), image.GetData()

    chans = [Image.new("L", (w, h)) for i in range(3)]
    for i in range(3): chans[i].frombytes(str(data[i::3]))
    if image.HasAlpha():
        chans += [Image.new("L", (w, h))]
        chans[-1].frombytes(str(image.GetAlpha()))

    return Image.merge("RGBA"[:len(chans)], chans)


def img_wx_to_raw(img, format="PNG"):
    """Returns the wx.Image or wx.Bitmap as raw data of specified type."""
    stream = io.BytesIO()
    img = img if isinstance(img, wx.Image) else img.ConvertToImage()
    fmttype = getattr(wx, "BITMAP_TYPE_" + format.upper(), wx.BITMAP_TYPE_PNG)
    img.SaveFile(stream, fmttype)
    result = stream.getvalue()
    return result


def ctx(enter, exit, *a, **kw):
    """
    Creates a context manager for callable result. Example usage:

        with ctx(wx.TextCtrl, wx.TextCtrl.Destroy, parent=self) as x:
            defaultfont = x.Font.FaceName

    @param   enter  function returning the value,
                    invoked with positional and keyword arguments
    @param   exit   cleanup function, invoked with result of enter()
    @return         context-managed result of enter(*a, **kw)
    """
    def yielder():
        result = enter(*a, **kw)
        yield result
        exit(result)
    return contextlib.GeneratorContextManager(yielder())


def m(o, name, case_insensitive=True):
    """Returns the members of the object or dict, filtered by name."""
    members = o.keys() if isinstance(o, dict) else dir(o)
    if case_insensitive:
        return [i for i in members if name.lower() in i.lower()]
    else:
        return [i for i in members if name in i]


def safedivf(a, b):
    """A zero-safe division, returns 0.0 if b is 0, a / float(b) otherwise."""
    return a / float(b) if b else 0.0


def safe_filename(filename):
    """Returns the filename with characters like \:*?"<>| removed."""
    return re.sub(r"[\/\\\:\*\?\"\<\>\|\x00-\x1f]", "", filename)


@memoize
def unprint(s, escape=True):
    """Returns string with unprintable characters escaped or stripped."""
    enc = "unicode_escape" if isinstance(s, unicode) else "string_escape"
    repl = (lambda m: m.group(0).encode(enc)) if escape else ""
    return re.sub(r"[\x00-\x1f]", repl, s)


def html_escape(v):
    """Converts characters like "ä" in string to HTML entities like "&auml;"."""
    lookup, patterns = {}, []
    for cp, n in htmlentitydefs.codepoint2name.items():
        c = unichr(cp)
        if "'" != c: patterns.append(c); lookup[c] = n
    subst = lambda m: "&%s;" % lookup[m.group(0)]
    return re.sub("[%s]" % "".join(patterns), subst, v)


@memoize
def format_bytes(size, precision=2, max_units=True, with_units=True):
    """
    Returns a formatted byte size (e.g. "421.45 MB" or "421,451,273 bytes").

    @param   precision   number of decimals to leave after converting to
                         maximum units
    @param   max_units   whether to convert value to corresponding maximum
                         unit, or leave as bytes and add thousand separators
    @param   with_units  whether to include units in result
    """
    size, formatted, unit = int(size), "0", "bytes"
    if size:
        byteunit = "byte" if 1 == size else "bytes"
        if max_units:
            UNITS = [byteunit, "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
            log = min(len(UNITS) - 1, math.floor(math.log(size, 1024)))
            formatted = "%.*f" % (precision, size / math.pow(1024, log))
            formatted = formatted.rstrip("0").rstrip(".")
            unit = UNITS[int(log)]
        else:
            formatted = "".join([x + ("," if i and not i % 3 else "")
                                 for i, x in enumerate(str(size)[::-1])][::-1])
            unit = byteunit
    return formatted + ((" " + unit) if with_units else "")


def format_exc(e):
    """Formats an exception as Class: message, or Class: (arg1, arg2, ..)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore") # DeprecationWarning on e.message
        msg = to_unicode(e.message) if getattr(e, "message", None) \
              else "(%s)" % ", ".join(map(to_unicode, e.args)) if e.args else ""
    result = u"%s%s" % (type(e).__name__, ": " + msg if msg else "")
    return result


def plural(word, items=None, numbers=True, single="1", sep="", pref="", suf="", max_units=False):
    """
    Returns the word as 'count words', or '1 word' if count is 1,
    or 'words' if count omitted.

    @param   items      item collection or count,
                        or None to get just the plural of the word
    @param   numbers    if False, count is omitted from final result
    @param   single     prefix to use for word if count is 1, e.g. "a"
    @param   sep        thousand-separator to use for count
    @param   pref       prefix to prepend to count, e.g. "~150"
    @param   suf        suffix to append to count, e.g. "150+"
    @param   max_units  whether to convert count to corresponding maximum
                        unit (K, M, G..), or leave as is and add thousand separators
    """
    count   = len(items) if hasattr(items, "__len__") else items or 0
    isupper = word[-1:].isupper()
    suffix = "es" if word and word[-1:].lower() in "xyz" \
             and not word[-2:].lower().endswith("ay") \
             else "s" if word else ""
    if isupper: suffix = suffix.upper()
    if count != 1 and "es" == suffix and "y" == word[-1:].lower():
        word = word[:-1] + ("I" if isupper else "i")
    result = word + ("" if 1 == count else suffix)
    if numbers and items is not None:
        if 1 == count: fmtcount = single
        elif max_units:
            UNITS = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]
            log = min(len(UNITS) - 1, math.floor(math.log(count, 1000)))
            formatted = "%.*f" % (2, count / math.pow(1000, log))
            fmtcount = formatted.rstrip("0").rstrip(".") + UNITS[int(log)]
        elif sep: fmtcount = "".join([
            x + ("," if i and not i % 3 else "") for i, x in enumerate(str(count)[::-1])
        ][::-1])
        else: fmtcount = str(count)

        fmtcount = pref + fmtcount + suf
        result = "%s %s" % (single if 1 == count else fmtcount, result)
    return result.strip()


def count(items, unit=None, key="count", suf=""):
    """
    Returns formatted count string, prefixed with "~" and rounded to the lowest
    hundred if count is estimated.

    @param   items   [{count, ?is_count_estimated}] or {count, ?is_count_estimated}
                     or numeric count
    @param   unit    name to append to count, pluralized if count != 1
    @param   key     name of item key holding count (also changes key for estimate)
    @param   suf     suffix to append to count, e.g. "150+"
    """
    result = ""
    if isinstance(items, dict): items = [items]
    elif isinstance(items, (int, long, float)): items = [{key: items}]
    value = sum(x.get(key) or 0 for x in items)
    pref = "~" if any(x.get("is_%s_estimated" % key) for x in items) else ""
    if pref: value = int(math.ceil(value / 100.) * 100)
    result = plural(unit or "", value, sep=",", pref=pref, suf=suf)
    return result


def try_until(func, limit=1, sleep=0.5):
    """
    Tries to execute the specified function a number of times.

    @param    func   callable to execute
    @param    limit  number of times to try (default 1)
    @param    sleep  seconds to sleep after failed attempts, if any
                     (default 0.5)
    @return          (True, func_result) if success else (False, None)
    """
    result, func_result, tries = False, None, 0
    while tries < limit:
        tries += 1
        try: result, func_result = True, func()
        except Exception:
            time.sleep(sleep) if tries < limit and sleep else None
    return result, func_result


def to_int(value):
    """Returns the value as integer, or None if not integer."""
    try: return int(value)
    except ValueError: return None


def unique_path(pathname):
    """
    Returns a unique version of the path. If a file or directory with the
    same name already exists, returns a unique version
    (e.g. "C:\config (2).sys" if ""C:\config.sys" already exists).
    """
    result = pathname
    if "linux2" == sys.platform and isinstance(result, unicode) \
    and "utf-8" != sys.getfilesystemencoding():
        result = result.encode("utf-8") # Linux has trouble if locale not UTF-8
    path, name = os.path.split(result)
    base, ext = os.path.splitext(name)
    if len(name) > 255: # Filesystem limitation
        name = base[:255 - len(ext) - 2] + ".." + ext
        result = os.path.join(path, name)
    counter = 2
    while os.path.exists(result):
        suffix = " (%s)%s" % (counter, ext)
        name = base + suffix
        if len(name) > 255:
            name = base[:255 - len(suffix) - 2] + ".." + suffix
        result = os.path.join(path, name)
        counter += 1
    return result


def start_file(filepath):
    """
    Tries to open the specified file or directory in the operating system.

    @return  (success, error message)
    """
    success, error = True, ""
    try:
        if "nt" == os.name:
            try: os.startfile(filepath)
            except WindowsError as e:
                if 1155 == e.winerror: # ERROR_NO_ASSOCIATION
                    cmd = "Rundll32.exe SHELL32.dll, OpenAs_RunDLL %s"
                    os.popen(cmd % filepath)
                else: raise
        elif "mac" == os.name:
            subprocess.call(("open", filepath))
        elif "posix" == os.name:
            subprocess.call(("xdg-open", filepath))
    except Exception as e:
        success, error = False, format_exc(e)
    return success, error


def select_file(filepath):
    """
    Tries to open the file directory and select file.
    Falls back to opening directory only (select is Windows-only).
    """
    if not os.path.exists(filepath):
        return start_file(os.path.split(filepath)[0])
    try: subprocess.Popen('explorer /select, "%s"' % shortpath(filepath))
    except Exception: start_file(os.path.split(filepath)[0])


def is_os_64bit():
    """Returns whether the operating system is 64-bit."""
    return "64" in platform.architecture()[0]


def is_python_64bit():
    """Returns whether Python is 64-bit."""
    return (struct.calcsize("P") * 8) == 64


def run_once(function):
    """Runs the function in a later thread at most once."""
    myqueue = getattr(run_once, "queue", __builtin__.set())
    setattr(run_once, "queue", myqueue)

    def later():
        functions = list(myqueue)
        myqueue.clear()
        for f in functions: f()

    if function not in myqueue:
        myqueue.add(function)
        if wx: wx.CallLater(100, later)
        else: threading.Thread(target=later).start()


def round_float(value, precision=1):
    """
    Returns the float as a string, rounded to the specified precision and
    with trailing zeroes (and . if no decimals) removed.
    """
    return str(round(value, precision)).rstrip("0").rstrip(".")


def divide_delta(td1, td2):
    """Divides two timedeltas and returns the integer result."""
    us1 = td1.microseconds + 1000000 * (td1.seconds + 86400 * td1.days)
    us2 = td2.microseconds + 1000000 * (td2.seconds + 86400 * td2.days)
    # Integer division, fractional division would be float(us1) / us2
    return us1 / us2


def timedelta_seconds(timedelta):
    """Returns the total timedelta duration in seconds."""
    if hasattr(timedelta, "total_seconds"):
        result = timedelta.total_seconds()
    else: # Python 2.6 compatibility
        result = timedelta.days * 24 * 3600 + timedelta.seconds + \
                 timedelta.microseconds / 1000000.
    return result


def add_unique(lst, item, direction=1, maxlen=sys.maxint):
    """
    Adds the item to the list from start or end. If item is already in list,
    removes it first. If list is longer than maxlen, shortens it.

    @param   direction  side from which item is added, -1/1 for start/end
    @param   maxlen     maximum length list is allowed to grow to before
                        shortened from the other direction
    """
    if item in lst:
        lst.remove(item)
    lst.insert(0, item) if direction < 0 else lst.append(item)
    if len(lst) > maxlen:
        lst[:] = lst[:maxlen] if direction < 0 else lst[-maxlen:]
    return lst


def make_unique(value, existing, suffix="_%s", counter=2, case=False):
    """
    Returns a unique string, appending suffix % counter as necessary.

    @param   existing  collection of existing strings to check
    @oaram   case      whether uniqueness should be case-sensitive
    """
    result, is_present = value, (lambda: result in existing)
    if not case:
        existing = [x.lower() for x in existing]
        is_present = lambda: result.lower() in existing
    while is_present(): result, counter = value + suffix % counter, counter + 1
    return result


def make_spreadsheet_column(index):
    """Returns spreadsheet-like column name for index, e.g. "AA" for 26."""
    digits, base = string.ascii_uppercase, len(string.ascii_uppercase)
    t, n = "", index + 1 # Convert to 1-based alphabetic label
    while n: t, n = digits[(n % base or base) - 1] + t, (n - 1) / base
    return t


def getval(collection, *path, **kwargs):
    """
    Returns the value at specified collection path. If path not available,
    returns the first keyword argument if any given, or None.
    Collection can be a nested structure of dicts, lists, tuples or strings,
    or objects with named attributes.
    E.g. getval({"root": {"first": [{"k": "v"}]}}, "root", "first", 0, "k").
    """
    default = (list(kwargs.values()) + [None])[0]
    result = collection if path else default
    if len(path) == 1 and isinstance(path[0], list): path = path[0]
    for p in path:
        if isinstance(result, collections.Sequence):  # Iterable with index
            if isinstance(p, (int, long)) and p < len(result):
                result = result[p]
            else:
                result = default
        elif isinstance(result, collections.Mapping): # Container with lookup
            result = result.get(p, default)
        elif isinstance(p, basestring) and hasattr(result, p): # Object attribute
            result = getattr(result, p)
        else:
            result = default
        if result == default: break  # for p
    return result


def setval(collection, value, *path):
    """
    Sets the value at specified collection path. If a path step does not exist,
    it is created as dict. Collection can be a nested structure of dicts and lists.
    Returns value.
    """
    if len(path) == 1 and isinstance(path[0], list): path = path[0]
    ptr = collection
    for p in path[:-1]:
        if isinstance(ptr, collections.Sequence):  # Iterable with index
            if isinstance(p, (int, long)) and p < len(ptr):
                ptr = ptr[p]
            else:
                ptr.append({})
                ptr = ptr[-1]
        elif isinstance(ptr, collections.Mapping): # Container with lookup
            if p not in ptr: ptr[p] = {}
            ptr = ptr[p]
    ptr[path[-1]] = value
    return value


def walk(data, callback):
    """
    Walks through the collection of nested dicts or lists or tuples, invoking
    callback(child, key, parent) for each element, recursively.
    """
    if isinstance(data, collections.Iterable) and not isinstance(data, basestring):
        for k, v in enumerate(data):
            if isinstance(data, collections.Mapping): k, v = v, data[v]
            callback(k, v, data)
            walk(v, callback)


def tuplefy(value):
    """Returns the value in or as a tuple if not already a tuple."""
    return value if isinstance(value, tuple) \
           else tuple(value) if isinstance(value, list) else (value, )


@memoize
def lceq(a, b):
    """Returns whether x and y are caselessly equal."""
    a, b = (x if isinstance(x, basestring) else "" if x is None else str(x)
            for x in (a, b))
    return a.lower() == b.lower()


def get_locale_day_date(dt):
    """Returns a formatted (weekday, weekdate) in current locale language."""
    weekday, weekdate = dt.strftime("%A"), dt.strftime("%d. %B %Y")
    if locale.getpreferredencoding():
        for enc in (locale.getpreferredencoding(), "latin1"):
            try:
                weekday, weekdate = (x.decode(enc) for x in [weekday, weekdate])
                break
            except Exception: pass
    weekday = weekday.capitalize()
    return weekday, weekdate


def path_to_url(path, encoding="utf-8"):
    """
    Returns the local file path as a URL, e.g. "file:///C:/path/file.ext".
    """
    path = path.encode(encoding) if isinstance(path, unicode) else path
    if ":" not in path:
        # No drive specifier, just convert slashes and quote the name
        if path[:2] == "\\\\":
            path = "\\\\" + path
        url = urllib.quote("/".join(path.split("\\")))
    else:
        url, parts = "", path.split(":")
        if len(parts[0]) == 1: # Looks like a proper drive, e.g. C:\
            url = "///" + urllib.quote(parts[0].upper()) + ":"
            parts = parts[1:]
        components = ":".join(parts).split("\\")
        for part in filter(None, components):
            url += "/" + urllib.quote(part)
    url = "file:%s%s" % ("" if url.startswith("///") else "///" , url)
    return url


def titlecase(text):
    """
    Returns a titlecased version of text, leaving URLs as is 
    and not considering apostrophe as word separator.
    """
    re_url = re.compile(r"((?:(?:(?:(?:[a-z]+)?://)|(?:www\.))" # protocol:// or www.
                         r"(?:[\w.:_\-/?#%@]+))"                # domain + path etc
                        r"|(?:[\w\-_.]+)@(?:[\w\-_.]+))", re.I) # e-mail address
    re_inter = re.compile(r'([\s!"“#%&()*+,.\/:;?@\\[\]_`{|}~])')
    done = []
    for i, part in enumerate(re_url.split(text)):
        if i % 2:
            done.append(part) # Found URL: leave as is
            continue # for i, part

        for word in re_inter.split(part):
            if i % 2: done.append(word) # Whitespace or separator: leave as is
            elif word: done.append(word[0].upper() + word[1:].lower())
    return "".join(done)


def to_str(value, encoding=None):
    """
    Returns the value as an 8-bit string. Tries encoding as UTF-8 if
    locale encoding fails.
    """
    result = value
    if isinstance(value, unicode):
        encoding = encoding or locale.getpreferredencoding()
        try: result = value.encode(encoding)
        except Exception:
            try: result = value.encode("utf-8", errors="backslashreplace")
            except Exception:
                try: result = value.encode("latin1", errors="backslashreplace")
                except Exception: result = value.encode("latin1", errors="replace")
    elif not isinstance(value, str): result = str(value)
    return result


def to_unicode(value, encoding=None):
    """
    Returns the value as a Unicode string. Tries decoding as UTF-8 if
    locale decoding fails.
    """
    result = value
    if type(value) != unicode:
        encoding = encoding or locale.getpreferredencoding()
        if not isinstance(value, str):
            try: value = str(value)
            except Exception: value = repr(value)
        try: result = unicode(value, encoding)
        except Exception:
            try: result = unicode(value, "utf-8", errors="backslashreplace")
            except Exception:
                try: result = unicode(value, "latin1", errors="backslashreplace")
                except Exception: result = unicode(value, "latin1", errors="replace")
    return result


@memoize
def ellipsize(text, limit=50, front=False, ellipsis=".."):
    """
    Returns text ellipsized if beyond limit.

    @param   text      value to ellipsize, converted to string if not string
    @param   limit     length beyond which text is truncated
    @param   front     if true, ellipsis is inserted in front
                       and text is truncated from the end
    @param   ellipsis  the ellipsis string to use
    """
    if type(text) not in (str, unicode): text = to_unicode(text)
    if len(text) <= limit: return text
    if front: return (ellipsis + text[-limit + len(ellipsis):])
    else:     return (text[:limit - len(ellipsis)] + ellipsis)


def longpath(path):
    """Returns the path in long Windows form ("Program Files" not PROGRA~1)."""
    result = path
    try:
        buf = ctypes.create_unicode_buffer(65536)
        GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
        if GetLongPathNameW(unicode(path), buf, 65536):
            result = buf.value
        else:
            head, tail = os.path.split(path)
            if GetLongPathNameW(unicode(head), buf, 65536):
                result = os.path.join(buf.value, tail)
    except Exception: pass
    return result


def shortpath(path):
    """Returns the path in short Windows form (PROGRA~1 not "Program Files")."""
    if isinstance(path, str): return path
    from ctypes import wintypes

    ctypes.windll.kernel32.GetShortPathNameW.argtypes = [
        # lpszLongPath, lpszShortPath, cchBuffer
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD 
    ]
    ctypes.windll.kernel32.GetShortPathNameW.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(4 * len(path))
    ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value


def win32_unicode_argv():
    """
    Returns Windows command-line arguments converted to Unicode.

    @from    http://stackoverflow.com/a/846931/145400
    """
    result = sys.argv[:]
    try:
        from ctypes import POINTER, byref, cdll, c_int, windll
        from ctypes.wintypes import LPCWSTR, LPWSTR
    except Exception: return result

    GetCommandLineW = cdll.kernel32.GetCommandLineW
    GetCommandLineW.argtypes = []
    GetCommandLineW.restype = LPCWSTR

    CommandLineToArgvW = windll.shell32.CommandLineToArgvW
    CommandLineToArgvW.argtypes = [LPCWSTR, POINTER(c_int)]
    CommandLineToArgvW.restype = POINTER(LPWSTR)

    argc = c_int(0)
    argv = CommandLineToArgvW(GetCommandLineW(), byref(argc))
    if argc.value:
        # Remove Python executable and commands if present
        start = argc.value - len(sys.argv)
        result = [argv[i].encode("utf-8") for i in range(start, argc.value)]
    return result
