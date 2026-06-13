#!/usr/bin/env python3
"""Setup script for kport - Cross-platform port inspector and killer"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kport",
    version="3.2.0",
    author="Farman Ali",
    author_email="alienhub.dev@gmail.com",
    description="A cross-platform command-line tool to inspect and kill processes using specific ports",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/farman20ali/port-killer",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Networking",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: GNU Affero General Public License v3",
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
    python_requires=">=3.8",
    install_requires=[],  # zero mandatory deps; psutil optional via [psutil] extra
    entry_points={
        "console_scripts": [
            "kport=kport.cli:main",
        ],
    },
    keywords="port, kill, process, network, cross-platform, cli",
    project_urls={
        "Bug Reports": "https://github.com/farman20ali/port-killer/issues",
        "Source": "https://github.com/farman20ali/port-killer",
    },
)
