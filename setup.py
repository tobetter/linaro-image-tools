#!/usr/bin/env python

from distutils.core import setup
import os
import subprocess

setup(
        name="linaro-image-tools",
        version="0.4.1.1",
        packages=["hwpack", "linaro_media_create"],
     )
