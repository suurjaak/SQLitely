# -*- coding: utf-8 -*-
"""
Background workers for potentially long-running tasks like searching.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    10.09.2019
------------------------------------------------------------------------------
"""
import logging
import Queue
import re
import threading
import traceback

try:
    import wx
except ImportError:
    pass # Most functionality works without wx

from . lib import util
from . lib.vendor import step
from . import conf
from . import database
from . import searchparser
from . import templates

logger = logging.getLogger(__name__)


class WorkerThread(threading.Thread):
    """Base class for worker threads."""

    def __init__(self, callback):
        """
        @param   callback  function to call with result chunks
        """
        threading.Thread.__init__(self)
        self._callback = callback
        self._is_running = False
        self._stop_work = False   # Flag to stop the current work
        self._drop_results = False # Flag to not post back obtained results
        self._queue = Queue.Queue()


    def work(self, data):
        """
        Registers new work to process. Stops current work, if any. Starts
        thread if not running.

        @param   data  a dict with work data
        """
        self._stop_work = True
        self._queue.put(data)
        if not self._is_running: self.start()


    def stop(self):
        """Stops the worker thread."""
        self._is_running = False
        self._drop_results = True
        self._stop_work = True
        self._queue.put(None) # To wake up thread waiting on queue


    def stop_work(self, drop_results=False):
        """
        Signals to stop the currently ongoing work, if any. Obtained results
        will be posted back, unless drop_results is True.
        """
        self._stop_work = True
        self._drop_results = drop_results


    def postback(self, data):
        # Check whether callback is still bound to a valid object instance
        if getattr(self._callback, "__self__", True):
            self._callback(data)


    def yield_ui(self):
        """Allows UI to respond to user input."""
        try: wx.YieldIfNeeded()
        except Exception: pass



