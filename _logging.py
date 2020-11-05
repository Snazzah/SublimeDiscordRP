import logging

import sublime


DEFAULT_LOG_LEVEL = logging.WARNING
DEFAULT_LOG_LEVEL_NAME = logging.getLevelName(DEFAULT_LOG_LEVEL)
EVENT_LEVEL = logging.INFO

pkg_logger = logging.getLogger(__package__)
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt="[{name}] {levelname}: {message}", style='{')
handler.setFormatter(formatter)
pkg_logger.addHandler(handler)
pkg_logger.setLevel(DEFAULT_LOG_LEVEL)

logger = logging.getLogger(__name__)


def _settings():
    """
    Return the settings for all sublime settings.

    Args:
    """
    return sublime.load_settings("DiscordRichPresence.sublime-settings")


def plugin_loaded():
    """
    Configure the plugin plugin.

    Args:
    """
    def on_settings_reload():
        """
        Reload logging settings.

        Args:
        """
        cur_log_level = pkg_logger.getEffectiveLevel()
        cur_log_level_name = logging.getLevelName(cur_log_level)
        new_log_level_name = _settings().get('log_level', DEFAULT_LOG_LEVEL_NAME).upper()
        new_log_level = getattr(logging, new_log_level_name, DEFAULT_LOG_LEVEL)

        if new_log_level_name != cur_log_level_name:
            if cur_log_level > EVENT_LEVEL and new_log_level <= EVENT_LEVEL:
                # Only set level before emitting log event if it would not be seen otherwise
                pkg_logger.setLevel(new_log_level)
            logger.log(EVENT_LEVEL,
                       "Changing log level from %r to %r",
                       cur_log_level_name, new_log_level_name)
            pkg_logger.setLevel(new_log_level)  # Just set it again to be sure

    _settings().add_on_change(__name__, on_settings_reload)
    on_settings_reload()  # trigger on inital settings load, too


def plugin_unloaded():
    """
    Unloaded plugin

    Args:
    """
    _settings().clear_on_change(__name__)
    pkg_logger.removeHandler(handler)
