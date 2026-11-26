import os
import sys

# Let the tests import the project's modules (common, triage, ...) from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
