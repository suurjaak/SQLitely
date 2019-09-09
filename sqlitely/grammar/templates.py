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
@modified    08.09.2019
------------------------------------------------------------------------------
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
{{ LF() }}

%for i, c in enumerate(data["columns"]):
  {{ PRE() }}
  {{ Q(c["name"]) }}{{ PAD("name", c) }}

    %if c.get("type") is not None:
  {{ c["type"] }}{{ PAD("type", c) }}
    %endif

    %if c.get("pk") is not None:
  PRIMARY KEY {{ c["pk"].get("direction", "") }}
        %if c["pk"].get("conflict"):
  ON CONFLICT {{ c["pk"]["conflict"] }}
        %endif
        %if c["pk"].get("autoincrement"):
  AUTOINCREMENT
        %endif
    %endif

    %if c.get("notnull") is not None:
  NOT NULL
        %if c["notnull"].get("conflict"):
  ON CONFLICT {{ c["notnull"]["conflict"] }}
        %endif
    %endif

    %if c.get("unique") is not None:
  UNIQUE
        %if c["unique"].get("conflict"):
  ON CONFLICT {{ c["unique"]["conflict"] }}
        %endif
    %endif

    %if c.get("default") is not None:
  DEFAULT {{ WS(c["default"]) }}
    %endif

    %if c.get("collate") is not None:
  COLLATE {{ c["collate"] }}
    %endif

    %if c.get("check") is not None:
  CHECK ({{ WS(c["check"]) }})
    %endif

    %if c.get("fk") is not None:
  REFERENCES {{ Q(c["fk"]["table"]) }}
        %if c["fk"].get("key"):
  ({{ Q(c["fk"]["key"]) }})
        %endif
        %if c["fk"].get("defer") is not None:
    {{ "NOT" if c["fk"]["defer"].get("not") else "" }}
    DEFERRABLE 
            %if c["fk"].get("initial"):
    INITIALLY {{ c["fk"]["defer"]["initial"] }}
            %endif
        %endif
        %for action, act in c["fk"].get("action", {}).items():
    ON {{ action }} {{ act }}
        %endfor
        %for match in c["fk"].get("match", []):
    MATCH {{ match }}
        %endfor
    %endif

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
  {{ WS(" ") }}(
  {{ LF() }}
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
