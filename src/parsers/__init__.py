"""
Parsers package for job scraping from different websites.
"""

from .linkedin import extract_linkedin
from .generic import extract_generic

__all__ = ['extract_linkedin', 'extract_generic']