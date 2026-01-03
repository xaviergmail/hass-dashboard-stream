# Contributing to Dashboard Streams

Thank you for your interest in contributing to Dashboard Streams! This document provides guidelines for contributing to the project.

## Getting Started

### Development Environment

1. Clone the repository
2. Open in VS Code with the Dev Container extension
3. The devcontainer will set up a complete Home Assistant environment for testing

### Local Development

```bash
# Build the add-on locally
./scripts/build-local.sh

# Run locally (requires Docker)
./scripts/run-local.sh
```

### Testing with Home Assistant

The devcontainer includes a full Home Assistant instance at `http://localhost:7123`. The add-on will be available after building.

## Making Changes

### Code Style

- Python code should follow PEP 8
- Use meaningful variable names
- Add comments for complex logic
- Keep functions focused and small

### Commit Messages

Use clear, descriptive commit messages:

```
Add feature X for Y reason

- Detail about the change
- Another detail
```

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit your changes
6. Push to your fork
7. Open a Pull Request

### PR Guidelines

- Describe what the PR does and why
- Reference any related issues
- Include screenshots for UI changes
- Ensure the add-on builds and runs correctly

## Reporting Issues

### Bug Reports

Please include:
- Home Assistant version
- Add-on version
- Device/platform you're streaming to
- Steps to reproduce
- Add-on logs (with sensitive info redacted)

### Feature Requests

- Describe the feature and its use case
- Explain why it would benefit other users

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Feel free to open an issue for questions or discussions about the project.
