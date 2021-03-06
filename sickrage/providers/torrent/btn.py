# Author: Daniel Heimans
# URL: http://code.google.com/p/sickrage
#
# This file is part of SiCKRAGE.
#
# SiCKRAGE is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SiCKRAGE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SiCKRAGE.  If not, see <http://www.gnu.org/licenses/>.
import uuid

import sickrage
from sickrage.core.caches.tv_cache import TVCache
from sickrage.core.helpers import sanitize_scene_name, episode_num, try_int
from sickrage.core.tv.show.helpers import find_show
from sickrage.providers import TorrentProvider


class BTNProvider(TorrentProvider):
    def __init__(self):
        super(BTNProvider, self).__init__("BTN", 'https://broadcasthe.net', True)

        self._urls.update({
            'api': 'https://api.broadcasthe.net',
        })

        self.supports_absolute_numbering = True
        self.api_key = None
        self.reject_m2ts = False

        self.minseed = None
        self.minleech = None

        self.cache = TVCache(self, min_time=10)

    def _check_auth(self):
        if not self.api_key:
            sickrage.app.log.warning("Missing/Invalid API key. Check your settings")
            return False
        return True

    def search(self, search_strings, age=0, show_id=None, season=None, episode=None, **kwargs):
        """
        Search a provider and parse the results.
        :param search_strings: A dict with {mode: search value}
        :param age: Not used
        :returns: A list of search results (structure)
        """
        results = []
        if not self._check_auth():
            return results

        # Search Params
        search_params = {
            'age': '<=10800',  # Results from the past 3 hours
        }

        for mode in search_strings:
            sickrage.app.log.debug('Search mode: {}'.format(mode))

            if mode != 'RSS':
                searches = self._search_params(show_id, season, episode, mode)
            else:
                searches = [search_params]

            for search_params in searches:
                if mode != 'RSS':
                    sickrage.app.log.debug('Search string: {}'.format(search_params))

                response = self._api_call(search_params)
                if not response or response.get('results') == '0':
                    sickrage.app.log.debug('No data returned from provider')
                    continue

                results += self.parse(response.get('torrents', {}), mode)

        return results

    def parse(self, data, mode, **kwargs):
        """
        Parse search results for items.
        :param data: The raw response from a search
        :param mode: The current mode used to search, e.g. RSS
        :return: A list of items found
        """
        results = []

        torrent_rows = data.values()

        for row in torrent_rows:
            title, download_url = self._process_title_and_url(row)
            if not all([title, download_url]):
                continue

            seeders = try_int(row.get('Seeders'))
            leechers = try_int(row.get('Leechers'))
            size = try_int(row.get('Size'), -1)

            results += [{
                'title': title,
                'link': download_url,
                'size': size,
                'seeders': seeders,
                'leechers': leechers
            }]

            sickrage.app.log.debug("Found result: {}".format(title))

        return results

    @staticmethod
    def _process_title_and_url(parsed_json, **kwargs):
        # The BTN API gives a lot of information in response,
        # however SickRage is built mostly around Scene or
        # release names, which is why we are using them here.

        if 'ReleaseName' in parsed_json and parsed_json['ReleaseName']:
            title = parsed_json['ReleaseName']

        else:
            # If we don't have a release name we need to get creative
            title = ''
            if 'Series' in parsed_json:
                title += parsed_json['Series']
            if 'GroupName' in parsed_json:
                title += '.' + parsed_json['GroupName']
            if 'Resolution' in parsed_json:
                title += '.' + parsed_json['Resolution']
            if 'Source' in parsed_json:
                title += '.' + parsed_json['Source']
            if 'Codec' in parsed_json:
                title += '.' + parsed_json['Codec']
            if title:
                title = title.replace(' ', '.')

        url = parsed_json.get('DownloadURL')
        if not url:
            sickrage.app.log.debug('Download URL is missing from response for release "{}"'.format(title))
        else:
            url = url.replace('\\/', '/')

        return title, url

    def _search_params(self, show_id, season, episode, mode, season_numbering=None):
        searches = []

        show_object = find_show(show_id)
        episode_object = show_object.get_episode(season, episode)

        air_by_date = show_object.air_by_date
        sports = show_object.sports

        if not season_numbering and (air_by_date or sports):
            date_fmt = '%Y' if mode == 'Season' else '%Y.%m.%d'
            search_name = episode_object.airdate.strftime(date_fmt)
        else:
            search_name = '{type} {number}'.format(
                type='Season' if mode == 'Season' else '',
                number=episode_object.scene_season if mode == 'Season' and season else episode_num(episode_object.scene_season, episode_object.scene_episode),
            ).strip()

        params = {
            'category': mode,
            'name': search_name,
        }

        # Search
        if show_object.indexer == 1:
            params['tvdb'] = show_object.indexer_id
            params['series'] = show_object.name
            searches.append(params)

        for scene_exception in [x.split('|')[0] for x in show_object.scene_exceptions]:
            series_params = params.copy()
            series_params['series'] = sanitize_scene_name(scene_exception)
            searches.append(series_params)

        # extend air by date searches to include season numbering
        if air_by_date and not season_numbering:
            searches.extend(self._search_params(show_id, season, episode, mode, season_numbering=True))

        return searches

    def _api_call(self, params=None, results_per_page=300, offset=0):
        response = {}

        json_rpc = {
            "jsonrpc": "2.0",
            "method": "getTorrents",
            "params": [self.api_key, params or {}, results_per_page, offset],
            "id": uuid.uuid4().hex,
        }

        try:
            response = self.session.post(self.urls['api'], json=json_rpc, headers={'Content-Type': 'application/json-rpc'}).json()
            if 'error' in response:
                error = response["error"]
                message = error["message"]
                code = error["code"]
                if code == -32001:
                    sickrage.app.log.warning('Incorrect authentication credentials.')
                elif code == -32002:
                    sickrage.app.log.warning('You have exceeded the limit of 150 calls per hour.')
                elif code in (500, 502, 521, 524):
                    sickrage.app.log.warning('Provider is currently unavailable. Error: {} {}'.format(code, message))
                else:
                    sickrage.app.log.error('JSON-RPC protocol error while accessing provider. Error: {error!r}'.format(error=error))
            elif 'result' in response:
                response = response['result']
        except Exception as e:
            sickrage.app.log.warning("Error while accessing provider. Error: {}".format(e))

        return response
