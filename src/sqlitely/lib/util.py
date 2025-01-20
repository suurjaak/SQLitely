# -*- coding: utf-8 -*-
"""
Miscellaneous utility functions.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    20.01.2025
------------------------------------------------------------------------------
"""
from __future__ import print_function
try: import __builtin__ as builtins  # Py2
except ImportError: import builtins  # Py3
import collections
import copy
import ctypes
import datetime
try: import fcntl
except Exception: fcntl = None
import functools
import inspect
import io
import itertools
import locale
import math
import multiprocessing.connection
import os
import platform
import re
import stat
import string
import struct
import subprocess
import sys
import threading
import time
import warnings

from PIL import Image
import six
from six.moves import collections_abc
from six.moves import html_entities
from six.moves import urllib
import pytz
try: import wx
except ImportError: wx = None


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
        sortkey = lambda x: tuplefy(coalesce(x[0], ""))
        return iter(x for _, x in sorted(self._keys.items(), key=sortkey))

    def __setitem__(self, key, value):
        lc, self._keys[lc], self._data[lc] = self._(key), key, value
        if self._order is not None and lc not in self._order:
            self._order.append(lc)

    def _(self, key):
        """Returns lowercased key value."""
        if key is None: return key
        if isinstance(key, six.string_types): return key.lower()
        return tuple(x.lower() if isinstance(x, six.string_types) else x for x in key)

    def __str__(self): return repr(self)

    def __repr__(self): return "%s(%s)" % (type(self).__name__, list(self.items()))



