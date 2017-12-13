import os
import sys
import socket
import struct
import platform
import math
import json
import numbers
import threading
from time import time

import sublime
import sublime_plugin

SETTINGS_FILE = 'DiscordRichPresence.sublime-settings'
SETTINGS = {}
DISCORD_CLIENT_ID = '389368374645227520'
ST_VERSION = str(sublime.version())
START_TIME = time()
LAST_FILE = ''
LAST_EDIT = 0
IPC = None

class DRPLangMatcher(object):
	ICONS = {
		'.js': 'javascript',
		'.py': 'python',
		'.lua': 'lua',
		'.rb': 'ruby',
		'.gemspec': 'ruby',
		'.cr': 'crystal',
		'.css': 'css',
		'.html': 'html',
		'.htm': 'html',
		'.shtml': 'html',
		'.xhtml': 'html',
		'.md': 'markdown',
		'.mdown': 'markdown',
		'.markdown': 'markdown',
		'.markdn': 'markdown',
		'.cs': 'cs',
		'.csproj': 'cs',
		'.cpp': 'cpp',
		'.php': 'php',
		'.php3': 'php',
		'.go': 'go',
		'.d': 'd',
		'.c': 'c',
		'.json': 'json',
		'.exs': 'elixir',
		'.ex': 'elixir',
		'.java': 'java',
		'.properties': 'java',
		'.ts': 'typescript',
		'.sublime-settings': 'json',
		'.sublime-snippet': 'json',
		'.sublime-theme': 'json',
		'.sublime-menu': 'json',
		'.sublime-commands': 'json',
		'.sublime-keymap': 'json',
		'.sublime-mousemap': 'json',
		'.sublime-build': 'json',
		'.sublime-macro': 'json',
		'.sublime-completions': 'json',
		'.sublime-project': 'json'
	}

	@staticmethod
	def get_icon(ext):
		try:
			return 'lang-%s' % DRPLangMatcher.ICONS[ext]
		except KeyError:
			return 'lang-unknown'

"""
Definitions equivalent to node.js Buffer
"""

def encode(op, data):
	data = json.dumps(data, separators=(',',':'))
	length = len(data)
	packet = bytearray(8 + length)
	wi32le(packet, op, 0)
	wi32le(packet, length, 4)
	ba_write(packet, data, 8, length)
	return packet

def wi32le(array, value, offset):
	value = +value
	offset = offset >> 0
	array[offset] = value if value < 256 else value-256
	array[offset + 1] = (value >> 8)
	array[offset + 2] = (value >> 16)
	array[offset + 3] = (value >> 24)
	return offset+4

def ba_write(ba, string, offset, length):
	for i in range(length):
		if not isinstance(ba[offset+i], numbers.Number):
			raise Exception("OUT_OF_BOUNDS")
		ba[offset+i] = ord(string[i])

"""
IPC Connections

  0 - HANDSHAKE
  1 - FRAME
  2 - CLOSE
  3 - PING
  4 - PONG
"""

def sizehf(num):
	for unit in ['','K','M','G','T','P','E','Z']:
		if abs(num) < 1024.0:
			return "%3.1f%s%s" % (num, unit, 'B')
		num /= 1024.0
	return "%.1f%s%s" % (num, 'Yi', 'B')

class DRPIPC(object):
	def __init__(self):
		self.open = False
		self.pipe = None

	def connect(self):
		self._connect()

	def _connect(self, id=0):
		path = get_ipc_path(id)
		self.ipc_id = id
		print('[DiscordRP] Testing pipe %s' % path)
		try:
			self.pipe = os.open(path, os.O_RDWR)
			self.open = True
			print('[DiscordRP] Sending Handshake')
			self.send({ 'v': 1, 'client_id': DISCORD_CLIENT_ID }, 0)

			act = { 'timestamps': { 'start': START_TIME }, 'assets': { 'large_image': 'sublime%s' % ST_VERSION[0], 'large_text': 'Sublime Text %s v%s' % (ST_VERSION[0], ST_VERSION) }, 'instance': False }

			if isinstance(SETTINGS.get('start_state'), basestring):
				act['state'] = SETTINGS.get('start_state')
			else:
				act['state'] = 'Just launched'

			self.set_activity(act)
		except OSError as error:
			self.on_error(error)

	def send(self, data, op=1):
		try:
			os.write(self.pipe, encode(op, data))
		except OSError:
			self.on_close()
			sublime.error_message('DiscordRP\n\nIPC was closed unexpectedly. Either you closed Discord or Discord is having network problems.\n\nIf you have closed Discord please run "Discord Rich Presence: Disconnect" after.\n\nIf you did not mean for this to happen, fix issues (and also check Discord console, Ctrl+Shift+I) and run "Discord Rich Presence: Connect to Discord"')

	def close(self):
		self.send({}, 2)
		self.on_close()

	def on_error(self, error):
		if SETTINGS.get('debug') == True:
			print('[DiscordRP] IPC recieved an error! %s' % error)
		if self.ipc_id > 9:
			if SETTINGS.get('debug') == True:
				print('[DiscordRP] IPC iteration failed. No pipes available.')
			sublime.error_message('DiscordRP\n\nCould not find IPC. Please open Discord and run "DiscordRichPresence: Connect to Discord"')
			return
		self.ipc_id += 1
		self._connect(self.ipc_id)

	def on_close(self):
		self.open = False
		print('[DiscordRP] IPC closed')

	def set_activity(self, act):
		self.send({ 'cmd': 'SET_ACTIVITY', 'args': { 'pid': os.getpid(), 'activity': act }, 'nonce': DRPSnowflake.generate() })

