#!/usr/bin/env python

from distutils.core import setup
import os
import subprocess

setup(
        name="linaro-image-tools",
        version="0.4.1.1",
        description="Tools to create and write Linaro images",
        url="https://launchpad.net/linaro-image-tools",
        license="GPL v2 or later",
        author='Linaro Infrastructure team',
        author_email="linaro-dev@lists.linaro.org",

        packages=["hwpack", "linaro_media_create"],
        scripts=[
            "linaro-hwpack-create", "linaro-hwpack-install",
            "linaro-media-create"],
     )
