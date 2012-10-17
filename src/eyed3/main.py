# -*- coding: utf-8 -*-
################################################################################
#  Copyright (C) 2009-2012  Travis Shirk <travis@pobox.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
################################################################################
from __future__ import print_function
import sys, exceptions, os.path
import ConfigParser
import traceback, pdb
import eyed3, eyed3.utils, eyed3.utils.cli, eyed3.plugins, eyed3.info


DEFAULT_PLUGIN = "classic"
DEFAULT_CONFIG = os.path.join(eyed3.info.USER_DIR, "config.ini")


def main(args, config):
    args.plugin.start(args, config)

    # Process paths (files/directories)
    for p in args.paths:
        eyed3.utils.walk(args.plugin, p, excludes=args.excludes,
                         fs_encoding=args.fs_encoding)

    args.plugin.handleDone()

    return 0


def _listPlugins():
    print("")

    all_plugins = eyed3.plugins.load(reload=True)
    # Create a new dict for sorted display
    plugin_names = []
    for plugin in set(all_plugins.values()):
        plugin_names.append(plugin.NAMES[0])

    plugin_names.sort()
    for name in plugin_names:
        plugin = all_plugins[name]

        alt_names = plugin.NAMES[1:]
        alt_names = " (%s)" % ", ".join(alt_names) if alt_names else ""

        print("- %s%s:\n%s\n" % (eyed3.utils.cli.boldText(name),
                                 alt_names, plugin.SUMMARY))


def _loadConfig(config_file=None):
    import os
    import ConfigParser

    config = None
    if config_file:
        config_file = os.path.abspath(config_file)
    else:
        config_file = DEFAULT_CONFIG

    if os.path.isfile(config_file):
        try:
            config = ConfigParser.SafeConfigParser()
            config.read(config_file)
        except ConfigParser.Error as ex:
            eyed3.log.warning("User config error: " + str(ex))
            return None
    elif config_file != DEFAULT_CONFIG:
        raise IOError("User config not found: %s" % config_file)

    return config


def profileMain(args, config):  # pragma: no cover
    '''This is the main function for profiling
    http://code.google.com/appengine/kb/commontasks.html#profiling
    '''
    import cProfile, pstats, StringIO

    eyed3.log.debug("driver profileMain")
    prof = cProfile.Profile()
    prof = prof.runctx("main(args)", globals(), locals())

    stream = StringIO.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("time")  # Or cumulative
    stats.print_stats(100)  # 80 = how many to print

    # The rest is optional.
    stats.print_callees()
    stats.print_callers()
    sys.stderr.write("Profile data:\n%s\n" % stream.getvalue())

    return 0


def parseCommandLine(cmd_line_args=None):
    from eyed3.utils.cli import ArgumentParser

    def makeParser():
        p = ArgumentParser(prog=eyed3.info.NAME, add_help=True)
        p.add_argument("paths", metavar="PATH", nargs="*",
                       help="Files or directory paths")
        p.add_argument("--exclude", action="append", metavar="PATTERN",
                       dest="excludes",
                       help="A regular expression for path exclusion. May be "
                            "specified multiple times.")
        p.add_argument("-L", "--plugins", action="store_true", default=False,
                       dest="list_plugins", help="List all available plugins")
        p.add_argument("-P", "--plugin", action="store", dest="plugin",
                       default=None, metavar="NAME",
                       help="Specify which plugin to use. The default is '%s'" %
                            DEFAULT_PLUGIN)
        p.add_argument("-C", "--config", action="store", dest="config",
                       default=None, metavar="FILE",
                       help="Supply a configuration file. The default is "
                            "'%s', although even that is optional." %
                            DEFAULT_CONFIG)
        p.add_argument("-Q", "--quiet", action="store_true", dest="quiet",
                       default=False, help="A hint to plugins to output less.")

        p.add_argument("--fs-encoding", action="store",
                       dest="fs_encoding", default=eyed3.LOCAL_FS_ENCODING,
                       metavar="ENCODING",
                       help="Use the specified file system encoding for "
                            "filenames.  Default as it was detected is '%s' "
                            "but this option is still useful when reading "
                            "from mounted file systems." %
                            eyed3.LOCAL_FS_ENCODING)
        # Debugging options
        group = p.debug_arg_group
        group.add_argument("--profile", action="store_true", default=False,
                           dest="debug_profile",
                           help="Run using python profiler.")
        group.add_argument("--pdb", action="store_true", dest="debug_pdb",
                           help="Drop into 'pdb' when errors occur.")
        return p

    cmd_line_args = list(cmd_line_args) if cmd_line_args else list(sys.argv[1:])

    # Remove any options not related to plugin/config for first parse. These
    # determine the parser for the next stage.
    stage_one_args = []
    idx, auto_append = 0, False
    while idx < len(cmd_line_args):
        opt = cmd_line_args[idx]
        if auto_append:
            stage_one_args.append(opt)
            auto_append = False
        if opt in ("-C", "--config", "-P", "--plugin"):
            stage_one_args.append(opt)
            auto_append = True
        elif (opt.startswith("-C=") or opt.startswith("--config=") or
                opt.startswith("-P=") or opt.startswith("--plugin=")):
            stage_one_args.append(opt)
        idx += 1

    parser = makeParser()
    args = parser.parse_args(stage_one_args)

    config = _loadConfig(args.config)

    if args.plugin:
        # Plugins on the command line take precedence over config.
        plugin_name = args.plugin
    elif config:
        # Get default plugin from config or use DEFAULT_CONFIG
        try:
            plugin_name = config.get("DEFAULT", "plugin")
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as ex:
            plugin_name = DEFAULT_PLUGIN
    else:
        plugin_name = DEFAULT_PLUGIN
    assert(plugin_name)

    PluginClass = eyed3.plugins.load(plugin_name)
    if PluginClass is None:
        eyed3.utils.cli.printError("Plugin not found: %s" % plugin_name)
        parser.exit(1)
    plugin = PluginClass(parser)

    # Reparse the command line with options from the config.
    if config:
        try:
            config_opts = config.get("DEFAULT", "options").split()
            cmd_line_args.extend(config_opts)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as ex:
            pass
    args = parser.parse_args(args=cmd_line_args)

    if args.list_plugins:
        _listPlugins()
        parser.exit(0)

    args.plugin = plugin
    eyed3.log.debug("command line args: %s", args)
    eyed3.log.debug("plugin is: %s", plugin)

    return args, parser, config


if __name__ == "__main__":  # pragma: no cover
    retval = 1

    # We should run against the same install
    eyed3.require(eyed3.info.VERSION)

    try:
        args, _, config = parseCommandLine()

        for fp in [sys.stdout, sys.stderr]:
            eyed3.utils.cli.enableColorOutput(fp, os.isatty(fp.fileno()))

        mainFunc = main if args.debug_profile == False else profileMain
        retval = mainFunc(args, config)
    except KeyboardInterrupt:
        retval = 0
    except IOError as ex:
        eyed3.utils.cli.printError(ex)
    except exceptions.Exception as ex:
        msg = "Uncaught exception: %s\n%s" % (str(ex), traceback.format_exc())
        eyed3.log.exception(msg)
        sys.stderr.write("%s\n" % msg)

        if args.debug_pdb:
            pdb.post_mortem()
    finally:
        sys.exit(retval)

# vim: set ft=python:
