#!/usr/bin/env python3
"""Setup script for kport - Cross-platform port inspector and killer"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kport",
    version="3.1.0",
    author="Farman Ali",
    author_email="farman20ali@gmail.com",
    description="A cross-platform command-line tool to inspect and kill processes using specific ports",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/farman20ali/port-killer",
    py_modules=["kport"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Networking",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
    ],
    python_requires=">=3.6",
    install_requires=[
        "psutil>=5.9.0",
    ],
    entry_points={
        "console_scripts": [
            "kport=kport:main",
        ],
    },
    keywords="port, kill, process, network, cross-platform, cli",
    project_urls={
        "Bug Reports": "https://github.com/farman20ali/port-killer/issues",
        "Source": "https://github.com/farman20ali/port-killer",
    },
)
