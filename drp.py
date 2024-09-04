from functools import partial
import logging
import os
import time
import re
import subprocess
from time import mktime

import sublime
import sublime_plugin

from . import discord_ipc

SETTINGS_FILE = 'DiscordRichPresence.sublime-settings'
settings = {}
DISCORD_CLIENT_ID = '389368374645227520'
RECONNECT_DELAY = 15000

logger = logging.getLogger(__name__)

last_file = ''
last_edit = 0
ipc = None
is_connecting = False

start_time = mktime(time.localtime())
stamp = start_time


def base_activity(started=False):
    activity = {
        'assets': {
            'small_image': 'afk',
            'small_text': 'Idle',
            'large_image': 'sublime3',
            'large_text': 'Sublime Text v%s' % (sublime.version())
        },
        'state': settings.get('start_state') if started else 'Idle'
    }
    if settings.get('big_icon'):
        activity['assets'] = {
            'large_image': 'afk',
            'large_text': 'Idle',
            'small_image': 'sublime3',
            'small_text': 'Sublime Text v%s' % (sublime.version())
        }
    return activity


# List of extensions mapped to language names.
ICONS = {
    'asm': 'assembly',
    'ahk': 'ahk',
    'c,h': 'c',
    'clj,cljs,edn': 'clojure',
    'coffeescript,coffee': 'coffeescript',
    'cpp,hpp,cc,hxx,cxx': 'cpp',
    'cr': 'crystal',
    'cs': 'cs',
    'css': 'css',
    'd': 'd',
    'dart': 'dart',
    'ejs,tmpl': 'ejs',
    'ex,exs': 'elixir',
    'gitignore,gitattributes,gitmodules': 'git',
    'go': 'go',
    'ml,mli,mll,mly': 'ocaml',
    'hs': 'haskell',
    'htm,html,mhtml': 'html',
    'hx': 'haxe',
    'j2,jinja,jinja2': 'jinja',
    'java,class,properties': 'java',
    'js': 'javascript',
    'json': 'json',
    'jsx,tsx': 'react',
    'kt': 'kotlin',
    'lua': 'lua',
    'md': 'markdown',
    'php': 'php',
    'png,jpg,jpeg,jfif,gif,webp': 'image',
    'py,pyx': 'python',
    'p,sp': 'pawn',
    'r,rda,rdata,rds,rhistory': 'r',
    'rb': 'ruby',
    'rs': 'rust',
    'sh,bat': 'shell',
    'swift': 'swift',
    'svelte': 'svelte',
    't': 'perl',
    'toml': 'toml',
    'ts': 'typescript',
    'tex,bib': 'latex',
    'txt,rst,rest': 'text',
    'vue': 'vue',
    'xml,svg,yml,yaml,cfg,ini': 'xml',
    'yar,yara': 'yara',
    'pp,pas,inc': 'pascal',
    'scss,sass': 'sass',
    'nim': 'nim',
    'nite,nitecode,nightcode,nc': 'nitecode',
    'p6,pm6,pod6,raku,rakumod,rakudoc,rakutest,nqp,crotmp': 'raku',
    'gml,yy': 'gml',
    'factor,facts': 'factor'
}

# Scopes we can/should fallback to
SCOPES = {
    'assembly',
    'ahk',
    'c',
    'clojure',
    'cpp',
    'cs',
    'css',
    'd',
    'erlang',
    'haxe',
    'html',
    'java',
    'json',
    'latex',
    'pde',
    'perl',
    'php',
    'pawn',
    'python',
    'r',
    'scala',
    'svelte',
    'yara',
    'pascal',
    'ocaml',
    'v',
    'sass',
    'nim',
    'nitecode',
    'raku',
    'gml',
    'factor'
}


def get_icon(file, ext, _scope):
    main_scope = _scope.split()[0]
    try:
        sub_scope = '.'.join(main_scope.split()[0].split('.')[1::])
    except Exception:
        sub_scope = ''

    for _icon in ICONS:
        if ext in _icon.split(','):
            icon = ICONS[_icon]
            break
        else:
            for scope in yield_subscopes(sub_scope):
                if scope.replace(',', '') in SCOPES:
                    icon = scope.replace(',', '')
                    break
                else:
                    icon = 'unknown'

    if file == 'LICENSE':
        icon = 'license'
    logger.debug('Using icon "%s" for file %s (scope: %s)', icon, file, main_scope)

    return 'https://raw.githubusercontent.com/Snazzah/SublimeDiscordRP/master/icons/lang-%s.png' % icon


