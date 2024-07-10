#!/bin/bash
BASEDIR=$(realpath $(dirname "${BASH_SOURCE[0]:-$0}"))  # Absolute path to script directory
PYTHONPATH=$BASEDIR/src:$PYTHONPATH python3 -m sqlitely "$@"
