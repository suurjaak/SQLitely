CHANGELOG
=========

2.2, 2023-09-19
---------------
- add line number and word-wrap toggles to more controls
- add diagram export to Tools-menu
- add option to export diagram with selected entities
- add refresh-button and copy-button to diagram toolbar
- add option to copy diagram image to clipboard
- add YAML formatting options to value editor
- retain undo history when loading SQL from file to SQL editor
- fix error on changing column order in trigger/view editor
- fix error on reindexing table from diagram if table has no index
- fix error on checking foreign keys if foreign table has no primary key
- fix Excel export error, from breaking changes in PIL


2.1, 2023-08-16
---------------
- add user-defined functions to value editor
- add button panels to data and schema tabs
- add NULL column icons to schema diagram
- add column and key toggles to schema diagram
- add option to hide data grid columns
- add filter and hide column options in grid row context menu
- add support for multiple item export into any supported output format
- add command-line flag --config-file
- add NULLS FIRST|LAST to SQLite grammar ORDER BY clause
- add splitter to program main page
- add file encoding detection in CSV import, improve CSV dialect detection
- order database categories as table-view-index-trigger
- use uniform icons for schema tree items
- retain schema diagram custom layout on schema change
- support index and trigger keywords in meta search
- support importing structured data from YAML to database
- support importing JSON files containing a single dict
- support TIMESTAMP as date column type in search
- omit comments from JSON export
- underline matched texts in meta search results
- include journal file sizes in database size
- improve compatibility with GTK and Python 3.8+ on Linux.
- update step, the vendored template library
- fix loading user-specific configuration file
- fix schema diagram not loading entity positions from last config
- fix schema diagram adopting custom layout on clicking an entity
- fix collecting related entities on getting all related SQL or exporting to another database
- fix error on canceling a single grid export
- fix error on toggling diagram foreign labels on
- fix diagram in statistics HTML export using current view settings
- fix operating on key columns of BLOB affinity in data grids
- fix encoding errors in running disk usage analyzer
- fix escaping special characters for regex in exported HTML search functions
- fix complex alter ignoring related triggers (SQLite 3.25+ compatibility)
- fix JSON/YAML import not using column names from data
- fix spreadsheet import using same columns for all sheets


2.0, 2022-04-02
---------------
- add schema diagram, exportable as bitmap or vector
- add data import wizard
- add option to create database from spreadsheet or JSON
- add option to have only single instance running
- add option to clone a table or view
- add option to drop entire schema
- add support for single-user install
- add easy rename options to data & schema tree
- add easy drop column options to data & schema tree
- add spreadsheet file drag-drop support to database page
- add YAML support
- add Dockerfile
- full Python2 / Python3 compatibility
- improve auto-altering related items
- move to src-layout
- many fixes and UI tweaks


1.1, 2020-08-08
---------------
- add value editor tool
- add transform and date options to column value editor
- use OS- and user-specific config directory where necessary
- bugfixes and UI tweaks


1.0, 2020-07-07
---------------
- first public release
