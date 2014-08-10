hackerfeed
==========

Twisted daemon that checks Hacker News for updates and pushes selected topics in desktop notification box

Installation
------------

In addition to the packages from ``requirements.txt``, it also relies on the system's dbus, so it won't run under virtual environment.

Copy the ``config.yaml.example`` template to ``config.yaml`` and edit the keywords and domains (comma separated) per your needs.

This software runs in the background. At regular intervals, it checks the `newest` page on hacker news for updates and matches the
title for keywords, as well as the domains (sources) - if there is a match it pushes system notification with the title and link.

You can run it with: ::

    twistd -y run.py
