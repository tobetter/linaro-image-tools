#!/usr/bin/env python
# Copyright (C) 2010, 2011 Linaro
#
# Author: James Tunnicliffe <james.tunnicliffe@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import os
import sys
import re
import urllib2
import argparse
import sqlite3
import yaml
import urlparse
import logging
import bz2
import time
import shutil
import datetime
import threading
import subprocess
import BeautifulSoup
import utils


class DownloadManager():
    def __init__(self, cachedir):
        self.cachedir           = cachedir
        self.image_url          = None
        self.hwpack_url         = None
        self.settings           = None
        self.event_queue        = None
        self.to_download        = None
        self.sha1_files         = None
        self.gpg_files          = None
        self.downloaded_files   = None
        self.sig_files          = None
        self.verified_files     = None
        self.gpg_sig_ok         = None
        self.have_sha1sums      = None
        self.have_gpg_sigs      = None

    def name_and_path_from_url(self, url):
        """Return the file name and the path at which the file will be stored
        on the local system based on the URL we are downloading from"""
        # Use urlparse to get rid of everything but the host and path
        scheme, host, path, params, query, fragment = urlparse.urlparse(url)

        url_search = re.search(r"^(.*)/(.*?)$", host + path)
        assert url_search, "URL in unexpectd format" + host + path

        # Everything in url_search.group(1) should be directories and the
        # server name and url_search.group(2) the file name
        file_path = self.cachedir + os.sep + url_search.group(1)
        file_name = url_search.group(2)

        return file_name, file_path

    def urllib2_open(self, url):
        maxtries = 10
        for trycount in range(0, maxtries):
            try:
                response = urllib2.urlopen(url)
            except:
                if trycount < maxtries - 1:
                    print "Unable to connect to", url, "retrying in 5 seconds..."
                    time.sleep(5)
                    continue
                else:
                    print "Connect failed:", url
                    raise
                    return None
            else:
                return response

        return None

    def list_files_in_dir_of_url(self, url):
        """
        return a directory listing of the directory that url sits in
        """

        url = os.path.dirname(url)
        response = self.urllib2_open(url)
        page = response.read()

        dir = []
        # Use BeautifulSoup to parse the HTML and iterate over all 'a' tags
        soup = BeautifulSoup.BeautifulSoup(page)
        for link in soup.findAll('a'):
            for attr, value in link.attrs:
                if(    attr == "href"
                   and not re.search(r'[\?=;/]', value)):
                    # Ignore links that don't look like plain files
                    dir.append('/'.join([url, value]))

        return dir

    def sha1sum_file_download_list(self):
        """
        Need more than just the hwpack and OS image if we want signature
        verification to work, we need sha1sums, signatures for sha1sums
        and manifest files.

        Note that this code is a bit sloppy and may result in downloading
        more sums than are strictly required, but the
        files are small and the wrong files won't be used.
        """

        downloads_list = []

        # Get list of files in OS image directory
        image_dir  = self.list_files_in_dir_of_url(self.image_url)
        hwpack_dir = self.list_files_in_dir_of_url(self.hwpack_url)

        for link in image_dir:
            if re.search("sha1sums\.txt$", link):
                downloads_list.append(link)

        for link in hwpack_dir:
            if(    re.search(self.settings['hwpack'], link)
               and re.search("sha1sums\.txt$", link)):
                downloads_list.append(link)

        return downloads_list

    def generate_download_list(self):
        """
        Generate a list of files based on what is in the sums files that
        we have downloaded. We may have downloaded some sig files based on
        a rather sloppy file name match that we don't want to use. For the
        hwpack sig files, check to see if the hwpack listed matches the hwpack
        URL. If it doesn't ignore it.

        1. Download sig file(s) that match the hardware spec (done by this
           point).
        2. Find which sig file really matches the hardware pack we have
           downloaded. (this function calculates this list)
        3. Download all the files listed in the sig file (done by another func)
        
        We go through this process because sometimes a directory will have
        more than one hardware pack that will match the hardware pack name,
        for example panda and panda-x11 will both match "panda". These checks
        make sure we only try and validate the signatures of the files that
        we should be downloading and not try and validatate a signature of a
        file that there is no reason for us to download, which would result in
        an an invalid warning about installing unsigned packages when running
        linaro-media-create.
        """

        downloads_list = [self.image_url, self.hwpack_url]

        for sha1sum_file_name in self.sha1_files.values():
            sha1sum_file = open(sha1sum_file_name)

            common_prefix = None

            files = []
            for line in sha1sum_file:
                line = line.split()    # line[1] is now the file name

                if line[1] == os.path.basename(self.image_url):
                    # Found a line that matches an image or hwpack URL - keep
                    # the contents of this sig file
                    common_prefix = os.path.dirname(self.image_url)

                if line[1] == os.path.basename(self.hwpack_url):
                    # Found a line that matches an image or hwpack URL - keep
                    # the contents of this sig file
                    common_prefix = os.path.dirname(self.hwpack_url)

            if common_prefix:
                for file_name in files:
                    downloads_list.append('/'.join([common_prefix,
                                                    file_name]))

                dir = self.list_files_in_dir_of_url(common_prefix + '/')

                # We include the sha1sum files that pointed to the files that
                # we are going to download so the full file list can be parsed
                # later. The files won't be re-downloaded because they will be
                # cached.
                file_name = os.path.basename(sha1sum_file_name)
                downloads_list.append('/'.join([common_prefix, file_name]))
                signed_sums = os.path.basename(sha1sum_file_name) + ".asc"

                for link in dir:
                    if re.search(signed_sums, link):
                        downloads_list.append(link)

            sha1sum_file.close()

        return downloads_list

    def download_files(self,
                       downloads_list,
                       settings,
                       event_queue=None,
                       force_download=False):
        """
        Download files specified in the downloads_list, which is a list of
        url, name tuples.
        """

        force_download = settings["force_download"] or force_download

        downloaded_files = {}

        bytes_to_download = 0

        for url in downloads_list:
            file_name, file_path = self.name_and_path_from_url(url)

            file_name = file_path + os.sep + file_name
            if os.path.exists(file_name) and not force_download:
                continue  # If file already exists, don't download it

            response = self.urllib2_open(url)
            if response:
                bytes_to_download += int(response.info()
                                          .getheader('Content-Length').strip())
                response.close()

        if event_queue:
            event_queue.put(("start", "download"))
            event_queue.put(("update",
                             "download",
                             "total bytes",
                             bytes_to_download))

        for url in downloads_list:
            path = None
            try:
                path = self.download(url,
                                     event_queue,
                                     force_download)
            except Exception:
                # Download error. Hardly matters what, we can't continue.
                print "Unexpected error:", sys.exc_info()[0]
                logging.error("Unable to download " + url + " - aborting.")

            if path == None:  # User hit cancel when downloading
                sys.exit(0)

            downloaded_files[url] = path
            logging.info("Have downloaded {0} to {1}".format(url, path))

        if event_queue:
            event_queue.put(("end", "download"))

        return downloaded_files

    def download(self,
                 url,
                 event_queue,
                 force_download=False):
        """Downloads the file requested buy URL to the local cache and returns
        the full path to the downloaded file"""

        file_name, file_path = self.name_and_path_from_url(url)
        file_name = file_path + os.sep + file_name

        if not os.path.isdir(file_path):
            os.makedirs(file_path)

        if force_download != True and os.path.exists(file_name):
            logging.info(file_name + " already cached. Not downloading (use "
                                     "--force-download to override).")
            return file_name

        logging.info("Fetching " + url)

        response = self.urllib2_open(url)

        self.do_download = True
        file_out = open(file_name, 'w')
        download_size_in_bytes = int(response.info()
                                     .getheader('Content-Length').strip())
        chunks_downloaded = 0

        show_progress = download_size_in_bytes > 1024 * 200

        if show_progress:
            chunk_size = download_size_in_bytes / 1000
            if not event_queue:
                print "Fetching", url
        else:
            chunk_size = download_size_in_bytes

        printed_progress = False
        while self.do_download:
            chunk = response.read(chunk_size)
            if len(chunk):
                # Print a % download complete so we don't get too bored
                if show_progress:
                    if event_queue:
                        event_queue.put(("update",
                                         "download",
                                         "progress",
                                         len(chunk)))
                    else:
                        # Have 1000 chunks so div by 10 to get %...
                        sys.stdout.write("\r%d%%" % (chunks_downloaded / 10))
                        printed_progress = True
                sys.stdout.flush()

                file_out.write(chunk)
                chunks_downloaded += 1

            else:
                if printed_progress:
                    print ""
                break

        file_out.close()

        if self.do_download == False:
            os.remove(file_name)
            return None

        return file_name

    def download_if_old(self, url, event_queue, force_download):
        file_name, file_path = self.name_and_path_from_url(url)

        file_path_and_name = file_path + os.sep + file_name

        if(not os.path.isdir(file_path)):
            os.makedirs(file_path)
        try:
            force_download = (force_download == True
                              or (    time.mktime(time.localtime())
                                    - os.path.getmtime(file_path_and_name)
                                  > 60 * 60))
        except OSError:
            force_download = True  # File not found...

        return self.download(url, event_queue, force_download)

    def get_sig_files(self):
        """
        Find sha1sum.txt files in downloaded_files, append ".asc" and return
        list.

        The reason for not just searching for .asc files is because if they
        don't exist, utils.verify_file_integrity(sig_files) won't check the
        sha1sums that do exist, and they are useful to us. Trying to check
        a GPG signature that doesn't exist just results in the signature check
        failing, which is correct and we act accordingly.
        """

        self.sig_files = []

        for filename in self.downloaded_files.values():
            if re.search(r"sha1sums\.txt$", filename):
                self.sig_files.append(filename + ".asc")

    def _download_sigs_gen_download_list(self, force_download=False):

        to_download = self.sha1sum_file_download_list()
        self.sha1_files = self.download_files(
                            to_download, self.settings, self.event_queue,
                            force_download=force_download)

        self.to_download = self.generate_download_list()

        gpg_urls = [f for f in self.to_download if re.search('\.asc$', f)]
        gpg_files = self.download_files(gpg_urls, self.settings,
                                        force_download=force_download)

    def _check_downloads(self):
        self.get_sig_files()

        self.verified_files, self.gpg_sig_ok = utils.verify_file_integrity(
                                                            self.sig_files)

        # Expect to have 2 sha1sum files (one for hwpack, one for OS bin)
        self.have_sha1sums = len(self.sha1_files) ==2

        # We expect 2 GPG signatures. Check that we have both of them.

        self.have_gpg_sigs = (len(self.sig_files) == 2 and
                              os.path.exists(self.sig_files[0]) and
                              os.path.exists(self.sig_files[1]))

    def _unverified_files(self):
        """
        Return a list of URLs of files that didn't get verified
        """
        verified_files = self.verified_files

        unverified_files = []
        for sig_file in self.sig_files:
            name = os.path.basename(sig_file)
            verified_files.append(name)
            verified_files.append(name[0:-len('.asc')])
        
        # Generate a list of files that didn't verify
        for url in self.to_download:
            url_file = os.path.basename(url)
            if url_file not in verified_files:
                unverified_files.append(url)

        return unverified_files

    def download_files_and_verify(self, image_url, hwpack_url,
                                  settings, event_queue=None):

        self.image_url      = image_url
        self.hwpack_url     = hwpack_url
        self.settings       = settings
        self.event_queue    = event_queue

        self._download_sigs_gen_download_list()

        self.downloaded_files = self.download_files(self.to_download,
                                                    self.settings,
                                                    self.event_queue)

        self._check_downloads()

        if(self.have_sha1sums and self.have_gpg_sigs
           and not self.gpg_sig_ok):
            # GPG signatures failed for sha1sum files. Re-download the
            # sha1sums and GPG signatues. If the GPG signature then
            # matches the sha1sums we will re-download any failing hwpack
            # and OS binary files in the if below.

            self._download_sigs_gen_download_list(force_download=True)
            self._check_downloads()

        if self.have_sha1sums and self.gpg_sig_ok:
            # The GPG signature is OK, so the sha1sums file and GPG sig are
            # both good. 

            to_retry = self._unverified_files()

            if len(to_retry):
                if self.event_queue:
                    self.event_queue.put(("message", "Retrying bad files"))
                else:
                    print "Re-downloading corrupt files"
                # There are some files to re-download
                redownloaded_files = self.download_files(
                                           to_retry, self.settings,
                                           self.event_queue,
                                           force_download=True)

                (self.verified_files,
                 self.gpg_sig_ok) = utils.verify_file_integrity(self.sig_files)

                to_retry = self._unverified_files()

                if len(to_retry):
                    # We have a good GPG signature and can't get valid
                    # package downloads. Either the sha1sums file was
                    # incorrectly generated or the download is corrupt.
                    # Display a message to the user and quit.
                    message = "Download retry failed. Aborting"
                    if self.event_queue:
                        self.event_queue.put("message", message)
                        self.event_queue.put("abort")
                    else:
                        print >> sys.stderr, message

                    return [], False

        hwpack = os.path.basename(self.downloaded_files[hwpack_url])
        hwpack_verified = (hwpack in self.verified_files) and self.gpg_sig_ok

        if self.event_queue:  # Clear messages, if any, from GUI
            self.event_queue.put(("message", ""))

        return self.downloaded_files, hwpack_verified


