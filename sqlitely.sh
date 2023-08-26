#!/bin/bash
PYTHONPATH=src:$PYTHONPATH exec >/dev/null 2>&1 python3 -m sqlitely "$@"