def yield_subscopes(scope):
    last_dot = len(scope)
    while last_dot > 0:
        yield scope[:last_dot]
        last_dot = scope[:last_dot].rfind('.')


def sizehf(num):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, 'B')
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', 'B')


def handle_activity(view):
    window = view.window()
    entity = view.file_name()
    if not (ipc and window and entity):
        return

    act = base_activity()

    # TODO refactor these globals
    global last_file
    global last_edit
    global stamp
    if last_file != entity and settings.get('time_per_file'):
        logger.info('adding new timestamp')
        stamp = mktime(time.localtime())

    logger.info('Updating activity')

    try:
        extension = entity.split('.')[len(entity.split('.')) - 1]
    except Exception:
        extension = ''

    language = os.path.splitext(os.path.basename(view.settings().get('syntax')))[0]
    if len(language) < 2:
        language = language.upper() + ' Syntax'
    format_dict = dict(
        file=os.path.basename(entity),
        extension=extension,
        lang=language,
        project=get_project_name(window, entity),
        size=view.size(),
        sizehf=sizehf(view.size()),
        loc=view.rowcol(view.size())[0] + 1,
        folders=len(window.folders()),
    )
    last_file = entity
    last_edit = time.time()

    details_format = settings.get('details')
    if details_format:
        act['details'] = details_format.format(**format_dict)

    state_format = settings.get('state')
    if state_format:
        act['state'] = state_format.format(**format_dict)

    main_scope = view.scope_name(0)
    icon = get_icon(format_dict['file'], format_dict['extension'], main_scope)
    if settings.get('big_icon'):
        act['assets']['small_text'] = act['assets']['small_text']
        act['assets']['large_image'] = icon
        act['assets']['large_text'] = language
    elif settings.get('small_icon'):
        act['assets']['small_image'] = icon
        act['assets']['small_text'] = language

    if settings.get('show_elapsed_time'):
        act['timestamps'] = {'start': stamp}

    if settings.get('git_repository_button'):
        git_url = get_git_url(entity)
        git_btn_format = settings.get('git_repository_message')

        if git_btn_format and git_url is not None:
            act['buttons'] = [{'label': git_btn_format.format(**format_dict), 'url': git_url}]

    logger.info(window.folders())
    try:
        ipc.set_activity(act)
    except OSError as e:
        handle_error(e)


def reset_activity(started = False):
    if not ipc:
        return
    last_file = ''
    try: ipc.set_activity(base_activity(started))
    except OSError as e: handle_error(e)


def handle_error(exc, retry=True):
    sublime.active_window().status_message("[DiscordRP] Sending activity failed")
    logger.error("Sending activity failed. Error: %s", exc)
    disconnect()

    if retry:
        global is_connecting
        is_connecting = True
        sublime.set_timeout_async(connect_background, 0)


def git_config_parser(path):
    obj = dict()
    with open(path) as cfg:
        lines = cfg.read().split("\n")
        current_section = None

        for line in lines:
            # remove comments and spaces
            line = re.sub(" |;(.*)|#(.*)", "", line)
            if not line:
                continue

            if line.startswith("["):
                res = re.search('"(.*)"', line)
                if res is not None:
                    sec_name = re.sub(r'\[|"(.*)"|\]', "", line)
                    subsec_name = res.group(1)
                    if sec_name not in obj:
                        obj[sec_name] = {}

                    obj[sec_name][subsec_name] = {}
                    current_section = [sec_name, subsec_name]
                else:
                    sec_name = re.sub(r"\[|\]", "", line)
                    obj[sec_name] = {}
                    current_section = [sec_name]

            else:
                parts = re.sub("\t|\0", "", line).split("=")
                if len(current_section) < 2:
                    obj[current_section[0]][parts[0]] = parts[1]
                else:
                    obj[current_section[0]][current_section[1]][parts[0]] = parts[1]

    return obj


def get_git_url_from_config(folder):
    gitcfg_path = folder + "/.git/config"
    if os.path.exists(gitcfg_path):
        cfg = git_config_parser(gitcfg_path)
        if "remote" in cfg and "origin" in cfg["remote"]:
            return cfg["remote"]["origin"]["url"]

    return None


def parse_git_url(url):
    url = re.sub(r"\.git\n?$", "", url)
    if url.startswith("https"):
        return url

    elif url.startswith("git@") or url.startswith("ssh"):
        url = url.replace(":", "/")
        return re.sub("git@|ssh///", "https://", url)

    else:
        return None


