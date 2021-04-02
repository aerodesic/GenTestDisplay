from DistUtilsExtra.auto import setup
from distutils.command.install import install
import os

PACKAGE="gentestdisplay"
VERSION="1.0"

# In case we need hooks
class post_install(install):
    def run(self):
        install.run(self)

setup(
    name              = PACKAGE,
    author            = "Gary Oliver",
    author_email      = "go@robosity.com",
    url               = "https://www.robosity.com",
    version           = VERSION,
    packages          = [ "gentestdisplay" ],
    package_data      = { "gentestdisplay": [ "bitmaps/gentestlogo.png", ] },
    license           = "Copyright 2021, Gary Oliver",
    description       = "Generator Test main display",
    long_description  = open("README.md").read(),
    data_files        = [
        ("/usr/sbin",                        [ "gentestdisplay/gentestdisplay" ]),
        ("share/bitmaps",                    [ "bitmaps/gentestlogo.png", ] ),
        ("share/GenTestDisplay",             [ "extra/COPYING", ] ),
    ],
    cmdclass = { 'install': post_install },
)
