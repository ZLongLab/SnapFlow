"""Minimal temporary directory fixture for capture, long-capture, video, and startup tests."""
import shutil
import tempfile
import unittest
from pathlib import Path


class TempFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='capture-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
