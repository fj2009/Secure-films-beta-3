# AGENTS.md

## Project overview
This repository contains a terminal-based secure file manager implemented in Python. The main entry point is `secure_file_manager.py`.

The tool provides:
- User and administrator management
- Encrypted file storage
- Permission-based access control
- CLI commands for init, add/remove users, encrypt/decrypt, authorization, and status reporting

## Key files
- `secure_file_manager.py`: Main application and CLI implementation
- `requirements.txt`: Python dependencies

## Development notes
- The project depends on `cryptography`.
- Keep the CLI interface backward-compatible when modifying commands.
- Preserve the current JSON storage format for users, files, and the master key.
- Avoid logging sensitive secrets or plaintext passwords.
- Prefer small, focused changes and validate them with the CLI after editing.

## Working conventions
- Use clear, descriptive names for new functions and variables.
- Keep error messages user-friendly and localized in Spanish where appropriate.
- When adding functionality, maintain consistency with the existing terminal UI styling helpers.
- If a change affects encryption or permissions, verify it with the relevant CLI commands.

## Verification
Before considering a change complete, run:
- `python secure_file_manager.py --help`

If you modify behavior related to storage or security, test the relevant commands against a temporary storage directory.
