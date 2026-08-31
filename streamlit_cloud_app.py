"""Dedicated Streamlit Community Cloud entry point.

Keeping this entry point separate lets the Python 3.11 deployment coexist
with the historical deployment while both execute the same reviewed app.
The reviewed ``app.py`` is executed as ``__main__`` so its name cannot shadow
the ``src/app`` package used by the read-only data adapter.
"""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
