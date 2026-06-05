# PasarGuard CLI

A modern, type-safe command-line interface for managing PasarGuard, built with Typer. PasarGuard supports both [Xray-core](https://github.com/XTLS/Xray-core) and [WireGuard](https://www.wireguard.com/).

## Features

-   🎯 Type-safe CLI with rich output
-   🔒 One-time temp key generation for owner setup
-   ⌨️ Simple project-root and installed-service usage

## Installation

The CLI is included with PasarGuard and can be used directly:

```bash
PasarGuard cli --help

# Or from the project root
uv run PasarGuard-cli.py --help
```

## Usage

### General Commands

```bash
# Show version
pasarguard cli version

# Generate a one-time temp key for owner setup
pasarguard cli generate-temp-key

# Show help
pasarguard cli --help
```

### Owner Setup

Admin management is handled from the dashboard. For owner setup, reset, delete, or upgrade operations, generate a one-time temp key and use it on the dashboard login page.

```bash
pasarguard cli generate-temp-key
```
