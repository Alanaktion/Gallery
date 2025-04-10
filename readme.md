## Gallery

The ultimate single-file photo gallery

### PHP

Simply put the gallery.php file in any folder and it will display a gallery formatted to fit any screen, with some simple configurable options in the file. You can also rename the file to whatever you desire, it will work as an index.php file.

This application requires the GD library for generation of thumbnails.

### Python

Run the `gallery.py` file with Python. Use `-d` to specify a directory other than cwd to list images from, `-p` to specify which TCP port to listen on.

```bash
python3 gallery.py -d ~/Pictures/
```

This application requires the Pillow library to be installed:

```bash
pip3 install Pillow
```

Create a `config.ini` file in the cwd to customize the gallery features. See [config-sample.ini](config-sample.ini) for the defaults.

### Changelog

0.7.0

- Lazy-load thumbnail images
- AVIF image handling (where supported)
- List 7z, SVG, and other common files by default
- Python implementation
- Dark theme improvements

0.6.1

- High-DPI thumbnails
- Automatic dark theme

0.6.0

- Completely rewritten codebase
- Added nested subdirectory support
- Added breadcrumbs
- Added dark theme
- Added new configuration format
- Added new dynamic thumbnail sizing
- Added Windows hidden filesystem object detection
- Improved thumbnail cache storage
- Removed EXIF comment support

0.5.2

- Support for many more screen sizes from iPhone to Apple Cinema Display with a 2560px width.
- Captions now use embedded EXIF Comments if available

0.5.1

- Added new supported file types
- Added photo labels

0.5

- Added ability to rename file
- Improved thumbnail caching

0.4.1

- Generated thumbnails are now stored in a directory
- Added thumbnail directory hiding for Windows/Linux/Mac/UNIX
- Added option to customize window/tab title
- Removed option to cache all thumbnails in a single file (performance issues)

0.4

- Added file listing after gallery
- Added option to cache all thumbnails in a single file

0.3

- Added image sorting (alphabetic/filesystem order)

0.2.1

- New thumbnail naming conventions

0.2

- Added local thumbnail caching

0.1

- First release
