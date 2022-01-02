#!/bin/bash
PYTHONPATH=src:$PYTHONPATH exec >/dev/null 2>&1 python2 -m sqlitely "$@"
