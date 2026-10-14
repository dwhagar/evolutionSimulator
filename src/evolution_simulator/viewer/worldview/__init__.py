"""The world view's parts (UX.12), kept apart from the panel so each can be tested on its own.

- ``layers``: a packed frame block read into numpy arrays.
- ``camera``: pan and zoom arithmetic (pixels per world unit, the point at the centre).
- ``glide``: the in-between positions that let creatures slide from one tick to the next.
- ``palette``: the colour modes and the colour-blind-safe colours they use.
- ``canvas``: the widget that draws it all with ``QPainter``.
- ``panel``: the canvas with its toolbar, the thing ``viewer/panels/world.py`` hands to the window.

Only ``layers``, ``camera``, ``glide`` and ``palette`` need numpy alone; none of them touches Qt.
World coordinates have y up (a heading of 90 degrees points to the top of the screen), as the
simulation's headings are counterclockwise.
"""
