# Contributing to kport

First off, thank you for considering contributing to kport! 🎉

## How Can I Contribute?

### Reporting Bugs 🐛

Before creating bug reports, please check the existing issues to avoid duplicates. When creating a bug report, include:

- **Description**: Clear and concise description of the bug
- **Steps to Reproduce**: Detailed steps to reproduce the behavior
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**:
  - OS (Windows/Linux/macOS) and version
  - Python version (`python --version`)
  - kport version (`kport --version`)
- **Screenshots**: If applicable
- **Additional Context**: Any other relevant information

### Suggesting Features 💡

Feature suggestions are welcome! Please:

- Use a clear and descriptive title
- Provide detailed description of the suggested feature
- Explain why this feature would be useful
- Provide examples of how it would be used

### Pull Requests 🔀

1. **Fork the repository**
   ```bash
   git clone https://github.com/farman20ali/port-killer.git
   cd port-killer
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Make your changes**
   - Write clear, commented code
   - Follow existing code style
   - Update documentation if needed

4. **Test your changes**
   ```bash
   # Test on your platform
   python kport.py -l
   python kport.py -i 8080
   # etc.
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add amazing feature"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/amazing-feature
   ```

7. **Open a Pull Request**
   - Provide clear description of changes
   - Reference related issues
   - Include screenshots if UI changes

## Development Setup

### Prerequisites
- Python 3.6 or higher
- Git

### Installation for Development
```bash
# Clone your fork
git clone https://github.com/farman20ali/port-killer.git
cd port-killer

# Install in editable mode
pip install --user -e .

# Run tests
python kport.py --version
python kport.py -h
```

## Code Style Guidelines

- Follow PEP 8 style guide
- Use meaningful variable and function names
- Add docstrings to functions
- Keep functions focused and small
- Comment complex logic
- Use type hints where appropriate

### Example:
```python
def find_pid(port: int) -> tuple:
    """
    Find process ID using given port
    
    Args:
        port: Port number to search for
        
    Returns:
        tuple: (pid, process_info) or (None, None) if not found
    """
    # Implementation
    pass
```

## Testing

### Manual Testing Checklist
- [ ] Test on Windows
- [ ] Test on Linux
- [ ] Test on macOS
- [ ] Test all command flags
- [ ] Test error handling
- [ ] Test edge cases (invalid ports, etc.)

### Areas That Need Tests
- Port validation
- Process detection
- Cross-platform compatibility
- Error handling
- Edge cases

## Documentation

When adding features, update:
- `README.md` - Main documentation
- `CHANGELOG.md` - Version history
- Docstrings in code
- Help text in argparse

## Release Process

(For maintainers)

1. Update version in `setup.py` and `kport.py`
2. Update `CHANGELOG.md`
3. Create git tag
4. Build and upload to PyPI
5. Create GitHub release

## Questions?

Feel free to:
- Open an issue for questions
- Start a discussion on GitHub
- Reach out to maintainers

## Code of Conduct

### Our Pledge
We pledge to make participation in our project a harassment-free experience for everyone.

### Our Standards
- Be respectful and inclusive
- Accept constructive criticism
- Focus on what's best for the community
- Show empathy towards others

### Enforcement
Unacceptable behavior can be reported to project maintainers.

---

Thank you for contributing! 🙏
