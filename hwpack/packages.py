import os
import shutil
import tempfile

from apt.cache import Cache

from bzrlib.transport import get_transport
from bzrlib import urlutils


class PackageFetcher(object):

    def __init__(self, sources):
        self.tempdir = tempfile.mkdtemp(prefix="hwpack-apt-cache-")
        files = ["var/lib/dpkg/status",
                ]
        dirs = ["var/lib/dpkg",
                "etc/apt/",
                "var/cache/apt/archives/partial",
                "var/lib/apt/lists/partial",
               ]
        for d in dirs:
            os.makedirs(os.path.join(self.tempdir, d))
        for fn in files:
            with open(os.path.join(self.tempdir, fn), 'w'):
                pass
        sources_list = os.path.join(
            self.tempdir, "etc", "apt", "sources.list")
        with open(sources_list, 'w') as f:
            for source in sources:
                f.write("deb %s\n" % source)
        self.cache = Cache(rootdir=self.tempdir, memonly=True)
        self.cache.update()
        self.cache.open()

    def cleanup(self):
        shutil.rmtree(self.tempdir)

    def fetch_packages(self, packages):
        results = {}
        possible_transports = []
        for package in packages:
            apt_pkg = self.cache[package]
            candidate = apt_pkg.candidate
            base = os.path.basename(candidate.filename)
            dir_url = urlutils.dirname(candidate.uri)
            if dir_url.startswith("file:/") and dir_url[len("file:/")] != '/':
                dir_url = "file:///" + dir_url[len("file:/"):]
            results[base] = get_transport(
                dir_url,
                possible_transports=possible_transports).get(base)
        return results
