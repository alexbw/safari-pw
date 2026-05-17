#!/bin/sh
# Build the safari-trusted-click helper.
# Requires Xcode Command Line Tools (xcode-select --install).
set -e
cd "$(dirname "$0")"
swiftc -O SafariTrustedClick.swift -o safari-trusted-click
echo "built: $(pwd)/safari-trusted-click"
