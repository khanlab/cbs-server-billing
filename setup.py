"""Build script for cbsserverbilling."""

import setuptools

setuptools.setup(
    name="cbsserverbilling",
    version="1.0.0",
    author="Tristan Kuehn",
    author_email="tkuehn@uwo.ca",
    description="A script to generate CBS Server bills.",
    url="https://github.com/tkkuehn/cbs-server-billing",
    packages=setuptools.find_packages(),
    package_data={
        "cbsserverbilling": ["templates/cbs_server_bill.tex.jinja"]
    },
    install_requires=[
        "pandas",
        "xlrd",
        "Jinja2"])