class DRPSnowflake(object):
	EPOCH = 1420070400000
	INCREMENT = 0
	@staticmethod
	def generate():
		if DRPSnowflake.INCREMENT >= 4095:
			DRPSnowflake.INCREMENT = 0
		DRPSnowflake.INCREMENT += 1
		left_bin = bin(int(time()*1000) - DRPSnowflake.EPOCH)[2:].rjust(42, '0')
		right_bin = bin(DRPSnowflake.INCREMENT)[2:].rjust(12, '0')
		binary = '%s0000100000%s' % (left_bin, right_bin)
		return DRPSnowflake.bin_to_id(binary)
	@staticmethod
	def bin_to_id(num):
		dec = ''
		while len(num) > 50:
			high = int(num[:-32], 2)
			low = int(bin(high % 10)[2:]+num[-32:],2)
			dec = str(low % 10) + dec
			num = bin(int(math.floor(float(high) / 10)))[2:] + bin(int(math.floor(float(low) / 10)))[2:].rjust(32, '0')
		num = int(num, 2)

		while num > 0:
			dec = str(num % 10) + dec
			num = int(math.floor(float(num) / 10))

		return dec

def get_ipc_path(id=0):
	if platform.system() == 'Windows':
		return '\\\\?\\pipe\\discord-ipc-%s' % id
	def get_env(name):
		if hasattr(os.environ, name):
			return os.environ[name]
		else:
			return None
	prefix = get_env('XDG_RUNTIME_DIR') or get_env('TMPDIR') or get_env('TMP') or get_env('TEMP') or '/tmp'
	return '%s/discord-ipc-%s' % (prefix.replace(r"\/$", ''), id)

def handle_activity(view, is_write=False):
	window = view.window()
	if window is not None and IPC.open == True:
		entity = view.file_name()
		if entity:
			global LAST_FILE
			global LAST_EDIT
			if LAST_FILE == entity and time() - LAST_EDIT < 59 and not is_write:
				return
			project = window.project_data() if hasattr(window, 'project_data') else None
			folders = window.folders()
			extension = os.path.splitext(entity)[1]
			LAST_FILE = entity
			LAST_EDIT = time()
			if SETTINGS.get('debug') == True:
				print('[DiscordRP] Updating activity')

			act = { 'timestamps': { 'start': START_TIME }, 'assets': { 'large_image': 'sublime%s' % ST_VERSION[0], 'large_text': 'Sublime Text %s v%s' % (ST_VERSION[0], ST_VERSION) }, 'instance': False }

			if isinstance(SETTINGS.get('details'), basestring):
				act['details'] = parse_line(SETTINGS.get('details'), view, entity, window, folders)

			if isinstance(SETTINGS.get('state'), basestring):
				act['state'] = parse_line(SETTINGS.get('state'), view, entity, window, folders)
			else:
				act['state'] = "Editing Files"

			if SETTINGS.get('small_icon') == True:
				act['assets']['small_image'] = DRPLangMatcher.get_icon(extension)
				act['assets']['small_text'] = os.path.splitext(os.path.basename(view.settings().get('syntax')))[0]

			IPC.set_activity(act)

def parse_line(string, view, entity, window, folders):
	extension = os.path.splitext(entity)[1]
	return string.format(
		file = os.path.basename(entity),
		extension = extension,
		lang = os.path.splitext(os.path.basename(view.settings().get('syntax')))[0],
		project = find_project_from_folders(folders, entity),
		size = view.size(),
		sizehf = sizehf(view.size()),
		folders = len(window.folders())
	)

def plugin_loaded():

def plugin_unloaded():
	print('[DiscordRP] Unloading')
	if IPC.open == True:
		IPC.close()

def find_folder_containing_file(folders, current_file):
	parent_folder = None
	current_folder = current_file
	while True:
		for folder in folders:
			if os.path.realpath(os.path.dirname(current_folder)) == os.path.realpath(folder):
				parent_folder = folder
				break
		if parent_folder is not None:
			break
		if not current_folder or os.path.dirname(current_folder) == current_folder:
			break
		current_folder = os.path.dirname(current_folder)

	return parent_folder

def find_project_from_folders(folders, current_file):
	folder = find_folder_containing_file(folders, current_file)
	return os.path.basename(folder) if folder and not SETTINGS.get('pick_folder_over_project') == True else current_file.split('\\')[-2]

def is_view_active(view):
	if view:
		active_window = sublime.active_window()
		if active_window:
			active_view = active_window.active_view()
			if active_view:
				return active_view.buffer_id() == view.buffer_id()
	return False

class DRPListener(sublime_plugin.EventListener):

	def on_post_save(self, view):
		handle_activity(view, is_write=True)

	def on_modified(self, view):
		if is_view_active(view):
			handle_activity(view)

class DiscordrpConnectCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		IPC.connect()

class DiscordrpDisconnectCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		if IPC.open == True:
			IPC.close()

class DiscordrpRefreshSettingsCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		SETTINGS = sublime.load_settings(SETTINGS_FILE)

""" plugin_loaded() """

SETTINGS = sublime.load_settings(SETTINGS_FILE)
print('[DiscordRP] Loaded')
IPC = DRPIPC()
if not SETTINGS.get('connect_on_startup') == True:
	return
print('[DiscordRP] Starting IPC with client id %s' % DISCORD_CLIENT_ID)
IPC.connect()