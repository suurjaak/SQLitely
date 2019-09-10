# -*- coding: utf-8 -*-
"""
Templates for generating SQL statements.

Parameters expected by templates:

    data    statement data structure
    CM      comma setter(type, i)
    GLUE    surrounding whitespace consuming token setter()
    LF      linefeed token setter()
    PAD     padding token setter(key, data)
    PRE     line start indentation token setter()
    Q       quoted name token setter(identifier)
    WS      whitespace as-is token setter(val)

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     07.09.2019
@modified    10.09.2019
------------------------------------------------------------------------------
"""


COLUMN_DEFINITION = """
  {{ Q(data["name"]) }}{{ PAD("name", data, quoted=True) }}

    %if data.get("type") is not None:
  {{ data["type"] }}{{ PAD("type", data) }}
    %endif

    %if data.get("pk") is not None:
  PRIMARY KEY {{ data["pk"].get("direction", "") }}
        %if data["pk"].get("conflict"):
  ON CONFLICT {{ data["pk"]["conflict"] }}
        %endif
        %if data["pk"].get("autoincrement"):
  AUTOINCREMENT
        %endif
    %endif

    %if data.get("notnull") is not None:
  NOT NULL
        %if data["notnull"].get("conflict"):
  ON CONFLICT {{ data["notnull"]["conflict"] }}
        %endif
    %endif

    %if data.get("unique") is not None:
  UNIQUE
        %if data["unique"].get("conflict"):
  ON CONFLICT {{ data["unique"]["conflict"] }}
        %endif
    %endif

    %if data.get("default") is not None:
  DEFAULT {{ WS(data["default"]) }}
    %endif

    %if data.get("collate") is not None:
  COLLATE {{ data["collate"] }}
    %endif

    %if data.get("check") is not None:
  CHECK ({{ WS(data["check"]) }})
    %endif

    %if data.get("fk") is not None:
  REFERENCES {{ Q(data["fk"]["table"]) }}
        %if data["fk"].get("key"):
  ({{ Q(data["fk"]["key"]) }})
        %endif
        %if data["fk"].get("defer") is not None:
    {{ "NOT" if data["fk"]["defer"].get("not") else "" }}
    DEFERRABLE 
            %if data["fk"].get("initial"):
    INITIALLY {{ data["fk"]["defer"]["initial"] }}
            %endif
        %endif
        %for action, act in data["fk"].get("action", {}).items():
    ON {{ action }} {{ act }}
        %endfor
        %for match in data["fk"].get("match", []):
    MATCH {{ match }}
        %endfor
    %endif
"""



CREATE_INDEX = """
CREATE

%if data.get("unique") is not None:
  UNIQUE
%endif
INDEX

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) }}
{{ LF() if data.get("exists") and data.get("schema") else "" }}
ON {{ Q(data["table"]) }}{{ WS(" ") }}

(
{{ GLUE() }}
%for i, col in enumerate(data["columns"]):
  {{ Q(col["name"]) if col.get("name") else WS(col["expr"]) }}
    %if col.get("collate") is not None:
  COLLATE {{ col["collate"] }}
    %endif
    %if col.get("direction") is not None:
  {{ col["direction"] }}
    %endif
  {{ CM("columns", i) }}
%endfor
{{ GLUE() }}
)

%if data.get("where"):
  {{ LF() if len(data["where"]) > 40 else "" }}
  WHERE {{ WS(data["where"]) }}
%endif
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
{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) }}{{ WS(" ") }}(
{{ LF() or GLUE() }}

%for i, c in enumerate(data["columns"]):
  {{ PRE() }}
  {{ step.Template(templates.COLUMN_DEFINITION, strip=True, collapse=True).expand(dict(locals(), data=c)) }}
  {{ CM("columns", i) }}
  {{ LF() }}
%endfor



%for i, c in enumerate(data.get("constraints", [])):
{{ PRE() }}

    %if c.get("name"):
  CONSTRAINT {{ Q(c["name"]) }}
    %endif

  {{ c["type"] }}

    %if "CHECK" == c.get("type"):
  ({{ WS(c["check"]) }})
    %endif

    %if c.get("type") in ("PRIMARY KEY", "UNIQUE"):
  (
  {{ GLUE() }}
        %for j, col in enumerate(c["key"]):
  {{ Q(col["name"]) if col.get("name") else WS(col["expr"]) }}
            %if col.get("collate") is not None:
  COLLATE {{ col["collate"] }}
            %endif
            %if col.get("direction") is not None:
  {{ col["direction"] }}
            %endif
  {{ CM("constraints", i, "key", j) }}
        %endfor
  {{ GLUE() }}
  )
        %if c.get("conflict"):
  ON CONFLICT {{ c["conflict"] }}
        %endif
    %endif


    %if "FOREIGN KEY" == c.get("type"):
  ({{ ", ".join(map(Q, c["columns"])) }})
  REFERENCES  {{ Q(c["table"]) }}
        %if c.get("key"):
  ({{ ", ".join(map(Q, c["key"])) }})
        %endif
        %if c.get("defer") is not None:
    {{ "NOT" if c["defer"].get("not") else "" }}
    DEFERRABLE 
            %if c.get("initial"):
    INITIALLY {{ c["defer"]["initial"] }}
            %endif
        %endif
        %for action, act in c.get("action", {}).items():
    ON {{ action }} {{ act }}
        %endfor
        %for match in c.get("match", []):
    MATCH {{ match }}
        %endfor
    %endif


  {{ CM("constraints", i) }}
  {{ LF() }}
%endfor
{{ GLUE() }}
)

%if data.get("without"):
WITHOUT ROWID
%endif
"""



CREATE_TRIGGER = """
CREATE

%if data.get("temporary"):
  TEMPORARY
%endif

TRIGGER

%if data.get("exists"):
  IF NOT EXISTS
%endif

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) }}

%if data.get("upon"):
  {{ data["upon"] }}
%endif

{{ data["action"] }}

%if data.get("columns"):
  OF {{ ", ".join(map(Q, data["columns"])) }}
%endif

ON
{{ Q(data["table"]) }}

%if data.get("for"):
  FOR EACH ROW
%endif

%if data.get("when"):
  {{ LF() }}
  WHEN {{ WS(data["when"]) }}
%endif

{{ LF() }}BEGIN
{{ WS(data["body"]) }}
{{ LF() }}END
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

{{ "%s." % Q(data["schema"]) if data.get("schema") else "" }}{{ Q(data["name"]) }}

%if data.get("columns"):
  {{ GLUE() }}{{ WS(" ") }}(
  {{ LF() or GLUE() }}
    %for i, c in enumerate(data["columns"]):
  {{ PRE() }}{{ Q(c) }}
  {{ CM("columns", i) }}
  {{ LF() }}
    %endfor
  )
%endif


AS {{ WS(data["select"]) }}
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
  ({{ ", ".join(data["module"]["arguments"]) }})
%endif
"""
