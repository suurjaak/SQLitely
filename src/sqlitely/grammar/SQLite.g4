/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2013 by Bart Kiers
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use,
 * copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following
 * conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 *
 * Project      : sqlite-parser; an ANTLR4 grammar for SQLite
 *                https://github.com/bkiers/sqlite-parser
 * Developed by : Bart Kiers, bart@big-o.nl
 *
 * Updates:       unicode identifiers;
 *                add column_name to CREATE VIEW;
 *                add table_function_name;
 *                drop cte_table_name;
 *                fix multi-word column type;
 *                more use of with_clause;
 *                drop Java-specific exception;
 *                double quotes allowed in string_literal;
 *                fix module arguments;
 *                only ROWID allowed after WITHOUT;
 *                disallow certain keywords in column types and constraint names;
 *                add TRUE/FALSE literals;
 *                add support for INDEX expressions;
 *                add support for NULLS FIRST|LAST in ORDER BY;
 *                ensure statement list is delimited;
 *                fix ambiguity in parsing INDEX expressions with COLLATE,
 *                update keywords;
 *                add support for CREATE TABLE .. STRICT;
 *                add support for generated columns;
 *                add support for IS DISTINCT FROM and IS NOT DISTINCT FROM;
 *                add support for JSON operators -> and ->>;
 *                add support for UPSERT statements;
 *                add support for window functions;
 *                add support from UPDATE FROM;
 *                add support RIGHT and FULL JOIN;
 *                add support for ORDER BY in function calls;
 *                add support for VACUUM INTO;
 *                add support for RETURNING;
 *                add support for ALTER TABLE DROP/RENAME column;
 *                add support for table alias in INSERT.
 *                add support for column name list in UPDATE;
 *                rename database_name to schema_name;
 *                add support for underscore separator in numeric literals.
 *
 * Updated for  : SQLitely, an SQLite database tool.
 * Updated by   : Erki Suurjaak, 2019-2024
 * Update to:   : full coverage of SQLite grammar up to version 3.46.
 */
grammar SQLite;

parse
 : ( sql_stmt_list | error )? EOF
 ;

error
 : UNEXPECTED_CHAR 
 ;

sql_stmt_list
 : ';'* sql_stmt ( ';'+ sql_stmt )* ';'*
 ;

sql_stmt
 : ( K_EXPLAIN ( K_QUERY K_PLAN )? )? ( alter_table_stmt
                                      | analyze_stmt
                                      | attach_stmt
                                      | begin_stmt
                                      | commit_stmt
                                      | compound_select_stmt
                                      | create_index_stmt
                                      | create_table_stmt
                                      | create_trigger_stmt
                                      | create_view_stmt
                                      | create_virtual_table_stmt
                                      | delete_stmt
                                      | delete_stmt_limited
                                      | detach_stmt
                                      | drop_index_stmt
                                      | drop_table_stmt
                                      | drop_trigger_stmt
                                      | drop_view_stmt
                                      | factored_select_stmt
                                      | insert_stmt
                                      | pragma_stmt
                                      | reindex_stmt
                                      | release_stmt
                                      | rollback_stmt
                                      | savepoint_stmt
                                      | simple_select_stmt
                                      | select_stmt
                                      | update_stmt
                                      | update_stmt_limited
                                      | vacuum_stmt )
 ;

alter_table_stmt
 : K_ALTER K_TABLE ( schema_name '.' )? table_name
   ( K_RENAME K_TO new_table_name = table_name
   | K_RENAME K_COLUMN? old_column_name = column_name K_TO new_column_name = column_name
   | K_ADD K_COLUMN? column_def
   | K_DROP K_COLUMN? column_def
   )
 ;

analyze_stmt
 : K_ANALYZE ( schema_name | table_or_index_name | schema_name '.' table_or_index_name )?
 ;

attach_stmt
 : K_ATTACH K_DATABASE? expr K_AS schema_name
 ;

begin_stmt
 : K_BEGIN ( K_DEFERRED | K_IMMEDIATE | K_EXCLUSIVE )? ( K_TRANSACTION transaction_name? )?
 ;

commit_stmt
 : ( K_COMMIT | K_END ) ( K_TRANSACTION transaction_name? )?
 ;

compound_select_stmt
 : with_clause?
   select_core ( ( K_UNION K_ALL? | K_INTERSECT | K_EXCEPT ) select_core )+
   ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
   ( K_LIMIT expr ( ( K_OFFSET | ',' ) expr )? )?
 ;