def get_git_url(entity):
    folder = os.path.dirname(entity)
    url = None
    try:
        si = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags = subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
        url = subprocess.check_output(["git", "-C", folder, "remote", "get-url", "origin"], universal_newlines=True, startupinfo=si)
    except Exception:
        url = get_git_url_from_config(folder)

    if url is not None:
        url = parse_git_url(url).strip()
        return url

    return None


def get_project_name(window, current_file):
    sources = settings.get("project_name", [])
    for source in sources:
        if source == "project_folder_name":
            folder = find_folder_containing_file(window.folders(), current_file)
            if folder:
                return os.path.basename(folder)
        elif source == "project_file_name":
            project_file_path = window.project_file_name()
            if project_file_path:
                return os.path.splitext(os.path.basename(project_file_path))[0]
        elif source == "folder_name":
            if os.path.basename(os.path.dirname(current_file)) == "src":
                return os.path.basename(os.path.abspath(os.path.join(os.path.dirname(current_file), os.pardir)))
            else:
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
    if not view:
        return False

    if int(sublime.version()) > 4000:
        return view.element() is None

    active_window = sublime.active_window()
    if active_window:
        active_view = active_window.active_view()
        if active_view:
            return active_view.buffer_id() == view.buffer_id()

    return False


def connect(silent=False, retry=True):
    global ipc
    if ipc:
        logger.error("Already connected")
        return True

    try:
        ipc = discord_ipc.DiscordIpcClient.for_platform(DISCORD_CLIENT_ID)
    except (OSError, discord_ipc.DiscordIpcError) as e:
        logger.info("Unable to connect to Discord client")
        logger.debug("Error while connecting", exc_info=e)
        if not silent:
            sublime.error_message("[DiscordRP] Unable to connect to Discord client."
                                  "\n\nPlease verify that it is running."
                                  " Run 'Discord Rich Presence: Connect to Discord'"
                                  " to try again.")
        if retry:
            global is_connecting
            is_connecting = True
            sublime.set_timeout_async(connect_background, RECONNECT_DELAY)
        return

    act = base_activity(True)
    if settings.get('show_elapsed_time'):
        act['timestamps'] = {'start': start_time}

    try:
        ipc.set_activity(act)
    except OSError as e:
        handle_error(e, retry=retry)
        return

    return True


def connect_background():
    if not is_connecting:
        logger.warning("Automatic connection retry aborted")
        return

    logger.info("Trying to reconnect to Discord client...")
    if not connect(silent=True, retry=False):
        sublime.set_timeout_async(connect_background, RECONNECT_DELAY)


def disconnect():
    global ipc
    if ipc:
        try:
            ipc.clear_activity()
            ipc.close()
        except OSError as e:
            logger.debug("Error while disconnecting", exc_info=e)
        ipc = None


deactivate_bounce_count = 0


def _bounce_deactivate(expected_bounce_count):
    if deactivate_bounce_count == expected_bounce_count:
        reset_activity()


class DRPListener(sublime_plugin.EventListener):

    def on_activated_async(self, view):
        global deactivate_bounce_count
        deactivate_bounce_count += 1

        if not is_view_active(view) or view.file_name() == last_file:
            return
        logger.debug("Setting presence to file %r from %r", view.file_name(), last_file)
        handle_activity(view)

    def on_deactivated_async(self, _view):
        global deactivate_bounce_count
        deactivate_bounce_count += 1

        timeout = settings.get('idle_timeout', 0) * 1000
        if timeout:
            sublime.set_timeout_async(partial(_bounce_deactivate, deactivate_bounce_count), timeout)


class DiscordrpConnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return not bool(ipc)

    def run(self):
        sublime.set_timeout_async(self.run_async)

    def run_async(self):
        connect()


class DiscordrpReconnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return bool(ipc)

    def run(self):
        sublime.set_timeout_async(self.run_async)

    def run_async(self):
        disconnect()
        connect()


class DiscordrpDisconnectCommand(sublime_plugin.ApplicationCommand):

    def is_enabled(self):
        return bool(ipc) or is_connecting

    def run(self):
        sublime.set_timeout_async(self.run_async)

    def run_async(self):
        global is_connecting
        is_connecting = False
        disconnect()


def plugin_loaded():
    global settings
    settings = sublime.load_settings(SETTINGS_FILE)
    if settings.get('connect_on_startup'):
        sublime.set_timeout_async(partial(connect, silent=True), 0)


def plugin_unloaded():
    global is_connecting
    is_connecting = False
    disconnect()
