# 🚀 kport v3.2.3 — Release Notes

**Release Date:** June 2026
**Branch:** `refactor`
**Previous Version:** 3.2.2

---

## Overview

kport 3.2.3 is an enhancement release introducing the official VS Code extension for KPort and improving CLI feedback for edge cases. This release expands the kport ecosystem with native IDE integration while maintaining full backward compatibility with 3.2.2.

---

## 🆕 New Features

### 📦 KPort VS Code Extension

Launch of the official VS Code extension bringing kport functionality directly into the editor:

- **Port Inspector**: Inspect all ports and processes directly from VS Code
- **Port Management**: Free up ports with a single command from the editor
- **Port Listing**: View detailed port information with process details
- **MCP Configuration**: Seamless Model Context Protocol (MCP) server configuration for AI-powered development workflows
- **Command Palette Integration**: Quick access to all kport features via VS Code command palette
- **Smart MCP Setup**: First-time users see an interactive consent prompt to configure MCP on extension activation

#### Features:
- `KPort: Inspect Ports` - View all active ports and their associated processes
- `KPort: Free Port` - Kill processes using a specific port
- `KPort: List Ports` - Display all listening ports with details
- `KPort: Configure MCP Server` - Set up MCP server for advanced automation

#### MCP Server Integration:
The extension now includes improved MCP setup with:
- **First-run consent prompt**: Users are asked once whether to configure MCP for AI integration
- **Automatic configuration**: Generates `.vscode/mcp.json` with proper settings
- **Manual override**: Users can configure MCP anytime via Command Palette
- **MCP stdio protocol**: Full stdio-based MCP server for AI assistants (Claude, Copilot, etc.)

**Installation:** Available on the VS Code Extension Marketplace

### 📦 Package Manager Support Expansion

Extended platform coverage with new package managers:

- **Chocolatey Support**: Now available for Windows users via Chocolatey package manager (`choco install kport`)
- **Snap Support**: Linux users can now install kport from the Snap Store (`snap install kport`)
- Automated building and publishing pipelines for both package managers
- Improved CI/CD workflow with dedicated build scripts for Chocolatey and Snap packages

### 🔨 Unified Build & Packaging System

New developer tools for streamlined build and release workflows:

- **`build.py`**: Unified orchestrator for all package building and publishing
  - Check prerequisites for all platforms
  - Build all packages or individual formats
  - Publish to all destinations (PyPI, VS Code Marketplace, Snap Store)
  - Dry-run mode for safe preview of operations
  - Interactive menu and CLI modes
  
- **`vscode_build.py`**: Dedicated VS Code extension builder
  - Build `.vsix` files with automatic dependency management
  - Install extensions locally for testing
  - Publish to VS Code Marketplace with token authentication
  - Check Node.js, npm, and VS Code CLI prerequisites
  
- **`snap_publish.py`**: Snap Store publisher
  - Publish to Snap Store with channel management (stable, edge, candidate)
  - Snapcraft authentication handling
  - Built snap file discovery and version extraction
  
- **`BUILD_GUIDE.md`**: Comprehensive developer documentation
  - Complete usage guide for all build scripts
  - Quick-start examples and interactive menus
  - Full release workflow examples
  - Troubleshooting and environment setup

---

## 🔧 Improvements

### ⚠️ Enhanced CLI Feedback

Improved user experience with warning messages for edge cases:

- **Inaccessible Process Warnings**: CLI now displays warnings when certain processes cannot be accessed due to permission restrictions
- Better handling of scenarios where port bindings are found but processes cannot be inspected
- More informative feedback when running `kport` commands to help users understand the full picture

Example:
```bash
kport list  # Now shows warnings for inaccessible processes
```

### 🛠️ Developer Experience

Streamlined build and release workflows for maintainers:

- **Unified build commands**: Single entry point for all package builds
- **Prerequisite checking**: Automatic validation of required tools before building
- **Interactive menus**: User-friendly prompts for common operations
- **Dry-run support**: Safe preview of build and publish operations
- **Multi-platform support**: Build for Windows, macOS, Linux, Snap, Chocolatey, and PyPI from one tool
- **Environment configuration**: Clear guidance on required tokens and credentials

Developers can now build and publish with:
```bash
# Interactive mode (recommended)
python3 build.py

# Command-line mode (CI/CD)
python3 build.py --build-all
python3 build.py --publish-all

# Build VS Code extension
python3 vscode_build.py

# Publish to Snap Store
python3 snap_publish.py
```

---

## 📝 Build & Packaging Updates

- Unified build orchestration system for all package formats
- New developer-focused build scripts with prerequisite checking
- Enhanced Snap and Chocolatey package building pipelines
- Improved CI/CD workflow with VS Code extension automation
- Comprehensive BUILD_GUIDE.md for developers and maintainers

---

## 🔄 Backward Compatibility

✅ Full backward compatibility maintained with kport 3.2.2

All existing command-line interfaces, APIs, and configurations continue to work without modification.

---

## 📦 Downloads

KPort v3.2.3 is available in the following formats:

- **PyPI**: `pip install kport==3.2.3`
- **Linux**: DEB/RPM packages
- **Linux Snap**: `snap install kport`
- **macOS**: DMG installer
- **Windows**: Chocolatey (`choco install kport`)
- **VS Code**: Extension Marketplace

### VS Code Extension

Install the official KPort extension from the VS Code Marketplace:
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X / Cmd+Shift+X)
3. Search for "KPort"
4. Click "Install"

Or install from command line:
```bash
code --install-extension farmanali.kport-vscode@3.2.3
```

---

## 🛠️ For Developers & Maintainers

### Building from Source

Comprehensive build guide available in `BUILD_GUIDE.md`:

```bash
# Check prerequisites
python3 build.py --check

# Build all packages
python3 build.py --build-all

# Build specific formats
python3 build.py --build-vscode    # VS Code extension
python3 build.py --build-snap      # Snap package
python3 build.py --build-pypi      # Python packages
```

### Publishing Packages

```bash
# Publish all
python3 build.py --publish-all

# Or publish specific formats
python3 vscode_build.py --publish            # VS Code Marketplace
python3 snap_publish.py --publish            # Snap Store
python3 publish.py                           # PyPI
```

See `BUILD_GUIDE.md` for complete documentation on:
- Environment setup and prerequisites
- Interactive and automated workflows
- Release channel management
- CI/CD integration
- Troubleshooting

---

## 🙏 Contributors

This release includes contributions from the kport development team. Thank you for your continued support!

---

## 📖 Additional Resources

- [GitHub Repository](https://github.com/alienhub/port-killer)
- [Documentation](https://github.com/alienhub/port-killer#readme)
- [Build Guide](./BUILD_GUIDE.md) - Comprehensive guide for building and publishing
- [Issue Tracker](https://github.com/alienhub/port-killer/issues)
- [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=farmanali.kport-vscode)
- [Snap Package](https://snapcraft.io/kport)
- [PyPI Package](https://pypi.org/project/kport/)

### MCP Integration

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Integration Guide](https://claude.ai)
- [VS Code Copilot Integration](https://github.com/features/copilot)

