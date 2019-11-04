# -*- coding: utf-8 -*-
"""
Background workers for potentially long-running tasks like searching.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    04.11.2019
------------------------------------------------------------------------------
"""
from collections import OrderedDict
import hashlib
import logging
import os
import Queue
import re
import sqlite3
import subprocess
import threading
import traceback

from . lib import util
from . lib.vendor import step
from . import conf
from . import database
from . searchparser import flatten, match_words, SearchQueryParser
from . import templates

logger = logging.getLogger(__name__)


class WorkerThread(threading.Thread):
    """Base class for worker threads."""

    def __init__(self, callback=None):
        """
        @param   callback  function to call with result chunks
        """
        threading.Thread.__init__(self)
        self.daemon = True
        self._callback = callback
        self._is_running   = False # Flag whether thread is running
        self._is_working   = False # Flag whether thread is currently working
        self._drop_results = False # Flag to not post back obtained results
        self._queue = Queue.Queue()


    def work(self, data):
        """
        Registers new work to process. Stops current work, if any. Starts
        thread if not running.

        @param   data  a dict with work data
        """
        self._is_working = False
        self._queue.put(data)
        if not self._is_running: self.start()


    def stop(self):
        """Stops the worker thread."""
        self._is_running = False
        self._is_working = False
        self._drop_results = True
        self._queue.put(None) # To wake up thread waiting on queue


    def stop_work(self, drop_results=False):
        """
        Signals to stop the currently ongoing work, if any. Obtained results
        will be posted back, unless drop_results is True.
        """
        self._is_working = False
        self._drop_results = drop_results


    def is_working(self):
        """Returns whether the thread is currently doing work."""
        return self._is_working


    def postback(self, data):
        # Check whether callback is still bound to a valid object instance
        if callable(self._callback) and getattr(self._callback, "__self__", True):
            self._callback(data)


    def run(self):
        """Generic runner, expects a callable to invoke."""
        self._is_running = True
        while self._is_running:
            func = self._queue.get()
            if not func: continue # while self._is_running

            result, error = None, None

            self._is_working, self._drop_results = True, False
            try: result = func()
            except Exception as e:
                if self._is_running:
                    logger.exception("Error running %s.", func)
                    error = util.format_exc(e)

            if self._drop_results: continue # while self._is_running
            if error: self.postback({"error": error})
            else:
                self.postback({"done": True, "result": result, "callable": func})
            self._is_working = False