class FileHandler():
    """Downloads files and creates images from them by calling
    linaro-media-create"""
    def __init__(self):
        import xdg.BaseDirectory as xdgBaseDir
        self.homedir = os.path.join(xdgBaseDir.xdg_config_home,
                                     "linaro",
                                     "image-tools",
                                     "fetch_image")

        self.cachedir = os.path.join(xdgBaseDir.xdg_cache_home,
                                     "linaro",
                                     "image-tools",
                                     "fetch_image")

        self.downloader = DownloadManager(self.cachedir)

    def has_key_and_evaluates_True(self, dictionary, key):
        return bool(key in dictionary and dictionary[key])

    def append_setting_to(self, list, dictionary, key, setting_name=None):
        if not setting_name:
            setting_name = "--" + key

        if self.has_key_and_evaluates_True(dictionary, key):
            list.append(setting_name)
            list.append(dictionary[key])

    def build_lmc_command(self,
                          binary_file,
                          hwpack_file,
                          settings,
                          tools_dir,
                          hwpack_verified,
                          run_in_gui=False):

        import linaro_image_tools.utils

        args = ["pkexec"]

        # Prefer a local linaro-media-create (from a bzr checkout for instance)
        # to an installed one
        lmc_command = linaro_image_tools.utils.find_command(
                                                    'linaro-media-create',
                                                    tools_dir)

        if lmc_command:
            args.append(os.path.abspath(lmc_command))
        else:
            args.append("linaro-media-create")

        if run_in_gui:
            args.append("--nocheck-mmc")

        if hwpack_verified:
            # We verify the hwpack before calling linaro-media-create because
            # these tools run linaro-media-create as root and to get the GPG
            # signature verification to work, root would need to have GPG set
            # up with the Canonical Linaro Image Build Automatic Signing Key
            # imported. It seems far more likely that users will import keys
            # as themselves, not root!
            args.append("--hwpack-force-yes")

        if 'rootfs' in settings and settings['rootfs']:
            args.append("--rootfs")
            args.append(settings['rootfs'])

        assert(self.has_key_and_evaluates_True(settings, 'image_file') ^
               self.has_key_and_evaluates_True(settings, 'mmc')), ("Please "
               "specify either an image file, or an mmc target, not both.")

        self.append_setting_to(args, settings, 'mmc')
        self.append_setting_to(args, settings, 'image_file')
        self.append_setting_to(args, settings, 'swap_size')
        self.append_setting_to(args, settings, 'swap_file')
        self.append_setting_to(args, settings, 'yes_to_mmc_selection',
                                               '--nocheck_mmc')

        args.append("--dev")
        args.append(settings['hardware'])
        args.append("--binary")
        args.append(binary_file)
        args.append("--hwpack")
        args.append(hwpack_file)

        logging.info(" ".join(args))

        return args

    def create_media(self, image_url, hwpack_url, settings, tools_dir):
        """Create a command line for linaro-media-create based on the settings
        provided then run linaro-media-create, either in a separate thread
        (GUI mode) or in the current one (CLI mode)."""

        downloaded_files, hwpack_verified = (
            self.downloader.download_files_and_verify(image_url, hwpack_url,
                                                      settings))

        if len(downloaded_files) == 0:
            return

        lmc_command = self.build_lmc_command(downloaded_files[image_url],
                                             downloaded_files[hwpack_url],
                                             settings,
                                             tools_dir,
                                             hwpack_verified)

        self.create_process = subprocess.Popen(lmc_command)
        self.create_process.wait()

    class LinaroMediaCreate(threading.Thread):
        """Thread class for running linaro-media-create"""
        def __init__(self,
                     image_url,
                     hwpack_url,
                     file_handler,
                     event_queue,
                     settings,
                     tools_dir):

            threading.Thread.__init__(self)

            self.image_url      = image_url
            self.hwpack_url     = hwpack_url
            self.file_handler   = file_handler
            self.downloader     = file_handler.downloader
            self.event_queue    = event_queue
            self.settings       = settings
            self.tools_dir      = tools_dir

        def run(self):
            """
            1. Download required files.
            2. Build linaro-media-create command
            3. Start linaro-media-create and look for lines in the output that:
               1. Tell us that an event has happened that we can use to update
                  the UI progress.
               2. Tell us that linaro-media-create is asking a question that
                  needs to be re-directed to the GUI
            """

            self.event_queue.put(("update",
                                  "download",
                                  "message",
                                  "Downloading"))

            files, hwpack_ok = self.downloader.download_files_and_verify(
                                self.image_url, self.hwpack_url,
                                self.settings, self.event_queue)

            if len(files) == 0:
                return

            lmc_command = self.file_handler.build_lmc_command(
                                            files[self.image_url],
                                            files[self.hwpack_url],
                                            self.settings,
                                            self.tools_dir,
                                            hwpack_ok,
                                            True)

            self.create_process = subprocess.Popen(lmc_command,
                                                   stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE,
                                                   stderr=subprocess.STDOUT)

            self.line                       = ""
            self.saved_lines                = ""
            self.save_lines                 = False
            self.state                      = None
            self.waiting_for_event_response = False
            self.event_queue.put(("start", "unpack"))

            while(1):
                if self.create_process.poll() != None:   # linaro-media-create
                                                         # has finished.
                    self.event_queue.put(("terminate"))  # Tell the GUI
                    return                               # Terminate the thread

                self.input = self.create_process.stdout.read(1)

                # We build up lines by extracting data from linaro-media-create
                # a single character at a time. This is because if we fetch
                # whole lines, using Popen.communicate a character is
                # automatically sent back to the running process, which if the
                # process is waiting for user input, can trigger a default
                # action. By using stdout.read(1) we pick off a character at a
                # time and avoid this problem.
                if self.input == '\n':
                    if self.save_lines:
                        self.saved_lines += self.line

                    self.line = ""
                else:
                    self.line += self.input

                if self.line == "Updating apt package lists ...":
                    self.event_queue.put(("end", "unpack"))
                    self.event_queue.put(("start", "installing packages"))
                    self.state = "apt"

                elif(self.line ==
                     "WARNING: The following packages cannot be authenticated!"):
                    self.saved_lines = ""
                    self.save_lines = True

                elif(self.line ==
                     "Install these packages without verification [y/N]? "):
                    self.saved_lines = re.sub("WARNING: The following packages"
                                              " cannot be authenticated!",
                                              "", self.saved_lines)
                    self.event_queue.put(("start",
                                          "unverified_packages:"
                                          + self.saved_lines))
                    self.line = ""
                    self.waiting_for_event_response = True  # Wait for restart

                elif self.line == "Do you want to continue [Y/n]? ":
                    self.send_to_create_process("y")
                    self.line = ""

                elif self.line == "Done" and self.state == "apt":
                    self.state = "create file system"
                    self.event_queue.put(("end", "installing packages"))
                    self.event_queue.put(("start", "create file system"))

                elif(    self.line == "Created:"
                     and self.state == "create file system"):
                    self.event_queue.put(("end", "create file system"))
                    self.event_queue.put(("start", "populate file system"))
                    self.state = "populate file system"

                while self.waiting_for_event_response:
                    time.sleep(0.2)

        def send_to_create_process(self, text):
            print >> self.create_process.stdin, text
            self.waiting_for_event_response = False


    def update_files_from_server(self, force_download=False,
                                 event_queue=None):

        settings_url     = "http://releases.linaro.org/fetch_image/fetch_image_settings.yaml"
        server_index_url = "http://releases.linaro.org/fetch_image/server_index.bz2"

        self.settings_file = self.downloader.download_if_old(settings_url,
                                                             event_queue,
                                                             force_download)

        self.index_file = self.downloader.download_if_old(server_index_url,
                                                          event_queue,
                                                          force_download)

        zip_search = re.search(r"^(.*)\.bz2$", self.index_file)

        if zip_search:
            # index file is compressed, unzip it
            zipped = bz2.BZ2File(self.index_file)
            unzipped = open(zip_search.group(1), "w")

            unzipped.write(zipped.read())

            zipped.close()
            unzipped.close()

            self.index_file = zip_search.group(1)

    def clean_cache(self):
        shutil.rmtree(self.cachedir)


