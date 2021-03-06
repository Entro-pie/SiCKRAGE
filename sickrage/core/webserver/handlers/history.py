# ##############################################################################
#  Author: echel0n <echel0n@sickrage.ca>
#  URL: https://sickrage.ca/
#  Git: https://git.sickrage.ca/SiCKRAGE/sickrage.git
#  -
#  This file is part of SiCKRAGE.
#  -
#  SiCKRAGE is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  -
#  SiCKRAGE is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  -
#  You should have received a copy of the GNU General Public License
#  along with SiCKRAGE.  If not, see <http://www.gnu.org/licenses/>.
# ##############################################################################
from abc import ABC

from tornado.web import authenticated

import sickrage
from sickrage.core.tv.show.history import History
from sickrage.core.webserver.handlers.base import BaseHandler


class HistoryHandler(BaseHandler, ABC):
    @authenticated
    async def get(self, *args, **kwargs):
        limit = self.get_argument('limit', None)

        if limit is None:
            if sickrage.app.config.history_limit:
                limit = int(sickrage.app.config.history_limit)
            else:
                limit = 100
        else:
            limit = int(limit)

        if sickrage.app.config.history_limit != limit:
            sickrage.app.config.history_limit = limit
            sickrage.app.config.save()

        compact = []

        for row in History().get(limit):
            action = {
                'action': row['action'],
                'provider': row['provider'],
                'release_group': row['release_group'],
                'resource': row['resource'],
                'time': row['date']
            }

            if not any((history['show_id'] == row['show_id'] and
                        history['season'] == row['season'] and
                        history['episode'] == row['episode'] and
                        history['quality'] == row['quality']) for history in compact):

                history = {
                    'actions': [action],
                    'quality': row['quality'],
                    'resource': row['resource'],
                    'season': row['season'],
                    'episode': row['episode'],
                    'show_id': row['show_id'],
                    'show_name': row['show_name']
                }

                compact.append(history)
            else:
                index = [i for i, item in enumerate(compact)
                         if item['show_id'] == row['show_id'] and
                         item['season'] == row['season'] and
                         item['episode'] == row['episode'] and
                         item['quality'] == row['quality']][0]

                history = compact[index]
                history['actions'].append(action)

                history['actions'].sort(key=lambda d: d['time'], reverse=True)

        submenu = [
            {'title': _('Clear History'), 'path': '/history/clear', 'icon': 'fas fa-trash',
             'class': 'clearhistory', 'confirm': True},
            {'title': _('Trim History'), 'path': '/history/trim', 'icon': 'fas fa-cut',
             'class': 'trimhistory', 'confirm': True},
        ]

        return await self.render(
            "/history.mako",
            historyResults=History().get(limit),
            compactResults=compact,
            limit=limit,
            submenu=submenu,
            title=_('History'),
            header=_('History'),
            topmenu="history",
            controller='root',
            action='history'
        )


class HistoryClearHandler(BaseHandler, ABC):
    @authenticated
    async def get(self, *args, **kwargs):
        await self.run_task(History().clear)
        sickrage.app.alerts.message(_('History cleared'))
        return self.redirect("/history/")


class HistoryTrimHandler(BaseHandler, ABC):
    @authenticated
    async def get(self, *args, **kwargs):
        await self.run_task(History().trim)
        sickrage.app.alerts.message(_('Removed history entries older than 30 days'))
        return self.redirect("/history/")
