# Workspace Rules & Instructions

## Automatic Executable & Website Build Rule
- After completing any feature change, bug fix, or performance update in this repository, **ALWAYS automatically run tests (`python -m pytest tests/`) and compile the PyInstaller executable (`python -m PyInstaller -y UCC_Drawing_Review_Intelligence.spec`)** to keep `dist/UCC_Drawing_Review_Intelligence/UCC_Drawing_Review_Intelligence.exe` fully updated.
- The user should never have to manually ask to rebuild the EXE or update the executable package after code changes.
