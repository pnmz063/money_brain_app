"""Mock psycopg2 so tests can run without a real database."""
import sys
from unittest.mock import MagicMock

# Create a fake psycopg2 module so all imports succeed
mock_psycopg2 = MagicMock()
mock_psycopg2.extras = MagicMock()
mock_psycopg2.extras.RealDictCursor = MagicMock()
sys.modules["psycopg2"] = mock_psycopg2
sys.modules["psycopg2.extras"] = mock_psycopg2.extras
