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

import os, sys, re
import urllib2, time
import argparse
import sqlite3
import yaml
import urlparse
import logging
import bz2
import time

sys.setrecursionlimit(300)

class FileHandler():
    """Downloads files and creates images from them by calling linaro-media-create"""
    def __init__(self):
        import xdg.BaseDirectory as xdgBaseDir
        self.homedir = xdgBaseDir.xdg_config_home + os.sep + "fetch_image"
        self.cachedir = xdgBaseDir.xdg_cache_home + os.sep + "fetch_image"

    def create_media(self, image_url_, hwpack_url_, settings_):
        import cmd_runner
        
        args = ["linaro-media-create"]
        
        try:
            
            binary_file = self.download(image_url_, settings_["force_download"])
        except:
            # Something went wrong with downloading. Hardly matters what, we can't continue.
            logging.error("Unable to download " + image_url_ + " - aborting.")
            sys.exit(1)
            
        try:
            hwpack_file = self.download(hwpack_url_, settings_["force_download"])
        except:
            # Something went wrong with downloading. Hardly matters what, we can't continue.
            logging.error("Unable to download " + hwpack_url_ + " - aborting.")
            sys.exit(1)

        logging.info(binary_file, hwpack_file)

        if(settings_.has_key('rootfs') and settings_['rootfs']):
            args.append("--rootfs")
            args.append(settings_['rootfs'])

        assert bool(settings_.has_key('image_file') and settings_['image_file']) ^ bool(settings_.has_key('mmc') and settings_['mmc']), "Please specify either an image file, or an mmc target, not both."

        if(settings_.has_key('mmc') and settings_['mmc']):
            args.append("--mmc")
            args.append(settings_['mmc'])

        if(settings_.has_key('image_file') and settings_['image_file']):
            args.append("--image_file")
            args.append(settings_['image_file'])

        if(settings_.has_key('image_size') and settings_['image_size']):
            args.append("--image_size")
            args.append(settings_['image_size'])

        if(settings_.has_key('swap_file') and settings_['swap_file']):
            args.append("--swap_file")
            args.append(settings_['swap_file'])

        args.append("--dev")
        args.append(settings_['hardware'])
        args.append("--binary")
        args.append(binary_file)
        args.append("--hwpack")
        args.append(hwpack_file)

        logging.info(args)
        create_process = cmd_runner.Popen(args)
        create_process.wait()

    def name_and_path_from_url(self, url_):
        # Use urlparse to get rid of everything but the host and path
        scheme, host, path, params, query, fragment = urlparse.urlparse(url_)
        
        url_search = re.search(r"^(.*)/(.*?)$", host + path)
        assert url_search, "URL in unexpectd format" + host+path

        # Everything in url_search.group(1) should be directories and the server name and url_search.group(2) the file name
        file_path = self.cachedir + os.sep + url_search.group(1)
        file_name = file_path + os.sep + url_search.group(2)
        
        return file_name, file_path

    def download(self, url_, force_download_ = False):
        """Downloads the file requested buy URL to the local cache and returns the full path to the downloaded file"""

        file_name, file_path = self.name_and_path_from_url(url_)

        if(not os.path.isdir(file_path)):
            os.makedirs(file_path)

        if(force_download_ != True and os.path.exists(file_name)):
            logging.info(file_name + " already cached. Not downloading (use --force-download to override).")
            return file_name

        logging.info("Fetching", url_)

        maxtries = 10
        for trycount in range(0, maxtries):
            try:
                response = urllib2.urlopen(url_)
            except:
                if(trycount < maxtries - 1):
                    time.sleep(50)
                    continue
                else:
                    raise
                    return

        file_out = open(file_name, 'w')
        download_size_in_bytes = int(response.info().getheader('Content-Length').strip())
        chunks_downloaded = 0

        if download_size_in_bytes > 1024 * 200:
            chunk_size = download_size_in_bytes / 100
            print "Fetching", url_
        else:
            chunk_size = download_size_in_bytes

        printed_progress = False
        while(1):
            chunk = response.read(chunk_size)
            if(len(chunk)):
                # Print a % download complete so we don't get too bored
                if(chunk_size != download_size_in_bytes):
                    sys.stdout.write("\r%d%%" % chunks_downloaded)
                    printed_progress = True
                sys.stdout.flush()

                file_out.write(chunk)
                chunks_downloaded += 1

            else:
                if printed_progress:
                    print ""
                break

        file_out.close()
        
        return file_name
    
    def download_if_old(self, url_, force_download_):
        file_name, file_path = self.name_and_path_from_url(url_)
        
        if(not os.path.isdir(file_path)):
            os.makedirs(file_path)
        try:
            force_download = force_download_ == True or (time.clock() - os.path.getmtime(file_name) > 60 * 60 * 24)
        except OSError:
            force_download = True # File not found...
            
        
        return self.download(url_, force_download)
    
    def update_files_from_server(self, force_download_):
        
        settings_url      = "http://z.nanosheep.org/fetch_image_settings.yaml"
        server_index_url  = "http://z.nanosheep.org/server_index.bz2"
        
        self.settings_file = self.download_if_old(settings_url,     force_download_)
        self.index_file    = self.download_if_old(server_index_url, force_download_)
        
        zip_search = re.search(r"^(.*)\.bz2$", self.index_file)
        if(zip_search):
            # index file is compressed, unzip it
            zipped = bz2.BZ2File(self.index_file)
            unzipped = open(zip_search.group(1), "w")

            unzipped.write(zipped.read())
            
            zipped.close()
            unzipped.close()
            
            self.index_file = zip_search.group(1)

