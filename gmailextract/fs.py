"""Utility functions for interacting with the filesystem used by the gmail
image extractor program.
"""

import string
import os

VALID_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)
def sanatize_filename(filename):
    """Returns a filename that is safe for using when saving to disk.
    This is only used for the basename of a file, not the directory path

    Args:
        filename -- a possible base name for a file to be saved as

    Returns:
        A safe version of the same filename, that won't cause any problems
        saving to disk
    """
    return ''.join(c for c in filename if c in VALID_CHARS)

def unique_filename(path, filename):
    """Returns a version of the given filename that is unique in the given
    directory.

    A unique name is found by first trying the given filename in the given path.
    If that file already exists, integers are added before the file extension
    (if one exists) until a unique filename is found

    Args:
        path     -- a directory path
        filename -- a potential filename to try in the given directory

    Returns:
        A filename that is not currently used in the given directory
    """
    if not os.path.isfile(os.path.join(path, filename)):
        return filename

    file_name_parts = filename.split(".")
    if len(file_name_parts) > 1:
        extension = u"." + file_name_parts[-1]
        base_filename = u".".join(file_name_parts[:-1])
    else:
        extension = u""
        base_filename = filename

    index = 2
    while os.path.isfile(os.path.join(path, u"{0} - {1}{2}".format(base_filename, index, extension))):
        index += 1

    return u"{0} - {1}{2}".format(base_filename, index, extension)
