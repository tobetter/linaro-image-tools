from distutils.core import setup
import os
import subprocess


def get_version():
    proc = subprocess.Popen(
        ["dpkg-parsechangelog"],
        cwd=os.path.abspath(os.path.dirname(__file__)),
        stdout=subprocess.PIPE)
    output, _ = proc.communicate()
    version = None
    for line in output.split("\n"):
        if line.startswith("Version: "):
            version = line.split(" ", 1)[1].strip()
    assert version is not None, (
        "Couldn't determine version number from debian changelog")


setup(
        name="hwpack",
        version=get_version(),
        # XXX: Probably makes sense to rename media_create to
        # linaro_media_create.  Even though it's longer, it's way more
        # meaningful than just media_create.
        packages=["hwpack", "media_create"],
     )