class Config():
    """AReads settings from the settings YAML file as well as those from the command
       line providing a central settings repository."""
    def read_config(self, file_name_):

        try:
            f = open(file_name_, "r")

            if(f):
                self.settings = yaml.load(f.read())

        except IOError:
            logging.error("Unable to read settings file %s", file_name_)
            sys.exit(0)

    def parse_args(self, args_):
        parser = argparse.ArgumentParser(description = "Create a board image, first downloading any required files.")

        for (key, value) in self.settings['choice'].items():
            parser.add_argument("-" + self.settings['UI']['cmdline short names'][key],
                                 "--" + key,
                                 help = self.settings['UI']['descriptions']['choice'][key],
                                 required = True)

        parser.add_argument("-x", "--clean-cache", help = "Delete all cached downloads", action = 'store_true')
        parser.add_argument("-d", "--force-download", help = "Force re-downloading of cached files", action = 'store_true')
        parser.add_argument("-t", "--image-file", help = "Where to write image file to (use this XOR mmc)")
        parser.add_argument("-m", "--mmc", help = "What disk to write image to (use this XOR image-file)")
        parser.add_argument("--swap-file", help = "Swap file size for created image")
        parser.add_argument("--image-size", help = "Image file size for created image")
        parser.add_argument("--rootfs", help = "Root file system type for created image")

        self.args = vars(parser.parse_args(args_))

