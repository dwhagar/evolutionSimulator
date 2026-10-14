"""The graphical viewer (UX.11): a PySide6 window over a simulation session.

This package lives outside the core and sits behind the ``gui`` extra (``pip install
evolution-simulator[gui]``). The core never imports it, and this ``__init__`` imports nothing from
Qt, so ``evolution_simulator.viewer.backend`` and the command line can be used without it.

The pieces:

- ``backend``: what the window talks to (``Backend``: send commands, poll for updates).
  ``LocalBackend`` runs a ``Session`` in the same process; the process host of UX.7 fits the same
  two methods.
- ``controller``: ``ViewerController``, which polls the backend on a timer and turns what comes back
  into Qt signals (frames, details, status, events) for the panels.
- ``panels``: one module per screen, each exposing a ``PANEL`` (``PanelSpec``) that the window finds
  by itself, so the screens of UX.12 to UX.17 do not edit shared code.
- ``worldview``: the world view's camera, colours, gliding and canvas (UX.12).
- ``inspector``: the creature inspector's text, widgets, tabs and dock (UX.14).
- ``window``: ``MainWindow``, with the dock slots, menus, status bar and saved layout.
- ``app``: the command line and ``main``.
"""
