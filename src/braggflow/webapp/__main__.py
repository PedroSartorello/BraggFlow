"""
``python -m braggflow.webapp``: the same as the ``braggflow-web`` command.

On Windows, Smart App Control (or another application control policy) can
block ``braggflow-web.exe``, the launcher pip writes, because it is not
signed. ``python.exe`` is signed, so this way still starts the app.
"""

from .app import main

if __name__ == "__main__":
    main()
