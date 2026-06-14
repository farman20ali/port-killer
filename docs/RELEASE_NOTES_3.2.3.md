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

#### Features:
- `KPort: Inspect Ports` - View all active ports and their associated processes
- `KPort: Free Port` - Kill processes using a specific port
- `KPort: List Ports` - Display all listening ports with details
- `KPort: Configure MCP Server` - Set up MCP server for advanced automation

**Installation:** Available on the VS Code Extension Marketplace

### 📦 Package Manager Support Expansion

Extended platform coverage with new package managers:

- **Chocolatey Support**: Now available for Windows users via Chocolatey package manager (`choco install kport`)
- **Snap Support**: Linux users can now install kport from the Snap Store (`snap install kport`)
- Automated building and publishing pipelines for both package managers
- Improved CI/CD workflow with dedicated build scripts for Chocolatey and Snap packages

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

---

## 📝 Build & Packaging Updates

- Added support for additional package managers and distribution methods
- Enhanced build scripts for improved cross-platform compatibility
- Improved CI/CD pipeline with VS Code extension build automation

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

---

## 🙏 Contributors

This release includes contributions from the kport development team. Thank you for your continued support!

---

## 📖 Additional Resources

- [GitHub Repository](https://github.com/alienhub/port-killer)
- [Documentation](https://github.com/alienhub/port-killer#readme)
- [Issue Tracker](https://github.com/alienhub/port-killer/issues)
- [VS Code Extension](https://marketplace.visualstudio.com)