create_index_stmt
 : K_CREATE K_UNIQUE? K_INDEX ( K_IF K_NOT K_EXISTS )?
   ( schema_name '.' )? index_name K_ON table_name '(' indexed_column ( ',' indexed_column )* ')'
   ( K_WHERE expr )?
 ;

create_table_stmt
 : K_CREATE ( K_TEMP | K_TEMPORARY )? K_TABLE ( K_IF K_NOT K_EXISTS )?
   ( schema_name '.' )? table_name
   ( '(' column_def ( ',' column_def )*? ( ',' table_constraint )* ')'
   ( table_option ( ',' table_option )* )?
   | K_AS select_stmt
   )
 ;

create_trigger_stmt
 : K_CREATE ( K_TEMP | K_TEMPORARY )? K_TRIGGER ( K_IF K_NOT K_EXISTS )?
   ( schema_name '.' )? trigger_name ( K_BEFORE  | K_AFTER | K_INSTEAD K_OF )? 
   ( K_DELETE | K_INSERT | K_UPDATE ( K_OF column_name ( ',' column_name )* )? ) K_ON ( schema_name '.' )? table_name
   ( K_FOR K_EACH K_ROW )? ( K_WHEN expr )?
   K_BEGIN ( ( update_stmt | insert_stmt | delete_stmt | select_stmt ) ';' )+ K_END
 ;

create_view_stmt
 : K_CREATE ( K_TEMP | K_TEMPORARY )? K_VIEW ( K_IF K_NOT K_EXISTS )?
   ( schema_name '.' )? view_name 
   ( '(' column_name ( ',' column_name )* ')' )?
   K_AS select_stmt
 ;

create_virtual_table_stmt
 : K_CREATE K_VIRTUAL K_TABLE ( K_IF K_NOT K_EXISTS )?
   ( schema_name '.' )? table_name
   K_USING module_name ( '(' module_argument ( ',' module_argument )* ')' )?
 ;

delete_stmt
 : with_clause? K_DELETE K_FROM qualified_table_name 
   ( K_WHERE expr )?
   returning_clause?
 ;

delete_stmt_limited
 : with_clause? K_DELETE K_FROM qualified_table_name 
   ( K_WHERE expr )? returning_clause?
   ( ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
     K_LIMIT expr ( ( K_OFFSET | ',' ) expr )?
   )?
 ;

detach_stmt
 : K_DETACH K_DATABASE? schema_name
 ;

drop_index_stmt
 : K_DROP K_INDEX ( K_IF K_EXISTS )? ( schema_name '.' )? index_name
 ;

drop_table_stmt
 : K_DROP K_TABLE ( K_IF K_EXISTS )? ( schema_name '.' )? table_name
 ;

drop_trigger_stmt
 : K_DROP K_TRIGGER ( K_IF K_EXISTS )? ( schema_name '.' )? trigger_name
 ;

drop_view_stmt
 : K_DROP K_VIEW ( K_IF K_EXISTS )? ( schema_name '.' )? view_name
 ;

factored_select_stmt
 : with_clause?
   select_core ( compound_operator select_core )*
   ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
   ( K_LIMIT expr ( ( K_OFFSET | ',' ) expr )? )?
 ;

insert_stmt
 : with_clause? ( K_INSERT 
                | K_REPLACE
                | K_INSERT K_OR K_REPLACE
                | K_INSERT K_OR K_ROLLBACK
                | K_INSERT K_OR K_ABORT
                | K_INSERT K_OR K_FAIL
                | K_INSERT K_OR K_IGNORE ) K_INTO
   ( schema_name '.' )? table_name (K_AS table_alias)?
   ( '(' column_name ( ',' column_name )* ')' )?
   ( K_VALUES '(' expr ( ',' expr )* ')' ( ',' '(' expr ( ',' expr )* ')' )* upsert_clause?
   | select_stmt upsert_clause?
   | K_DEFAULT K_VALUES
   )
   returning_clause?
 ;

pragma_stmt
 : K_PRAGMA ( schema_name '.' )? pragma_name ( '=' pragma_value
                                               | '(' pragma_value ')' )?
 ;

reindex_stmt
 : K_REINDEX ( collation_name
             | ( schema_name '.' )? ( table_name | index_name )
             )?
 ;

