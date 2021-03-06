# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt

from ...logging import make_logger
log = make_logger(__name__)

from .. import InitCommand, CmdError
from ...completion import candidates
from . import _mixin as mixin
from ... import objects
from ._common import (make_X_FILTER_spec, make_COLUMNS_doc,
                      make_SORT_ORDERS_doc, make_SCRIPTING_doc)

import asyncio
import os


class AddTorrentsCmdbase(metaclass=InitCommand):
    name = 'add'
    aliases = ('download','get')
    provides = set()
    category = 'torrent'
    description = 'Download torrents'
    usage = ('add [<OPTIONS>] <TORRENT> <TORRENT> <TORRENT> ...',)
    examples = ('add 72d7a3179da3de7a76b98f3782c31843e3f818ee',
                'add --stopped http://example.org/something.torrent')
    argspecs = (
        { 'names': ('TORRENT',), 'nargs': '+',
          'description': 'Link or path to torrent file, magnet link or info hash' },

        { 'names': ('--stopped','-s'), 'action': 'store_true',
          'description': 'Do not start downloading the added torrent(s)' },

        { 'names': ('--path','-p'),
          'description': ('Custom download directory for added torrent(s) '
                          'relative to "srv.path.complete" setting')},
    )

    async def run(self, TORRENT, stopped, path):
        success = True
        force_torrentlist_update = False
        for source in TORRENT:
            response = await self.make_request(objects.srvapi.torrent.add(source, stopped=stopped, path=path))
            success = success and response.success
            force_torrentlist_update = force_torrentlist_update or success

        # Update torrentlist AFTER all 'add' requests
        if force_torrentlist_update and hasattr(self, 'polling_frenzy'):
            self.polling_frenzy()

        if not success:
            raise CmdError()

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        return candidates.fs_path(args.curarg.before_cursor,
                                  glob=r'*.torrent')

    @classmethod
    def completion_candidates_params(cls, option, args):
        """Complete parameters (e.g. --option parameter1,parameter2)"""
        if option == '--path':
            return candidates.fs_path(args.curarg.before_cursor,
                                      base=objects.remotecfg['path.complete'],
                                      directories_only=True)


class TorrentDetailsCmdbase(mixin.get_single_torrent, metaclass=InitCommand):
    name = 'details'
    aliases = ('info',)
    provides = set()
    category = 'torrent'
    description = 'Display detailed torrent information'
    usage = ('details',
             'details <TORRENT FILTER>')
    examples = ('details id=71',)
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),
    )

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True,
                                           prefer_focused=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            torrent = await self.get_single_torrent(tfilter, keys=('id', 'name'))
            if not torrent:
                raise CmdError()
            else:
                log.debug('Showing details of torrent %r: %r', tfilter, torrent)
                if asyncio.iscoroutinefunction(self.display_details):
                    await self.display_details(torrent['id'])
                else:
                    self.display_details(torrent['id'])

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        if args.curarg_index == 1:
            return candidates.torrent_filter(args.curarg)


class ListTorrentsCmdbase(mixin.get_torrent_sorter, mixin.get_torrent_columns,
                          metaclass=InitCommand):
    name = 'list'
    aliases = ('ls',)
    provides = set()
    category = 'torrent'
    description = 'List torrents'
    usage = ('list [<OPTIONS>]',
             'list [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('ls active',
                'ls !active',
                'ls seeds<10',
                'ls active&tracker~example.org',
                'ls active|idle&tracker~example')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=False, nargs='*'),

        { 'names': ('--sort', '-s'),
          'default_description': "current value of 'sort.torrents' setting",
          'description': ('Comma-separated list of sort orders '
                          "(see SORT ORDERS section)") },

        { 'names': ('--columns', '-c'),
          'default_description': "current value of 'columns.torrents' setting",
          'description': ('Comma-separated list of column names '
                          "(see COLUMNS section)") },
    )

    from ...views.torrent import COLUMNS
    from ...client.sorters import TorrentSorter
    more_sections = {
        'COLUMNS': make_COLUMNS_doc(COLUMNS, '--columns', 'columns.torrents'),
        'SORT ORDERS': make_SORT_ORDERS_doc(TorrentSorter, '--sort', 'sort.torrents'),
        'SCRIPTING': make_SCRIPTING_doc(name),
    }

    async def run(self, TORRENT_FILTER, sort, columns):
        sort = objects.localcfg['sort.torrents'] if sort is None else sort
        columns = objects.localcfg['columns.torrents'] if columns is None else columns
        try:
            columns = self.get_torrent_columns(columns)
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=True,
                                           discover_torrent=False)
            sort = self.get_torrent_sorter(sort)
        except ValueError as e:
            raise CmdError(e)
        else:
            log.debug('Listing %s torrents sorted by %s', tfilter, sort)
            if asyncio.iscoroutinefunction(self.make_torrent_list):
                await self.make_torrent_list(tfilter, sort, columns)
            else:
                self.make_torrent_list(tfilter, sort, columns)

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        return candidates.torrent_filter(args.curarg)

    @classmethod
    def completion_candidates_params(cls, option, args):
        """Complete parameters (e.g. --option parameter1,parameter2)"""
        if option == '--sort':
            return candidates.Candidates(objects.localcfg['sort.torrents'].options,
                                         curarg_seps=(objects.localcfg['sort.torrents'].sep.strip(),))
        elif option == '--columns':
            return candidates.Candidates(objects.localcfg['columns.torrents'].options,
                                         curarg_seps=(objects.localcfg['columns.torrents'].sep.strip(),))


