# -*- coding: utf-8 -*-
"""
Templates for generating SQL statements.

Parameters expected by templates:

    data       statement data structure
    root       root data structure
    Template   Template-class
    templates  this module
    CM         comma setter(type, i, ?subtype, ?j, ?root=None)
    GLUE       surrounding whitespace consuming token setter()
    LF         linefeed token setter()
    PAD        padding token setter(key, data)
    PRE        line start indentation token setter()
    Q          quoted name token setter(identifier)
    WS         whitespace as-is token setter(val)

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     07.09.2019
@modified    01.01.2022
------------------------------------------------------------------------------
"""



"""
Simple ALTER TABLE.

@param   data {
             name:      table old name
             name2:     table new name if renamed else old name
             ?columns:  [(column name in old, column name in new)]
             ?add:      [{column data}]
             ?no_tx:    whether to not include savepoint
         }
"""
ALTER_TABLE = """
%if not data.get("no_tx"):
SAVEPOINT alter_table;{{ LF() }}
{{ LF() }}
%endif
%if data["name"] != data["name2"]:
ALTER TABLE {{ Q(data["name"]) }} RENAME TO {{ Q(data["name2"]) }};{{ LF() }}
%endif

%for i, (c1, c2) in enumerate(data.get("columns", [])):
    %if not i and data["name"] != data["name2"]:
{{ LF() }}
    %endif
ALTER TABLE {{ Q(data["name"]) }} RENAME COLUMN {{ Q(c1) }} TO {{ Q(c2) }};{{ LF() }}
%endfor

%for i, c in enumerate(data.get("add", [])):
    %if not i and (data["name"] != data["name2"] or data.get("columns")):
{{ LF() }}
    %endif
ALTER TABLE {{ Q(data["name"]) }} ADD COLUMN{{ WS(" ") }}
  {{ Template(templates.COLUMN_DEFINITION, strip=True, collapse=True).expand(dict(locals(), data=c)) }};{{ LF() }}
%endfor

%if not data.get("no_tx"):
{{ LF() }}
RELEASE SAVEPOINT alter_table;{{ LF() }}
%endif
"""



"""
Complex ALTER TABLE: re-create table under new temporary name,
copy rows from existing to new, drop existing, rename new to existing. Steps:

 1. PRAGMA foreign_keys = off
 2. BEGIN TRANSACTION
 3. CREATE TABLE tempname
 4. INSERT INTO tempname (..) SELECT .. FROM oldname
 5. DROP all related indexes-views-triggers
 6. for every related table affected by change:
    - DROP all related indexes-views-triggers
 7. DROP TABLE oldname
 8. ALTER TABLE tempname RENAME TO oldname
 9. for every related table affected by change:
    - CREATE TABLE related_tempname
    - INSERT INTO related_tempname SELECT * FROM related_name
    - DROP TABLE related_name
    - ALTER TABLE related_tempname RENAME TO related_name
    - CREATE indexes-triggers for related_name
10. CREATE indexes-views-triggers
11. COMMIT TRANSACTION
12. PRAGMA foreign_keys = on

@param   data {
             name:      table old name
             name2:     table new name if renamed else old name
             tempname:  table temporary name
             sql:       table CREATE statement with tempname
             columns:   [(column name in old, column name in new)]
             fks:       whether foreign_keys PRAGMA is on
             ?table:    [{related table {name, tempname, sql, ?index, ?trigger}, using new names}, ]
             ?index:    [{related index {name, sql?}, using new names}, ]
             ?trigger:  [{related trigger {name, sql?}, using new names}, ]
             ?view:     [{related view {name, sql}, using new names}, ]
             ?no_tx:    whether to not include savepoint
         }
If a related index or trigger does not have "sql", it is only dropped not re-created
"""
ALTER_TABLE_COMPLEX = """<%
CATEGORIES = ["index", "view", "trigger"]

%>
%if data["fks"]:
PRAGMA foreign_keys = off;{{ LF() }}
{{ LF() }}

%endif
%if not data.get("no_tx"):
SAVEPOINT alter_table;{{ LF() }}
{{ LF() }}

%endif
{{ WS(data["sql"]) }}{{ LF() }}
{{ LF() }}

%if data.get("columns"):
INSERT INTO {{ Q(data["tempname"]) }}{{ WS(" ") }}
(
    %for i, (c1, c2) in enumerate(data["columns"]):
  {{ GLUE() }}{{ Q(c2) }}{{ CM("columns", i) }}
    %endfor
{{ GLUE() }}){{ LF() }}
SELECT{{ WS(" ") }}
    %for i, (c1, c2) in enumerate(data["columns"]):
  {{ GLUE() }}{{ Q(c1) }}{{ CM("columns", i) }}
    %endfor
FROM {{ Q(data["name"]) }};{{ LF() }}
{{ LF() }}
%endif

%for category in CATEGORIES:
    %for x in data.get(category) or []:
DROP {{ category.upper() }} IF EXISTS {{ Q(x["name"]) }};{{ LF() }}
    %endfor
%endfor

%for reltable in data.get("table") or []:
    %for category in CATEGORIES:
        %for x in reltable.get(category) or []:
DROP {{ category.upper() }} IF EXISTS {{ Q(x["name"]) }};{{ LF() }}
        %endfor
    %endfor
%endfor

DROP TABLE {{ Q(data["name"]) }};{{ LF() }}
{{ LF() }}

ALTER TABLE {{ Q(data["tempname"]) }} RENAME TO {{ Q(data["name2"]) }};{{ LF() }}
{{ LF() }}

%for reltable in data.get("table") or []:
{{ WS(reltable["sql"]) }}{{ LF() }}
INSERT INTO {{ Q(reltable["tempname"]) }} SELECT * FROM {{ Q(reltable["name"]) }};{{ LF() }}
DROP TABLE {{ Q(reltable["name"]) }};{{ LF() }}
ALTER TABLE {{ Q(reltable["tempname"]) }} RENAME TO {{ Q(reltable["name"]) }};{{ LF() }}
    %for category in CATEGORIES:
        %for x in reltable.get(category) or []:
{{ WS(x["sql"]) }}{{ LF() }}
        %endfor
    %endfor
{{ LF() }}
%endfor

<%
sep = False
%>
%for category in CATEGORIES:
    %for x in data.get(category) or []:
        %if not x.get("sql"):
<% continue %>
        %endif
{{ LF() if sep else "" }}
{{ WS(x["sql"]) }}{{ LF() }}
<%
sep = True
%>
    %endfor
%endfor

%if not data.get("no_tx"):
{{ LF() }}
RELEASE SAVEPOINT alter_table;{{ LF() }}
{{ LF() }}
%endif

%if data["fks"]:
{{ LF() }}
PRAGMA foreign_keys = on;{{ LF() }}
%endif
"""



"""
ALTER INDEX: re-create index.

1. BEGIN TRANSACTION
2. DROP INDEX oldname
3. CREATE INDEX newname
4. COMMIT TRANSACTION

@param   data {
             name:      index old name
             sql:       index CREATE statement, using new name
             ?no_tx:    whether to not include savepoint
         }
"""
ALTER_INDEX = """
%if not data.get("no_tx"):
SAVEPOINT alter_index;{{ LF() }}
{{ LF() }}

%endif
DROP INDEX {{ Q(data["name"]) }};{{ LF() }}
{{ LF() }}

{{ WS(data["sql"]) }}{{ LF() }}
{{ LF() }}

%if not data.get("no_tx"):
RELEASE SAVEPOINT alter_index;{{ LF() }}
{{ LF() }}
%endif
"""



"""
ALTER TRIGGER: re-create trigger.

1. BEGIN TRANSACTION
2. DROP TRIGGER oldname
3. CREATE TRIGGER newname
4. COMMIT TRANSACTION

@param   data {
             name:      trigger old name,
             sql:       trigger CREATE statement, using new name
             ?no_tx:    whether to not include savepoint
         }
"""
ALTER_TRIGGER = """
%if not data.get("no_tx"):
SAVEPOINT alter_trigger;{{ LF() }}
{{ LF() }}

%endif
DROP TRIGGER {{ Q(data["name"]) }};{{ LF() }}
{{ LF() }}

{{ WS(data["sql"]) }}{{ LF() }}
{{ LF() }}

%if not data.get("no_tx"):
RELEASE SAVEPOINT alter_trigger;{{ LF() }}
{{ LF() }}
%endif
"""



"""
ALTER VIEW: re-create view, re-create triggers and other views using this view.

1. BEGIN TRANSACTION
2. DROP VIEW oldname
3. DROP all related triggers-views
4. CREATE VIEW newname
5. CREATE triggers-views
6. COMMIT TRANSACTION

@param   data {
             name:      view old name
             sql:       view CREATE statement, using new name
             ?trigger:  [{related trigger {name, sql}, using new names}, ]
             ?view:     [{related view {name, sql}, using new names}, ]
             ?no_tx:    whether to not include savepoint
         }
"""
ALTER_VIEW = """<%
CATEGORIES = ["view", "trigger"]

%>
%if not data.get("no_tx"):
SAVEPOINT alter_view;{{ LF() }}
{{ LF() }}

%endif
DROP VIEW {{ Q(data["name"]) }};{{ LF() }}
{{ LF() }}

%for category in CATEGORIES:
    %for x in data.get(category) or []:
DROP {{ category.upper() }} IF EXISTS {{ Q(x["name"]) }};{{ LF() }}
    %endfor
%endfor
{{ LF() if any(data.get(x) for x in CATEGORIES) else "" }}

{{ WS(data["sql"]) }}{{ LF() }}
{{ LF() }}

%for category in CATEGORIES:
    %for x in data.get(category) or []:
{{ WS(x["sql"]) }}{{ LF() }}
    %endfor
%endfor
{{ LF() if any(data.get(x) for x in CATEGORIES) else "" }}

%if not data.get("no_tx"):
RELEASE SAVEPOINT alter_view;{{ LF() }}
{{ LF() }}
%endif
"""



"""
Alter sqlite_master directly.

1. BEGIN TRANSACTION
3. UPDATE sqlite_master SET sql = .. WHERE type = x AND name = y;
4. COMMIT TRANSACTION

@param   data {
             version:   schema_version PRAGMA to set afterward
             ?table:    {name: CREATE SQL, }
             ?index:    {name: CREATE SQL, }
             ?trigger:  {name: CREATE SQL, }
             ?view:     {name: CREATE SQL, }
         }
"""
ALTER_MASTER = """<%
CATEGORIES = ["table", "index", "view", "trigger"]
%>
{{ WS("-- Overwrite CREATE statements in sqlite_master directly,") }}{{ LF() }}
{{ WS("-- to avoid table names being force-quoted by SQLite") }}{{ LF() }}
{{ WS("-- upon executing ALTER TABLE .. RENAME TO ..") }}{{ LF() }}

SAVEPOINT alter_master;{{ LF() }}
{{ LF() }}

PRAGMA writable_SCHEMA = ON;{{ LF() }}
{{ LF() }}

%for category in CATEGORIES:
    %for name, sql in data.get(category, {}).items():
UPDATE sqlite_master {{ WS("SET sql = ") }}{{ Q(sql.rstrip(";"), force=True) }}{{ LF() }}
WHERE {{ WS("type = ") }}{{ Q(category, force=True) }} {{ WS(" AND name = ") }}{{ Q(name, force=True) }};{{ LF() }}
{{ LF() }}
    %endfor
%endfor

PRAGMA schema_version = {{ data["version"] }};{{ LF() }}
{{ LF() }}

PRAGMA writable_SCHEMA = OFF;{{ LF() }}
{{ LF() }}

RELEASE SAVEPOINT alter_master;{{ LF() }}
"""



COLUMN_DEFINITION = """<%
from collections import OrderedDict

get_constraints = lambda: (
    (k, data[k]) for k in ("pk", "notnull", "unique", "default", "collate", "check", "fk")
    if data.get(k) is not None and (k != "collate" or data[k].get("value") not in (None, ""))
    and (k not in ("default", "check") or data[k].get("expr")  not in (None, ""))
)

cnstr_breaks, name0 = OrderedDict(), None
for ctype, cnstr in get_constraints():
    cnstr_breaks[ctype] = name0 or cnstr.get("name") and (name0 is not None or data.get("type"))
    name0 = cnstr.get("name") or ""
%>

{{ GLUE() }}
    %if data.get("name"):
  {{ Q(data["name"]) }}
    %else:
  {{ WS("") }}
    %endif
    %if data.get("type") or cnstr_breaks:
  {{ PAD("name", data, quoted=True) }}
    %endif

    %if data.get("type"):
  {{ WS(" ") }}
  {{ Q(data["type"], allow="() ") }}
    %endif
    %if cnstr_breaks and data.get("type") and not next(iter(cnstr_breaks.values())):
  {{ PAD("type", data, quoted=True, quotekw=dict(allow="() ")) }}
    %endif


    %if data.get("pk") is not None:
        %if cnstr_breaks["pk"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["pk"].get("name"):
  CONSTRAINT {{ Q(data["pk"]["name"]) }}
        %endif
  PRIMARY KEY {{ data["pk"].get("order", "") }}
        %if data["pk"].get("conflict"):
  ON CONFLICT {{ data["pk"]["conflict"] }}
        %endif
        %if data["pk"].get("autoincrement"):
  AUTOINCREMENT
        %endif
    %endif


    %if data.get("notnull") is not None:
        %if cnstr_breaks["notnull"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["notnull"].get("name"):
  CONSTRAINT {{ Q(data["notnull"]["name"]) }}
        %endif
  NOT NULL
        %if data["notnull"].get("conflict"):
  ON CONFLICT {{ data["notnull"]["conflict"] }}
        %endif
    %endif


    %if data.get("unique") is not None:
        %if cnstr_breaks["unique"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["unique"].get("name"):
  CONSTRAINT {{ Q(data["unique"]["name"]) }}
        %endif
  UNIQUE
        %if data["unique"].get("conflict"):
  ON CONFLICT {{ data["unique"]["conflict"] }}
        %endif
    %endif


    %if data.get("default") and data["default"].get("expr") not in (None, ""):
        %if cnstr_breaks["default"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["default"].get("name"):
  CONSTRAINT {{ Q(data["default"]["name"]) }}
        %endif
  DEFAULT {{ WS(data["default"]["expr"]) }}
    %endif


    %if data.get("collate") and data["collate"].get("value") not in (None, ""):
        %if cnstr_breaks["collate"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["collate"].get("name"):
  CONSTRAINT {{ Q(data["collate"]["name"]) }}
        %endif
  COLLATE {{ data["collate"]["value"] }}
    %endif


    %if data.get("check") and data["check"].get("expr") not in (None, ""):
        %if cnstr_breaks["check"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["check"].get("name"):
  CONSTRAINT {{ Q(data["check"]["name"]) }}
        %endif
  CHECK ({{ WS(data["check"]["expr"]) }})
    %endif


    %if data.get("fk") is not None:
        %if cnstr_breaks["fk"]:
  {{ LF() }}
  {{ PAD("name", {"name": ""}) }}
        %endif
        %if data["fk"].get("name"):
  CONSTRAINT {{ Q(data["fk"]["name"]) }}
        %endif
  REFERENCES {{ Q(data["fk"]["table"]) if data["fk"].get("table") else "" }}
        %if data["fk"].get("key"):
  {{ WS(" ") }}({{ Q(data["fk"]["key"]) }})
        %endif
        %for action, act in data["fk"].get("action", {}).items():
    ON {{ action }} {{ act }}
        %endfor
        %if data["fk"].get("match"):
    MATCH {{ data["fk"]["match"] }}
        %endif
        %if data["fk"].get("defer") is not None:
    {{ "NOT" if data["fk"]["defer"].get("not") else "" }}
    DEFERRABLE
            %if data["fk"]["defer"].get("initial"):
    INITIALLY {{ data["fk"]["defer"]["initial"] }}
            %endif
        %endif
    %endif
"""



CREATE_INDEX = """
CREATE

%if data.get("unique"):
  UNIQUE
%endif
INDEX

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) if data.get("name") else "" }}
{{ LF() if data.get("exists") and data.get("schema") else "" }}
ON {{ Q(data["table"]) if "table" in data else "" }}{{ WS(" ") }}

(
{{ GLUE() }}
%for i, col in enumerate(data.get("columns", [])):
  {{ Q(col["name"]) if "name" in col else WS(col["expr"]) if "expr" in col else "" }}
    %if col.get("collate"):
  COLLATE {{ col["collate"] }}
    %endif
    %if col.get("order"):
  {{ col["order"] }}
    %endif
  {{ CM("columns", i, root=root) }}
%endfor
{{ GLUE() }}
)

%if data.get("where"):
  {{ LF() if len(data["where"]) > 40 else "" }}
  WHERE {{ WS(data["where"]) }}
%endif
{{ GLUE() }};
"""



CREATE_TABLE = """
CREATE
    %if data.get("temporary"):
  TEMPORARY
    %endif
TABLE
    %if data.get("exists"):
  IF NOT EXISTS
    %endif
{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) if data.get("name") else "" }}{{ WS(" ") if data.get("schema") or data.get("name") else "" }}(
{{ LF() or GLUE() }}

%for i, c in enumerate(data.get("columns") or []):
  {{ PRE(Template(templates.COLUMN_DEFINITION, strip=True, collapse=True).expand(dict(locals(), data=c))) }}
  {{ CM("columns", i, root=root) }}
  {{ LF() }}
%endfor

%for i, c in enumerate(data.get("constraints") or []):
  {{ PRE() }}
  {{ Template(templates.TABLE_CONSTRAINT, strip=True, collapse=True).expand(dict(locals(), data=c, i=i)) }}
  {{ CM("constraints", i, root=root) }}
  {{ LF() }}
%endfor

{{ GLUE() }}
)

%if data.get("without"):
WITHOUT ROWID
%endif
{{ GLUE() }};
"""



CREATE_TRIGGER = """<%
import re
%>
CREATE

%if data.get("temporary"):
  TEMPORARY
%endif

TRIGGER

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) if data.get("name") else "" }}

%if data.get("upon"):
  {{ data["upon"] }}
%endif

{{ data.get("action") or "" }}

%if data.get("columns"):
  OF
    %for i, c in enumerate(data["columns"]):
  {{ Q(c["name"]) }}{{ CM("columns", i, root=root) }}
    %endfor
%endif

ON
{{ Q(data["table"]) if data.get("table") else "" }}

%if data.get("for"):
  FOR EACH ROW
%endif

%if data.get("when"):
  {{ LF() }}
  WHEN {{ WS(data["when"]) }}
%endif

{{ LF() }}BEGIN{{ LF() }}
%if data.get("body"):
  {{ WS(data["body"]) }}{{ LF() }}
%endif
END;
"""



CREATE_VIEW = """
CREATE

%if data.get("temporary"):
  TEMPORARY
%endif

VIEW

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) if data.get("name") else "" }}

%if data.get("columns"):
  {{ GLUE() }}{{ WS(" ") }}(
  {{ LF() or GLUE() }}
    %for i, c in enumerate(data["columns"]):
  {{ PRE() }}{{ Q(c["name"]) }}
  {{ CM("columns", i, root=root) }}
  {{ LF() }}
    %endfor
  )
%endif


AS {{ WS(data["select"]) if data.get("select") else "" }};
"""



CREATE_VIRTUAL_TABLE = """
CREATE VIRTUAL TABLE

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) }}
{{ LF() }}
USING {{ data["module"]["name"] }}

%if data["module"].get("arguments"):
    %if len(data["module"]["arguments"]) > 2:
  ({{ LF() }}
        %for i, arg in enumerate(data["module"]["arguments"]):
  {{ PRE() }}{{ arg }}
  {{ CM("arguments", i, root=data["module"]) }}
  {{ LF() }}
        %endfor
  )
    %else:
  {{ GLUE() }}
  ({{ ", ".join(data["module"]["arguments"]) }})
    %endif
%endif
{{ GLUE() }};
"""



"""
@param   ?i     constraint index
"""
TABLE_CONSTRAINT = """<%
cmpath = []
if not isdef("i"): i = 0
else: cmpath = ["constraints", i]

%>

{{ GLUE() }}
%if data.get("name"):
  CONSTRAINT {{ Q(data["name"]) }}
%endif

  {{ data.get("type") or "" }}

%if "CHECK" == data.get("type"):
  ({{ WS(data.get("check") or "") }})
%endif

%if data.get("type") in ("PRIMARY KEY", "UNIQUE"):
  (
  {{ GLUE() }}
    %for j, col in enumerate(data.get("key") or []):
  {{ Q(col["name"]) if col.get("name") else "" }}
        %if col.get("collate") is not None:
  COLLATE {{ col["collate"] }}
        %endif
        %if col.get("order") is not None:
  {{ col["order"] }}
        %endif
  {{ CM(*cmpath + ["key", j], root=root) }}
    %endfor
  {{ GLUE() }}
  )
    %if data.get("conflict"):
  ON CONFLICT {{ data["conflict"] }}
    %endif
%endif


%if "FOREIGN KEY" == data.get("type"):
  {{ GLUE() }}{{ WS(" ") }}
  (
    {{ GLUE() }}
    %for j, c in enumerate(data.get("columns") or []):
    {{ Q(c) }}{{ CM(*cmpath + ["columns", j], root=root) }}
    %endfor
  )

  REFERENCES  {{ Q(data["table"]) if data.get("table") else "" }}
    %if data.get("key"):
  {{ GLUE() }}{{ WS(" ") }}
  (
  {{ GLUE() }}
        %for j, c in enumerate(data["key"]):
  {{ Q(c) if c else "" }}{{ CM(*cmpath + ["key", j], root=root) }}
        %endfor
  )
    %endif
    %if data.get("defer") is not None:
    {{ "NOT" if data["defer"].get("not") else "" }}
    DEFERRABLE
        %if data["defer"].get("initial"):
    INITIALLY {{ data["defer"]["initial"] }}
        %endif
    %endif
    %for action, act in data.get("action", {}).items():
    ON {{ action }} {{ act }}
    %endfor
    %if data.get("match"):
    MATCH {{ data["match"] }}
    %endfor
%endif
"""