release_stmt
 : K_RELEASE K_SAVEPOINT? savepoint_name
 ;

rollback_stmt
 : K_ROLLBACK ( K_TRANSACTION transaction_name? )? ( K_TO K_SAVEPOINT? savepoint_name )?
 ;

savepoint_stmt
 : K_SAVEPOINT savepoint_name
 ;

simple_select_stmt
 : with_clause?
   select_core ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
   ( K_LIMIT expr ( ( K_OFFSET | ',' ) expr )? )?
 ;

select_stmt
 : with_clause?
   select_core ( compound_operator select_core )*
   ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
   ( K_LIMIT expr ( ( K_OFFSET | ',' ) expr )? )?
 ;

update_stmt
 : with_clause? K_UPDATE ( K_OR K_ROLLBACK
                         | K_OR K_ABORT
                         | K_OR K_REPLACE
                         | K_OR K_FAIL
                         | K_OR K_IGNORE )? qualified_table_name
   K_SET ( column_name | column_name_list ) '=' expr
         ( ',' ( column_name | column_name_list ) '=' expr )*
   ( K_FROM ( table_or_subquery ( ',' table_or_subquery )* | join_clause ) )?
   ( K_WHERE expr )? returning_clause?
 ;

update_stmt_limited
 : with_clause? K_UPDATE ( K_OR K_ROLLBACK
                         | K_OR K_ABORT
                         | K_OR K_REPLACE
                         | K_OR K_FAIL
                         | K_OR K_IGNORE )? qualified_table_name
   K_SET ( column_name | column_name_list ) '=' expr
         ( ',' ( column_name | column_name_list ) '=' expr )*
   ( K_FROM ( table_or_subquery ( ',' table_or_subquery )* | join_clause ) )?
   ( K_WHERE expr )? returning_clause?
   ( ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
     K_LIMIT expr ( ( K_OFFSET | ',' ) expr )? 
   )?
 ;

vacuum_stmt
 : K_VACUUM ( K_INTO filename )?
 ;

column_def
 : column_name type_name? column_constraint*
 ;

type_name
 : type_name_text
   ( '(' signed_number ')' | '(' signed_number ',' signed_number ')' )?
 ;

type_name_text
 : ( STRING_LITERAL | '`' (~'`' | '``')* '`' | '[' ~']'* ']' )
 | type_or_constraint_name_word+
 ;

type_or_constraint_name_word
 : ~('(' | ',' | K_CONSTRAINT | K_PRIMARY | K_FOREIGN | K_NOT | K_NULL | K_UNIQUE | K_CHECK | K_DEFAULT | K_COLLATE | K_REFERENCES)
 ;

column_constraint
 : ( K_CONSTRAINT constraint_name )?
   (   K_PRIMARY K_KEY ( K_ASC | K_DESC )? conflict_clause K_AUTOINCREMENT?
     | K_NOT? K_NULL conflict_clause
     | K_UNIQUE conflict_clause
     | K_CHECK '(' expr ')'
     | K_DEFAULT (signed_number | literal_value | '(' expr ')')
     | K_COLLATE collation_name
     | foreign_key_clause
     | generated_clause
   )
 ;

constraint_name
 : ( STRING_LITERAL | '`' (~'`' | '``')* '`' | '[' ~']'* ']' )
 | type_or_constraint_name_word
 ;

conflict_clause
 : ( K_ON K_CONFLICT ( K_ROLLBACK
                     | K_ABORT
                     | K_FAIL
                     | K_IGNORE
                     | K_REPLACE
                     )
   )?
 ;

