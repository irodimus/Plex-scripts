#!/usr/bin/python3
#-*- coding: utf-8 -*-

"""
The use case of this script is the following:
	Export plex metadata to a file that can then be imported back later
Requirements (python3 -m pip install [requirement]):
	requests
Setup:
	Fill the variables below firstly, then run the script.
"""

plex_ip = ''
plex_port = ''
plex_api_token = ''

#ADVANCED SETTINGS
#Hardcode the folder where the plex database is in
#Leave empty unless really needed
database_folder = ''

from os import getenv, path
from sqlite3 import connect
from re import findall
from datetime import datetime
from time import perf_counter

# Environmental Variables
plex_ip = getenv('plex_ip', plex_ip)
plex_port = getenv('plex_port', plex_port)
plex_api_token = getenv('plex_api_token', plex_api_token)
base_url = f"http://{plex_ip}:{plex_port}"

media_types = {
	'movie': (
		(
			'title', 'titleSort', 'originalTitle',
			'originallyAvailableAt', 'contentRating', 'userRating',
			'studio', 'tagline', 'summary',
			'Genre', 'Writer', 'Director', 'Collection'
		),
		1,
		"""
		CREATE TABLE IF NOT EXISTS movie (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			titleSort TEXT,
			originalTitle TEXT,
			originallyAvailableAt TEXT,
			contentRating INTEGER,
			userRating INTEGER,
			studio TEXT,
			tagline TEXT,
			summary TEXT,
			Genre TEXT,
			Writer TEXT,
			Director TEXT,
			Collection TEXT,
			watched_status TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'show': (
		(
			'title', 'titleSort', 'originalTitle',
			'originallyAvailableAt', 'contentRating', 'userRating',
			'studio', 'tagline', 'summary',
			'Genre', 'Collection'
		),
		2,
		"""
		CREATE TABLE IF NOT EXISTS show (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			titleSort TEXT,
			originalTitle TEXT,
			originallyAvailableAt TEXT,
			contentRating INTEGER,
			userRating INTEGER,
			studio TEXT,
			tagline TEXT,
			summary TEXT,
			Genre TEXT,
			Collection TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'season': (
		(
			'title', 'summary'
		),
		3,
		"""
		CREATE TABLE IF NOT EXISTS season (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			summary TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'episode': (
		(
			'title', 'titleSort',
			'originallyAvailableAt', 'contentRating', 'userRating',
			'summary',
			'Writer', 'Director'
		),
		4,
		"""
		CREATE TABLE IF NOT EXISTS episode (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			titleSort TEXT,
			originallyAvailableAt TEXT,
			contentRating INTEGER,
			userRating INTEGER,
			summary TEXT,
			Writer TEXT,
			Director TEXT,
			intro_start INTEGER,
			intro_end INTEGER,
			watched_status TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'artist': (
		(
			'title', 'titleSort', 'summary',
			'Genre', 'Style', 'Mood', 'Country', 'Collection', 'Similar'
		),
		8,
		"""
		CREATE TABLE IF NOT EXISTS artist (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			titleSort TEXT,
			summary TEXT,
			Genre TEXT,
			Style TEXT,
			Mood TEXT,
			Country TEXT,
			Collection TEXT,
			Similar TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'album': (
		(
			'title', 'titleSort',
			'originallyAvailableAt', 'contentRating', 'userRating',
			'studio','summary',
			'Genre', 'Style', 'Mood', 'Collection'
		),
		9,
		"""
		CREATE TABLE IF NOT EXISTS album (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			titleSort TEXT,
			originallyAvailableAt TEXT,
			contentRating INTEGER,
			userRating INTEGER,
			studio TEXT,
			summary TEXT,
			Genre TEXT,
			Style TEXT,
			Mood TEXT,
			Collection TEXT,
			poster BLOB,
			art BLOB
		);
		"""
	),
	'track': (
		(
			'title', 'originalTitle',
			'contentRating', 'userRating', '[index]', 'parentIndex',
			'Mood'
		),
		10,
		"""
		CREATE TABLE IF NOT EXISTS track (
			rating_key TEXT UNIQUE,
			guid TEXT UNIQUE,
			updated_at INTEGER,
			title TEXT NOT NULL,
			originalTitle TEXT,
			contentRating INTEGER,
			userRating INTEGER,
			[index] INTEGER,
			parentIndex INTEGER,
			Mood TEXT
		);
		"""
	)
}

def _leave(db, plex_db=None):
	print('Shutting down...')
	db.commit()
	if plex_db != None:
		plex_db.commit()
	print('Progress saved')
	exit(0)

def _export(
		type: str, data: dict, ssn, cursor, user_data: tuple, watched_map: dict, timestamp_map: dict,
		target_metadata: bool, target_watched: bool, target_intro_markers: bool,
		target_poster: bool, target_episode_poster: bool, target_art: bool, target_episode_art: bool
	):
	user_ids, user_tokens = user_data

	#extract different data based on the type
	if type in media_types:
		keys = media_types[type][0]
	else:
		#unknown type of source
		return 'Unknown source type when trying to extract data (internal error)'

	rating_key = data['ratingKey']

	#skip media if it hasn't been edited since last time (or it isn't matched to any series)
	updated_at = timestamp_map[type].get(rating_key)
	if updated_at != None:
		if updated_at == data['updatedAt']:
			return
		else:
			cursor.execute(f"DELETE FROM {type} WHERE rating_key = {rating_key}")
	if not 'Guid' in data: return

	#request certain media again when we need it's metadata (lib output doesn't show all)
	if (target_metadata == True and type in ('movie','show','episode','artist','album','track')) or (target_intro_markers == True and type == 'episode'):
		media_info = ssn.get(f'{base_url}/library/metadata/{rating_key}', params={'includeGuids': '1', 'includeMarkers': '1'})
		if media_info.status_code != 200: return
		media_info = media_info.json()['MediaContainer']['Metadata'][0]
	else:
		media_info = data

	#extract data and built up key-value pair for db
	db_keys = ['rating_key','guid','updated_at']
	db_values = [rating_key,str(media_info['Guid']),media_info.get('updatedAt',0)]
	if target_metadata == True:
		for key in keys:
			if key[0].isupper():
				value = ",".join([x['tag'] for x in media_info.get(key, [])])
				if value == '': value = ''
			elif key == '[index]':
				value = media_info.get('index', None)
			elif key == 'titleSort' and type != 'track':
				value = media_info.get('titleSort', media_info.get('title', ''))
			else:
				value = media_info.get(key, None)
			if value != None:
				db_keys.append(key)
				db_values.append(value)

	if target_watched == True and type in ('movie','episode'):
		db_keys.append('watched_status')
		db_watched = ['_admin',str(media_info.get('viewOffset', 'viewCount' in media_info))]
		for user_id, user_token in zip(user_ids, user_tokens):
			db_watched += [user_id, watched_map[user_token].get(rating_key,'')]
		db_values.append(",".join(db_watched))

	if target_intro_markers == True and type in 'episode':
		for marker in media_info.get('Marker',[]):
			if marker['type'] == 'intro':
				#intro marker found
				db_keys += ['intro_start','intro_end']
				db_values += [marker['startTimeOffset'], marker['endTimeOffset']]
				break

	if (target_poster == True and type in ('movie','show','season','artist','album')) or (target_episode_poster == True and type == 'episode'):
		if 'thumb' in media_info:
			r = ssn.get(f'{base_url}{media_info["thumb"]}')
			if r.status_code == 200:
				db_keys.append('poster')
				db_values.append(r.content)

	if (target_art == True and type in ('movie','show','season','artist','album')) or (target_episode_art == True and type == 'episode'):
		if 'art' in media_info:
			r = ssn.get(f'{base_url}{media_info["art"]}')
			if r.status_code == 200:
				db_keys.append('art')
				db_values.append(r.content)

	#write to the database
	comm = f"""
	INSERT INTO {type} ({",".join(db_keys)})
	VALUES ({",".join(['?'] * len(db_keys))})
	"""
	cursor.execute(comm, db_values)

	return

def _import(
		type: str, data: dict, ssn, cursor, media_lib_id: str, user_data: tuple, watched_map: dict, timestamp_map: dict,
		target_metadata: bool, target_watched: bool, target_intro_markers: bool,
		target_poster: bool, target_episode_poster: bool, target_art: bool, target_episode_art: bool,
		plex_cursor=None
	):
	#import different data based on the type
	if type in media_types:
		media_type = media_types[type][1]
	else:
		return 'Unknown source type when trying to import data (internal error)'
	user_ids, user_tokens = user_data

	rating_key = data['ratingKey']
	if not 'Guid' in data: return

	#request certain media again when we need it's metadata (lib output doesn't show all)
	if target_metadata == True and type in ('movie','show','episode','artist','album','track'):
		media_info = ssn.get(f'{base_url}/library/metadata/{rating_key}', params={'includeGuids': '1', 'includeMarkers': '1'})
		if media_info.status_code != 200: return
		media_info = media_info.json()['MediaContainer']['Metadata'][0]
	else:
		media_info = data

	#find media in database
	guid = str(media_info['Guid'])
	cursor.execute(f"SELECT * FROM {type} WHERE guid = ?", [guid])
	target = cursor.fetchone()
	if target == None: return
	cursor.execute(f"SELECT * FROM {type} LIMIT 1;")
	target_keys = next(zip(*cursor.description))

	#import data
	if target_metadata == True:
		payload = {
			'type': media_type,
			'id': rating_key,
			'thumb.locked': 1,
			'art.locked': 1
		}
		if type == 'album':
			payload['artist.id.value'] = data['parentRatingKey']

		#build the payload that sets all the values
		for option, value in zip(target_keys[3:], target[3:]):
			if option in ('poster','art','watched_status','intro_start','intro_end'): continue
			elif option[0].isupper():
				#list of labels
				value = value.split(",")
				lower_option = option.lower()
				#add tags
				for offset, list_item in enumerate(value):
					payload[f'{lower_option}[{offset}].tag.tag'] = list_item
				#remove other tags
				if option in media_info:
					payload[f'{lower_option}[].tag.tag-'] = ",".join(map(lambda x: x['tag'], media_info[option]))
				payload[f'{lower_option}.locked'] = 1
			else:
				#normal key value pair
				payload[f'{option}.value'] = value or ''
				payload[f'{option}.locked'] = 1

		#upload to plex
		ssn.put(f'{base_url}/library/sections/{media_lib_id}/all', params=payload)

	if 'poster' in target_keys and ((type != 'episode' and target_poster == True) or (type == 'episode' and target_episode_poster == True)):
		ssn.post(f'{base_url}/library/metadata/{rating_key}/posters', data=target[target_keys.index('poster')])

	if 'art' in target_keys and ((type != 'episode' and target_art == True) or (type == 'episode' and target_episode_art == True)):
		ssn.post(f'{base_url}/library/metadata/{rating_key}/arts', data=target[target_keys.index('art')])

	if 'watched_status' in target_keys and target_watched == True:
		watched_info = target[target_keys.index('watched_status')].split(',')
		for user, watched_state in zip(watched_info[::2], watched_info[1::2]):
			if user == '_admin': user_token = plex_api_token
			else: user_token = user_tokens[user_ids.index(user)]

			#set watched status of media for this user
			if watched_state == 'True':
				#mark watched
				ssn.get(f'{base_url}/:/scrobble', params={'identifier': 'com.plexapp.plugins.library', 'key': rating_key, 'X-Plex-Token': user_token})
			elif watched_state == 'False':
				#mark not-watched
				ssn.get(f'{base_url}/:/unscrobble', params={'identifier': 'com.plexapp.plugins.library', 'key': rating_key, 'X-Plex-Token': user_token})
			elif watched_state.isdigit():
				#mark partially watched
				ssn.get(f'{base_url}/:/progress', params={'identifier': 'com.plexapp.plugins.library', 'key': rating_key, 'time': watched_state, 'state': 'stopped', 'X-Plex-Token': user_token})

	if 'intro_start' in target_keys and 'intro_end' in target_keys and target_intro_markers == True:
		#check if media already has intro marker
		plex_cursor.execute(f"SELECT * FROM taggings WHERE text = 'intro' AND metadata_item_id = '{rating_key}';")
		if plex_cursor.fetchone() == None:
			#no intro marker exists so create one
			d = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
			plex_cursor.execute("SELECT tag_id FROM taggings WHERE text = 'intro' LIMIT 1;")
			i = plex_cursor.fetchone()
			if i == None:
				#no id yet for intro's so make one that isn't taken yet
				plex_cursor.execute("SELECT tag_id FROM taggings ORDER BY tag_id DESC LIMIT 1;")
				i = int(plex_cursor.fetchone()[0]) + 1
			else:
				i = i[0]
			plex_cursor.execute(f"INSERT INTO taggings (metadata_item_id,tag_id,[index],text,time_offset,end_time_offset,thumb_url,created_at,extra_data) VALUES ({rating_key},{i},0,'intro',{target[target_keys.index('intro_start')]},{target[target_keys.index('intro_end')]},'','{d}','pv%3Aversion=5');")
		else:
			#intro marker exists so update timestamps
			plex_cursor.execute(f"UPDATE taggings SET time_offset = '{target[target_keys.index('intro_start')]}' WHERE text = 'intro' AND metadata_item_id = '{rating_key}';")
			plex_cursor.execute(f"UPDATE taggings SET end_time_offset = '{target[target_keys.index('intro_end')]}' WHERE text = 'intro' AND metadata_item_id = '{rating_key}';")

	return

def _reset(
		type: str, data: dict, ssn, cursor, media_lib_id: str, watched_map: dict, timestamp_map: dict,
		target_metadata: bool, target_poster: bool, target_art: bool
	):
	#reset different data based on the type
	if type in media_types:
		keys, media_type = media_types[type][:2]
	else:
		return 'Unknown source type when trying to reset data (internal error)'

	#set all fields to unlocked in plex
	rating_key = data['ratingKey']
	payload = {
		'type': media_type,
		'id': rating_key
	}
	if target_poster == True:
		payload['thumb.locked'] = 0
	if target_art == True:
		payload['art.locked'] = 0
	if target_metadata == True:
		for key in keys:
			if key[0].isupper():
				payload[f'{key.lower()}.locked'] = 0
			else:
				payload[f'{key}.locked'] = 0

	ssn.put(f'{base_url}/library/sections/{media_lib_id}/all', params=payload)

	return

def plex_exporter_importer(
		verbose: bool, ssn, type: str, process: list, location: str,
		all: bool, all_movie: bool=False, all_show: bool=False, all_music: bool=False,
		library_name: str=None,
		movie_name: str=None,
		series_name: str=None, season_number: int=None, episode_number: int=None,
		artist_name: str=None, album_name: str=None, track_name: str=None
	):
	result_json, watched_map, timestamp_map = [], {}, {}

	#check for illegal arg parsing
	if not type in ('import','export','reset'):
		return 'Invalid value for "type"'
	if type == 'export':
		if path.isdir(location):
			database_file = path.join(location, f'{path.splitext(__file__)[0]}.db')
			print(f'Exporting to {database_file}')
			if path.isfile(database_file):
				print('Database file already exists, so updating')

		elif path.isfile(location):
			database_file = location
			print(f'Exporting to {database_file} (Updating)')

		else:
			return 'Location not found'

	elif type == 'import':
		if path.isfile(location):
			database_file = location
			print(f'Importing from {database_file}')
		else:
			return 'Location not found'

		if 'intro_marker' in process:
			#importing intro markers requires root and access to target plex database file
			from os import geteuid
			if geteuid() != 0:
				return 'Intro Marker importing is requested but script is not run as root'

			#get location to database file
			if database_folder == '':
				db_folder = [s['value'] for s in ssn.get(f'{base_url}/:/prefs').json()['MediaContainer']['Setting'] if s['id'] == 'ButlerDatabaseBackupPath'][0]
			db_file = path.join(db_folder, 'com.plexapp.plugins.library.db')
			if not path.isfile(db_file):
				return 'Intro Marker importing is requested but script is not run on target plex server, or value of database_folder is invalid'

			#setup db connection
			plex_db = connect(db_file)

	elif type == 'reset':
		if path.isdir(location):
			database_file = path.join(location, f'{path.splitext(__file__)[0]}.db')
		elif path.isfile(location):
			database_file = location
		else:
			return 'Location not found'

	if all == True:
		print(f'{type.capitalize()}ing complete plex library')
		lib_target_specifiers = (library_name,movie_name,series_name,season_number,episode_number,artist_name,album_name,track_name)
		if lib_target_specifiers.count(None) < len(lib_target_specifiers) or any((all_movie,all_show,all_music)):
			return 'Both "all" and a target-specifier are set'

	else:
		if not any((all_movie,all_show,all_music)) and library_name == None:
			return '"all" is set to False but no target-specifier is given'
		if season_number != None and series_name == None:
			return '"season_number" is set but not "series_name"'
		if episode_number != None and (season_number == None or series_name == None):
			return '"episode_number" is set but not "season_number" or "series_name"'
		if album_name != None and artist_name == None:
			return '"album_name" is set but not "artist_name"'
		if track_name != None and (album_name == None or artist_name == None):
			return '"track_name" is set but not "album_name" or "artist_name"'
	print('')

	#setup variables
	db = connect(database_file)
	cursor = db.cursor()
	for media_type in media_types.values():
		cursor.execute(media_type[2])

	machine_id = ssn.get(f'{base_url}/').json()['MediaContainer']['machineIdentifier']
	shared_users = ssn.get(f'http://plex.tv/api/servers/{machine_id}/shared_servers', headers={}).text
	user_ids = findall(r'(?<=userID=")\d+(?=")', shared_users)
	user_tokens = findall(r'(?<=accessToken=")\S+(?=")', shared_users)
	user_data = user_ids, user_tokens
	if type == 'export':
		method = _export
	elif type == 'import':
		method = _import
	elif type == 'reset':
		method = _reset
	args = {
		'ssn': ssn,
		'cursor': cursor,
		'target_poster': 'poster' in process,
		'target_art': 'art' in process,
		'target_metadata': 'metadata' in process
	}
	if type in ('export','import'):
		args['user_data'] = user_data
		args['target_episode_poster'] = 'episode_poster' in process
		args['target_episode_art'] = 'episode_art' in process
		args['target_watched'] = 'watched_status' in process
		args['target_intro_markers'] = 'intro_marker' in process
	exit_args = {
		'db': db
	}
	if type == 'import' and 'intro_marker' in process:
		args['plex_cursor'] = plex_db.cursor()
		exit_args['plex_db'] = plex_db

	#start working on the media
	sections = ssn.get(f'{base_url}/library/sections').json()['MediaContainer'].get('Directory',[])
	for lib in sections:
		if not (all == True \
		or (library_name != None and lib['title'] == library_name) \
		or (all_movie == True and lib['type'] == 'movie') \
		or (all_show == True and lib['type'] == 'show') \
		or (all_music == True and lib['type'] == 'artist')):
			#a specific library is targeted and this one is not it, so skip
			continue

		#this library (or something in it) should be processed
		print(lib['title'])
		if type in ('import','reset'):
			args['media_lib_id'] = lib['key']
		lib_output = ssn.get(f'{base_url}/library/sections/{lib["key"]}/all', params={'includeGuids': '1'})
		if lib_output.status_code != 200: continue
		lib_output = lib_output.json()['MediaContainer'].get('Metadata',[])

		if lib['type'] in ('movie','show') and type == 'export' and 'watched_status' in process:
			#create watched map for every user to reduce requests
			for user_token in user_tokens:
				user_lib_output = ssn.get(f'{base_url}/library/sections/{lib["key"]}/all', params={'X-Plex-Token': user_token, 'type': '4' if lib['type'] == 'show' else '1'})
				if user_lib_output.status_code != 200: continue
				user_lib_output = user_lib_output.json()['MediaContainer'].get('Metadata', [])
				watched_map[user_token] = {}
				for media in user_lib_output:
					watched_map[user_token][media['ratingKey']] = str(media.get('viewOffset', 'viewCount' in media))

		if type == 'export' and not lib['type'] in timestamp_map:
			if lib['type'] == 'show':
				lib_types = ['show','season','episode']
			elif lib['type'] == 'artist':
				lib_types = ['artist','album','track']
			else:
				lib_types = [lib['type']]

			for lib_type in lib_types:
				timestamp_map[lib_type] = {}
				cursor.execute(f"SELECT rating_key, updated_at FROM {lib_type};")
				for time_key, time_stamp in cursor.fetchall():
					timestamp_map[lib_type][time_key] = time_stamp

		if lib['type'] == 'movie':
			for movie in lib_output:
				if movie_name != None and movie['title'] != movie_name:
					continue

				if verbose == True: print(f'	{movie["title"]}')
				try:
					response = method(type='movie', data=movie, watched_map=watched_map, timestamp_map=timestamp_map, **args)
				except KeyboardInterrupt:
					_leave(**exit_args)
				else:
					if isinstance(response, str): return response
					else: result_json.append(movie['ratingKey'])

				if movie_name != None:
					break
			else:
				if movie_name != None:
					return 'Movie not found'

		elif lib['type'] == 'show':
			for show in lib_output:
				if series_name != None and show['title'] != series_name:
					continue

				season_info = ssn.get(f'{base_url}{show["key"]}', params={'includeGuids': '1'})
				if season_info.status_code != 200: continue
				season_info = season_info.json()['MediaContainer']['Metadata']
				if verbose == True: print(f'	{show["title"]}')
				#process show
				show_info = ssn.get(f'{base_url}/library/metadata/{show["ratingKey"]}').json()['MediaContainer']['Metadata'][0]
				try:
					response = method(type='show', data=show_info, watched_map=watched_map, timestamp_map=timestamp_map, **args)
				except KeyboardInterrupt:
					_leave(**exit_args)
				else:
					if isinstance(response, str): return response
					else: result_json.append(show['ratingKey'])

				#process seasons
				for season in season_info:
					if season_number != None and season['index'] != season_number:
						continue

					try:
						response = method(type='season', data=season, watched_map=watched_map, timestamp_map=timestamp_map, **args)
					except KeyboardInterrupt:
						_leave(**exit_args)
					else:
						if isinstance(response, str): return response
						else: result_json.append(season['ratingKey'])

					if season_number != None:
						break
				else:
					if season_number != None:
						return 'Season not found'

				#process episodes
				episode_info = ssn.get(f'{base_url}/library/metadata/{show["ratingKey"]}/allLeaves', params={'includeGuids': '1'}).json()['MediaContainer']['Metadata']
				for episode in episode_info:
					if season_number != None and episode['parentIndex'] != season_number:
						continue
					if episode_number != None and episode['index'] != episode_number:
						continue

					if verbose == True: print(f'		S{episode["parentIndex"]}E{episode["index"]} - {episode["title"]}')
					try:
						response = method(type='episode', data=episode, watched_map=watched_map, timestamp_map=timestamp_map, **args)
					except KeyboardInterrupt:
						_leave(**exit_args)
					else:
						if isinstance(response, str): return response
						else: result_json.append(episode['ratingKey'])

					if episode_number != None:
						break
				else:
					if episode_number != None:
						return 'Episode not found'

				if series_name != None:
					break
			else:
				if series_name != None:
					return 'Series not found'

		elif lib['type'] == 'artist':
			for artist in lib_output:
				if artist_name != None and artist['title'] != artist_name:
					continue

				album_info = ssn.get(f'{base_url}{artist["key"]}', params={'includeGuids': '1'})
				if album_info.status_code != 200: continue
				album_info = album_info.json()['MediaContainer']['Metadata']
				if verbose == True: print(f'	{artist["title"]}')
				#process artist
				artist_info = ssn.get(f'{base_url}/library/metadata/{artist["ratingKey"]}').json()['MediaContainer']['Metadata'][0]
				try:
					response = method(type='artist', data=artist_info, watched_map=watched_map, timestamp_map=timestamp_map, **args)
				except KeyboardInterrupt:
					_leave(**exit_args)
				else:
					if isinstance(response, str): return response
					else: result_json.append(artist['ratingKey'])

				#process albums
				for album in album_info:
					if album_name != None and album['title'] != album_name:
						continue

					try:
						response = method(type='album', data=album, watched_map=watched_map, timestamp_map=timestamp_map, **args)
					except KeyboardInterrupt:
						_leave(**exit_args)
					else:
						if isinstance(response, str): return response
						else: result_json.append(album['ratingKey'])

					if album_name != None:
						break
				else:
					if album_name != None:
						return 'Album not found'

				#process tracks
				track_info = ssn.get(f'{base_url}/library/metadata/{artist["ratingKey"]}/allLeaves', params={'includeGuids': '1'}).json()['MediaContainer']['Metadata']
				for track in track_info:
					if album_name != None and track['parentTitle'] != album_name:
						continue
					if track_name != None and track['title'] != track_name:
						continue

					if verbose == True: print(f'		D{track["parentIndex"]}T{track["index"]} - {track["title"]}')
					try:
						response = method(type='track', data=track, watched_map=watched_map, timestamp_map=timestamp_map, **args)
					except KeyboardInterrupt:
						_leave(**exit_args)
					else:
						if isinstance(response, str): return response
						else: result_json.append(track['ratingKey'])

					if track_name != None:
						break
				else:
					if track_name != None:
						return 'Track not found'

				if artist_name != None:
					break
			else:
				if artist_name != None:
					return 'Artist not found'

		else:
			print('	Library not supported')

		if library_name != None:
			break
	else:
		if library_name != None:
			return 'Library not found'

	#save the database
	db.commit()
	if 'intro_marker' in process and type == 'import':
		plex_db.commit()

	return result_json

if __name__ == '__main__':
	from requests import Session
	from argparse import ArgumentParser, RawDescriptionHelpFormatter

	#setup vars
	ssn = Session()
	ssn.headers.update({'Accept':'application/json'})
	ssn.params.update({'X-Plex-Token': plex_api_token})

	#setup arg parsing
	epilog = """-------------------
EPILOG

If you want to use the "intro_marker" feature when importing, it is REQUIRED that the script is run on the server on which the targeted plex server is too and that the script is run using the root user (administrative user).

-L/--Location
	When exporting, you might want to set a different folder to put the database file in (default is script folder),
	which you can set using the -L/--Location option.

	When exporting after already having a database created (e.g. you run the script weekly),
	pass the path to the already existing database to update that one instead of making a new one (STRONGLY RECOMMENDED).

	When importing, it\'s required to pass the path to the database file as the value.
"""
	parser = ArgumentParser(formatter_class=RawDescriptionHelpFormatter, description='Export plex metadata to a database that can then be imported back later', epilog=epilog)
	parser.add_argument('-t','--Type', choices=['import','export','reset'], required=True, type=str, help='Either export/import plex metadata or reset import (unlock all fields)')
	parser.add_argument('-p','--Process', choices=['metadata','watched_status','poster','episode_poster','art','episode_art','intro_marker'], help='EXPORT/IMPORT ONLY: Select what to export/import; this argument can be given multiple times to select multiple things', action='append', required=True)
	parser.add_argument('-L','--Location', type=str, help='SEE EPILOG', default='.')
	parser.add_argument('-v','--Verbose', help='Make script more verbose', action='store_true')

	#args regarding target selection
	#general selectors
	parser.add_argument('-a','--All', action='store_true', help='Target every media item in every library (use with care!)')
	parser.add_argument('--AllMovie', action='store_true', help='Target all movie libraries')
	parser.add_argument('--AllShow', action='store_true', help='Target all show libraries')
	parser.add_argument('--AllMusic', action='store_true', help='Target all music libraries')
	parser.add_argument('-l','--LibraryName', type=str, help='Target a specific library based on it\'s name (movie, show and music libraries supported)')
	#movie selectors
	parser.add_argument('-m','--MovieName', type=str, help='Target a specific movie inside a movie library based on it\'s name (only accepted when -l is a movie library)')
	#show selectors
	parser.add_argument('-s','--SeriesName', type=str, help='Target a specific series inside a show library based on it\'s name (only accepted when -l is a show library)')
	parser.add_argument('-S','--SeasonNumber', type=int, help='Target a specific season inside the targeted series based on it\'s number (only accepted when -s is given) (specials is 0)')
	parser.add_argument('-e','--EpisodeNumber', type=int, help='Target a specific episode inside the targeted season based on it\'s number (only accepted when -S is given)')
	#music selectors
	parser.add_argument('-A','--ArtistName', type=str, help='Target a specific artist inside a music library based on it\'s name (only accepted when -l is a music library)')
	parser.add_argument('-d','--AlbumName', type=str, help='Target a specific album inside the targeted artist based on it\'s name (only accepted when -A is given)')
	parser.add_argument('-T','--TrackName', type=str, help='Target a specific track inside the targeted album based on it\'s name (only accepted when -d is given)')

	args = parser.parse_args()
	#get general info about targets, check for illegal arg parsing and call functions

	start_time = perf_counter()
	response = plex_exporter_importer(
		verbose=args.Verbose, ssn=ssn, type=args.Type, process=args.Process, location=args.Location,
		all=args.All, all_movie=args.AllMovie, all_show=args.AllShow, all_music=args.AllMusic,
		library_name=args.LibraryName,
		movie_name=args.MovieName,
		series_name=args.SeriesName, season_number=args.SeasonNumber, episode_number=args.EpisodeNumber,
		artist_name=args.ArtistName, album_name=args.AlbumName, track_name=args.TrackName
	)
	print(f'Time: {round(perf_counter() - start_time, 3)}s')
	if not isinstance(response, list):
		if response == 'Both "all" and a target-specifier are set':
			parser.error('Both -a/--All and a target-specifier are set')
		elif response == '"all" is set to False but no target-specifier is given':
			parser.error('-a/--All is not set but also no target-specifier is set')
		elif response == '"season_number" is set but not "series_name"':
			parser.error('-S/--SeasonNumber is set but not -s/--SeriesName')
		elif response == '"episode_number" is set but not "season_number" or "series_name"':
			parser.error('-e/--EpisodeNumber is set but not -S/--SeasonNumber or -s/--SeriesName')
		elif response == '"album_name" is set but not "artist_name"':
			parser.error('-d/--AlbumName is set but not -A/--ArtistName')
		elif response == '"track_name" is set but not "album_name" or "artist_name"':
			parser.error('-T/--TrackName is set but not -d/--AlbumName or -A/--ArtistName')
		else:
			parser.error(response)
