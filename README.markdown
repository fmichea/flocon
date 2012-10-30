flocon - Archlinux packages shared on local network
===================================================

Introduction
------------

This project aims to provide a easy way to share pacman cache between multiple
machines on the same local network.

There already is a project that does this: [pacserve][1]. I tried to use it,
failed and decided to rewrite it with twisted (I may learn some things on the
path :d), and it's in the TODO anyway.

Todo:
-----

* Establish connection between all hosts using udp multicast packets.
* Look-up a packet in all the nodes of the graph.
* If not found, get it on standart mirrors.
* Do we need authentication and "trust check" (using public/private key system)?
    - AFAIK, packets are now signed, so it will fail on this check if packet is
      corrupted, it may be a pain though if you can't update a package through
      flocon... Maybe check all packages before sending them?

[1]: http://xyne.archlinux.ca/projects/pacserve/
