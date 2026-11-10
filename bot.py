#!/usr/bin/env python3
"""Compatibility entry point: starts the unified web panel and customer bot."""

import runpy

if __name__ == "__main__":
    runpy.run_module("app", run_name="__main__")
