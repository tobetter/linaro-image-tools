import os
import shutil
from StringIO import StringIO
import tempfile

from apt.cache import Cache
from apt.package import FetchError
import apt_pkg


def get_packages_file(packages, extra_text=None):
    """Get the Packages file contents indexing `packages`.

    :param packages: the packages to index.
    :type packages: an iterable of FetchedPackages.
    :param extra_text: extra text to insert in to each stanza.
         Should not end with a newline.
    :type extra_text: str or None
    :return: the Packages file contents indexing `packages`.
    :rtype: str
    """
    content = ""
    for package in packages:
        parts = []
        parts.append('Package: %s' % package.name)
        if extra_text is not None:
            parts.append(extra_text)
        parts.append('Version: %s' % package.version)
        parts.append('Filename: %s' % package.filename)
        parts.append('Size: %d' % package.size)
        parts.append('Architecture: %s' % package.architecture)
        if package.depends:
            parts.append('Depends: %s' % package.depends)
        if package.pre_depends:
            parts.append('Pre-Depends: %s' % package.pre_depends)
        if package.conflicts:
            parts.append('Conflicts: %s' % package.conflicts)
        if package.recommends:
            parts.append('Recommends: %s' % package.recommends)
        parts.append('MD5sum: %s' % package.md5)
        content += "\n".join(parts)
        content += "\n\n"
    return content


def stringify_relationship(pkg, relationship):
    """Given a Package, return a string of the specified relationship.

    apt.package.Version stores the relationship information of the
    package as objects. This function will convert those objects
    in to the string form that we are used to from debian/control
    or Packages files.

    :param pkg: the package to take the relationship information from.
    :type pkg: apt.package.Version
    :param relationship: the relationship to stringify, as understood
        by apt.package.Package.get_dependencies, e.g. "Depends",
        "PreDepends".
    :type relationship: str or None if the package has no relationships
         of that type.
    """
    relationship_str = None
    pkg_dependencies = pkg.get_dependencies(relationship)
    if pkg_dependencies:
        relationship_list = []
        for or_dep in pkg_dependencies:
            or_list = []
            for or_alternative in or_dep.or_dependencies:
                suffix = ""
                if or_alternative.relation:
                    suffix = " (%s %s)" % (
                        or_alternative.relation,
                        or_alternative.version)
                or_list.append("%s%s" % (or_alternative.name, suffix))
            relationship_list.append(" | ".join(or_list))
        relationship_str = ", ".join(relationship_list)
    return relationship_str


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
    :ivar depends: the Depends string that the package has, i.e. the
        dependencies as specified in debian/control. May be None if the
        package has none.
    :type depends: str or None
    :ivar pre_depends: the Pre-Depends string that the package has, i.e. the
        pre-dependencies as specified in debian/control. May be None if the
        package has none.
    :type pre_depends: str or None
    :ivar conflicts: the Conflicts string that the package has, i.e. the
        conflicts as specified in debian/control. May be None if the
        package has none.
    :type conflicts: str or None
    :ivar recommends: the Recommends string that the package has, i.e. the
        recommends as specified in debian/control. May be None if the
        package has none.
    :type recommends: str or None
    """

    def __init__(self, name, version, filename, content, size, md5,
                 architecture, depends=None, pre_depends=None,
                 conflicts=None, recommends=None):
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
        self.pre_depends = pre_depends
        self.conflicts = conflicts
        self.recommends = recommends

    @classmethod
    def from_apt(cls, pkg, filename, content):
        """Create a FetchedPackage from a python-apt Version (package).

        This is an alternative constructor for FetchedPackages that
        takes most of the information from an apt.package.Version
        object (i.e. a single version of a package), with some additional
        information supplied by tha caller.

        :param pkg: the python-apt package to take the information from.
        :type pkg: apt.package.Version instance
        :param filename: the filename that the package has.
        :type filename: str
        :param content: the content of the package.
        :type content: file-like object
        """
        depends = stringify_relationship(pkg, "Depends")
        pre_depends = stringify_relationship(pkg, "PreDepends")
        conflicts = stringify_relationship(pkg, "Conflicts")
        recommends = stringify_relationship(pkg, "Recommends")
        return cls(
            pkg.package.name, pkg.version, filename, content, pkg.size,
            pkg.md5, pkg.architecture, depends=depends,
            pre_depends=pre_depends, conflicts=conflicts,
            recommends=recommends)

    def __eq__(self, other):
        return (self.name == other.name
                and self.version == other.version
                and self.filename == other.filename
                and self.content.read() == other.content.read()
                and self.size == other.size
                and self.md5 == other.md5
                and self.architecture == other.architecture
                and self.depends == other.depends
                and self.pre_depends == other.pre_depends
                and self.conflicts == other.conflicts
                and self.recommends == other.recommends)

    def __hash__(self):
        return hash(
            (self.name, self.version, self.filename, self.size, self.md5,
             self.depends))

    def __repr__(self):
        return (
            '<%s name=%s version=%s size=%s md5=%s architecture=%s '
            'depends="%s" pre_depends="%s" conflicts="%s" recommends="%s">'
            % (self.__class__.__name__, self.name, self.version, self.size,
                self.md5, self.architecture, self.depends, self.pre_depends,
                self.conflicts, self.recommends))


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
        dirs = ["var/lib/dpkg",
                "etc/apt/",
                "var/cache/apt/archives/partial",
                "var/lib/apt/lists/partial",
               ]
        for d in dirs:
            os.makedirs(os.path.join(self.tempdir, d))
        self.set_installed_packages([], reopen=False)
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

    def set_installed_packages(self, packages, reopen=True):
        with open(
            os.path.join(self.tempdir, "var/lib/dpkg/status"), "w") as f:
            f.write(
                get_packages_file(
                    packages, extra_text="Status: install ok installed"))
        if reopen:
            self.cache.open()

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


class DependencyNotSatisfied(Exception):
    pass


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

    def ignore_packages(self, packages):
        for package in packages:
            self.cache.cache[package].mark_install(auto_fix=False)
            if self.cache.cache.broken_count:
                raise DependencyNotSatisfied(
                    "Unable to satisfy dependencies of %s" %
                    ", ".join([p.name for p in self.cache.cache
                        if p.is_inst_broken]))
        installed = []
        for package in self.cache.cache.get_changes():
            candidate = package.candidate
            base = os.path.basename(candidate.filename)
            installed.append(
                FetchedPackage.from_apt(
                    candidate, base, StringIO()))
        self.cache.set_installed_packages(installed)

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
            self.cache.cache[package].mark_install(auto_fix=False)
            if self.cache.cache.broken_count:
                raise DependencyNotSatisfied(
                    "Unable to satisfy dependencies of %s" %
                    ", ".join([p.name for p in self.cache.cache
                        if p.is_inst_broken]))
        acq = apt_pkg.Acquire(DummyProgress())
        acqfiles = []
        for package in self.cache.cache.get_changes():
            candidate = package.candidate
            base = os.path.basename(candidate.filename)
            destfile = os.path.join(self.cache.tempdir, base)
            acqfile = apt_pkg.AcquireFile(
                acq, candidate.uri, candidate.md5, candidate.size,
                base, destfile=destfile)
            acqfiles.append((acqfile, candidate, base, destfile))
        acq.run()
        for acqfile, candidate, base, destfile in acqfiles:
            if acqfile.status != acqfile.STAT_DONE:
                raise FetchError(
                    "The item %r could not be fetched: %s" %
                    (acqfile.destfile, acqfile.error_text))
            result_package = FetchedPackage.from_apt(
                candidate, base, open(destfile))
            results.append(result_package)
        return results
