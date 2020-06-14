# -*- coding: utf-8 -*-
"""
Miscellaneous utility functions.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    03.06.2020
------------------------------------------------------------------------------
"""
import collections
import ctypes
import datetime
import locale
import math
import os
import re
import subprocess
import sys
import time
import urllib
import warnings

from PIL import Image
import pytz
import wx


class CaselessDict(dict):
    """
    A case-insensitive dict for string keys, keys are returned in original case
    in case-insensitive order. Keys can be strings, or tuples of strings, or None.
    """

    def __init__(self, iterable=None, **kwargs):
        self._data = {} # {lowercase key: value}
        self._keys = {} # {lowercase key: original key}
        self.update(iterable, **kwargs)

    def clear(self): self._data.clear(), self._keys.clear()

    def copy(self): return type(self)((k, self[k]) for k in self)

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
            v = self[key]
            del self[key]
            return v
        elif args: return args[0]
        else: raise KeyError(key)

    def popitem(self):
        if not self: raise KeyError("popitem(): dictionary is empty")
        k = next(iter(self))
        v = self[k]
        del self[k]
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

    def __delitem__(self, key):
        lc = self._(key)
        del self._data[lc], self._keys[lc]

    def __getitem__(self, key): return self._data[self._(key)]

    def __len__(self): return len(self._data)

    def __iter__(self):
        sortkey = lambda (a, b): a if isinstance(a, tuple) else (a, )
        return iter(x for _, x in sorted(self._keys.items(), key=sortkey))

    def __setitem__(self, key, value):
        lc, self._keys[lc], self._data[lc] = self._(key), key, value

    def _(self, key):
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
    for i in range(3): chans[i].fromstring(str(data[i::3]))
    if image.HasAlpha():
        chans += [Image.new("L", (w, h))]
        chans[-1].fromstring(str(image.GetAlpha()))

    return Image.merge("RGBA"[:len(chans)], chans)


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


def unprint(s, escape=True):
    """Returns string with unprintable characters escaped or stripped."""
    enc = "unicode_escape" if isinstance(s, unicode) else "string_escape"
    repl = (lambda m: m.group(0).encode(enc)) if escape else ""
    return re.sub(r"[\x00-\x1f]", repl, s)


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


def plural(word, items=None, numbers=True, single="1", sep="", pref="", suf=""):
    """
    Returns the word as 'count words', or '1 word' if count is 1,
    or 'words' if count omitted.

    @param   items      item collection or count,
                        or None to get just the plural of the word
             numbers    if False, count is omitted from final result
             single     prefix to use for word if count is 1, e.g. "a"
             sep        thousand-separator to use for count
             pref       prefix to prepend to count, e.g. "~150"
             suf        suffix to append to count, e.g. "150+"
    """
    count   = len(items) if hasattr(items, "__len__") else items or 0
    isupper = word[-1:].isupper()
    suffix = "es" if word and word[-1:].lower() in "xyz" else "s" if word else ""
    if isupper: suffix = suffix.upper()
    if count != 1 and "y" == word[-1:].lower():
        word = word[:-1] + ("I" if isupper else "i")
    result = word + ("" if 1 == count else suffix)
    if numbers and items is not None:
        fmtcount = single if 1 == count else "".join([
            x + ("," if i and not i % 3 else "")
            for i, x in enumerate(str(count)[::-1])][::-1
        ]) if sep else str(count)
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


def try_until(func, count=1, sleep=0.5):
    """
    Tries to execute the specified function a number of times.

    @param    func   callable to execute
    @param    count  number of times to try (default 1)
    @param    sleep  seconds to sleep after failed attempts, if any
                     (default 0.5)
    @return          (True, func_result) if success else (False, None)
    """
    result, func_result, tries = False, None, 0
    while tries < count:
        tries += 1
        try: result, func_result = True, func()
        except Exception:
            time.sleep(sleep) if tries < count and sleep else None
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
    """Returns whether the operating system is 64-bit (Windows-only)."""
    return ('PROCESSOR_ARCHITEW6432' in os.environ
            or os.environ['PROCESSOR_ARCHITECTURE'].endswith('64'))


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


def get(collection, *path, **kwargs):
    """
    Returns the value at specified collection path. If path not available,
    returns the first keyword argument if any given, or None.
    Collection can be a nested structure of dicts, lists, tuples or strings.
    E.g. util.get({"root": {"first": [{"k": "v"}]}}, "root", "first", 0, "k").
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
        else:
            result = default
        if result == default: break  # for p
    return result


def set(collection, value, *path):
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


def to_unicode(value, encoding=None):
    """
    Returns the value as a Unicode string. Tries decoding as UTF-8 if
    locale encoading fails.
    """
    result = value
    if not isinstance(value, unicode):
        encoding = encoding or locale.getpreferredencoding()
        if isinstance(value, str):
            try:
                result = unicode(value, encoding)
            except Exception:
                result = unicode(value, "utf-8", errors="replace")
        else:
            result = unicode(str(value), errors="replace")
    return result


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
    buf = ctypes.create_unicode_buffer(path)
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
