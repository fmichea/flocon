#!/usr/bin/env python

from distutils.core import setup

setup(
    name='flocon',
    version='0.0.1b',
    description='Archlinux packages shared on local network',
    author='Franck Michea',
    author_email='franck.michea@gmail.com',
    url='https://bitbucket.org/kushou/flocon',
    packages=['flocon'],
    scripts=['bin/flocon'],
)
