from textual.app import ComposeResult
from textual.widgets import Static, Button
from textual.containers import Container
from tui import BaseModal


class HelpModal(BaseModal):
    def __init__(self, app_bindings, admin_bindings, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.app_bindings = app_bindings
        self.admin_bindings = admin_bindings

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-help"):
            yield Static("Help Menu", classes="title")
            yield Static(self._format_bindings(), classes="help-content")
            yield Button("Close", id="close", variant="primary")

    def _format_bindings(self) -> str:
        help_text = "Available Commands:\n\n"

        # Format app bindings
        help_text += "Global Commands:\n"
        for key, _, description in self.app_bindings:
            help_text += f"  {key:3} - {description}\n"

        # Format admin bindings
        help_text += "\nAdmin Section Commands:\n"
        for key, _, description in self.admin_bindings:
            help_text += f"  {key:3} - {description}\n"

        return help_text

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            await self.key_escape()
