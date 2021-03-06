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

"""
Application-wide instances that are always needed, regardless of interface
or features
"""

import asyncio
aioloop = asyncio.get_event_loop()


from . import logging
log = logging.make_logger()


from . import settings
localcfg = settings.Settings()
settings.init_defaults(localcfg)


from .client import API
srvapi = API(host=localcfg['connect.host'],
             port=localcfg['connect.port'],
             path=localcfg['connect.path'],
             user=localcfg['connect.user'],
             password=localcfg['connect.password'],
             tls=localcfg['connect.tls'],
             interval=localcfg['tui.poll'],
             loop=aioloop)
remotecfg = srvapi.settings


from .helpmgr import HelpManager
helpmgr = HelpManager()
helpmgr.localcfg = localcfg
helpmgr.remotecfg = remotecfg


from .commands import CommandManager
cmdmgr = CommandManager(loop=aioloop,
                        info_handler=lambda msg: log.info(msg),
                        error_handler=lambda msg: log.error(msg))
cmdmgr.resources.update(aioloop=aioloop,
                        srvapi=srvapi,
                        cfg=localcfg,
                        srvcfg=remotecfg,
                        helpmgr=helpmgr)
helpmgr.cmdmgr = cmdmgr

def _pre_run_hook(cmdline):
    # Change command before it is executed

    # If there is '-h' or '--help' in the arguments, replace it with 'help
    # <cmd>'.  This is dirty but easier than forcing argparse to ignore all
    # other arguments without calling sys.exit().
    if '-h' in cmdline or '--help' in cmdline:
        cmdcls = cmdmgr.get_cmdcls(cmdline[0], interface='ANY')
        if cmdcls is not None:
            if cmdcls.name != 'tab':
                return ['help', cmdcls.name]
            else:
                # 'tab ls -h' is a little trickier because both 'tab' and 'ls'
                # can have arbitrary additional arguments which we must remove.
                #
                # Find first argument to 'tab' that is also a valid command
                # name.  Preserve all arguments before that.
                tab_args = []
                for arg in cmdline[1:]:
                    if cmdmgr.get_cmdcls(arg, interface='ANY') is not None:
                        return ['tab'] + tab_args + ['help', arg]
                    else:
                        tab_args.append(arg)
                return ['help', 'tab']
    return cmdline
cmdmgr.pre_run_hook = _pre_run_hook


from .client import geoip
if geoip.available:
    geoip.cachedir = localcfg['geoip.dir']
else:
    localcfg['geoip'] = False
geoip.enabled = localcfg['geoip']