/*
    SQLite understands the following binary operators, in order from highest to
    lowest precedence:

    ||
    -> ->>
    *    /    %
    +    -
    <<   >>   &    |
    <    <=   >    >=
    =    ==   !=   <>   IS   IS NOT   IS DISTINCT FROM   IS NOT DISTINCT FROM   IN   LIKE   GLOB   MATCH   REGEXP
    AND
    OR
*/
expr
 : literal_value
 | BIND_PARAMETER
 | ( ( schema_name '.' )? table_name '.' )? column_name
 | unary_operator expr
 | expr '||' expr
 | expr ( '*' | '/' | '%' ) expr
 | expr ( '+' | '-' ) expr
 | expr ( '<<' | '>>' | '&' | '|' ) expr
 | expr ( '<' | '<=' | '>' | '>=' ) expr
 | expr ( '->' | '->>' ) expr
 | expr ( '=' | '==' | '!=' | '<>' | K_IS | K_IS K_NOT | K_IN | K_LIKE | K_GLOB | K_MATCH | K_REGEXP ) expr
 | expr K_AND expr
 | expr K_OR expr
 | function_name '(' function_arguments? ')' filter_clause? over_clause?
 | '(' expr ( ',' expr )* ')'
 | K_CAST '(' expr K_AS type_name ')'
 | expr K_COLLATE collation_name
 | expr K_NOT? ( K_LIKE | K_GLOB | K_REGEXP | K_MATCH ) expr ( K_ESCAPE expr )?
 | expr ( K_ISNULL | K_NOTNULL | K_NOT K_NULL )
 | expr K_IS K_NOT? ( K_DISTINCT K_FROM )? expr
 | expr K_NOT? K_BETWEEN expr K_AND expr
 | expr K_NOT? K_IN ( '(' ( select_stmt | expr ( ',' expr )* )?  ')'
                    | ( schema_name '.' )? table_name )
                    | ( schema_name '.' table_function_name '(' ( expr ( ',' expr )* )? ')' )
 | ( ( K_NOT )? K_EXISTS )? '(' select_stmt ')'
 | K_CASE expr? ( K_WHEN expr K_THEN expr )+ ( K_ELSE expr )? K_END
 | raise_function
 ;

filter_clause
 : K_FILTER '(' K_WHERE expr ')'
 ;

foreign_key_clause
 : K_REFERENCES foreign_table ( '(' column_name ( ',' column_name )* ')' )?
   ( ( K_ON ( K_DELETE | K_UPDATE ) ( K_SET K_NULL
                                    | K_SET K_DEFAULT
                                    | K_CASCADE
                                    | K_RESTRICT
                                    | K_NO K_ACTION )
     | K_MATCH name
     ) 
   )*
   ( K_NOT? K_DEFERRABLE ( K_INITIALLY K_DEFERRED | K_INITIALLY K_IMMEDIATE )? )?
 ;

function_arguments
 :  K_DISTINCT? expr ( ',' expr )*
    ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
 | '*' 
 ;

generated_clause
 : ( K_GENERATED K_ALWAYS )? K_AS '(' expr ')' ( C_STORED | K_VIRTUAL )?
 ;

over_clause
 : K_OVER ( window_name | window_defn )
 ;

returning_clause
 : K_RETURNING ( '*' | expr ( K_AS? column_alias )? ) ( ',' ( '*' | expr ( K_AS? column_alias )? ) )*
 ;

window_defn
 : '(' base_window_name? (K_PARTITION K_BY expr ( ',' expr )* )?
       ( K_ORDER K_BY ordering_term ( ',' ordering_term )* )?
       frame_spec?
   ')'
 ;

frame_spec
 : frame_clause ( K_EXCLUDE ( K_NO K_OTHERS | K_CURRENT K_ROW | K_GROUP | K_TIES ) )?
 ;

frame_clause
 : ( K_RANGE | K_ROWS | K_GROUPS ) 
   ( frame_single
   | K_BETWEEN frame_left K_AND frame_right
   )
 ;

frame_single
 : expr K_PRECEDING
 | K_UNBOUNDED K_PRECEDING
 | K_CURRENT K_ROW
 ;

frame_left
 : expr K_PRECEDING
 | expr K_FOLLOWING
 | K_CURRENT K_ROW
 | K_UNBOUNDED K_PRECEDING
 ;

frame_right
 : expr K_PRECEDING
 | expr K_FOLLOWING
 | K_CURRENT K_ROW
 | K_UNBOUNDED K_FOLLOWING
 ;

raise_function
 : K_RAISE '(' ( K_IGNORE 
               | ( K_ROLLBACK | K_ABORT | K_FAIL ) ',' error_message )
           ')'
 ;

indexed_column
 : ( column_name | expr ) ( K_COLLATE collation_name )? ( K_ASC | K_DESC )?
 ;

table_constraint
 : ( K_CONSTRAINT constraint_name )?
   ( ( K_PRIMARY K_KEY | K_UNIQUE ) '(' indexed_column ( ',' indexed_column )* ')' conflict_clause
   | K_CHECK '(' expr ')'
   | K_FOREIGN K_KEY '(' column_name ( ',' column_name )* ')' foreign_key_clause
   )
 ;

