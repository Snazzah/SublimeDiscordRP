import logging
import os
import time

import sublime
import sublime_plugin

from . import discord_ipc

SETTINGS_FILE = 'DiscordRichPresence.sublime-settings'
settings = {}
DISCORD_CLIENT_ID = '389368374645227520'

logger = logging.getLogger(__name__)

last_file = ''
last_edit = 0
ipc = None

start_time = time.time()


def base_activity():
    activity = {
        'assets': {'large_image': 'sublime3',
                   'large_text': 'Sublime Text 3 v%s' % (sublime.version())},
        'instance': False
    }
    if settings.get('send_start_timestamp'):
        activity['timestamps'] = {'start': start_time}
    return activity


# TODO base these on base scope name
EXT_ICON_MAP = {
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
    '.sublime-project': 'json',
    '.rs': 'rust',
    '.toml': 'toml',
    '.vue': 'vue',
    '.scss': 'scss',
    '.sass': 'sass',
    '.pug': 'pug'
}


def get_icon(ext):
    return 'lang-%s' % EXT_ICON_MAP.get(ext, "unknown")


def sizehf(num):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, 'B')
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', 'B')


def handle_activity(view, is_write=False):
    window = view.window()
    entity = view.file_name()
    if not (ipc and window and entity):
        return

    # TODO refactor these globals
    global last_file
    global last_edit
    if last_file == entity and time.time() - last_edit < 15 and not is_write:
        return

    logger.info('Updating activity')

    extension = os.path.splitext(entity)[1]
    language = os.path.splitext(os.path.basename(view.settings().get('syntax')))[0]
    format_dict = dict(
        file=os.path.basename(entity),
        extension=extension,
        lang=language,
        project=get_project_name(window, entity),
        size=view.size(),
        sizehf=sizehf(view.size()),
        folders=len(window.folders()),
    )
    last_file = entity
    last_edit = time.time()

    act = base_activity()

    details_format = settings.get('details')
    if details_format:
        act['details'] = details_format.format(**format_dict)

    state_format = settings.get('state')
    if state_format:
        act['state'] = state_format.format(**format_dict)

    if settings.get('small_icon'):
        act['assets']['small_image'] = get_icon(extension)
        act['assets']['small_text'] = language

    try:
        ipc.set_activity(act)
    except OSError as e:
        sublime.error_message("[DiscordRP] Sending activity failed."
                              "\n\nYou have been disconnected from your Discord instance."
                              " Run 'Discord Rich Presence: Connect to Discord'"
                              " after you restarted your Discord client."
                              "\n\nError: {}".format(e))
        disconnect()


def get_project_name(window, current_file):
    sources = settings.get("project_name")
    for source in sources:
        if source == "project_folder_name":
            folder = find_folder_containing_file(window.folders(), current_file)
            if folder:
                return os.path.basename(folder)
        elif source == "project_file_name":
            project_file_path = window.project_file_name()
            if project_file_path:
                return os.path.basename(os.path.dirname(current_file))
        elif source == "folder_name":
            return os.path.basename(os.path.dirname(current_file))
        else:
            logger.error("Unknown source for `project_name` setting: %r", source)

    return "No project"


def find_folder_containing_file(folders, current_file):
    for folder in folders:
        real_folder = os.path.realpath(folder)
        if os.path.realpath(current_file).startswith(real_folder):
            return folder
    return None


def is_view_active(view):
    if view:
        active_window = sublime.active_window()
        if active_window:
            active_view = active_window.active_view()
            if active_view:
                return active_view.buffer_id() == view.buffer_id()
    return False


class DRPListener(sublime_plugin.EventListener):

    def on_post_save_async(self, view):
        handle_activity(view, is_write=True)

    def on_modified_async(self, view):
        if is_view_active(view):
            handle_activity(view)


def connect():
    global ipc
    if ipc:
        logger.error("Already connected")
        return

    try:
        ipc = discord_ipc.DiscordIpcClient.for_platform(DISCORD_CLIENT_ID)
    except OSError:
        sublime.error_message("[DiscordRP] Unable to connect to Discord."
                              "\n\nPlease verify that it is running."
                              " Run 'Discord Rich Presence: Connect to Discord'"
                              " to try again.")
        return

    try:
        ipc.set_activity(base_activity())
    except OSError as e:
        sublime.error_message("[DiscordRP] Sending activity failed."
                              "\n\nYou have been disconnected from your Discord instance."
                              " Run 'Discord Rich Presence: Connect to Discord'"
                              " after you restarted your Discord client."
                              "\n\nError: {}".format(e))
        disconnect()


def disconnect():
    global ipc
    if ipc:
        # Remove detailed data before closing connection.
        # Discord will detect when the pid we passed earlier doesn't exist anymore.
        act = base_activity()
        act['details'] = "Client Disconnected"
        try:
            ipc.set_activity(act)
            ipc.close()
        except OSError:
            pass
        ipc = None


class DiscordrpConnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return not bool(ipc)

    def run(self):
        connect()


class DiscordrpReconnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return bool(ipc)

    def run(self):
        disconnect()
        connect()


class DiscordrpDisconnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return bool(ipc)

    def run(self):
        disconnect()


def plugin_loaded():
    global settings
    settings = sublime.load_settings(SETTINGS_FILE)
    if settings.get('connect_on_startup'):
        connect()


def plugin_unloaded():
    disconnect()
