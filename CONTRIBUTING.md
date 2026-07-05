# Contributing to SONLab FRET Tool

Thank you for considering contributing to the SONLab FRET Tool! We appreciate your interest in helping us improve this software.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)
- [Code Style and Standards](#code-style-and-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [License](#license)

## Code of Conduct

This project and everyone participating in it are governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report any unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
   ```bash
   git clone https://github.com/sonlab-metu/SONLab-FRET-Tool.git
   cd SONLab-FRET-Tool
   ```
3. Set up your development environment (see below)
4. Create a new branch for your changes
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Environment Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

### Setup Steps

#### Windows
1. Clone the repository
2. Run the setup script:
   ```powershell
   .\installers\windows_installer.ps1
   ```
   This will set up a virtual environment and install all dependencies.

#### macOS/Linux
1. Clone the repository
2. Make the installer executable:
   ```bash
   chmod +x installers/install_*.sh
   ```
3. Run the appropriate installer:
   ```bash
   # For macOS
   ./installers/install_mac.sh
   
   # For Linux
   ./installers/install_linux.sh
   ```

## Making Changes

1. Make your changes in the appropriate files
2. Run tests (see [Testing](#testing))
3. Update documentation as needed
4. Commit your changes with a descriptive message:
   ```bash
   git commit -m "Brief description of changes"
   ```
5. Push your changes to your fork:
   ```bash
   git push origin your-branch-name
   ```

## Pull Request Process

1. Ensure all tests pass
2. Update the README.md with details of changes if needed
3. Submit a pull request to the `main` branch
4. Address any code review feedback
5. Once approved, your changes will be merged

## Reporting Bugs

Bugs are tracked as [GitHub Issues](https://github.com/sonlab-metu/SONLab-FRET-Tool/issues). When creating a bug report, please include:

- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs. actual behavior
- Screenshots if applicable
- Your operating system and Python version
- Any error messages received

## Feature Requests

Feature requests are welcome! Please open an issue to discuss your idea before implementing it. Include:

- The problem you're trying to solve
- Why this feature is important
- Any alternative solutions you've considered

## Code Style and Standards

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code
- Use descriptive variable and function names
- Include docstrings for all public functions and classes
- Keep functions small and focused on a single task
- Write unit tests for new functionality

## Testing

Before submitting changes, please ensure all tests pass:

```bash
# Will be added later
```

## Documentation

Good documentation is crucial. Please ensure that:

- All public APIs are documented with docstrings
- New features include usage examples
- The README is updated if needed
- Any new dependencies are documented

## License

By contributing to this project, you agree that your contributions will be licensed under the [project's LICENSE](LICENSE).

## Getting Help

If you need help or have questions, please open an issue on GitHub or contact the maintainers.

---

Thank you for contributing to the SONLab FRET Tool! Your help is greatly appreciated.
