flocon - Archlinux packages shared on local network
===================================================

Introduction
------------

This project aims to provide a easy way to share pacman cache between multiple
machines on the same local network.

There already is a project that does this: [pacserve][1]. I tried to use it,
failed and decided to rewrite it with twisted (I may learn some things on the
path :d), and it's in the TODO anyway.

Installation
------------

1. Install `python2` and `python2-pip` from official repositories.
2. Clone this repository: `git clone https://bitbucket.org/kushou/flocon.git`
3. Run `pip2 install -r requirements.txt`
4. Modify your /etc/pacman.d/mirrorlist with (needs root priviledge):
    1. Add `Server = http://localhost:19433/$repo/os/$arch` as your first
       server.
    2. Add the following comment in front of your current first mirror:
       `# flocon: Server = ...`, so that flocon will use it as a fallback.
5. Then you can run `python2 flocon.py` (You can add --debug as an option)

Do that on all your hosts and you are done. You can then use pacman like any
other time. It will use the cache of one the machines on your LAN if it finds
it, else it will fallback on the default server. Keep other servers
uncommented, in case you don't have flocon started. If it is the case, you will
just see pacman complaining that sevrer localhost is not responding and it will
try with the next one not commented.

Btw, you need port 19432 open on both udp and tcp protocols, and tcp port 19433
open on loopback interface.

Flocon doesn't need special rights. It can be run in a special account, with no
specific configuration (read: you don't need to run it as root/your user)

Todo:
-----

* Could be nice to list/ban clients.
* Do we need authentication and "trust check"? (using public/private key system)
    - AFAIK, packets are now signed, so it will fail on this check if packet is
      corrupted, it may be a pain though if you can't update a package through
      flocon... Maybe check all packages before sending them?
* Moreover, security?


[1]: http://xyne.archlinux.ca/projects/pacserve/
