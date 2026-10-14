Evolution Simulator (Windows)
=============================

To start: unzip this whole folder somewhere (not inside the zip), then double-click
evolutionSimulator.exe.

Windows may say "Windows protected your PC" the first time. The program is not signed with a
certificate, because certificates cost money every year and this is a free, public-domain project.
The warning means "I do not know who made this", not "this is harmful". To run it anyway, click
"More info", then "Run anyway". You can look at everything it does: the source is public.

  https://github.com/dwhagar/evolutionSimulator

What is in this folder
  evolutionSimulator.exe   the program
  _internal\               the files it needs (Python, Qt, libraries); keep it next to the .exe
  LICENSE                  the project's licence (CC0 1.0, public domain)
  THIRD_PARTY_NOTICES.md   software written by others that is included, and its licences
  VERSION                  the version of this build

To remove it, delete the folder. It writes nothing outside its folder except your window
settings (a few lines in the per-user Windows registry, under HKEY_CURRENT_USER\Software\evolutionSimulator).
