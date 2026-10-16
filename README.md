# gallery:review

This is a simple gallery-style app for reviewing images, making it easy to favorite and delete images from a directory. You probably want to either bind it to localhost or put it behind an authentication layer, since it allows users to move/delete your files!

## Configuration

Optional environment variables:

- `GALLERY_TITLE`: page title (default `Review`).
- `GALLERY_NO_FAV`: a `:`-separated list of paths (relative to the media root) where favoriting files and folders is disabled, at or below each path, e.g. `GALLERY_NO_FAV=Screenshots:Phone/DCIM`. Un-favoriting and trash still work there.
- `GALLERY_NO_DELETE`: set to `1` to disable permanent deletion (Empty Trash, Keep Favs Only, Delete Directory). Moving files to trash still works, since it's reversible.