class FetchImageConfig():
    """Reads settings from the settings YAML file as well as those from the
       command line providing a central settings repository."""

    def __init__(self):
        self.settings = {}

    def read_config(self, file_name):
        try:
            f = open(file_name, "r")

            if(f):
                self.settings = dict(self.settings.items() +
                                     yaml.load(f.read()).items())

        except IOError:
            print "Unable to read settings file %s", file_name
            logging.error("Unable to read settings file %s", file_name)
            sys.exit(0)

        self.settings['write_to_file_or_device'] = "file"

        # At this point, assume settings have been loaded.
        # We need some reverse mappings set up
        self.settings['UI']['reverse-descriptions'] = {}
        for (key, value) in self.settings['UI']['descriptions'].items():
            if isinstance(value, basestring):
                value = re.sub('LEB:\s*', '', value)
                self.settings['UI']['reverse-descriptions'][value] = key

        self.settings['UI']['reverse-translate'] = {}
        for (key, value) in self.settings['UI']['translate'].items():
            self.settings['UI']['reverse-translate'][value] = key

    def parse_args(self, args):
        parser = argparse.ArgumentParser(description="Create a board image, "
                                         "first downloading any required "
                                         "files.")

        for (key, value) in self.settings['choice'].items():
            parser.add_argument(
                       "-" + self.settings['UI']['cmdline short names'][key],
                       "--" + key,
                       help=self.settings['UI']['descriptions']['choice'][key],
                       required=True)

        parser.add_argument("-x", "--clean-cache",
                            help="Delete all cached downloads",
                            action='store_true')
        parser.add_argument("-d", "--force-download",
                            help="Force re-downloading of cached files",
                            action='store_true')
        parser.add_argument(
                    "-t", "--image-file",
                    help="Where to write image file to (use this XOR mmc)")
        parser.add_argument(
                  "-m", "--mmc",
                  help="What disk to write image to (use this XOR image-file)")
        parser.add_argument("--swap-file",
                            help="Swap file size for created image")
        parser.add_argument("--image-size",
                            help="Image file size for created image")
        parser.add_argument("--rootfs",
                            help="Root file system type for created image")

        self.args = vars(parser.parse_args(args))