class TorrentMagnetURICmdbase(metaclass=InitCommand):
    name = 'magnet'
    aliases = ('uri',)
    provides = set()
    category = 'torrent'
    description = 'Display torrent(s) magnet URI'
    usage = ('magnet',
             'magnet <TORRENT FILTER>')
    examples = ('magnet name~ubuntu',)
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),
    )

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True,
                                           prefer_focused=False)
        except ValueError as e:
            raise CmdError(e)
        else:
            try:
                uris = await objects.srvapi.torrent.get_magnet_uris(tfilter)
            except objects.srvapi.ClientError as e:
                raise CmdError(e)
            else:
                self.display_uris(uris)

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        if args.curarg_index == 1:
            return candidates.torrent_filter(args.curarg)


class MoveTorrentsCmdbase(metaclass=InitCommand):
    name = 'move'
    aliases = ('mv',)
    provides = set()
    category = 'torrent'
    description = "Change torrents' location"
    usage = ('move <PATH>',
             'move <TORRENT FILTER> <PATH>')
    examples = ('move ./new/path',
                'move size>50G /path/to/lots/of/storage')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),

        { 'names': ('PATH',),
          'description': ('Move the specified torrent(s) to this directory.  If PATH is relative '
                          '(i.e. does not start with "/"), it is relative to the value of the '
                          'setting "srv.path.complete".  That means "." is the download path.') },
    )

    async def run(self, TORRENT_FILTER, PATH):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            response = await self.make_request(objects.srvapi.torrent.move(tfilter, PATH),
                                               polling_frenzy=True)
            if not response.success:
                raise CmdError()


class RemoveTorrentsCmdbase(metaclass=InitCommand):
    name = 'remove'
    aliases = ('rm', 'delete')
    provides = set()
    category = 'torrent'
    description = 'Remove torrents'
    usage = ('remove [<OPTIONS>]',
             'remove [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('remove',
                r'remove "stupid torrent" silly\ torrent and_this_torrent',
                'remove -d "unwanted torrent"')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),

        { 'names': ('--delete-files','-d'), 'action': 'store_true',
          'description': 'Delete any downloaded files' },

        { 'names': ('--force','-f'), 'action': 'store_true',
          'description': ('Ignore remove.max-hits setting: Remove all '
                          'matching torrents instead of asking for confirmation '
                          'if the number of matches exceeds remove.max-hits')},
    )

    async def run(self, TORRENT_FILTER, delete_files, force):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            async def do_remove(tfilter=tfilter, delete_files=delete_files):
                response = await self.make_request(
                    objects.srvapi.torrent.remove(tfilter, delete=delete_files),
                    polling_frenzy=True)
                if not response.success:
                    raise CmdError()

            async def do_keep(tfilter=tfilter):
                self.error(('Keeping %s torrents: Too many hits ' % tfilter) +
                           '(use --force or increase remove.max-hits setting)')

            response = await objects.srvapi.torrent.torrents(tfilter, keys=('id',))
            hits = len(response.torrents)
            success = hits > 0
            if force or objects.localcfg['remove.max-hits'] < 0 or hits < objects.localcfg['remove.max-hits']:
                return await do_remove()
            else:
                await self.show_list_of_hits(tfilter)
                if hits > 0:
                    question = 'Are you sure you want to remove %d torrent%s' % (
                        hits, '' if hits == 1 else 's')
                    if delete_files:
                        question += ' and their files'
                    question += '?'
                    success = await self.ask_yes_no(question, yes=do_remove, no=do_keep,
                                                    after=self.remove_list_of_hits)
                if not success:
                    raise CmdError()

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        return candidates.torrent_filter(args.curarg)


