#!/usr/bin/env python

# https://launchpad.net/python-distutils-extra
import DistUtilsExtra.auto
from linaro_image_tools.__version__ import __version__


DistUtilsExtra.auto.setup(
    name="linaro-image-tools",
    version=__version__,
    description="Tools to create and write Linaro images",
    url="https://launchpad.net/linaro-image-tools",
    license="GPL v3 or later",
    author='Linaro Infrastructure team',
    author_email="linaro-dev@lists.linaro.org",

    scripts=[
        "initrd-do",
        "linaro-hwpack-create", "linaro-hwpack-install",
        "linaro-media-create", "linaro-android-media-create",
        "linaro-hwpack-replace"],
)
