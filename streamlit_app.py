"""Entry point for the chat interface:  streamlit run streamlit_app.py

It lives at the repo root so that the root is on sys.path and the interface can
import from src/. The interface itself is in src/ui/app.py.
"""

from src.ui.app import main

main()