class RenameCmdbase(metaclass=InitCommand):
    name = 'rename'
    aliases = ('rn',)
    provides = set()
    category = 'torrent'
    description = 'Rename a torrent or one of its files or directories'
    usage = ('rename <NEW>',
             'rename <TORRENT> <NEW>')
    examples = ('rename "A Better Name"',
                'rename id=123 Foo',
                'rename id=123/some/file new_file_name')
    argspecs = (
        { 'names': ('TORRENT',), 'nargs': '?',
          'description': ('Torrent filter expression, optionally followed by a "/" and '
                          'the relative path to a file or directory in the torrent'),
          'default_description': 'Focused torrent, file or directory in the TUI' },

        { 'names': ('NEW',),
          'description': ('New name of the torrent, file or directory specified by TORRENT '
                          '(must not contain "/" or be "." or "..")') },

        { 'names': ('--unique', '-u'), 'action': 'store_true',
          'description': ('Ensure the torrent filter expression in TORRENT matches exactly '
                          'one torrent; if not given, all matching files in all matching '
                          'torrents are renamed'),
          'default_description': 'Enabled automatically when renaming torrents' },
    )

    async def run(self, TORRENT, NEW, unique):
        if not TORRENT:
            # Autodetect path
            path = self.get_relative_path_from_focused(unique=unique)
            if path:
                # path is <TORRENT IDENTIFIER>/relative/path/to/file/in/torrent
                TORRENT = path

        # Split torrent filter from relative path in torrent
        if TORRENT and '/' in TORRENT:
            FILTER, PATH = TORRENT.split('/', maxsplit=1)
        else:
            FILTER, PATH = TORRENT, None
            unique = True

        try:
            tfilter = self.select_torrents(FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            response = await self.make_request(
                objects.srvapi.torrent.torrents(tfilter, keys=('id',)),
                quiet=True)
            if not response.success:
                raise CmdError()
            elif unique and len(response.torrents) > 1:
                # When renaming a torrent or the user said so, tfilter must
                # match exactly one torrent.  If it matches zero torrents,
                # make_request() below with produce the appropriate error
                # message.
                raise CmdError('%s matches more than one torrent' % tfilter)
            else:
                success = True
                for torrent in response.torrents:
                    tid = torrent['id']
                    response = await self.make_request(
                        objects.srvapi.torrent.rename(tid, path=PATH, new_name=NEW),
                        polling_frenzy=True)
                    if not response.success:
                        success = False
                if not success:
                    raise CmdError()


# Argument definitions that are shared between commands
ARGSPEC_TOGGLE = {
    'names': ('--toggle','-t'), 'action': 'store_true',
    'description': ('Start TORRENT if stopped and vice versa')
}

class StartTorrentsCmdbase(metaclass=InitCommand):
    name = 'start'
    aliases = ()
    provides = set()
    category = 'torrent'
    description = 'Start downloading torrents'
    usage = ('start [<OPTIONS>]',
             'start [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('start',
                "start 'night of the living dead' Metropolis",
                'start ubuntu --force')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),

        { 'names': ('--force','-f'), 'action': 'store_true',
          'description': 'Ignore download queue' },

        ARGSPEC_TOGGLE,
    )

    async def run(self, TORRENT_FILTER, toggle, force):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            if toggle:
                response = await self.make_request(
                    objects.srvapi.torrent.toggle_stopped(tfilter, force=force),
                    polling_frenzy=True)
            else:
                response = await self.make_request(
                    objects.srvapi.torrent.start(tfilter, force=force),
                    polling_frenzy=True)
            if not response.success:
                raise CmdError()


class StopTorrentsCmdbase(metaclass=InitCommand):
    name = 'stop'
    aliases = ('pause',)
    provides = set()
    category = 'torrent'
    description = 'Stop downloading torrents'
    usage = ('stop [<OPTIONS>]',
             'stop [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('stop',
                'stop "night of the living dead" idle',
                'stop --toggle ubuntu')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
        ARGSPEC_TOGGLE,
    )

    async def run(self, TORRENT_FILTER, toggle):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            if toggle:
                response = await self.make_request(
                    objects.srvapi.torrent.toggle_stopped(tfilter),
                    polling_frenzy=True)
            else:
                response = await self.make_request(
                    objects.srvapi.torrent.stop(tfilter),
                    polling_frenzy=True)
            if not response.success:
                raise CmdError()


class VerifyTorrentsCmdbase(metaclass=InitCommand):
    name = 'verify'
    aliases = ('check',)
    provides = set()
    category = 'torrent'
    description = 'Verify downloaded torrent data'
    usage = ('verify [<OPTIONS>]',
             'verify [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('verify',
                'verify debian')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
    )

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            response = await self.make_request(objects.srvapi.torrent.verify(tfilter),
                                               polling_frenzy=False)
            if not response.success:
                raise CmdError()
