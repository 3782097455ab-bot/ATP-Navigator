"""One-command entry point for the ATP-Navigator Phase 9 decision agent."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "src" / "research_decision_agent.py"
    runpy.run_path(str(script), run_name="__main__")
