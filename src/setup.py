#!/usr/bin/env python

import time

from setuptools import setup
#from distutils.core import setup

r = 1
v = time.strftime("%Y%m%d%H%M")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="casino",
    packages=["casino"],
#    py_modules=["casino", "libcasino"],
    requires=["ttyio5", "bbsengine5"],
    scripts=["bin/casino"],
    version=v,
    author="zoidtechnologies.com",
    author_email="casino@projects.zoidtechnologies.com",
    description="Casino games for bbsengine5",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jonez734/casino",
    project_urls={
        "Bug Tracker": "https://github.com/jonez734/casino/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
#        "License :: OSI Approved :: MIT License",
    ],
#    package_dir={"": "blackjack"},
#    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.9",
)