class SearchThread(WorkerThread):
    """
    Search background thread, searches the database on demand, yielding
    results back to main thread in chunks.
    """


    def match_all(self, text, words):
        """Returns whether the text contains all the specified words."""
        text_lower = text.lower()
        result = all(w in text_lower for w in words)
        return result


    def run(self):
        self._is_running = True
        # For identifying "table:xxx" and "column:xxx" keywords
        query_parser = searchparser.SearchQueryParser()
        result = None
        while self._is_running:
            try:
                search = self._queue.get()
                if not search:
                    continue # continue while self._is_running

                TEMPLATES = {"meta":  templates.SEARCH_ROW_META_HTML,
                             "table": templates.SEARCH_ROW_TABLE_HEADER_HTML,
                             "row":   templates.SEARCH_ROW_TABLE_HTML}
                wrap_b = lambda x: "<b>%s</b>" % x.group(0)
                FACTORY = lambda x: step.Template(TEMPLATES[x], escape=True)
                logger.info('Searching "%(text)s" in %(table)s (%(db)s).' % search)
                self._stop_work = False
                self._drop_results = False

                # {"output": text with results, "map": link data map}
                # map data: {"table:name:index": {"table": "name", "row": {}}, }
                result_type, result_count, count = None, 0, 0
                result = {"output": "", "map": {},
                          "search": search, "count": 0}
                _, _, match_words, _ = query_parser.Parse(search["text"])

                # Turn wildcard characters * into regex-compatible .*
                match_words_re = [".*".join(re.escape(step.escape_html(x))
                                  for w in match_words for x in w.split("*"))]
                patt = "(%s)" % "|".join(match_words_re)
                # For replacing matching words with <b>words</b>
                pattern_replace = re.compile(patt, re.IGNORECASE)
                infotext = search["table"]

                # Find from database CREATE SQL
                if not self._stop_work and "meta" == search["table"] \
                and match_words:
                    infotext = "database CREATE SQL"
                    count = 0
                    template_meta = FACTORY("meta")

                    for category in "table", "view", "index", "trigger":
                        for item in search["db"].get_category(category).values():
                            matches = self.match_all(item["sql"], match_words)
                            if not matches: continue # for item

                            count += 1
                            result_count += 1
                            result["output"] += template_meta.expand(locals())
                            if "table" == category:
                                key = "table:%s" % item["name"]
                                result["map"][key] = {"table": item["name"]}
                            if not count % conf.SearchResultsChunk \
                            and not self._drop_results:
                                result["count"] = result_count
                                self.postback(result)
                                result = {"output": "", "map": {},
                                          "search": search, "count": 0}
                            if self._stop_work:
                                break # for item
                        if self._stop_work:
                            break # for category
                if result["output"] and not self._drop_results:
                    result["count"] = result_count
                    self.postback(result)
                    result = {"output": "", "map": {},
                              "search": search, "count": 0}


                # Find from table content
                if not self._stop_work and "tables" == search["table"]:
                    infotext, result_type = "", "table row"
                    # Search over all fields of all tables.
                    template_table = FACTORY("table")
                    template_row = FACTORY("row")
                    for table in search["db"].get_category("table").values():
                        sql, params, words, keywords = \
                            query_parser.Parse(search["text"], table)
                        if not sql:
                            continue # continue for table in search["db"]..
                        cursor = search["db"].execute(sql, params)
                        row = cursor.fetchone()
                        namepre, namesuf = ("<b>", "</b>") if row else ("", "")
                        countpre, countsuf = (("<a href='#%s'><font color='%s'>" %
                            (step.escape_html(table["name"]), conf.LinkColour),
                            "</font></a>")) if row else ("", "")
                        infotext += (", " if infotext else "") \
                                    + namepre + table["name"] + namesuf
                        if not row:
                            continue # continue for table in search["db"]..
                        result["output"] = template_table.expand(locals())
                        count = 0
                        while row:
                            count += 1
                            result_count += 1
                            result["output"] += template_row.expand(locals())
                            key = "table:%s:%s" % (table["name"], count)
                            result["map"][key] = {"table": table["name"],
                                                  "row": row}
                            if not count % conf.SearchResultsChunk \
                            and not self._drop_results:
                                result["count"] = result_count
                                self.postback(result)
                                result = {"output": "", "map": {},
                                          "search": search, "count": 0}
                            if self._stop_work \
                            or result_count >= conf.MaxSearchTableRows:
                                break # break while row
                            row = cursor.fetchone()
                        if not self._drop_results:
                            result["output"] += "</table></font>"
                            result["count"] = result_count
                            self.postback(result)
                            result = {"output": "", "map": {},
                                      "search": search, "count": 0}
                        infotext += " (%s%s%s)" % (countpre,
                                    util.plural("result", count), countsuf)
                        if self._stop_work \
                        or result_count >= conf.MaxSearchTableRows:
                            break # break for table in search["db"]..
                    single_table = ("," not in infotext)
                    infotext = "table%s: %s" % \
                               ("" if single_table else "s", infotext)
                    if not single_table:
                        infotext += "; %s in total" % \
                                    util.plural("result", result_count)


                final_text = "No matches found."
                if self._drop_results:
                    result["output"] = ""
                if result_count:
                    final_text = "Finished searching %s." % infotext

                if self._stop_work:
                    final_text += " Stopped by user."
                elif "messages" == result_type \
                and count >= conf.MaxSearchMessages:
                    final_text += " Stopped at %s limit %s." % \
                                  (result_type, conf.MaxSearchMessages)
                elif "table row" == result_type \
                and count >= conf.MaxSearchTableRows:
                    final_text += " Stopped at %s limit %s." % \
                                  (result_type, conf.MaxSearchTableRows)

                result["output"] += "</table><br /><br />%s</font>" % final_text
                result["done"] = True
                result["count"] = result_count
                self.postback(result)
                logger.info("Search found %s results.", result["count"])
            except Exception as e:
                if not result:
                    result = {}
                result["done"], result["error"] = True, traceback.format_exc()
                result["error_short"] = util.format_exc(e)
                self.postback(result)



class DetectDatabaseThread(WorkerThread):
    """
    SQLite database detection background thread, goes through potential
    directories and yields database filenames back to main thread one by one.
    """

    def run(self):
        self._is_running = True
        while self._is_running:
            search = self._queue.get()
            self._stop_work = self._drop_results = False
            if search:
                all_filenames = set() # To handle potential duplicates
                for filenames in database.detect_databases():
                    filenames = all_filenames.symmetric_difference(filenames)
                    if not self._drop_results:
                        result = {"filenames": filenames}
                        self.postback(result)
                    all_filenames.update(filenames)
                    if self._stop_work:
                        break # break for filename in database.detect_data...

                result = {"done": True, "count": len(all_filenames)}
                self.postback(result)
