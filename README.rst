hackerfeed
==========

Twisted daemon that checks Hacker News for updates and pushes selected topics in desktop notification box

Installation
------------

In addition to the packages from ``requirements.txt``, it also relies on the system's dbus, so it won't run under virtual environment.

Copy the ``config.yaml.example`` template to ``config.yaml`` and edit the keywords (comma separated) per your needs.

You can run it with: ::

    twistd -y run.py
