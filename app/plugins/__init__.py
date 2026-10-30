"""Plugin system ("sub-modules").

Plugins are trusted Python packages installed on the server (``PLUGINS_DIR``) and enabled by id
(``PLUGINS``). With ``PLUGINS`` empty nothing in this package touches plugin code; the hooks in the
panel only check ``registry.active``. See the "Plugins" section of README.md.

Keep this module free of heavy imports: notification, subscription and router code import
``app.plugins.registry`` on every process start.
"""