table_option
 : K_WITHOUT C_ROWID
 | C_STRICT
 ;

upsert_clause
 : 
 ( K_ON K_CONFLICT
   ( '(' indexed_column ( ',' indexed_column )* ')' ( K_WHERE expr)? )?
   K_DO (
     K_NOTHING
     | K_UPDATE K_SET (
       ( column_name | column_name_list ) '=' expr ( ',' ( column_name | column_name_list ) '=' expr )*
     ) ( K_WHERE expr )?
   )
 )+
 ;

with_clause
 : K_WITH K_RECURSIVE? common_table_expression ( ',' common_table_expression )*
 ;

qualified_table_name
 : ( schema_name '.' )? table_name ( K_INDEXED K_BY index_name
                                     | K_NOT K_INDEXED )?
 ;

ordering_term
 : expr ( K_COLLATE collation_name )? ( K_ASC | K_DESC )? ( K_NULLS ( K_FIRST | K_LAST ) )?
 ;

pragma_value
 : signed_number
 | name
 | STRING_LITERAL
 ;

common_table_expression
 : table_name ( '(' column_name ( ',' column_name )* ')' )?
   K_AS ( K_NOT? K_MATERIALIZED )? '(' select_stmt ')'
 ;

result_column
 : '*'
 | table_name '.' '*'
 | expr ( K_AS? column_alias )?
 ;

table_or_subquery
 : ( schema_name '.' )? table_name ( K_AS? table_alias )?
   ( K_INDEXED K_BY index_name | K_NOT K_INDEXED )?
 | ( schema_name '.' )? table_function_name '(' ( expr ( ',' expr )* )? ')' ( K_AS? table_alias )?
 | '(' ( table_or_subquery ( ',' table_or_subquery )* | join_clause )
   ')' ( K_AS? table_alias )?
 | '(' select_stmt ')' ( K_AS? table_alias )?
 ;

join_clause
 : table_or_subquery ( join_operator table_or_subquery join_constraint )*
 ;

join_operator
 : ','
 | K_NATURAL? ( ( K_LEFT | K_RIGHT | K_FULL ) K_OUTER? | K_INNER | K_CROSS )? K_JOIN
 ;

join_constraint
 : ( K_ON expr
   | K_USING '(' column_name ( ',' column_name )* ')' )?
 ;

select_core
 : K_SELECT ( K_DISTINCT | K_ALL )? result_column ( ',' result_column )*
   ( K_FROM ( table_or_subquery ( ',' table_or_subquery )* | join_clause ) )?
   ( K_WHERE expr )?
   ( K_GROUP K_BY expr ( ',' expr )* ( K_HAVING expr )? )?
   ( K_WINDOW window_name K_AS window_defn ( ',' window_name K_AS window_defn )* )?
 | K_VALUES '(' expr ( ',' expr )* ')' ( ',' '(' expr ( ',' expr )* ')' )*
 ;

compound_operator
 : K_UNION
 | K_UNION K_ALL
 | K_INTERSECT
 | K_EXCEPT
 ;

signed_number
 : ( '+' | '-' )? NUMERIC_LITERAL
 ;

literal_value
 : NUMERIC_LITERAL
 | STRING_LITERAL
 | BLOB_LITERAL
 | K_NULL
 | C_TRUE
 | C_FALSE
 | K_CURRENT_TIME
 | K_CURRENT_DATE
 | K_CURRENT_TIMESTAMP
 ;

unary_operator
 : '-'
 | '+'
 | '~'
 | K_NOT
 ;

error_message
 : STRING_LITERAL
 ;

module_argument
 : column_def
 | expr
 ;

column_alias
 : IDENTIFIER
 | keyword
 | STRING_LITERAL
 ;