class SearchThread(WorkerThread):
    """
    Search background thread, searches the database on demand, yielding
    results back to main thread in chunks.

    @param   dict  {text, db, table}
    """

    def __init__(self, callback):
        super(self.__class__, self).__init__(callback)
        self.parser = SearchQueryParser()


    def make_replacer(self, words):
        """Returns word/phrase matcher regex."""
        words_re = [x if isinstance(w, tuple) else x.replace(r"\*", ".*")
                    for w in words
                    for x in [re.escape(step.escape_html(flatten(w)[0]))]]
        patterns = "(%s)" % "|".join(words_re)
        # For replacing matching words with <b>words</b>
        pattern_replace = re.compile(patterns, re.IGNORECASE)
        return pattern_replace


    def search_meta(self, search):
        """Searches database metadata, yielding (infotext, result)."""
        infotext = "database metadata"
        _, _, words, kws = self.parser.Parse(search["text"])
        pattern_replace = self.make_replacer(words)
        tpl = step.Template(templates.SEARCH_ROW_META_HTML, escape=True)
        result = {"output": "", "map": {}, "search": search, "count": 0}

        counts = OrderedDict() # {category: count}
        for category in database.Database.CATEGORIES if (words or kws) else ():
            othercats = set(database.Database.CATEGORIES) - set([category])
            if category not in kws and othercats & set(kws):
                continue # for category

            for item in search["db"].get_category(category).values():
                if (category in kws 
                and not match_words(item["name"], kws[category], any)
                or "-" + category in kws 
                and match_words(item["name"], kws["-" + category], any)):
                    continue # for item

                if not match_words(item["sql"], words) \
                and (words or category not in kws):
                    continue # for item

                counts[category] = counts.get(category, 0) + 1
                result["count"] += 1
                ns = dict(category=category, item=item,
                          pattern_replace=pattern_replace)
                result["output"] += tpl.expand(ns)
                key = "%s:%s" % (category, item["name"])
                result["map"][key] = {"category": category, "page": "schema",
                                      "name": item["name"]}
                if not result["count"] % conf.SearchResultsChunk:
                    yield "", result
                    result = dict(result, output="", map={})
                if not self._is_working: break # for item
            if not self._is_working: break # for category
        if counts: infotext += ": found %s; %s in total" % (
            ", ".join("<a href='#%s'><font color='%s'>%s</font></a>" %
                      (k, conf.LinkColour, util.plural(k, v))
                      for k, v in counts.items()),
            util.plural("result", result["count"])
        )
        yield infotext, result


    def search_data(self, search):
        """Searches database data, yielding (infotext, result)."""
        infotext = ""
        _, _, words, kws = self.parser.Parse(search["text"])
        pattern_replace = self.make_replacer(words)
        tpl_item = step.Template(templates.SEARCH_ROW_DATA_HEADER_HTML, escape=True)
        tpl_row  = step.Template(templates.SEARCH_ROW_DATA_HTML, escape=True)
        result = {"output": "", "map": {}, "search": search, "count": 0}

        for category in "table", "view":
            if category not in kws \
            and ("table" if "view" == category else "view") in kws:
                continue # for category

            mytexts = []
            for item in search["db"].get_category(category).values():
                sql, params, _, _ = self.parser.Parse(search["text"], item)
                if not self._is_working: break # for item
                if not sql: continue # for item

                cursor = search["db"].execute(sql, params)
                row = cursor.fetchone()
                if not row:
                    mytexts.append(step.escape_html(item["name"]))
                    continue # for item

                result["output"] = tpl_item.expand(category=category, item=item)
                count = 0
                while row:
                    result["count"], count = result["count"] + 1, count + 1

                    ns = dict(category=category, item=item, row=row,
                              keywords=kws, count=count,
                              pattern_replace=pattern_replace)
                    result["output"] += tpl_row.expand(ns)
                    key = "%s:%s:%s" % (category, item["name"], count)
                    result["map"][key] = {"category": category,
                                          "name": item["name"],
                                          "row": row}
                    if not result["count"] % conf.SearchResultsChunk:
                        yield "", result
                        result = dict(result, output="", map={})

                    if not self._is_working \
                    or result["count"] >= conf.MaxSearchResults:
                        break # while row

                    row = cursor.fetchone()

                if not self._drop_results:
                    result["output"] += "</table></font>"
                    yield "", result
                    result = dict(result, output="", map={})

                mytexts.append("<b>%s</b> (<a href='#%s'><font color='%s'>%s</font></a>)" % (
                    step.escape_html(item["name"]), step.escape_html(item["name"]),
                    conf.LinkColour, util.plural("result", count)
                ))
                if not self._is_working \
                or result["count"] >= conf.MaxSearchResults:
                    break # for item

            infotext += "%s%s: %s" % ("; " if infotext else "",
                util.plural(category, mytexts, numbers=False),
                ", ".join(mytexts))
            if not self._is_working or result["count"] >= conf.MaxSearchResults:
                break # for category
        if infotext:
            infotext += "; %s in total" % util.plural("result", result["count"])
        yield infotext, result


    def run(self):
        self._is_running = True
        while self._is_running:
            try:
                search = self._queue.get()
                if not search: continue # while self._is_running

                logger.info('Searching "%(text)s" in %(source)s (%(db)s).', search)
                self._is_working, self._drop_results = True, False
                infotext = search["source"]
                result = {"output": "", "map": {}, "search": search, "count": 0}

                searcher = self.search_meta if "meta" == search["source"] \
                           else self.search_data
                for infotext, result in searcher(search):
                    if not self._drop_results: self.postback(result)
                    if not self._is_working: break # for result

                if not result["count"]: final_text = "No matches found."
                else: final_text = "Finished searching %s." % infotext

                if not self._is_working: final_text += " Stopped by user."
                elif "data" == search["source"] \
                and result["count"] >= conf.MaxSearchResults:
                    final_text += " Stopped at limit %s." % conf.MaxSearchResults

                result = dict(result, done=True,
                              output="</table><br /><br />%s</font>" % final_text)
                self.postback(result)
                logger.info("Search found %s results.", result["count"])
                self._is_working = False
            except Exception as e:
                result["done"], result["error"] = True, traceback.format_exc()
                result["error_short"] = util.format_exc(e)
                self.postback(result)
                self._is_working = False



class DetectDatabaseThread(WorkerThread):
    """
    SQLite database detection background thread, goes through potential
    directories and yields database filenames back to main thread one by one.

    @param   bool  whether to run detection
    """

    def run(self):
        self._is_running = True
        while self._is_running:
            search = self._queue.get()
            if not search: continue # while self._is_running

            self._is_working, self._drop_results = True, False
            all_filenames = set() # To handle potential duplicates
            for filenames in database.detect_databases():
                filenames = all_filenames.symmetric_difference(filenames)
                if not self._drop_results:
                    self.postback({"filenames": filenames})
                all_filenames.update(filenames)
                if not self._is_working:
                    break # for filename

            if not self._drop_results:
                self.postback({"done": True, "count": len(all_filenames)})
            self._is_working = False



class ImportFolderThread(WorkerThread):
    """
    SQLite database import background thread, goes through given folder
    and yields database filenames back to main thread one by one.

    @param   path  directory path to import
    """

    def run(self):
        self._is_running = True
        while self._is_running:
            path = self._queue.get()
            if not path: continue # while self._is_running

            self._is_working, self._drop_results = True, False
            all_filenames = set()
            for filenames in database.find_databases(path):
                all_filenames.update(filenames)
                if filenames and not self._drop_results:
                    self.postback({"filenames": filenames, "folder": path})
                if not self._is_working:
                    break # for filename

            if not self._drop_results:
                self.postback({"done": True, "count": len(all_filenames), "folder": path})
            self._is_working = False



