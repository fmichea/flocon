flocon - Archlinux packages shared on local network
===================================================

Introduction
------------

This project aims to provide a easy way to share pacman cache between multiple
machines on the same local network.

There already is a project that does this: [pacserve][1]. I tried to use it,
failed and decided to rewrite it with twisted.

Installation
------------

### AUR Packaging

The easiest way to install flocon is to install `flocon-git` from AUR with your
favorite AUR package manager. Do the configuration steps below. Then you can
activate the systemd daemon named `flocon-git`.

### Manual installation

#### Getting and using from sources

1. Install `python2` and `python2-pip` from official repositories.
2. Clone this repository: `git clone https://bitbucket.org/kushou/flocon.git`
3. Run `pip2 install -r requirements.txt`
4. Do the Configuration step below.
5. Then you can run `python2 flocon.py` (You can add --debug as an option)

#### Installing from sources

You can use the following script to install flocon from a clone of the git
repository manually.

    #! /bin/sh

    set -e on

    cd `mktemp -d`
    git clone https://bitbucket.org/kushou/flocon.git
    cd flocon/
    makepkg -s --noconfirm
    sudo pacman --noconfirm -U flocon-git-*-1-any.pkg.tar.xz

### Configuration

Modify your /etc/pacman.d/mirrorlist with (needs root priviledge):

1. Add `Server = http://localhost:19433/$repo/os/$arch` as your first
   server.
2. Optionally, if you don't want to see 404 from flocon, add the following
   comment in front of a copy of your current first mirror:
   `# flocon: Serv...`, so that flocon will use it as a fallback.

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

Features
--------

* Every node of the "local shared cache network" is found automatically
  using multicast (thanks pacserve for the idea)
* It lists current connected clients on `SIGUSR1` (``kill -USR1 `pgrep flocon` ``)
* If it didn't succeed connection (join multicast group, 15 minutes try every 5
  seconds), you need to send it `SIGUSR2` to retry (when you finally are
  connected).

Todo:
-----

* Could be nice to ban clients. (if sending corrupted packages)
* Do we need authentication and "trust check"? (using public/private key system)
    - AFAIK, packets are now signed, so it will fail on this check if packet is
      corrupted, it may be a pain though if you can't update a package through
      flocon... Maybe check all packages before sending them?
* Moreover, security?

[1]: http://xyne.archlinux.ca/projects/pacserve/
