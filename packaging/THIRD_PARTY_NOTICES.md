# Third-party notices

Evolution Simulator itself is released under CC0 1.0 (see `LICENSE`). The Windows download also
contains software written by others. It is listed here with its licence.

## Qt for Python (PySide6) and Qt

The window, menus and drawing use **PySide6** (Qt for Python) and the **Qt** libraries it carries.
They are free software under the **GNU Lesser General Public License, version 3 (LGPL v3)**.

- Project: <https://doc.qt.io/qtforpython-6/> and <https://www.qt.io/>
- Licence text: <https://www.gnu.org/licenses/lgpl-3.0.html>
- Source code of the Qt libraries and PySide6: <https://download.qt.io/official_releases/> and
  <https://code.qt.io/cgit/pyside/pyside-setup.git/>

The Qt libraries are shipped as separate files (the `.dll` files in the `_internal\PySide6` folder
of the download), not merged into the program. The LGPL gives you the right to replace them with a
version you build yourself: close the program, build or download a compatible PySide6 and Qt, and
copy its `.dll` files over the ones in that folder. Nothing else needs to change.

## pyqtgraph

The graphs use **pyqtgraph**, MIT licence. <https://www.pyqtgraph.org/>

## NumPy

Array maths in the viewer uses **NumPy**, BSD 3-clause licence. <https://numpy.org/>

## Python and PyInstaller

The program is packaged with **PyInstaller** (GPL v2 with an exception that allows its output to be
distributed under any licence) and runs on the **Python** interpreter (Python Software Foundation
licence). <https://pyinstaller.org/> and <https://www.python.org/>
