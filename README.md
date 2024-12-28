## A tray utility for quickly connecting to chalmers studat computers

A small windows tray written in python that allows you to connect to available studat computers without visiting the website.
It's not completed but the basic functionality works as of 2024-12-28

The program expects two environment variables, they can be specified with a .env file in the same folder as the script.
```
CID_USERNAME=cid@net.chalmers.se
CID_PASSWORD=pass
```

**Do not use this without verifying the source code! Giving out your credentials in plain text is very dangerous!**

Currently salar.json is filled with a couple of rooms, this list is used for matching the computer to a timeedit room, it should be filled with ids from vantcomp as keys and ids from timeedit as values