keyword
 : K_ABORT
 | K_ACTION
 | K_ADD
 | K_AFTER
 | K_ALL
 | K_ALTER
 | K_ALWAYS
 | K_ANALYZE
 | K_AND
 | K_AS
 | K_ASC
 | K_ATTACH
 | K_AUTOINCREMENT
 | K_BEFORE
 | K_BEGIN
 | K_BETWEEN
 | K_BY
 | K_CASCADE
 | K_CASE
 | K_CAST
 | K_CHECK
 | K_COLLATE
 | K_COLUMN
 | K_COMMIT
 | K_CONFLICT
 | K_CONSTRAINT
 | K_CREATE
 | K_CROSS
 | K_CURRENT
 | K_CURRENT_DATE
 | K_CURRENT_TIME
 | K_CURRENT_TIMESTAMP
 | K_DATABASE
 | K_DEFAULT
 | K_DEFERRABLE
 | K_DEFERRED
 | K_DELETE
 | K_DESC
 | K_DETACH
 | K_DISTINCT
 | K_DO
 | K_DROP
 | K_EACH
 | K_ELSE
 | K_END
 | K_ESCAPE
 | K_EXCEPT
 | K_EXCLUDE
 | K_EXCLUSIVE
 | K_EXISTS
 | K_EXPLAIN
 | K_FAIL
 | K_FILTER
 | K_FIRST
 | K_FOLLOWING
 | K_FOR
 | K_FOREIGN
 | K_FROM
 | K_FULL
 | K_GENERATED
 | K_GLOB
 | K_GROUP
 | K_GROUPS
 | K_HAVING
 | K_IF
 | K_IGNORE
 | K_IMMEDIATE
 | K_IN
 | K_INDEX
 | K_INDEXED
 | K_INITIALLY
 | K_INNER
 | K_INSERT
 | K_INSTEAD
 | K_INTERSECT
 | K_INTO
 | K_IS
 | K_ISNULL
 | K_JOIN
 | K_KEY
 | K_LAST
 | K_LEFT
 | K_LIKE
 | K_LIMIT
 | K_MATCH
 | K_MATERIALIZED
 | K_NATURAL
 | K_NO
 | K_NOT
 | K_NOTHING
 | K_NOTNULL
 | K_NULL
 | K_NULLS
 | K_OF
 | K_OFFSET
 | K_ON
 | K_OR
 | K_ORDER
 | K_OTHERS
 | K_OUTER
 | K_OVER
 | K_PARTITION
 | K_PLAN
 | K_PRAGMA
 | K_PRECEDING
 | K_PRIMARY
 | K_QUERY
 | K_RAISE
 | K_RANGE
 | K_RECURSIVE
 | K_REFERENCES
 | K_REGEXP
 | K_REINDEX
 | K_RELEASE
 | K_RENAME
 | K_REPLACE
 | K_RESTRICT
 | K_RETURNING
 | K_RIGHT
 | K_ROLLBACK
 | K_ROW
 | K_ROWS
 | K_SAVEPOINT
 | K_SELECT
 | K_SET
 | K_TABLE
 | K_TEMP
 | K_TEMPORARY
 | K_THEN
 | K_TIES
 | K_TO
 | K_TRANSACTION
 | K_TRIGGER
 | K_UNBOUNDED
 | K_UNION
 | K_UNIQUE
 | K_UPDATE
 | K_USING
 | K_VACUUM
 | K_VALUES
 | K_VIEW
 | K_VIRTUAL
 | K_WHEN
 | K_WHERE
 | K_WINDOW
 | K_WITH
 | K_WITHOUT
 // Keywords only in some context:
 | C_ROWID
 | C_STORED
 | C_STRICT
 | C_TRUE
 | C_FALSE
 ;

// TODO check all names below

name
 : any_name
 ;

function_name
 : any_name
 ;

schema_name
 : any_name
 ;

table_function_name
 : any_name
 ;

table_name 
 : any_name
 ;

table_or_index_name 
 : any_name
 ;

column_name 
 : any_name
 ;

column_name_list
 : '(' column_name ( ',' column_name )* ')'
 ;

collation_name 
 : any_name
 ;

foreign_table 
 : any_name
 ;

index_name 
 : any_name
 ;

trigger_name
 : any_name
 ;

view_name 
 : any_name
 ;

module_name 
 : any_name
 ;

pragma_name 
 : any_name
 ;

savepoint_name 
 : any_name
 ;

table_alias
 : IDENTIFIER
 | keyword
 | STRING_LITERAL
 ;

transaction_name
 : any_name
 ;

window_name
 : any_name
 ;

base_window_name
 : any_name
 ;

filename
 : any_name
 ;

any_name
 : IDENTIFIER 
 | keyword
 | STRING_LITERAL
 | '(' any_name ')'
 ;