class DB():
    """Interacts with the database storing URLs of files that are available
       for download to create images with. Provides functions for both creation
       and reading."""

    def __init__(self, index_name):
        # http://www.sqlite.org/lang_transaction.html - defer acquiring a locK
        # until it is required.
        self.db_file_name = index_name
        self.database = sqlite3.connect(index_name, isolation_level="DEFERRED")
        self.c = self.database.cursor()
        self.touched_urls = {}

    def close(self):
        self.database.close()
        self.database = None

    def set_url_parse_info(self, url_parse):
        self.url_parse = url_parse

    def record_url(self, url, table):
        """Check to see if the record exists in the index, if not, add it"""

        assert self.url_parse[table]["base_url"] != None, ("Can not match the "
               "URL received (%s) to an entry provided by add_url_parse_list",
               url)
        assert re.search('^' + self.url_parse[table]["base_url"], url)

        if(not re.search(self.url_parse[table]["url_validator"], url)):
            #Make sure that the URL matches the validator
            return

        logging.info("Recording URL", url)

        assert url not in self.touched_urls, ("URLs expected to only be added "
                                              "to 1 place\n" + url)

        self.touched_urls[url] = True

        # Do not add the record if it already exists
        self.c.execute("select url from " + table + " where url == ?", (url,))
        if(self.c.fetchone()):
            return

        url_match = re.search(self.url_parse[table]["base_url"] + r"(.*)$",
                              url)
        url_chunks = url_match.group(1).lstrip('/').encode('ascii').split('/')
        # url_chunks now contains all parts of the url, split on /,
        # not including the base URL

        # We now construct an SQL command to insert the index data into the
        # database using the information we have.

        # Work out how many values we will insert into the database
        length = 0
        for name in self.url_parse[table]["url_chunks"]:
            if(name != ""):
                length += 1

        sqlcmd = "insert into " + table + " values ("

        # Add the appropriate number of ?s (+1 is so we have room for url)
        sqlcmd += "".join(["?, " for x in range(length + 1)])
        sqlcmd = sqlcmd.rstrip(" ")  # get rid of unwanted space
        sqlcmd = sqlcmd.rstrip(",")  # get rid of unwanted comma
        sqlcmd += ")"

        # Get the parameters from the URL to record in the SQL database
        sqlparams = []
        chunk_index = 0
        for name in self.url_parse[table]["url_chunks"]:
            # If this part of the URL isn't a parameter, don't insert it
            if(name != ""):
                # If the entry is a tuple, it indicates it is of the form
                # name, regexp
                if(isinstance(name, tuple)):
                    # use stored regexp to extract data for the database
                    match = re.search(name[1], url_chunks[chunk_index])
                    assert match, ("Unable to match regexp to string ",
                                  + url_chunks[chunk_index] + " " + name[1])
                    sqlparams.append(match.group(1))

                else:
                    sqlparams.append(url_chunks[chunk_index])

            chunk_index += 1

        sqlparams.append(url)

        self.c.execute(sqlcmd, tuple(sqlparams))

    def commit(self):
        self.database.commit()

    def __del__(self):
        if(self.database):
            self.commit()
            self.database.close()

    def create_table_with_url_text_items(self, table, items):
        cmd = "create table if not exists "
        cmd += table + " ("

        for item in items:
            cmd += item + " TEXT, "

        cmd += "url TEXT)"

        self.execute(cmd)

    def execute(self, cmd, params=None):
        self.c = self.database.cursor()
        logging.info(cmd)
        if(params):
            logging.info(params)
            self.c.execute(cmd, params)
        else:
            self.c.execute(cmd)

    def execute_return_list(self, cmd, params=None):
        self.execute(cmd, params)
        list = []
        item = self.c.fetchone()
        while item:
            list.append(item)
            item = self.c.fetchone()

        return list

    def delete_by_url(self, table, url):
        self.execute("delete from " + table + " where url == ?", (url,))

    def clean_removed_urls_from_db(self):
        self.c = self.database.cursor()

        for table, info in self.url_parse.items():
            self.c.execute("select url from " + table)
            to_delete = []

            while(1):
                url = self.c.fetchone()
                if(url == None):
                    break

                if(url[0] not in self.touched_urls):
                    to_delete.append(url[0])

            # We can't delete an item from the database while iterating on the
            # results of a previous query, so we store the URLs of entries to
            # delete, and batch them up
            for url in to_delete:
                self.delete_by_url(table, url)

        self.commit()

    def get_url(self, table, key_value_pairs, sql_extras=None):
        """Return the first matching URL from the specified table building up a
        SQL query based on the values inkey_value_pairs creating key == value
        sections of the query. sql_extras is appended to the created SQL query,
         so we can get the first entry in an ordered list for instance"""
        self.c = self.database.cursor()

        cmd = "select url from " + table + " where "
        params = []

        first = True
        for key, value in key_value_pairs:
            if(first == False):
                cmd += " AND "
            else:
                first = False

            cmd += key + " == ? "
            params.append(value)

        if(sql_extras):
            cmd += " " + sql_extras

        self.c.execute(cmd, tuple(params))
        url = self.c.fetchone()

        return url

    def get_platforms(self, table):
        self.execute("select distinct platform from ?", table)

        platforms = []
        platform = self.c.fetchone()

        while(platform):
            platforms.append(platform)
            platform = self.c.fetchone()

        return platforms

    def get_builds(self, platform, image=None):
        """return a complete list of builds available from the releases
        repository"""

        build_tuples = self.execute_return_list(
                                'select distinct build from release_binaries '
                                'where platform == "' + platform + '"')
        hwpack_build_tuples = self.execute_return_list(
                                   'select distinct build from release_hwpacks'
                                   ' where platform == "' + platform + '"')

        # Need to also check hwpacks and image -> some builds are only
        # Available for a particular image (OS). Guess this makes sense as OS
        # customisations may come and go.

        image_builds = [build[0] for build in build_tuples]
        hwpack_builds = [build[0] for build in hwpack_build_tuples]

        builds = []
        for build in image_builds:
            if build in hwpack_builds:
                # Only use a build if it exists for the hardware pack as well
                # as the image and platform chosen
                builds.append(build)

        builds.sort()

        # Just so final is always the last item, if it exists...
        if "final" in builds:
            builds.remove("final")
            builds.append("final")

        return builds

    def get_hwpacks(self, table, platform=None):
        """Return a list of all the hardware packs available in the specified
        table"""

        query = 'select distinct hardware from ' + table
        if platform:
            query += ' where platform == "' + platform + '"'

        results = self.execute_return_list(query)

        hwpacks = [item[0] for item in results]
        return hwpacks

    def get_dates_and_builds_of_snapshots(self):
        """Return all the dates that match an an OS and hardware pack build"""
        # First get all dates from hwpack table
        self.execute("select distinct date from snapshot_hwpacks "
                     "order by date")

        date_with_hwpack = {}
        date = self.c.fetchone()

        while date:
            date_with_hwpack[date] = 1
            date = self.c.fetchone()

        # Now make sure there is a file system image for that date as well
        self.execute("select distinct date from snapshot_binaries "
                     "order by date")

        date = self.c.fetchone()
        while date:
            if date in date_with_hwpack:
                date_with_hwpack[date] = 2
            date = self.c.fetchone()

        # Now anything with both a hwpack and a file system has a value of 2
        # recorded in date_with_hwpack[date]
        date_with_build = {}

        for key, date in date_with_hwpack.items():
            if(key == 2):
                date_with_build[date] = True

        return date_with_build

    def get_hardware_from_db(self, table):
        """Get a list of hardware available from the given table"""
        self.execute("select distinct hardware from " + table +
                     " order by hardware")

        hardware = []
        hw = self.c.fetchone()
        while hw:
            hardware.append(hw[0])
            hw = self.c.fetchone()

        return hardware

    def image_hardware_combo_available(self,
                                       release_or_snapshot,
                                       image,
                                       hwpacks):
        """Try and find a matching plaform, build pair for both the provided
        image and one of the hwpacks in the list."""
        binary_table = release_or_snapshot + "_binaries"
        hwpack_table = release_or_snapshot + "_hwpacks"

        binary_list = self.execute_return_list(
                            'select distinct platform, build from '
                             + binary_table + ' where image == ?', (image,))

        for hwpack in hwpacks:
            hwpack_list = self.execute_return_list(
                                'select distinct platform, build from '
                                + hwpack_table +
                                ' where hardware == ?', (hwpack,))

            for item in binary_list:
                if item in hwpack_list:
                    return True

        return False

    def hardware_is_available_in_table(self, table, hardware):
        return len(self.execute_return_list(
                    'select url from ' + table +
                    ' where hardware == ?', (hardware,))) > 0

    def hardware_is_available_for_platform(self,
                                           hardware_list,
                                           platform,
                                           table="release_hwpacks"):

        for hardware in self.execute_return_list(
                              'select distinct hardware from ' + table +
                              ' where platform == ?', (platform,)):
            if hardware[0] in hardware_list:
                return True

        return False

    def get_available_hwpacks_for_hardware_build_plaform(self,
                                                         hardware_list,
                                                         platform,
                                                         build):
        hwpacks = []
        for hardware in self.execute_return_list(
                             'select distinct hardware from release_hwpacks '
                             'where platform == ? and build == ?',
                             (platform, build)):

            if hardware[0] in hardware_list:
                hwpacks.append(hardware[0])

        return hwpacks

    def image_is_available_for_platform(self,
                                        table,
                                        platform,
                                        image):

        return len(self.execute_return_list(
                        'select * from ' + table +
                        ' where platform == ? and image == ?',
                        (platform, image))) > 0

    def hardware_is_available_for_platform_build(self,
                                                 hardware_list,
                                                 platform,
                                                 build):

        for hardware in self.execute_return_list(
                             'select distinct hardware from release_hwpacks '
                             'where platform == ? and build == ?',
                              (platform, build)):

            if hardware[0] in hardware_list:
                return True

        return False

    def build_is_available_for_platform_image(self,
                                              table,
                                              platform,
                                              image,
                                              build):

        return len(self.execute_return_list(
                        'select * from ' + table +
                        ' where platform == ? and image == ? and build == ?',
                        (platform, image, build))) > 0

    def get_available_hwpacks_for_hardware_snapshot_build(self,
                                                          hardware_list,
                                                          platform,
                                                          date,
                                                          build):
        hwpacks = []
        for hardware in self.execute_return_list(
                             'select distinct hardware from snapshot_hwpacks '
                             'where platform == ? '
                             'and   date == ? '
                             'and   build == ?',
                              (platform, date, build)):
            if hardware[0] in hardware_list:
                hwpacks.append(hardware[0])

        return hwpacks

    def get_binary_builds_on_day_from_db(self, image, date, hwpacks):
        """Return a list of build numbers that are available on the given date
        for the given image ensuring that the reqiested hardware is also
        available."""

        # Remove the dashes from the date we get in (YYYY-MM-DD --> YYYYMMDD)
        date = re.sub('-', '', date)

        binaries = self.execute_return_list(
                        "select build from snapshot_binaries "
                        "where date == ? and image == ?",
                        (date, image))

        if len(binaries) == 0:
            # Try adding "linaro-" to the beginning of the image name
            binaries = self.execute_return_list(
                            "select build from snapshot_binaries "
                            "where date == ? and image == ?",
                            (date, "linaro-" + image))

        for hwpack in hwpacks:
            builds = self.execute_return_list(
                           "select build from snapshot_hwpacks "
                           "where date == ? and hardware == ?",
                           (date, hwpack))

            if len(builds):
                # A hardware pack exists for that date, return a list of builds
                # that exist for both hwpack and binary
                ret = []
                for build in builds:
                    if build in binaries:
                        ret.append(build)
                return ret

        # No hardware pack exists for the date requested, return empty table
        return []

    def get_next_prev_day_with_builds(self, image, date, hwpacks):
        """Searches forwards and backwards in the database for a date with a
        build. Will look 1 year in each direction. Returns a tuple of dates
        in YYYYMMDD format."""

        # Split ISO date into year, month, day
        date_chunks = date.split('-')

        current_date = datetime.date(int(date_chunks[0]),
                                     int(date_chunks[1]),
                                     int(date_chunks[2]))

        one_day = datetime.timedelta(days=1)

        # In case of time zone issues we add 1 day to max_search_date
        max_search_date = datetime.date.today() + one_day

        day_count = 0
        # Look in the future & past from the given date until we find a day
        # with a build on it

        test_date = {'future': current_date,
                      'past':   current_date}

        for in_the in ["future", "past"]:
            test_date[in_the] = None

            if in_the == "future":
                loop_date_increment = one_day
            else:
                loop_date_increment = -one_day

            test_date[in_the] = current_date

            while test_date[in_the] <= max_search_date:
                test_date[in_the] += loop_date_increment

                builds = []
                for hwpack in hwpacks:
                    builds = self.get_binary_builds_on_day_from_db(
                                    image,
                                    test_date[in_the].isoformat(),
                                    [hwpack])
                    if len(builds):
                        break

                if len(builds):
                    break

                day_count += 1
                if day_count > 365:
                    test_date[in_the] = None
                    break

            if test_date[in_the] and test_date[in_the] > max_search_date:
                test_date[in_the] = None

            if test_date[in_the]:
                test_date[in_the] = test_date[in_the].isoformat()

        return(test_date['future'], test_date['past'])

    def get_os_list_from(self, table):
        return [item[0] for item in self.execute_return_list(
                                        "select distinct image from "
                                         + table)]

    def get_image_and_hwpack_urls(self, args):
        """ We need a platform image and a hardware pack. These are specified
            either as
            Release:
                Image: platform, image, build
                HW Pack: platform, build, hardware
            Snapshot:
                Image: platform, image, date, build
                HW Pack: platform, hardware, date, build"""
        image_url = None
        hwpack_url = None

        if(args['release_or_snapshot'] == "snapshot"):
            count = 0
            while(1):  # Just so we can try several times...
                if(args['build'] == "latest"):
                    # Start from today, add 1 day because
                    # get_next_prev_day_with_builds aways searches from the
                    # day passed to it, not including that day. This will give
                    # us the latest build dated today or earlier with both
                    # a hwpack and OS binary
                    date = (datetime.date.today() +
                            datetime.timedelta(days=1)).isoformat()

                    _, past_date = self.get_next_prev_day_with_builds(
                                           args['image'],
                                           date,
                                           [args['hwpack']])

                    builds = self.get_binary_builds_on_day_from_db(
                                    args['image'], past_date, [args['hwpack']])
                    
                    # Work out latest build
                    build = None
                    for b in builds:
                        if build == None or b[0] > build:
                            build = b[0]
                        
                    # We store dates in the DB in ISO format with the dashes
                    # missing
                    date = re.sub('-', '', past_date)

                    image_url = self.get_url("snapshot_binaries",
                                    [
                                     ("image", args['image']),
                                     ("build", build),
                                     ("date", date)])

                    hwpack_url = self.get_url("snapshot_hwpacks",
                                    [
                                     ("hardware", args['hwpack']),
                                     ("build", build),
                                     ("date", date)])

                else:
                    build_bits = args['build'].split(":")
                    assert re.search("^\d+$", build_bits[0]), (
                            "Unexpected date format in build parameter "
                            + build_bits[0])
                    assert re.search("^\d+$", build_bits[1]), (
                            "Build number in shapshot build parameter should "
                            "be an integer " + build_bits[1])

                    image_url = self.get_url("snapshot_binaries",
                                    [
                                     ("image", args['image']),
                                     ("build", build_bits[1]),
                                     ("date", build_bits[0])])

                    hwpack_url = self.get_url("snapshot_hwpacks",
                                    [
                                     ("hardware", args['hwpack']),
                                     ("build", build_bits[1]),
                                     ("date", build_bits[0])])

                if(count == 1):
                    break
                count += 1

                if(image_url == None):
                    # If we didn't match anything, try prepending "linaro-"
                    # to the image name
                    args['image'] = "linaro-" + args['image']
                else:
                    break  # Got a URL, go.

        else:
            image_url = self.get_url("release_binaries",
                            [
                             ("image", args['image']),
                             ("build", args['build']),
                             ("platform", args['platform'])])

            hwpack_url = self.get_url("release_hwpacks",
                            [
                             ("hardware", args['hwpack']),
                             ("build", args['build']),
                             ("platform", args['platform'])])

        if(not image_url):
            # If didn't get an image URL set up something so the return line
            # doesn't crash
            image_url = [None]

        if(not hwpack_url):
            # If didn't get a hardware pack URL set up something so the return
            # line doesn't crash
            hwpack_url = [None]

        return(image_url[0], hwpack_url[0])