class DB():
    """Interacts with the database storing URLs of files that are available for download
       to create images with. Provides functions for both creation and reading."""
    def __init__(self, index_name_):
        # http://www.sqlite.org/lang_transaction.html - defer aquiring a lock until it is required.
        self.db_file_name = index_name_
        self.database = sqlite3.connect(index_name_, isolation_level = "DEFERRED")
        self.c = self.database.cursor()
        self.touched_urls = {}

    def close(self):
        self.database.close()
        self.database = None

    def set_url_parse_info(self, url_parse_):
        self.url_parse = url_parse_

    def record_url(self, url_, table_):
        """Check to see if the record exists in the index, if not, add it"""

        assert self.url_parse[table_]["base_url"] != None, "Can not match the URL received (" + url_ + ") to an entry provided by add_url_parse_list"
        assert re.search('^' + self.url_parse[table_]["base_url"], url_)

        if(not re.search(self.url_parse[table_]["url_validator"], url_)): #Make sure that the URL matches the validator
            return

        assert url_ not in self.touched_urls, "URLs expected to only be added to 1 place\n" + url_

        self.touched_urls[url_] = 1

        # Do not add the record if it already exists
        self.c.execute("select url from " + table_ + " where url == ?", (url_,))
        if(self.c.fetchone()):
            return

        url_match = re.search(self.url_parse[table_]["base_url"] + r"(.*)$", url_)
        url_chunks = url_match.group(1).lstrip('/').encode('ascii').split('/')
        # url_chunks now contains all parts of the url, split on /, not including the base URL

        # We now construct an SQL command to insert the index data into the database using the information we have
        # Work out how many values we will insert into the database
        length = 0
        for name in self.url_parse[table_]["url_chunks"]:
            if(name != ""):
                length += 1

        sqlcmd = "insert into " + table_ + " values ("
        sqlcmd += "".join([ "?, " for x in range(length + 1) ]) # +1 is so we have room for url_
        sqlcmd = sqlcmd.rstrip(" ") # get rid of unwanted space
        sqlcmd = sqlcmd.rstrip(",") # get rid of unwanted comma
        sqlcmd += ")"

        # Get the parameters from the URL to record in the SQL database
        sqlparams = []
        chunk_index = 0
        for name in self.url_parse[table_]["url_chunks"]:
            if(name != ""): # If this part of the URL isn't a parameter, don't insert it
                if(isinstance(name, tuple)): # If the entry is a tuple, it indicates it is of the form name, regexp
                    match = re.search(name[1], url_chunks[chunk_index]) # use stored regexp to extract data for the database
                    assert match, "Unable to match regexp to string " + url_chunks[chunk_index] + " " + name[1]
                    sqlparams.append(match.group(1))

                else:
                    sqlparams.append(url_chunks[chunk_index])

            chunk_index += 1

        sqlparams.append(url_)

        self.c.execute(sqlcmd, tuple(sqlparams))

    def commit(self):
        self.database.commit()

    def __del__(self):
        if( self.database ):
            self.commit()
            self.database.close()
        
    def create_table_with_url_text_items(self, table_, items_):
        cmd = "create table if not exists "
        cmd += table_ + " ("

        for item in items_:
            cmd += item + " TEXT, "

        cmd += "url TEXT)"

        self.execute(cmd)

    def execute(self, cmd_, params_ = None):
        self.c = self.database.cursor()
        logging.info(cmd_)
        if(params_):
            logging.info(params_)
            self.c.execute(cmd_, params_)
        else:
            self.c.execute(cmd_)

    def delete_by_url(self, table_, url_):
        self.execute("delete from " + table_ + " where url == ?", (url_,))

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

            # We can't delete an item from the database while iterating on the results of a previous
            # query, so we store the URLs of entries to delete, and batch them up
            for url in to_delete:
                self.delete_by_url(table, url)

        self.commit()

    def get_url(self, table_, key_value_pairs_, sql_extras_ = None):
        self.c = self.database.cursor()

        cmd = "select url from " + table_ + " where "
        params = []

        first = True
        for key, value in key_value_pairs_:
            if(first == False):
                cmd += " AND "
            else:
                first = False

            cmd += key + " == ? "
            params.append(value)

        if(sql_extras_):
            cmd += " " + sql_extras_

        self.c.execute(cmd, tuple(params))
        url = self.c.fetchone()
        
        return url

    def get_image_and_hwpack_urls(self, args_):
        """ We need a platform image and a hardware pack. These are specified either as
            Release: 
                Image: platform, image, build
                HW Pack: platform, build, hardware
            Snapshot:
                Image: platform, image, date, build
                HW Pack: platform, hardware, date, build"""
        image_url = None
        hwpack_url = None
        if(args_['platform'] == "snapshot"):
            count = 0
            while(1): # Just so we can try several times...
                if(args_['build'] == "latest"):
                    image_url = self.get_url("snapshot_binaries",
                                    [
                                     ("image", args_['image'])],
                                    "ORDER BY date DESC, build DESC") # First result is latest build

                    hwpack_url = self.get_url("snapshot_hwpacks",
                                    [
                                     ("hardware", args_['hwpack'])],
                                    "ORDER BY date DESC, build DESC") # First result is latest build

                else:
                    build_bits = args_['build'].split(":")
                    assert re.search("^\d+$", build_bits[0]), "Unexpected date format in build parameter " + build_bits[0]
                    assert re.search("^\d+$", build_bits[1]), "Build number in shapshot build parameter should be an integer " + build_bits[1]

                    image_url = self.get_url("snapshot_binaries",
                                    [
                                     ("image", args_['image']),
                                     ("build", build_bits[1]),
                                     ("date", build_bits[0])])

                    hwpack_url = self.get_url("snapshot_hwpacks",
                                    [
                                     ("hardware", args_['hwpack']),
                                     ("build", build_bits[1]),
                                     ("date", build_bits[0])])

                if(count == 1):
                    break
                count += 1

                if(image_url == None): # If we didn't match anything, try prepending linaro- to the image name
                    args_['image'] = "linaro-" + args_['image']
                else:
                    break # Got a URL, go.

        else:
            image_url = self.get_url("release_binaries",
                            [
                             ("image", args_['image']),
                             ("build", args_['build']),
                             ("platform", args_['platform'])])

            hwpack_url = self.get_url("release_hwpacks",
                            [
                             ("hardware", args_['hwpack']),
                             ("build", args_['build']),
                             ("platform", args_['platform'])])

        if(not image_url): # If didn't get an image URL set up something so the return line doesn't crash
            image_url = [None]

        if(not hwpack_url): # If didn't get a hardware pack URL set up something so the return line doesn't crash
            hwpack_url = [None]

        return(image_url[0], hwpack_url[0])
