#!/bin/bash
# Wrapper to run hdl-buspro-mqtt with the configured arguments
exec hdl-buspro-mqtt --hdl-host 192.168.88.1 --verbose /configuration.yaml
