#!/usr/bin/env python

# https://launchpad.net/python-distutils-extra
import DistUtilsExtra.auto

DistUtilsExtra.auto.setup(
        name="linaro-image-tools",
        version="0.4.3.1",
        description="Tools to create and write Linaro images",
        url="https://launchpad.net/linaro-image-tools",
        license="GPL v3 or later",
        author='Linaro Infrastructure team',
        author_email="linaro-dev@lists.linaro.org",

        scripts=[
            "linaro-hwpack-create", "linaro-hwpack-install",
            "linaro-media-create"],
     )
