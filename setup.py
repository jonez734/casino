#!/usr/bin/env python

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="casino",
    version="0.0.1",
    author="zoidtechnologies.com",
    author_email="casino@projects.zoidtechnologies.com",
    description="Casino games (blackjack, slots, etc) for bbsengine5",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jonez734/casino",
    project_urls={
        "Bug Tracker": "https://github.com/jonez734/casino/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
#    package_dir={"": "blackjack"},
#    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.9",
)
