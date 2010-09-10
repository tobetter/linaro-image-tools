import os
import shutil
import tempfile

from apt.cache import Cache
from apt.package import FetchError
import apt_pkg


def get_packages_file(packages):
    """Get the Packages file contents indexing `packages`.

    :param packages: the packages to index.
    :type packages: an iterable of FetchedPackages.
    :return: the Packages file contents indexing `packages`.
    :rtype: str
    """
    content = ""
    for package in packages:
        parts = []
        parts.append('Package: %s' % package.name)
        parts.append('Version: %s' % package.version)
        parts.append('Filename: %s' % package.filename)
        parts.append('Size: %d' % package.size)
        parts.append('Architecture: %s' % package.architecture)
        if package.depends:
            parts.append('Depends: %s' % package.depends)
        parts.append('MD5sum: %s' % package.md5)
        content += "\n".join(parts)
        content += "\n\n"
    return content


class DummyProgress(object):
    """An AcquireProgress that silences all output.

    This can be used to ensure that apt produces no output
    when fetching files.
    """

    def start(self):
        pass

    def ims_hit(self, item):
        pass

    def fail(self, item):
        pass

    def fetch(self, item):
        pass

    def pulse(self, owner):
        return True

    def media_change(self):
        return False

    def stop(self):
        pass


class FetchedPackage(object):
    """The result of fetching packages.

    :ivar name: the name of the fetched package.
    :type name: str
    :ivar version: the version of the fetched package.
    :type version: str
    :ivar filename: the filename that the package has.
    :type filename: str
    :ivar content: a file that the content of the package can be read from.
    :type content: a file-like object
    :ivar size: the size of the package
    :type size: int
    :ivar md5: the hex representation of the md5sum of the contents of
        the package.
    :type md5: str
    :ivar architecture: the architecture that the package is for, may be
        'all'.
    :type architecture: str
    :ivar depends: the depends string that the package has, i.e. the
        dependencies as specified in debian/control. May be None if the
        package has none.
    :type depends: str or None
    """

    def __init__(self, name, version, filename, content, size, md5,
                 architecture, depends=None):
        """Create a FetchedPackage.

        See the instance variables for the arguments.
        """
        self.name = name
        self.version = version
        self.filename = filename
        self.content = content
        self.size = size
        self.md5 = md5
        self.architecture = architecture
        self.depends = depends

    @classmethod
    def from_apt(cls, pkg, filename, content):
        depends = None
        pkg_dependencies = pkg.get_dependencies("Depends")
        if pkg_dependencies:
            depends_list = []
            for or_dep in pkg_dependencies:
                or_list = []
                for or_alternative in or_dep.or_dependencies:
                    suffix = ""
                    if or_alternative.relation:
                        suffix = " (%s %s)" % (
                            or_alternative.relation, or_alternative.version)
                    or_list.append("%s%s" % (or_alternative.name, suffix))
                depends_list.append(" | ".join(or_list))
            depends = ", ".join(depends_list)
        return cls(
            pkg.package.name, pkg.version, filename, content, pkg.size,
            pkg.md5, pkg.architecture, depends=depends)

    def __eq__(self, other):
        return (self.name == other.name
                and self.version == other.version
                and self.filename == other.filename
                and self.content.read() == other.content.read()
                and self.size == other.size
                and self.md5 == other.md5
                and self.architecture == other.architecture
                and self.depends == other.depends)

    def __hash__(self):
        return hash(
            (self.name, self.version, self.filename, self.size, self.md5,
             self.depends))

    def __repr__(self):
        return (
            '<%s name=%s version=%s size=%s md5=%s architecture=%s '
            'depends="%s">' % (self.__class__.__name__, self.name,
                self.version, self.size, self.md5, self.architecture,
                self.depends))


class IsolatedAptCache(object):
    """A apt.cache.Cache wrapper that isolates it from the system it runs on.

    :ivar cache: the isolated cache.
    :type cache: apt.cache.Cache
    """

    def __init__(self, sources, architecture=None):
        """Create an IsolatedAptCache.

        :param sources: a list of sources such that they can be prefixed
            with "deb " and fed to apt.
        :type sources: an iterable of str
        :param architecture: the architecture to fetch packages for.
        :type architecture: str
        """
        self.sources = sources
        self.architecture = architecture
        self.tempdir = None

    def prepare(self):
        """Prepare the IsolatedAptCache for use.

        Should be called before use, and after any modification to the list
        of sources.
        """
        self.cleanup()
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
            for source in self.sources:
                f.write("deb %s\n" % source)
        if self.architecture is not None:
            apt_conf = os.path.join(self.tempdir, "etc", "apt", "apt.conf")
            with open(apt_conf, 'w') as f:
                f.write('Apt {\nArchitecture "%s";\n}\n' % self.architecture)
        self.cache = Cache(rootdir=self.tempdir, memonly=True)
        self.cache.update()
        self.cache.open()
        return self

    __enter__ = prepare

    def cleanup(self):
        """Cleanup any remaining artefacts.

        Should be called on all IsolatedAptCache when they are finished
        with.
        """
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()
        return False


class PackageFetcher(object):
    """A class to fetch packages from a defined list of sources."""

    def __init__(self, sources, architecture=None):
        """Create a PackageFetcher.

        Once created a PackageFetcher should have its `prepare` method
        called before use.

        :param sources: a list of sources such that they can be prefixed
            with "deb " and fed to apt.
        :type sources: an iterable of str
        :param architecture: the architecture to fetch packages for.
        :type architecture: str
        """
        self.cache = IsolatedAptCache(sources, architecture=architecture)

    def prepare(self):
        """Prepare the PackageFetcher for use.

        Should be called before use.
        """
        self.cache.prepare()
        return self

    __enter__ = prepare

    def cleanup(self):
        """Cleanup any remaining artefacts.

        Should be called on all PackageFetchers when they are finished
        with.
        """
        self.cache.cleanup()

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()
        return False

    def fetch_packages(self, packages):
        """Fetch the files for the given list of package names.

        :param packages: a list of package names to install
        :type packages: an iterable of str
        :return: a list of the packages that were fetched, with relevant
            metdata and the contents of the files available.
        :rtype: an iterable of FetchedPackages.
        :raises KeyError: if any of the package names in the list couldn't
            be found.
        """
        results = []
        for package in packages:
            candidate = self.cache.cache[package].candidate
            base = os.path.basename(candidate.filename)
            destfile = os.path.join(self.cache.tempdir, base)
            acq = apt_pkg.Acquire(DummyProgress())
            acqfile = apt_pkg.AcquireFile(
                acq, candidate.uri, candidate.md5, candidate.size,
                base, destfile=destfile)
            acq.run()
            if acqfile.status != acqfile.STAT_DONE:
                raise FetchError(
                    "The item %r could not be fetched: %s" %
                    (acqfile.destfile, acqfile.error_text))
            result_package = FetchedPackage.from_apt(
                candidate, base, open(destfile))
            results.append(result_package)
        return results
