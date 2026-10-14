"""The creature inspector (UX.14), in parts.

``describe`` turns an ``AnimalDetail`` (and a frame, and the history) into text and small records
with no window involved; ``widgets`` are the few widgets the tabs share; ``tabs`` finds the
``tab_*`` modules (``tab_body``, ``tab_genes``, ``tab_family``; UX.15 adds ``tab_brain``); ``panel``
is the dock that holds the header and the tabs and owns the ``Esc`` action. The dock itself is
registered by ``viewer/panels/inspector.py``.
"""
