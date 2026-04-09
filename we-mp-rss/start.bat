@echo off
set CONFIG_PATH=%CONFIG_PATH%
if "%CONFIG_PATH%"=="" set CONFIG_PATH=config.yaml

set START_MODE=%START_MODE%
if "%START_MODE%"=="" set START_MODE=api

python3 main.py -config %CONFIG_PATH% --mode %START_MODE%
