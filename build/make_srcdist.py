"""
Creates SQLitely source distribution archive from current version in
sqlitely\. Sets execute flag permission on .sh files.

@author    Erki Suurjaak
@created   21.08.2019
@modified  10.07.2024
"""
import glob
import os
import sys
import time
import zipfile


if "__main__" == __name__:
    NAME = "sqlitely"
    INITIAL_DIR = os.getcwd()
    ROOT_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    SRC_DIR     = "src"
    sys.path.insert(0, os.path.join(ROOT_DIR, SRC_DIR))
    from sqlitely import conf

    BASE_DIR = ""
    ZIP_DIR = "%s_%s" % (NAME, conf.Version)
    DEST_FILE = "%s_%s-src.zip" % (NAME, conf.Version)
    print("Creating source distribution %s.\n" % DEST_FILE)

    def pathjoin(*args):
        # Cannot have ZIP system UNIX with paths like Windows
        return "/".join(filter(None, args))

    def add_files(zf, filenames, subdir=""):
        global BASE_DIR
        size = 0
        for filename in filenames:
            fullpath = os.path.join(BASE_DIR, subdir, filename)
            zi = zipfile.ZipInfo()
            zi.filename = pathjoin(ZIP_DIR, subdir, filename)
            zi.date_time = time.localtime(os.path.getmtime(fullpath))[:6]
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3 # UNIX
            zi.external_attr = 0o644 << 16 # Permission flag -rw-r--r--
            if os.path.splitext(filename)[-1] in [".sh"] \
            or os.path.split(subdir)[-1]      in ["bin"]:
                zi.external_attr = 0o755 << 16 # Permission flag -rwxr-xr-x
            print("Adding %s, %s bytes" % (zi.filename, os.path.getsize(fullpath)))
            zf.writestr(zi, open(fullpath, "rb").read())
            size += os.path.getsize(fullpath)
        return size

    os.chdir(ROOT_DIR)
    with zipfile.ZipFile(os.path.join(INITIAL_DIR, DEST_FILE), mode="w") as zf:
        size = 0
        for subdir, wildcard in [
            ("build",                                  "*"),
            ("res",                                    "*"),
            (pathjoin(SRC_DIR, NAME),                  "*.py"),
            (pathjoin(SRC_DIR, NAME, "bin"),           "*"),
            (pathjoin(SRC_DIR, NAME, "grammar"),       "*"),
            (pathjoin(SRC_DIR, NAME, "lib"),           "*.py"),
            (pathjoin(SRC_DIR, NAME, "media"),         "*"),
            (pathjoin(SRC_DIR, NAME, "etc"),           "%s.ini" % NAME),
            ("test",                                   "*"),
        ]:
            entries = glob.glob(os.path.join(BASE_DIR, subdir, wildcard))
            files = sorted([os.path.basename(x) for x in entries
                          if os.path.isfile(x)], key=str.lower)
            files = [f for f in files if not f.lower().endswith(".zip")]
            files = [f for f in files if not f.lower().endswith(".pyc")]
            size += add_files(zf, files, subdir)
        rootfiles = ["CHANGELOG.md", "LICENSE.md", "MANIFEST.in", "README.md",
                     "requirements.txt", "setup.py", "%s.bat" % NAME, "%s.sh" % NAME]
        size += add_files(zf, rootfiles)

    os.chdir(INITIAL_DIR)
    size_zip = os.path.getsize(DEST_FILE)
    print ("\nCreated %s, %s bytes (from %s, %.2f compression ratio)." %
           (DEST_FILE, size_zip, size, float(size_zip) / size))
