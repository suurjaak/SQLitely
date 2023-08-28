#!/bin/bash
BASEDIR=$(realpath $(dirname "${BASH_SOURCE[0]:-$0}"))  # Absolute path to script directory
PYTHONPATH=$BASEDIR/src:$PYTHONPATH exec >/dev/null 2>&1 python3 -m sqlitely "$@"
