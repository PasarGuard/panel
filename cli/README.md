# PasarGuard CLI

A modern, type-safe command-line interface for managing PasarGuard, built with Typer.

## Features

-   🎯 Type-safe CLI with rich output
-   📊 Beautiful tables and panels
-   🔒 Secure admin management
-   📈 System status monitoring
-   ⌨️ Interactive prompts and confirmations

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

# Show help
pasarguard cli --help
```

### Admin Management

```bash
# List all admins
pasarguard cli admins --list

# Create new admin
pasarguard cli admins --create username

# Delete admin
pasarguard cli admins --delete username

# Modify admin (password and sudo status)
PasarGuard cli admins --modify username

# Reset admin usage
pasarguard cli admins --reset-usage username
```

### System Information

```bash
# Show system status
PasarGuard cli system
```