SCOL : ';';
DOT : '.';
OPEN_PAR : '(';
CLOSE_PAR : ')';
COMMA : ',';
ASSIGN : '=';
STAR : '*';
PLUS : '+';
MINUS : '-';
TILDE : '~';
PIPE2 : '||';
DIV : '/';
MOD : '%';
LT2 : '<<';
GT2 : '>>';
AMP : '&';
PIPE : '|';
LT : '<';
LT_EQ : '<=';
GT : '>';
GT_EQ : '>=';
EQ : '==';
NOT_EQ1 : '!=';
NOT_EQ2 : '<>';

// http://www.sqlite.org/lang_keywords.html
K_ABORT             : A B O R T;
K_ACTION            : A C T I O N;
K_ADD               : A D D;
K_AFTER             : A F T E R;
K_ALL               : A L L;
K_ALTER             : A L T E R;
K_ALWAYS            : A L W A Y S;
K_ANALYZE           : A N A L Y Z E;
K_AND               : A N D;
K_AS                : A S;
K_ASC               : A S C;
K_ATTACH            : A T T A C H;
K_AUTOINCREMENT     : A U T O I N C R E M E N T;
K_BEFORE            : B E F O R E;
K_BEGIN             : B E G I N;
K_BETWEEN           : B E T W E E N;
K_BY                : B Y;
K_CASCADE           : C A S C A D E;
K_CASE              : C A S E;
K_CAST              : C A S T;
K_CHECK             : C H E C K;
K_COLLATE           : C O L L A T E;
K_COLUMN            : C O L U M N;
K_COMMIT            : C O M M I T;
K_CONFLICT          : C O N F L I C T;
K_CONSTRAINT        : C O N S T R A I N T;
K_CREATE            : C R E A T E;
K_CROSS             : C R O S S;
K_CURRENT           : C U R R E N T;
K_CURRENT_DATE      : C U R R E N T '_' D A T E;
K_CURRENT_TIME      : C U R R E N T '_' T I M E;
K_CURRENT_TIMESTAMP : C U R R E N T '_' T I M E S T A M P;
K_DATABASE          : D A T A B A S E;
K_DEFAULT           : D E F A U L T;
K_DEFERRABLE        : D E F E R R A B L E;
K_DEFERRED          : D E F E R R E D;
K_DELETE            : D E L E T E;
K_DESC              : D E S C;
K_DETACH            : D E T A C H;
K_DISTINCT          : D I S T I N C T;
K_DO                : D O;
K_DROP              : D R O P;
K_EACH              : E A C H;
K_ELSE              : E L S E;
K_END               : E N D;
K_ESCAPE            : E S C A P E;
K_EXCEPT            : E X C E P T;
K_EXCLUDE           : E X C L U D E;
K_EXCLUSIVE         : E X C L U S I V E;
K_EXISTS            : E X I S T S;
K_EXPLAIN           : E X P L A I N;
K_FAIL              : F A I L;
K_FILTER            : F I L T E R;
K_FIRST             : F I R S T;
K_FOLLOWING         : F O L L O W I N G;
K_FOR               : F O R;
K_FOREIGN           : F O R E I G N;
K_FROM              : F R O M;
K_FULL              : F U L L;
K_GENERATED         : G E N E R A T E D;
K_GLOB              : G L O B;
K_GROUP             : G R O U P;
K_GROUPS            : G R O U P S;
K_HAVING            : H A V I N G;
K_IF                : I F;
K_IGNORE            : I G N O R E;
K_IMMEDIATE         : I M M E D I A T E;
K_IN                : I N;
K_INDEX             : I N D E X;
K_INDEXED           : I N D E X E D;
K_INITIALLY         : I N I T I A L L Y;
K_INNER             : I N N E R;
K_INSERT            : I N S E R T;
K_INSTEAD           : I N S T E A D;
K_INTERSECT         : I N T E R S E C T;
K_INTO              : I N T O;
K_IS                : I S;
K_ISNULL            : I S N U L L;
K_JOIN              : J O I N;
K_KEY               : K E Y;
K_LAST              : L A S T;
K_LEFT              : L E F T;
K_LIKE              : L I K E;
K_LIMIT             : L I M I T;
K_MATCH             : M A T C H;
K_MATERIALIZED      : M A T E R I A L I Z E D;
K_NATURAL           : N A T U R A L;
K_NO                : N O;
K_NOT               : N O T;
K_NOTHING           : N O T H I N G;
K_NOTNULL           : N O T N U L L;
K_NULL              : N U L L;
K_NULLS             : N U L L S;
K_OF                : O F;
K_OFFSET            : O F F S E T;
K_ON                : O N;
K_OR                : O R;
K_ORDER             : O R D E R;
K_OTHERS            : O T H E R S;
K_OUTER             : O U T E R;
K_OVER              : O V E R;
K_PARTITION         : P A R T I T I O N;
K_PLAN              : P L A N;
K_PRAGMA            : P R A G M A;
K_PRECEDING         : P R E C E D I N G;
K_PRIMARY           : P R I M A R Y;
K_QUERY             : Q U E R Y;
K_RAISE             : R A I S E;
K_RANGE             : R A N G E;
K_RECURSIVE         : R E C U R S I V E;
K_REFERENCES        : R E F E R E N C E S;
K_REGEXP            : R E G E X P;
K_REINDEX           : R E I N D E X;
K_RELEASE           : R E L E A S E;
K_RENAME            : R E N A M E;
K_REPLACE           : R E P L A C E;
K_RESTRICT          : R E S T R I C T;
K_RETURNING         : R E T U R N I N G;
K_RIGHT             : R I G H T;
K_ROLLBACK          : R O L L B A C K;
K_ROW               : R O W;
K_ROWS              : R O W S;
K_SAVEPOINT         : S A V E P O I N T;
K_SELECT            : S E L E C T;
K_SET               : S E T;
K_TABLE             : T A B L E;
K_TEMP              : T E M P;
K_TEMPORARY         : T E M P O R A R Y;
K_THEN              : T H E N;
K_TIES              : T I E S;
K_TO                : T O;
K_TRANSACTION       : T R A N S A C T I O N;
K_TRIGGER           : T R I G G E R;
K_UNBOUNDED         : U N B O U N D E D;
K_UNION             : U N I O N;
K_UNIQUE            : U N I Q U E;
K_UPDATE            : U P D A T E;
K_USING             : U S I N G;
K_VACUUM            : V A C U U M;
K_VALUES            : V A L U E S;
K_VIEW              : V I E W;
K_VIRTUAL           : V I R T U A L;
K_WHEN              : W H E N;
K_WHERE             : W H E R E;
K_WINDOW            : W I N D O W;
K_WITH              : W I T H;
K_WITHOUT           : W I T H O U T;

