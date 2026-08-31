"""Dedicated Streamlit Community Cloud entry point.

Keeping this entry point separate lets the Python 3.11 deployment coexist
with the historical deployment while both execute the same reviewed app.
"""

from app import *  # noqa: F401,F403
