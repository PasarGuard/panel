# PasarGuard CLI

A modern, type-safe command-line interface for managing PasarGuard, built with Typer.

## Features

-   🎯 Type-safe CLI with rich output
-   📊 Beautiful tables and panels
-   🔒 Secure admin management
-   👥 User account listing
-   🖥️ Node listing
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
PasarGuard cli version

# Show help
PasarGuard cli --help
```

### Admin Management

```bash
# List all admins
PasarGuard cli admins --list

# Create new admin
PasarGuard cli admins --create username

# Delete admin
PasarGuard cli admins --delete username

# Modify admin (password and sudo status)
PasarGuard cli admins --modify username

# Reset admin usage
PasarGuard cli admins --reset-usage username
```

### User Account Listing

```bash
# List all users
PasarGuard cli users

# List users with status filter
PasarGuard cli users --status active

# List users with pagination
PasarGuard cli users --offset 10 --limit 20
```

### Node Listing

```bash
# List all nodes
PasarGuard cli nodes
```

### System Information

```bash
# Show system status
PasarGuard cli system
```