C_ROWID  : R O W I D;
C_STORED : S T O R E D;
C_STRICT : S T R I C T;
C_TRUE   : T R U E;
C_FALSE  : F A L S E;

STRING_LITERAL
 : '\'' (~'\'' | '\'\'')* '\''
 | '"'  (~'"'  | '""'  )* '"'
 ;

IDENTIFIER
 : '"' (~'"' | '""')* '"'
 | '`' (~'`' | '``')* '`'
 | '[' ~']'* ']'
 | [\p{Alpha}\p{General_Category=Other_Letter}_] [\p{Alnum}\p{General_Category=Other_Letter}_]*
 ;

NUMERIC_LITERAL
 : NUMBER ( '.' NUMBER? )? ( E [-+]? NUMBER )?
 | '.' NUMBER ( E [-+]? NUMBER )?
 ;

NUMBER
 : DIGIT ( '_'* DIGIT )*
 ;

BIND_PARAMETER
 : '?' DIGIT*
 | [:@$] IDENTIFIER
 ;

BLOB_LITERAL
 : X STRING_LITERAL
 ;

SINGLE_LINE_COMMENT
 : '--' ~[\r\n]* -> channel(2)
 ;

MULTILINE_COMMENT
 : '/*' .*? ( '*/' | EOF ) -> channel(2)
 ;

SPACES
 : [ \u000B\t\r\n] -> channel(HIDDEN)
 ;

UNEXPECTED_CHAR
 : .
 ;

fragment DIGIT : [0-9];

fragment A : [aA];
fragment B : [bB];
fragment C : [cC];
fragment D : [dD];
fragment E : [eE];
fragment F : [fF];
fragment G : [gG];
fragment H : [hH];
fragment I : [iI];
fragment J : [jJ];
fragment K : [kK];
fragment L : [lL];
fragment M : [mM];
fragment N : [nN];
fragment O : [oO];
fragment P : [pP];
fragment Q : [qQ];
fragment R : [rR];
fragment S : [sS];
fragment T : [tT];
fragment U : [uU];
fragment V : [vV];
fragment W : [wW];
fragment X : [xX];
fragment Y : [yY];
fragment Z : [zZ];
