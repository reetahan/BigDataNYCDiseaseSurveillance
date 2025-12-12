#!/bin/bash
# Wrapper script to set Java options for Spark

export SPARK_SUBMIT_OPTS="-Djava.security.manager.allow=true"
export _JAVA_OPTIONS="-Djava.security.manager.allow=true"

cd "$(dirname "$0")"
../venv/bin/python run_chained_pipeline.py "$@"