class ProgressBar(threading.Thread):
    """
    A simple ASCII progress bar with a ticker thread, drawn like
    '[---------\   36%            ] Progressing text..'.
    or for pulse mode
    '[    ----                    ] Progressing text..'.
    """

    def __init__(self, max=100, value=0, min=0, width=30, forechar="-",
                 backchar=" ", foreword="", afterword="", interval=1,
                 pulse=False, static=False, echo=print):
        """
        Creates a new progress bar, without drawing it yet.

        @param   max        progress bar maximum value, 100%
        @param   value      progress bar initial value
        @param   min        progress bar minimum value, for 0%
        @param   width      progress bar width (in characters)
        @param   forechar   character used for filling the progress bar
        @param   backchar   character used for filling the background
        @param   foreword   text in front of progress bar
        @param   afterword  text after progress bar
        @param   interval   ticker thread interval, in seconds
        @param   pulse      ignore value-min-max, use constant pulse instead
        @param   static     print stripped afterword only, on explicit update()
        @param   echo       print function
        """
        threading.Thread.__init__(self)
        for k, v in locals().items(): "self" != k and setattr(self, k, v)
        self.daemon = True # Daemon threads do not keep application running
        self.percent = None        # Current progress ratio in per cent
        self.value = None          # Current progress bar value
        self.pause = False         # Whether drawing is currently paused
        self.pulse_pos = 0         # Current pulse position
        self.bar = "%s[%s%s]%s" % (foreword,
                                   " ", #backchar if pulse else forechar,
                                   backchar * (width - 2),
                                   afterword)
        self.printbar = self.bar   # Printable text, with padding to clear previous
        self.progresschar = itertools.cycle("-\\|/")
        self.is_running = False
        if static or not pulse: self.update(value, draw=static)


    def update(self, value=None, afterword=None, draw=True, **kwargs):
        """Updates the progress bar value / afterword and any other properties, and redraws."""
        if afterword is not None: self.afterword = afterword
        for k, v in kwargs.items(): hasattr(self, k) and setattr(self, k, v)
        if self.static:
            if self.afterword.strip(): self.echo(self.afterword.strip())
            return

        if value is not None: self.value = min(self.max, max(self.min, value))
        w_full = self.width - 2
        if self.pulse:
            if self.pulse_pos is None:
                bartext = "%s[%s]%s" % (self.foreword,
                                        self.forechar * (self.width - 2),
                                        self.afterword)
            else:
                dash = self.forechar * max(1, (self.width - 2) // 7)
                pos = self.pulse_pos
                if pos < len(dash):
                    dash = dash[:pos]
                elif pos >= self.width - 1:
                    dash = dash[:-(pos - self.width - 2)]

                bar = "[%s]" % (self.backchar * w_full)
                # Write pulse dash into the middle of the bar
                pos1 = min(self.width - 1, pos + 1)
                bar = bar[:pos1 - len(dash)] + dash + bar[pos1:]
                bartext = "%s%s%s" % (self.foreword, bar, self.afterword)
                self.pulse_pos = (self.pulse_pos + 1) % (self.width + 2)
        else:
            percent = int(round(100.0 * self.value / (self.max or 1)))
            percent = 99 if percent == 100 and self.value < self.max else percent
            w_done = max(1, int(round((percent / 100.0) * w_full)))
            # Build bar outline, animate by cycling last char from progress chars
            char_last = self.forechar if self.value else self.backchar
            if draw and self.value and w_done < w_full: char_last = next(self.progresschar)
            bartext = "%s[%s%s%s]%s" % (
                       self.foreword, self.forechar * (w_done - 1), char_last,
                       self.backchar * (w_full - w_done), self.afterword)
            # Write percentage into the middle of the bar
            centertxt = " %2d%% " % percent
            pos = len(self.foreword) + self.width // 2 - len(centertxt) // 2
            bartext = bartext[:pos] + centertxt + bartext[pos + len(centertxt):]
            self.percent = percent
        self.printbar = bartext + " " * max(0, len(self.bar) - len(bartext))
        self.bar, prevbar = bartext, self.bar
        if draw and prevbar != self.bar: self.draw()


    def draw(self):
        """Prints the progress bar, from the beginning of the current line."""
        if self.static: return
        self.echo("\r" + self.printbar, end=" ")
        if len(self.printbar) != len(self.bar):
            self.printbar = self.bar # Discard padding to clear previous
            self.echo("\r" + self.printbar, end=" ")


    def run(self):
        if self.static: return # No running progress
        self.is_running = True
        while self.is_running:
            if not self.pause: self.update(self.value)
            time.sleep(self.interval)


    def stop(self):
        self.is_running = False



class SingleInstanceChecker(object):
    """
    Allows checking that only a single instance of a program is running, per user login.

    Allows sending data from one instance to another, via multiprocessing.connection.

    Uses wx.SingleInstanceChecker in Windows, and a custom lockfile otherwise,
    as wx.SingleInstanceChecker in Linux can fail.
    """

    def __init__(self, name=None, path=None, appname=None):
        """
        Creates new SingleInstanceChecker, acquiring exclusive lock on name.

        @param   name     unique ID for application, by default constructed from app name + username;
                          best if contains alphanumerics and other basic printables only
        @param   path     directory of lockfile, ignored in Windows, defaults to user data folder
        @param   appname  used for lockfile subdirectory under path if present, ignored in Windows
        """
        self._name     = name.strip() if name else None
        self._lockdir  = path
        self._appname  = appname.strip() if appname else None
        self._checker  = None # wx.SingleInstanceChecker instance in Windows if wx available
        self._lockpath = None # Path for lockfile in non-Windows
        self._lockfd   = None # File descriptor for lockfile
        self._hasother = None # True: another is running, False: only this running, None: unknown
        self._otherpid = None # Process ID of the other detected instance
        self._listener = None # multiprocessing.connection.Listener for data from other instances
        if "win32" != sys.platform: self._PopulatePath(), self._Lock()
        else: self._checker = wx.SingleInstanceChecker(*[name] if name else [])


    def IsAnotherRunning(self):
        """Returns whether another copy of this program is already running, or None if unknown."""
        if self._checker is not None: return self._checker.IsAnotherRunning()
        if self._hasother: self._Lock() # Try locking again, maybe the other has exited
        else: # Check if lockfile handle is still valid
            try: deleted = not os.fstat(self._lockfd).st_nlink # Number of hard links
            except Exception: deleted = None
            if deleted:
                try: os.close(self._lockfd)
                except Exception: pass
                self._lockfd = None
                self._Lock()
        return self._hasother


    def GetOtherPid(self):
        """Returns the process ID of the other running instance, or None if unknown or Windows."""
        return self._otherpid


    def SendToOther(self, data, port, portrange=1000):
        """
        Sends data to the other program instance via multiprocessing.

        @param   data       data to send, anything that can be pickled
        @param   port       default TCP port number for communications
        @param   portrange  maximum steps to try increasing port number if connection fails
        @return             True if operation successful, False otherwise
        """
        MAX_PORT = 65535
        result = None
        authkey = self._name or "%s-%s" % (wx.GetApp().AppName, wx.GetUserId())

        def launch_client(results, port, portrange):
            client = None
            while client is None and portrange >= 0 and port <= MAX_PORT:
                kwargs = {"address": ("localhost", port), "authkey": authkey}
                try: client = multiprocessing.connection.Client(**kwargs)
                except Exception: port, portrange = port + 1, portrange - 1
            if client is not None: results.append(client)

        clients = []
        t = threading.Thread(target=launch_client, args=(clients, port, portrange))
        t.daemon = True
        t.start() # Use thread because opening connection may stall if other side stalls
        t.join(timeout=2)
        if clients:
            client = clients[0]
            try: client.send(data)
            except Exception: result = False
            else: result = True
            finally: try_ignore(client.close)
        return result or False


    def IsReceiving(self):
        """Returns whether listener is currently active."""
        return bool(self._listener)


    def StartReceive(self, callback, port, portrange=10000):
        """
        Opens listener for receiving data from other instances, and runs it in background thread.

        @param   callback   function to invoke with received data
        @param   port       default TCP port number for communications
        @param   portrange  maximum steps to try increasing port number if opening listener fails
        @return             True if opening listener succeeded, false otherwise
        """
        authkey = self._name or "%s-%s" % (wx.GetApp().AppName, wx.GetUserId())
        while not self._listener and portrange >= 0:
            kwargs = {"address": ("localhost", port), "authkey": authkey}
            try: self._listener = multiprocessing.connection.Listener(**kwargs)
            except Exception: port, portrange = port + 1, portrange - 1
        if not self._listener: return False

        def receiver(self, callback):
            while self._listener:
                try: callback(self._listener.accept().recv())
                except Exception: pass

        t = threading.Thread(target=receiver, args=(self, callback))
        t.daemon = True
        t.start()
        return True


    def StopReceive(self):
        """
        Shuts down current IPC listener being received from, if any.

        @return  True if listener was active, False otherwise
        """
        listener, self._listener = self._listener, None
        listener and try_ignore(listener.close)
        return bool(listener)


    def __del__(self):
        """Unlocks current lock, if any."""
        if self._checker is not None: del self._checker
        else: self._Unlock()
        self._checker = None


    def _PopulatePath(self):
        """Populates lockfile path, and name if not populated."""
        name = self._name
        if not name:
            name = os.getenv("USER", os.getenv("USERNAME"))
            procname = sys.executable or (sys.argv[0] if sys.argv else "")
            name = re.sub(r"\W", "__", "__".join(filter(bool, (procname, name)))) or "__"
        lockdir = self._lockdir or os.path.join(os.path.expanduser("~"), ".local", "share")
        if self._appname: lockdir = os.path.join(lockdir, self._appname.lower())
        self._lockpath, self._name = os.path.join(lockdir, "%s.lock" % name), name


    def _Lock(self):
        """Tries to create lockfile and acquire lock, sets instance status."""
        if self._lockfd or not fcntl: return

        self._hasother = self._otherpid = None
        try:
            try: os.makedirs(os.path.dirname(self._lockpath))
            except Exception: pass

            flags, mode = os.O_RDWR | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR
            umask0 = os.umask(0) # Override default umask
            try: self._lockfd = os.open(self._lockpath, flags, mode)
            finally: os.umask(umask0) # Restore default umask

            try: fcntl.lockf(self._lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB) # Exclusive non-blocking
            except (IOError, OSError):
                try: self._otherpid = int(os.read(self._lockfd, 1024))
                except Exception: pass
                try: os.close(self._lockfd)
                except Exception: pass
                self._hasother, self._lockfd = True, None
            else:
                self._hasother = False
                try: os.write(self._lockfd, b"%d" % os.getpid()), os.fsync(self._lockfd)
                except Exception: pass
        except Exception:
            try: os.close(self._lockfd)
            except Exception: pass
            self._lockfd = None


    def _Unlock(self):
        """Unlocks and closes and deletes lockfile, if any."""
        if not self._lockfd: return
        funcs  = (fcntl.lockf,                   os.close,       os.unlink)
        argses = ([self._lockfd, fcntl.LOCK_UN], [self._lockfd], [self._lockpath])
        for func, args in zip(funcs, argses):
            try: func(*args)
            except Exception: pass
        self._lockfd = None


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

    Cached values are also available via memoize.get_cache(),
    and they can be pre-set via memoize.set_cache().

    @param   args        (function, ?arg1, ..) or () if argumented decorator
    @param   __key__     cache root key to use if not function, must be hashable
    @param   __nohash__  whether arguments can be unhashable,
                         checks unhashable arguments by equality instead
    """
    func, root, nohash, ns = None, None, False, {}
    cache       = getattr(memoize, "cache",       None)
    nohashcache = getattr(memoize, "nohashcache", None)
    wrappeds    = getattr(memoize, "wrappeds",    None)

    if cache is None:       # {root: {(args): value}}
        cache = collections.defaultdict(dict)
        setattr(memoize, "cache", cache)
    if nohashcache is None: # {root: {(args): [((unhashable args), value)]}}
        nohashcache = collections.defaultdict(lambda: collections.defaultdict(list))
        setattr(memoize, "nohashcache", nohashcache)
    if wrappeds is None: # {wrapper: original function}
        wrappeds = {}
        setattr(memoize, "wrappeds", wrappeds)

    if not hasattr(memoize, "get_cache"):
        def get_cache(root):
            """Returns cache for specified function or other root key."""
            return cache[wrappeds.get(root)]
        setattr(memoize, "get_cache", get_cache)
    if not hasattr(memoize, "set_cache"):
        def set_cache(root, items):
            """Sets cached items for specified function or other root key."""
            cache[wrappeds.get(root)].update(items)
        setattr(memoize, "set_cache", set_cache)


    NOCOPY = six.string_types + six.integer_types + (float, bool, type(None),
             datetime.date, datetime.datetime, datetime.time)
    def returner(v):
        if type(v) is tuple and all(type(x) in NOCOPY for x in v): return v
        return copy.deepcopy(v) if isinstance(v, (dict, list, set, tuple)) else v

    def decorate(func):
        ns["func"] = func
        if ns.get("root") is None: ns["root"] = func
        result = nohashget if nohash else hashget
        functools.update_wrapper(result, func)
        result.__doc__ = "%s\n\nDecorated with %s.memoize()." % (result.__doc__ or "", __name__)
        result.__wrapped__ = func
        wrappeds[result] = ns["root"]
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
        key2 = [copy.deepcopy(x) if isinstance(x, (dict, list, set, tuple)) else x for x in key2]
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


def add_unique(lst, item, direction=1, maxlen=sys.maxsize):
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


def articled(word):
    """Returns the word prefixed with an indefinite article, "a " or "an "."""
    return ("an " if word[0].lower() in "aeiou" else "a ") + word


def base_to_int(value, digits=string.ascii_uppercase):
    """
    Returns integer from a string representation of custom base. Raises on error.

    @param   value   integer string in given base, like "AAA"
    @param   digits  base digits, defaults to upper-case ASCII letters A..Z
    @return          integer value, like 762 for "AAA"
    """
    result, base = 0, len(digits)
    for i, v in enumerate(value[::-1]): result += (digits.index(v) + bool(i)) * (base**i)
    return result


@memoize
def cap(val, reverse=False):
    """Returns value with the first letter capitalized (or uncapitalized if reverse)."""
    val = val if isinstance(val, (six.binary_type, six.text_type)) else str(val)
    return (val[0].lower() if reverse else val[0].upper()) + val[1:]


def coalesce(value, fallback):
    """Returns fallback if value is None else value."""
    return fallback if value is None else value


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
    elif isinstance(items, six.integer_types + (float, )): items = [{key: items}]
    value = sum(x.get(key) or 0 for x in items)
    pref = "~" if any(x.get("is_%s_estimated" % key) for x in items) else ""
    if pref: value = int(math.ceil(value / 100.) * 100)
    result = plural(unit or "", value, sep=",", pref=pref, suf=suf)
    return result


def divide_delta(td1, td2):
    """Divides two timedeltas and returns the integer result."""
    us1 = td1.microseconds + 1000000 * (td1.seconds + 86400 * td1.days)
    us2 = td2.microseconds + 1000000 * (td2.seconds + 86400 * td2.days)
    return us1 // us2


@memoize
def ellipsize(text, limit=50, front=False, ellipsis=".."):
    """
    Returns text ellipsized if beyond limit. If text is enclosed in quotes or
    brackets ('' "" [] () <> {}), it is ellipsized inside the enclosure,
    e.g. ellipsize('"0123456789"', 10) returns '"012345.."'.

    @param   text      value to ellipsize, converted to string if not string
    @param   limit     length beyond which text is truncated
    @param   front     if true, ellipsis is inserted in front
                       and text is truncated from the end
    @param   ellipsis  the ellipsis string to use
    """
    if not isinstance(text, six.string_types): text = to_unicode(text)
    if len(text) <= limit: return text

    ENCLOSURES = "''", '""', "[]", "()", "<>", "{}"
    extra = next((a if front else b for a, b in ENCLOSURES
                  if a == text[0] and b == text[-1]), "")
    if extra: limit -= 1

    if front: return (extra + ellipsis + text[-limit + len(ellipsis):])
    else:     return (text[:limit - len(ellipsis)] + ellipsis + extra)


def filters_to_regex(texts, end=False, neg="~"):
    """
    Returns one or more simple filters as a single re.Pattern.

    Simple asterisk wildcards ('*') will match anything.
    A negation character ('~') at the beginning of a word will omit matches containing the word.

    @param   texts  one or more text filters, regex matches if any text matches and no skip matches
    @param   end    whether pattern should match until end (adds '$')
    @param   neg    negation character to use for skipping
    @return         re.Pattern for input values, like re.Pattern("(?!.*(xyz))(foo.*bar)", re.I)
                    for filters_to_regex(["foo*bar", "-xyz"])
    """
    wildify = lambda t: ".*".join(map(re.escape, t.split("*")))
    suff, texts = ("$" if end else ""), tuplefy(texts)
    includes, excludes = ([t[skip:] for t in texts if skip == t.startswith(neg)] for skip in (0, 1))
    matchstr = "|".join("(%s%s)" % (wildify(t), suff) for t in includes)
    skipstr = "(?!.*(%s)%s)" % ("|".join(map(wildify, excludes)), suff) if excludes else ""
    return re.compile(skipstr + ("(%s)" if skipstr else "%s") % matchstr, re.I)


@memoize
def format_bytes(size, precision=2, max_units=True, with_units=True):
    """
    Returns a formatted byte size (e.g. "421.45 MB" or "421,451,273 bytes").

    @param   size        size in bytes
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


def get_arity(func, positional=True, keyword=False):
    """
    Returns the maximum number of arguments the function takes, -1 if variable number.

    @param   positional  count positional-only and positional/keyword arguments
    @param   keyword     count keyword-only and positional/keyword arguments
    """
    if six.PY2:
        spec = inspect.getargspec(func)
        if positional and spec.varargs or keyword and spec.keywords: return -1
        else: return len(spec.args)

    POSITIONALS = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
    KEYWORDALS  = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    result, params = 0, inspect.signature(func).parameters
    if positional and any(x.kind == inspect.Parameter.VAR_POSITIONAL for x in params.values()) \
    or keyword    and any(x.kind == inspect.Parameter.VAR_KEYWORD    for x in params.values()):
        result = -1
    elif positional and keyword:
        result += sum(x.kind in POSITIONALS + KEYWORDALS for x in params.values())
    elif positional:
        result += sum(x.kind in POSITIONALS for x in params.values())
    elif keyword:
        result += sum(x.kind in KEYWORDALS  for x in params.values())
    return result


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
        if isinstance(result, collections_abc.Sequence):  # Iterable with index
            if isinstance(p, six.integer_types) and p < len(result):
                result = result[p]
            else:
                result = default
        elif isinstance(result, collections_abc.Mapping): # Container with lookup
            result = result.get(p, default)
        elif isinstance(p, six.string_types) and hasattr(result, p): # Object attribute
            result = getattr(result, p)
        else:
            result = default
        if result == default: break  # for p
    return result


def hashable(x):
    """Returns whether object is hashable."""
    KNOWN = six.string_types + six.integer_types + (float, bool, type(None),
            datetime.date, datetime.datetime, datetime.time)
    if isinstance(x, KNOWN): return True
    if type(x) is tuple: return all(hashable(y) for y in x)
    if isinstance(x, (dict, list, set)): return False
    try: hash(x)
    except TypeError: return False
    return True


def html_escape(v):
    """Converts characters like "ä" in string to HTML entities like "&auml;"."""
    lookup, patterns = {}, []
    for cp, n in html_entities.codepoint2name.items():
        c = six.unichr(cp)
        if "'" != c: patterns.append(c); lookup[c] = n
    subst = lambda m: "&%s;" % lookup[m.group(0)]
    return re.sub("[%s]" % "".join(patterns), subst, v)


def img_pil_resize(img, size, aspect_ratio=True, bg=(255, 255, 255)):
    """
    Returns a resized PIL.Image, centered if aspect ratio rescale resulted in
    free space on one axis.
    """
    result = img
    if size and list(size) != list(result.size):
        size2, align_pos = list(size), None
        if result.size[0] < size[0] and img.size[1] < size[1]:
            size2 = result.size
            align_pos = [(a - b) // 2 for a, b in zip(size, size2)]
        elif aspect_ratio:
            ratio = safedivf(*result.size[:2])
            size2[ratio > 1] = int(size2[ratio > 1] * (ratio if ratio < 1 else 1 / ratio))
            align_pos = [(a - b) // 2 for a, b in zip(size, size2)]
        if result.size[0] > size[0] or result.size[1] > size[1]:
            result.thumbnail(tuple(map(int, size2)), Image.LANCZOS)
        if align_pos:
            result, result0 = Image.new(img.mode, size, bg), result
            result.paste(result0, tuple(map(int, align_pos)))
    return result


def img_wx_to_pil(image):
    """Returns PIL.Image for wx.Image."""
    (w, h), data = image.GetSize(), image.GetData()

    chans = [Image.new("L", (w, h)) for i in range(3)]
    for i in range(3): chans[i].frombytes(bytes(data[i::3]))
    if image.HasAlpha():
        chans += [Image.new("L", (w, h))]
        chans[-1].frombytes(bytes(image.GetAlpha()))

    return Image.merge("RGBA"[:len(chans)], chans)


def img_wx_to_raw(img, format="PNG"):
    """Returns the wx.Image or wx.Bitmap as raw data of specified type."""
    stream = io.BytesIO()
    img = img if isinstance(img, wx.Image) else img.ConvertToImage()
    fmttype = getattr(wx, "BITMAP_TYPE_" + format.upper(), wx.BITMAP_TYPE_PNG)
    img.SaveFile(stream, fmttype)
    result = stream.getvalue()
    return result


def int_to_base(value, digits=string.ascii_uppercase):
    """
    Returns integer represented in custom base.

    @param   value   integer to represent, like 702
    @param   digits  base digits, defaults to upper-case ASCII letters A..Z
    @return          integer string in given base, like "AAA" for 702
    """
    result, base, n = "", len(digits), value + 1
    while n:
        result, n = digits[(n % base or base) - 1] + result, (n - 1) // base
    return result


def is_long(value):
    """Returns whether value is of type long in Python2, or int in Python3."""
    return isinstance(value, long if six.PY2 else int)


def is_os_64bit():
    """Returns whether the operating system is 64-bit."""
    return "64" in platform.architecture()[0]


def is_python_64bit():
    """Returns whether Python is 64-bit."""
    return (struct.calcsize("P") * 8) == 64


def is_samepath(path1, path2):
    """Returns whether the two paths point to the same file."""
    if six.PY3:
        try: return os.stat(path1) == os.stat(path2)
        except Exception: pass
    path1, path2 = (os.path.normcase(os.path.normpath(p)) for p in (path1, path2))
    return path1 == path2


def join(sep, iterable, last=" and "):
    """Returns sep.join(iterable) but with a custom separator before last."""
    lst = list(iterable)
    return "" if not lst else lst[0] if len(lst) < 2 else sep.join(lst[:-1]) + last + lst[-1]


@memoize
def lceq(a, b):
    """Returns whether x and y are caselessly equal."""
    a, b = (x if isinstance(x, six.string_types) else "" if x is None else str(x)
            for x in (a, b))
    return a.lower() == b.lower()


def longpath(path):
    """Returns the path in long Windows form ("Program Files" not PROGRA~1)."""
    result = path
    try:
        buf = ctypes.create_unicode_buffer(65536)
        GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
        if GetLongPathNameW(to_unicode(path), buf, 65536):
            result = buf.value
        else:
            head, tail = os.path.split(path)
            if GetLongPathNameW(to_unicode(head), buf, 65536):
                result = os.path.join(buf.value, tail)
    except Exception: pass
    return result


def m(o, name, case_insensitive=True):
    """Returns the members of the object or dict, filtered by name."""
    members = o if isinstance(o, dict) else dir(o)
    if case_insensitive:
        return [i for i in members if name.lower() in i.lower()]
    else:
        return [i for i in members if name in i]


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


@memoize
def parse_date(s):
    """
    Tries to parse string as date, returns input on error.
    Supports "YYYY-MM-DD", "YYYY.MM.DD", "YYYY/MM/DD", "YYYYMMDD",
    "DD.MM.YYYY", "DD/MM/YYYY", and "DD-MM-YYYY".
    """
    if not isinstance(s, six.string_types) or len(s) < 8: return s
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
def parse_datetime(s):
    """
    Tries to parse string as ISO8601 datetime, returns input on error.
    Supports "YYYY-MM-DD[ T]HH:MM(:SS)(.micros)?(Z|[+-]HH(:MM)?)?".
    """
    if not isinstance(s, six.string_types) or len(s) < 18: return s
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


def parse_ranges(value, sep=",", rng=".."):
    """
    Returns a list of indexes for a ranges string, given as integers or spreadsheet-like labels A B.

    Range end is inclusive.
    Integers in value are expected to be 1-based, result will be 0-based.

    E.g. [0, 1, 2, 4, 6, -1] for "..3,5,7.." amd "..C,E,G..".

    @param   value  any separated combination of INDEX  START..END  START..  ..END
    @param   sep    separator to use, defaults to ","
    @param   rng    range operator, defaults to ".."
    @return         [0-based index, ..]; a final -1 signifies "until last"
    """
    result, endless = [], sys.maxsize
    if not value: return result
    to_int = lambda v: max(0, int(v) - 1) if v.isdigit() else base_to_int(v)
    for part in filter(bool, (x.strip() for x in value.split(sep))):
        if rng not in part: result.append(to_int(part))
        else:
            start, end = (to_int(v.strip()) if v.strip() else None for v in part.split(rng))
            if start is None and end is None: continue # for part
            if end is None: endless = min(endless, start or 0)
            else: result.extend(range(start or 0, end + 1))
    result = sorted(set(result))
    if endless != sys.maxsize: result = [v for v in result if v < endless] + [endless, -1]
    if result == [0, -1]: result = [] # Drop all-inclusive range as unnecessary
    return result


@memoize
def parse_time(s):
    """
    Tries to parse string as time, returns input on error.
    Supports "HH:MM(:SS)?(.micros)?(Z|[+-]HH(:MM)?)?".
    """
    if not isinstance(s, six.string_types) or len(s) < 5: return s
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


def path_to_url(path):
    """Returns path as file URL, e.g. "/my file" as "file:///my%20file"."""
    return urllib.parse.urljoin('file:', urllib.request.pathname2url(path))


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
    suffix = "s" if word else ""
    if word and (word[-1:].lower() in "xyz" or word[-2:].lower() in ("ch", "sh", "ss")) \
    and not word[-2:].lower().endswith("ay"): suffix = "es"
    if isupper: suffix = suffix.upper()
    if count != 1 and "es" == suffix and "y" == word[-1:].lower():
        word = word[:-1] + ("I" if isupper else "i")
    result = word + ("" if 1 == count else suffix)
    if numbers and items is not None:
        if 1 == count: fmtcount = single
        elif not count: fmtcount = "0"
        elif max_units:
            UNITS = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]
            log = min(len(UNITS) - 1, math.floor(math.log(count, 1000)))
            formatted = "%.*f" % (2, count / math.pow(1000, log))
            fmtcount = formatted.rstrip("0").rstrip(".") + UNITS[int(log)]
        elif sep: fmtcount = "".join([
            x + (sep if i and not i % 3 else "") for i, x in enumerate(str(count)[::-1])
        ][::-1])
        else: fmtcount = str(count)

        fmtcount = pref + fmtcount + suf
        result = "%s %s" % (single if 1 == count else fmtcount, result)
    return result.strip()


def round_float(value, precision=1, force_decimal=False):
    """
    Returns number as a string, rounded to the specified precision and
    with trailing zeroes (and . if no decimals) removed.

    @param   value          float or int
    @param   precision      decimal places to keep
    @param   force_decimal  whether to retain at least one decimal even if 0
    """
    value = round(float(value), max(0, precision))
    text = str(value) # Prefer str as giving shortest decimal representation
    if "e" in text.lower(): text = "%f" % value # Enforce decimal notation over scientific
    text = re.sub(r"(\.\d+?)0+$", r"\1", text)
    return text if force_decimal else re.sub(r"\.0+$", "", text)


def run_once(function):
    """Runs the function in a later thread at most once."""
    myqueue = getattr(run_once, "queue", builtins.set())
    setattr(run_once, "queue", myqueue)

    def later():
        functions = list(myqueue)
        myqueue.clear()
        for f in functions: f()

    if function not in myqueue:
        myqueue.add(function)
        if wx: wx.CallLater(100, later)
        else: threading.Thread(target=later).start()


def safedivf(a, b):
    """A zero-safe division, returns 0.0 if b is 0, a / float(b) otherwise."""
    return a / float(b) if b else 0.0


def safe_filename(filename):
    """Returns the filename with characters like \:*?"<>| removed."""
    return re.sub(r"[\/\\\:\*\?\"\<\>\|\x00-\x1f]", "", filename)


def select_file(path):
    """
    Tries to open the file directory, and select file if path is a file.
    Falls back to opening directory only (select is Windows-only).
    """
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if "nt" != os.name or not os.path.exists(path) or path is folder:
        start_file(folder)
        return
    try: subprocess.Popen('explorer /select, "%s"' % shortpath(path))
    except Exception: start_file(folder)


def setval(collection, value, *path):
    """
    Sets the value at specified collection path. If a path step does not exist,
    it is created as dict. Collection can be a nested structure of dicts and lists.
    Returns value.
    """
    if len(path) == 1 and isinstance(path[0], list): path = path[0]
    ptr = collection
    for p in path[:-1]:
        if isinstance(ptr, collections_abc.Sequence):  # Iterable with index
            if isinstance(p, six.integer_types) and p < len(ptr):
                ptr = ptr[p]
            else:
                ptr.append({})
                ptr = ptr[-1]
        elif isinstance(ptr, collections_abc.Mapping): # Container with lookup
            if p not in ptr: ptr[p] = {}
            ptr = ptr[p]
    ptr[path[-1]] = value
    return value


def shortpath(path):
    """Returns the path in short Windows form (PROGRA~1 not "Program Files")."""
    if isinstance(path, bytes): return path
    from ctypes import wintypes

    ctypes.windll.kernel32.GetShortPathNameW.argtypes = [
        # lpszLongPath, lpszShortPath, cchBuffer
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD
    ]
    ctypes.windll.kernel32.GetShortPathNameW.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(4 * len(path))
    ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value


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


def timedelta_seconds(timedelta):
    """Returns the total timedelta duration in seconds."""
    if hasattr(timedelta, "total_seconds"):
        result = timedelta.total_seconds()
    else: # Python 2.6 compatibility
        result = timedelta.days * 24 * 3600 + timedelta.seconds + \
                 timedelta.microseconds / 1000000.
    return result


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


def to_int(value):
    """Returns the value as integer, or None if not integer."""
    try: return int(value)
    except ValueError: return None


def to_long(value):
    """Returns value as long in Python2, int in Python3."""
    return long(value) if six.PY2 else int(value)


def to_str(value, encoding=None):
    """
    Returns the value as an 8-bit string. Tries encoding as UTF-8 if
    locale encoding fails.
    """
    result = value
    if isinstance(value, six.text_type):
        encoding = encoding or locale.getpreferredencoding()
        try: result = value.encode(encoding)
        except Exception:
            try: result = value.encode("utf-8", errors="backslashreplace")
            except Exception:
                try: result = value.encode("latin1", errors="backslashreplace")
                except Exception: result = value.encode("latin1", errors="replace")
    elif not isinstance(value, six.binary_type): result = str(value)
    return result.decode("latin1") if six.PY3 else result


def to_unicode(value, encoding=None):
    """
    Returns the value as a Unicode string. Tries decoding as UTF-8 if
    locale decoding fails.
    """
    result = value
    if isinstance(result, six.binary_type):
        encoding = encoding or locale.getpreferredencoding()
        try: result = six.text_type(result, encoding)
        except Exception:
            try: result = six.text_type(result, "utf-8", errors="backslashreplace")
            except Exception:
                result = six.text_type(result, "utf-8", errors="ignore")
    elif not isinstance(result, six.text_type):
        try: result = six.text_type(result)
        except Exception: result = repr(result)
    if not isinstance(result, six.text_type):
        result = six.text_type(result)
    return result


def try_ignore(func, *args, **kwargs):
    """
    Tries to execute the specified function a number of times.

    @param    func   callable to execute
    @param    args   positional arguments to callable
    @param    limit  number of times to try (default 1)
    @param    sleep  seconds to sleep after failed attempts, if any (default 0.5)
    @return          (True, func_result) if success else (False, None)
    """
    result, func_result, tries = False, None, 0
    limit, sleep = kwargs.get("limit", 1), kwargs.get("sleep", 0.5)
    while tries < limit:
        tries += 1
        try: result, func_result = True, func(*args)
        except Exception:
            if sleep and tries < limit: time.sleep(sleep)
    return result, func_result


def tuplefy(value):
    """Returns the value as a tuple if list/set/tuple else as a tuple of one."""
    return value if isinstance(value, tuple) \
           else tuple(value) if isinstance(value, (list, set)) else (value, )


def unique_path(pathname):
    """
    Returns a unique version of the path. If a file or directory with the
    same name already exists, returns a unique version
    (e.g. "C:\config (2).sys" if ""C:\config.sys" already exists).
    """
    result = pathname
    if "linux" in sys.platform and isinstance(result, six.text_type) \
    and "utf-8" != sys.getfilesystemencoding():
        result = result.encode("utf-8").decode("latin1") # Linux has trouble if locale not UTF-8
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


@memoize
def unprint(s, escape=True):
    """Returns string with unprintable characters escaped or stripped."""
    repl = (lambda m: m.group(0).encode("unicode-escape").decode("latin1")) if escape else ""
    return re.sub(r"[\x00-\x1f]", repl, s)


def unrepeat(s, front="", end="", case=False):
    """
    Returns text with duplicate substrings removed from front or end.

    @param   front     prefix to deduplicate from front of string
    @param   end       suffix to deduplicate from end of string
    @oaram   case      whether deduplication should be case-sensitive
    @return            deduplicated text, like unrepeat("my.db.db", end=".db") == "my.db"
    """
    s = re.sub("^(%s){2,}" % re.escape(front), front, s, flags=0 if case else re.I) if front else s
    s = re.sub("(%s){2,}$" % re.escape(end),   end,   s, flags=0 if case else re.I) if end   else s
    return s


def url_to_path(url, double_decode=False):
    """Returns file URL as path, e.g. "file:///my%20file" as "/my file"."""
    if not url.startswith("file:"): return url
    path = urllib.request.url2pathname(url[5:])
    path = re.sub(r"^[\\/]+([\\/])([^\\/])", r"\1\2", path) # Strip redundant filelink slashes
    if double_decode and isinstance(path, six.text_type):
        # Workaround for wx.html.HtmlWindow double encoding
        try: path = path.encode("latin1", errors="xmlcharrefreplace").decode("utf-8")
        except Exception: pass
    return path


def walk(data, callback):
    """
    Walks through the collection of nested dicts or lists or tuples, invoking
    callback(child, key, parent) for each element, recursively.
    """
    if isinstance(data, collections_abc.Iterable) and not isinstance(data, six.string_types):
        for k, v in enumerate(data):
            if isinstance(data, collections_abc.Mapping): k, v = v, data[v]
            callback(k, v, data)
            walk(v, callback)


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
