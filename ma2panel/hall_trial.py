"""Identify the supervised LUMA Windows trial package."""
from pathlib import Path

ENABLED = Path(__file__).with_name("HALL_TRIAL").is_file()
