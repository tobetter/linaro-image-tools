import hashlib
import os
import re
import shutil
from string import Template
import subprocess
import tempfile

from apt.cache import Cache
from apt.package import FetchError
import apt_pkg

from debian.debfile import DebFile


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
        if package.provides:
            parts.append('Provides: %s' % package.provides)
        if package.replaces:
            parts.append('Replaces: %s' % package.replaces)
        if package.breaks:
            parts.append('Breaks: %s' % package.breaks)
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
                    relation = or_alternative.relation
                    if relation in ('<', '>'):
                        # The choice made here by python-apt is to report the
                        # relationship in a Python spelling; as far as apt
                        # knows, < is a deprecated spelling of <=; << is the
                        # spelling of "strictly less than".  Similarly for >.
                        relation *= 2
                    suffix = " (%s %s)" % (relation, or_alternative.version)
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


class PackageMaker(object):
    """An object that can create binary debs on the fly.

    PackageMakers implement the context manager protocol to manage the
    temporary directories the debs are created in.
    """

    def __init__(self):
        self._temporary_directories = None

    def __enter__(self):
        if self._temporary_directories is not None:
            raise AssertionError("__enter__ must not be called twice")
        self._temporary_directories = []
        return self

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        if self._temporary_directories is None:
            return
        for tmpdir in self._temporary_directories:
            shutil.rmtree(tmpdir)
        self._temporary_directories = None
        return False

    def make_temporary_directory(self):
        """Create a temporary directory and return its path.

        The created directory will be deleted on __exit__.
        """
        if self._temporary_directories is None:
            raise AssertionError("__enter__ must be called")
        tmpdir = tempfile.mkdtemp()
        self._temporary_directories.append(tmpdir)
        return tmpdir

    # This template (and the code that uses it) is made more awkward by the
    # fact that blank lines are invalid in control files -- so in particular
    # when there are no relationships, there must be no blank line between the
    # Maintainer and the Description.
    control_file_template = Template('''\
Package: ${name}
Version: ${version}
Architecture: ${architecture}
Maintainer: Nobody
${relationships}\
Description: Dummy package to install a hwpack
 This package was created automatically by linaro-media-create
''')

    def make_package(self, name, version, relationships, architecture='all'):
        tmp_dir = self.make_temporary_directory()
        filename = '%s_%s_%s' % (name, version, architecture)
        packaging_dir = os.path.join(tmp_dir, filename)
        os.mkdir(packaging_dir)
        os.mkdir(os.path.join(packaging_dir, 'DEBIAN'))
        relationship_strs = []
        for relationship_name, relationship_value in relationships.items():
            relationship_strs.append(
                '%s: %s\n' % (relationship_name, relationship_value))
        subst_vars = dict(
            architecture=architecture,
            name=name,
            relationships=''.join(relationship_strs),
            version=version,
            )
        control_file_text = self.control_file_template.safe_substitute(
            subst_vars)
        with open(os.path.join(
            packaging_dir, 'DEBIAN', 'control'), 'w') as control_file:
            control_file.write(control_file_text)
        proc = subprocess.Popen(
            ['dpkg-deb', '-b', packaging_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdoutdata, stderrdata) = proc.communicate()
        if proc.returncode:
            raise ValueError("dpkg-deb failed!\n%s" % stderrdata)
        if stderrdata:
            raise ValueError("dpkg-deb had warnings:\n%s" % stderrdata)
        deb_file_path_match = re.match(
            "dpkg-deb: building package `.*' in `(.*)'", stdoutdata)
        if not deb_file_path_match:
            raise ValueError(
                "failed to find filename in dpkg-deb output:\n%s"
                % stdoutdata)
        return deb_file_path_match.group(1)


class FetchedPackage(object):
    """The result of fetching packages.

    :ivar name: the name of the fetched package.
    :type name: str
    :ivar version: the version of the fetched package.
    :type version: str
    :ivar filename: the filename that the package has.
    :type filename: str
    :ivar content: a file that the content of the package can be read from,
        or None if the content is not known.
    :type content: a file-like object or None
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
    :ivar provides: the Provides string that the package has, i.e. the
        provides as specified in debian/control. May be None if the
        package has none.
    :type provides: str or None
    :ivar replaces: the Replaces string that the package has, i.e. the
        replaces as specified in debian/control. May be None if the
        package has none.
    :type replaces: str or None
    :ivar breaks: the Breaks string that the package has, i.e. the
        breaks as specified in debian/control. May be None if the
        package has none.
    :type breaks: str or None
    """

    def __init__(self, name, version, filename, size, md5,
                 architecture, depends=None, pre_depends=None,
                 conflicts=None, recommends=None, provides=None,
                 replaces=None, breaks=None):
        """Create a FetchedPackage.

        See the instance variables for the arguments.
        """
        self.name = name
        self.version = version
        self.filename = filename
        self.size = size
        self.md5 = md5
        self.architecture = architecture
        self.depends = depends
        self.pre_depends = pre_depends
        self.conflicts = conflicts
        self.recommends = recommends
        self.provides = provides
        self.replaces = replaces
        self.breaks = breaks
        self.content = None

    @classmethod
    def from_apt(cls, pkg, filename, content=None):
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
        replaces = stringify_relationship(pkg, "Replaces")
        breaks = stringify_relationship(pkg, "Breaks")
        provides = ", ".join([a[0] for a in pkg._cand.provides_list]) or None
        pkg = cls(
            pkg.package.name, pkg.version, filename, pkg.size,
            pkg.md5, pkg.architecture, depends=depends,
            pre_depends=pre_depends, conflicts=conflicts,
            recommends=recommends, provides=provides, replaces=replaces,
            breaks=breaks)
        if content is not None:
            pkg.content = content
        return pkg

    @classmethod
    def from_deb(cls, deb_file_path):
        """Create a FetchedPackage from a binary package on disk."""
        debcontrol = DebFile(deb_file_path).control.debcontrol()
        name = debcontrol['Package']
        version = debcontrol['Version']
        filename = os.path.basename(deb_file_path)
        size = os.path.getsize(deb_file_path)
        md5sum = hashlib.md5(open(deb_file_path).read()).hexdigest()
        architecture = debcontrol['Architecture']
        depends = debcontrol.get('Depends')
        pre_depends = debcontrol.get('Pre-Depends')
        conflicts = debcontrol.get('Conflicts')
        recommends = debcontrol.get('Recommends')
        provides = debcontrol.get('Provides')
        replaces = debcontrol.get('Replaces')
        breaks = debcontrol.get('Breaks')
        pkg = cls(
            name, version, filename, size, md5sum, architecture, depends,
            pre_depends, conflicts, recommends, provides, replaces, breaks)
        pkg.content = open(deb_file_path)
        return pkg

    # A list of attributes that are compared to determine equality.  Note that
    # we don't include the contents here -- we assume that comparing the md5
    # checksum is enough (more philosophically, FetchedPackages are equal if
    # they represent the same underlying package, even if they represent it in
    # slightly different ways)
    _equality_attributes = (
        'name',
        'version',
        'filename',
        'size',
        'md5',
        'architecture',
        'depends',
        'pre_depends',
        'conflicts',
        'recommends',
        'provides',
        'replaces',
        'breaks')

    @property
    def _equality_data(self):
        return tuple(
            getattr(self, attr) for attr in self._equality_attributes)

    def __eq__(self, other):
        return self._equality_data == other._equality_data

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._equality_data)

    def __repr__(self):
        has_content = self.content and "yes" or "no"
        return (
            '<%s name=%s version=%s size=%s md5=%s architecture=%s '
            'depends="%s" pre_depends="%s" conflicts="%s" recommends="%s" '
            'provides="%s" replaces="%s" breaks="%s" has_content=%s>'
            % (self.__class__.__name__, self.name, self.version, self.size,
                self.md5, self.architecture, self.depends, self.pre_depends,
                self.conflicts, self.recommends, self.provides,
                self.replaces, self.breaks, has_content))


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
                f.write(
                    'Apt {\nArchitecture "%s";\n'
                    'Install-Recommends "true";\n}\n' % self.architecture)
        self.cache = Cache(rootdir=self.tempdir, memonly=True)
        self.cache.update()
        self.cache.open()
        return self

    def set_installed_packages(self, packages, reopen=True):
        """Set a list of packages as those installed on the system.

        This does no installing, just changes dpkg's database to have
        the tools think the packages are installed.

        :param packages: a list of packages to "install" on the system,
            replacing any others.
        :type packages: an iterable of FetchedPackages.
        :param reopen: whether to reopen the apt cache after doing the
            operation. Default is to do so. Note that if it is not done,
            then the changes will not be visible in the cache until it
            is reopened.
        """
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
        """Ignore packages such that they will not be fetched.

        If a package is ignored then neither it or any of its recursive
        dependencies will be fetched by fetch_packages.

        :param packages: the list of package names to ignore.
        :type packages: an iterable of str
        """
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
            installed.append(FetchedPackage.from_apt(candidate, base))
        for package in self.cache.cache:
            if not package.isInstalled:
                continue
            candidate = package.installed
            base = os.path.basename(candidate.filename)
            installed.append(FetchedPackage.from_apt(candidate, base))
        self.cache.set_installed_packages(installed)
        broken = [p.name for p in self.cache.cache
                if p.is_inst_broken or p.is_now_broken]
        if broken:
            # If this happens then there is a bug, as we should have
            # caught this problem earlier
            raise AssertionError(
                "Weirdly unable to satisfy dependencies of %s" %
                ", ".join(broken))

    def _filter_ignored(self, package_dict):
        seen_packages = set()
        for package in self.cache.cache.get_changes():
            if package.name in package_dict:
                seen_packages.add(package.name)
        all_packages = set(package_dict.keys())
        for unseen_package in all_packages.difference(seen_packages):
            del package_dict[unseen_package]

    def fetch_packages(self, packages, download_content=True):
        """Fetch the files for the given list of package names.

        The files, and all their dependencies are download, and the metadata
        and content returned as FetchedPackage objects.

        If download_content is False then only the metadata is returned
        (i.e. the FetchedPackages will have None for their content
         attribute), and only information about the specified packages
        will be returned, no dependencies.

        No packages that have been ignored, or are recursive dependencies
        of ignored packages will be returned.

        :param packages: a list of package names to install
        :type packages: an iterable of str
        :param download_content: whether to download the content of the
            packages. Default is to do so.
        :type download_content: bool
        :return: a list of the packages that were fetched, with relevant
            metdata and the contents of the files available.
        :rtype: an iterable of FetchedPackages.
        :raises KeyError: if any of the package names in the list couldn't
            be found.
        """
        fetched = {}
        for package in packages:
            candidate = self.cache.cache[package].candidate
            base = os.path.basename(candidate.filename)
            result_package = FetchedPackage.from_apt(candidate, base)
            fetched[package] = result_package
        for package in packages:
            self.cache.cache[package].mark_install(auto_fix=False)
            if self.cache.cache.broken_count:
                raise DependencyNotSatisfied(
                    "Unable to satisfy dependencies of %s" %
                    ", ".join([p.name for p in self.cache.cache
                        if p.is_inst_broken]))
        self._filter_ignored(fetched)
        if not download_content:
            return fetched.values()
        acq = apt_pkg.Acquire(DummyProgress())
        acqfiles = []
        for package in self.cache.cache.get_changes():
            candidate = package.candidate
            base = os.path.basename(candidate.filename)
            if package.name not in fetched:
                result_package = FetchedPackage.from_apt(candidate, base)
                fetched[package.name] = result_package
            result_package = fetched[package.name]
            destfile = os.path.join(self.cache.tempdir, base)
            acqfile = apt_pkg.AcquireFile(
                acq, candidate.uri, candidate.md5, candidate.size,
                base, destfile=destfile)
            acqfiles.append((acqfile, result_package, destfile))
        self.cache.cache.clear()
        acq.run()
        for acqfile, result_package, destfile in acqfiles:
            if acqfile.status != acqfile.STAT_DONE:
                raise FetchError(
                    "The item %r could not be fetched: %s" %
                    (acqfile.destfile, acqfile.error_text))
            result_package.content = open(destfile)
        return fetched.values()
