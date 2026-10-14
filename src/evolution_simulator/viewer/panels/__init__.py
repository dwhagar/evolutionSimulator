"""The screens. One module per screen, each exposing ``PANEL`` (see ``viewer.registry``).

The shell ships a placeholder in each slot of the default layout; the item that builds the screen
replaces that module's contents and keeps its ``PANEL.id`` and ``PANEL.area``:

- ``world``: the world view (UX.12), centre.
- ``controls``: time and speed controls (UX.13), top.
- ``inspector``: the creature inspector and brain view (UX.14, UX.15), right.
- ``charts``: charts (UX.16), right, under the inspector.

A new screen is a new module here; nothing else needs editing.
"""
