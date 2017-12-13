import logging
import os
import time

import sublime
import sublime_plugin

from . import discord_ipc

SETTINGS_FILE = 'DiscordRichPresence.sublime-settings'
settings = {}
DISCORD_CLIENT_ID = '389368374645227520'
ST_VERSION = str(sublime.version())
start_time = time.time()

last_file = ''
last_edit = 0
ipc = None

logger = logging.getLogger(__name__)


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
    '.sublime-project': 'json'
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
    if last_file == entity and time.time() - last_edit < 59 and not is_write:
        return

    folders = window.folders()
    extension = os.path.splitext(entity)[1]
    last_file = entity
    last_edit = time.time()
    language = os.path.splitext(os.path.basename(view.settings().get('syntax')))[0]
    logger.info('Updating activity')

    act = {'timestamps': {'start': start_time},
           'assets': {'large_image': 'sublime3',
                      'large_text': 'Sublime Text 3 v%s' % (sublime.version())},
           'instance': False}

    details_format = settings.get('details')
    if details_format:
        act['details'] = format_line(details_format, view, entity, language, folders)

    state_format = settings.get('state')
    if state_format:
        act['state'] = format_line(state_format, view, entity, language, folders)
    else:
        act['state'] = "Editing Files"

    if settings.get('small_icon'):
        act['assets']['small_image'] = get_icon(extension)
        act['assets']['small_text'] = language

    ipc.set_activity(act)


def format_line(string, view, entity, language, folders):
    extension = os.path.splitext(entity)[1]
    return string.format(
        file=os.path.basename(entity),
        extension=extension,
        lang=language,
        project=find_project_from_folders(folders, entity),
        size=view.size(),
        sizehf=sizehf(view.size()),
        folders=len(folders)
    )


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
    return (os.path.basename(folder)
            if folder and not settings.get('pick_folder_over_project')
            else os.path.basename(os.path.dirname(current_file)))


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
        global ipc
        ipc = discord_ipc.DiscordIpcClient.for_platform()


class DiscordrpDisconnectCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        global ipc
        if ipc:
            ipc.close()
            ipc = None


def plugin_loaded():
    global ipc, settings
    settings = sublime.load_settings(SETTINGS_FILE)
    if settings.get('connect_on_startup'):
        ipc = discord_ipc.DiscordIpcClient.for_platform(DISCORD_CLIENT_ID)


def plugin_unloaded():
    global ipc
    if ipc:
        ipc.close()
        ipc = None