class AnalyzerThread(WorkerThread):
    """
    SQLite analyzer background thread, invokes the stand-alone analyzer tool
    and sends retrieved statistics to main thread.

    @param   path  database file path to analyze
    @return        {?error: str,
                    ?data: {"table": [{name, size, size_total, ?index: [], ?size_index}],
                            "index": [{name, size, table}]},
                            "filesize": int}
    """

    def __init__(self, callback):
        """
        @param   callback  function to call with result chunks
        """
        super(AnalyzerThread, self).__init__(callback)
        self._process = None # subprocess.Popen


    def stop(self):
        """Stops the worker thread."""
        super(AnalyzerThread, self).stop()
        try: self._process.kill()
        except Exception: pass
        self._process = None


    def stop_work(self, drop_results=False):
        """
        Signals to stop the currently ongoing work, if any.
        """
        super(AnalyzerThread, self).stop_work(drop_results)
        try: self._process.kill()
        except Exception: pass
        self._process = None


    def run(self):
        self._is_running = True
        while self._is_running:
            path = self._queue.get()
            if not path: continue # while self._is_running

            self._is_working, self._drop_results = True, False
            filesize, output, rows, error = 0, "", [], None

            if os.path.exists(path): filesize = os.path.getsize(path)
            else: error = "File does not exist."

            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                pargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             startupinfo=startupinfo)
                paths = [path]
                if filesize and "nt" == os.name and isinstance(path, unicode):
                    paths.append(util.shortpath(path))
                for mypath in paths if filesize else ():
                    args = [conf.DBAnalyzer, mypath]
                    logger.info('Invoking external command "%s".', " ".join(args))
                    try: self._process = subprocess.Popen(args, **pargs)
                    except Exception:
                        if mypath == paths[-1]: raise
                    else: break # for mypath
                if self._process: output, error = self._process.communicate()
            except Exception as e:
                if self._process:
                    try:
                        self._process.kill()
                        output, error = self._process.communicate()
                    except Exception: pass
                error = error or getattr(e, "output", None)
                if error: error = error.split("\n")[0].strip()
                else: error = util.format_exc(e)
                logger.exception("Error getting statistics for %s: %s.", path, error)
            else:
                if output and not output.strip().startswith("/**"):
                    output, error = "", output.split("\n")[0].strip()
                    logger.info("Error getting statistics for %s: %s.", path, error)
            self._process = None

            try:
                if output:
                    db = sqlite3.connect(":memory:")
                    db.row_factory = sqlite3.Row
                    db.executescript(output)
                    rows = db.execute("SELECT * FROM space_used "
                                      "WHERE name NOT LIKE 'sqlite_%' "
                                      "ORDER BY compressed_size DESC").fetchall()
                    db.close()
            except Exception as e:
                logger.exception("Error processing statistics for %s.", path)
                error = util.format_exc(e)
            if not rows and not error and self._is_working:
                error = "Database is empty."

            if self._drop_results: continue # while self._is_running
            if error:
                self.postback({"error": error})
            else:
                tablemap = {} # {name: {}}
                data = {"table": [], "index": [], "filesize": filesize, "sql": output}
                for row in rows:
                    category = "index" if row["is_index"] else "table"
                    item = {"name": row["name"], "size": row["compressed_size"]}
                    if "table" == category: tablemap[row["name"]] = item
                    else:
                        item["table"] = row["tblname"]
                        tablemap[row["tblname"]].setdefault("index", []).append(item)
                    data[category].append(item)
                for item in data["table"]:
                    size_index = sum(x["size"] for x in item["index"]) \
                                 if "index" in item else None
                    item["size_total"] = item["size"] + (size_index or 0)
                    if size_index is not None: item["size_index"] = size_index


                self.postback({"data": data})
            self._is_working = False



class ChecksumThread(WorkerThread):
    """
    Checksum calculator background thread, goes through database file
    and computes MD5 and SHA-1 hashes.

    @param   path  database file path to analyze
    @return        {?"error": str, ?"sha1": str, ?"md5": str}
    """

    def run(self):
        BLOCKSIZE = 1048576

        self._is_running = True
        while self._is_running:
            path = self._queue.get()
            if not path: continue # while self._is_running

            self._is_working, self._drop_results = True, False
            error = ""

            if not error:
                sha1, md5 = hashlib.sha1(), hashlib.md5()
                try:
                    with open(path, "rb") as f:
                        buf = f.read(BLOCKSIZE)
                        while len(buf):
                            sha1.update(buf), md5.update(buf)
                            buf = f.read(BLOCKSIZE)
                            if not self._is_working: break # while len
                except Exception as e:
                    logger.exception("Error calculating checksum for %s.", path)
                    error = util.format_exc(e)

            if self._drop_results: continue # while self._is_running
            if error: self.postback({"error": error})
            elif self._is_working:
                self.postback({"sha1": sha1.hexdigest(), "md5": md5.hexdigest()})
            self._is_working = False
