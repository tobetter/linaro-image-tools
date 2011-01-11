import os
import sys


def apt_get_install(command, package):
    print ("Installing required command %s from package %s"
           % (command, package))
    os.system('sudo apt-get install %s' % package)


def ensure_command(command, package):
    if os.system('which %s 2>/dev/null 1>/dev/null' % command) != 0:
        apt_get_install(command, package)
