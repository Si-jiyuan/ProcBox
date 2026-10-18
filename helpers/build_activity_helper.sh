#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p src/procbox/platforms/bin
swiftc -O helpers/activity_helper.swift -o src/procbox/platforms/bin/procbox-activity
