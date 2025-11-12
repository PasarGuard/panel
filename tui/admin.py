import asyncio

from decouple import UndefinedValueError, config
from pydantic import ValidationError
from rich.text import Text
from sqlalchemy import func, select
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Input, Static, Switch

from app.db import AsyncSession
from app.db.base import get_db
from app.db.models import Admin, User
from app.models.admin import AdminCreate, AdminDetails, AdminModify
from app.models.notification_enable import UserNotificationEnable
from app.operation import OperatorType
from app.operation.admin import AdminOperation
from app.utils.helpers import readable_datetime
from app.utils.system import readable_size
from tui import BaseModal

SYSTEM_ADMIN = AdminDetails(
    username="tui", is_sudo=True, telegram_id=None, discord_webhook=None, notification_enable=None
)


class AdminDelete(BaseModal):
    def __init__(
        self,
        db: AsyncSession,
        operation: AdminOperation,
        username: str,
        on_close: callable,
        user_count: int = 0,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db = db
        self.operation = operation
        self.username = username
        self.on_close = on_close
        self.user_count = user_count

    async def on_mount(self) -> None:
        """Ensure the first button is focused."""
        focus_target = "#delete-users" if self.user_count > 0 else "#no"
        self.set_focus(self.query_one(focus_target))

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static(f"Delete admin '{self.username}'?", classes="title")
            if self.user_count > 0:
                yield Static(
                    f"This admin has {self.user_count} users.\nYou must delete them to remove the admin.",
                    classes="subtitle",
                )
                yield Horizontal(
                    Static("Delete all users:", classes="label"),
                    Switch(animate=False, id="delete-users"),
                    classes="switch-container",
                )
            yield Horizontal(
                Button("Yes", id="yes", variant="success"),
                Button("No", id="no", variant="error"),
                classes="button-container",
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            try:
                if self.user_count > 0:
                    delete_users = self.query_one("#delete-users").value
                    if delete_users:
                        await self.operation.remove_all_users(self.db, self.username, SYSTEM_ADMIN)
                        self.notify("Admin users deleted successfully", severity="success", title="Success")
                await self.operation.remove_admin(self.db, self.username, SYSTEM_ADMIN)
                self.on_close()
            except ValueError as e:
                self.notify(str(e), severity="error", title="Error")
        await self.key_escape()


class AdminDeleteUsers(BaseModal):
    def __init__(
        self,
        db: AsyncSession,
        operation: AdminOperation,
        username: str,
        on_close: callable,
        user_count: int = 0,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db = db
        self.operation = operation
        self.username = username
        self.on_close = on_close
        self.user_count = user_count

    async def on_mount(self) -> None:
        confirm_button = self.query_one("#cancel")
        self.set_focus(confirm_button)

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static(
                f"Delete all users belonging to admin '{self.username}'?"
                f"\nFound {self.user_count} user(s). This action cannot be undone.",
                classes="title",
            )
            yield Horizontal(
                Button("Delete Users", id="delete", variant="warning"),
                Button("Cancel", id="cancel", variant="error"),
                classes="button-container",
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            try:
                deleted = await self.operation.remove_all_users(self.db, self.username, SYSTEM_ADMIN)
                if deleted == 0:
                    self.notify("No users were deleted (none found)", severity="warning", title="Info")
                else:
                    self.notify(
                        f"{deleted} users deleted for admin '{self.username}'", severity="success", title="Success"
                    )
                self.on_close()
            except ValueError as e:
                self.notify(str(e), severity="error", title="Error")
        await self.key_escape()


class AdminResetUsage(BaseModal):
    def __init__(
        self, db: AsyncSession, operation: AdminOperation, username: str, on_close: callable, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db = db
        self.operation = operation
        self.username = username
        self.on_close = on_close

    async def on_mount(self) -> None:
        """Ensure the first button is focused."""
        reset_button = self.query_one("#cancel")
        self.set_focus(reset_button)

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static("Are you sure about resetting this admin usage?", classes="title")
            yield Horizontal(
                Button("Reset", id="reset", variant="success"),
                Button("Cancel", id="cancel", variant="error"),
                classes="button-container",
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reset":
            try:
                await self.operation.reset_admin_usage(self.db, self.username, SYSTEM_ADMIN)
                self.notify("Admin usage reseted successfully", severity="success", title="Success")
                self.on_close()
            except ValueError as e:
                self.notify(str(e), severity="error", title="Error")
        await self.key_escape()


class AdminCreateModale(BaseModal):
    def __init__(
        self,
        db: AsyncSession,
        operation: AdminOperation,
        on_close: callable,
        format_tui_validation_error: callable,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db = db
        self.operation = operation
        self.on_close = on_close
        self.format_tui_validation_error = format_tui_validation_error

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-form"):
            yield Static("Create a new admin", classes="title")
            yield Vertical(
                Input(placeholder="Username", id="username"),
                Input(placeholder="Password", password=True, id="password"),
                Input(placeholder="Confirm Password", password=True, id="confirm_password"),
                Input(placeholder="Telegram ID", id="telegram_id", type="integer"),
                Input(placeholder="Discord ID", id="discord_id", type="integer"),
                Input(placeholder="Discord Webhook", id="discord_webhook"),
                Input(placeholder="Sub Template", id="sub_template"),
                Input(placeholder="Sub Domain", id="sub_domain"),
                Input(placeholder="Profile Title", id="profile_title"),
                Input(placeholder="Support URL", id="support_url"),
                Horizontal(
                    Static("Is sudo:     ", classes="label"),
                    Switch(animate=False, id="is_sudo"),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("Enable Notifications: ", classes="label"),
                    Switch(animate=False, id="notif_master", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Create:           ", classes="label"),
                    Switch(animate=False, id="notif_create", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Modify:           ", classes="label"),
                    Switch(animate=False, id="notif_modify", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Delete:           ", classes="label"),
                    Switch(animate=False, id="notif_delete", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Status Change:         ", classes="label"),
                    Switch(animate=False, id="notif_status_change", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Reset Data Usage:      ", classes="label"),
                    Switch(animate=False, id="notif_reset_data_usage", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Data Reset By Next:    ", classes="label"),
                    Switch(animate=False, id="notif_data_reset_by_next", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Subscription Revoked:  ", classes="label"),
                    Switch(animate=False, id="notif_subscription_revoked", value=False),
                    classes="switch-container",
                ),
                classes="input-container",
            )
            yield Horizontal(
                Button("Create", id="create", variant="success"),
                Button("Cancel", id="cancel", variant="error"),
                classes="button-container",
            )

    async def on_mount(self) -> None:
        """Ensure the first button is focused and disable notification switches."""
        username_input = self.query_one("#username")
        self.set_focus(username_input)
        # Disable all notification switches by default (master is OFF)
        for notif_id in [
            "notif_create",
            "notif_modify",
            "notif_delete",
            "notif_status_change",
            "notif_reset_data_usage",
            "notif_data_reset_by_next",
            "notif_subscription_revoked",
        ]:
            self.query_one(f"#{notif_id}").disabled = True

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle master toggle changes to enable/disable individual notification switches."""
        if event.switch.id == "notif_master":
            notification_switches = [
                "notif_create",
                "notif_modify",
                "notif_delete",
                "notif_status_change",
                "notif_reset_data_usage",
                "notif_data_reset_by_next",
                "notif_subscription_revoked",
            ]
            for notif_id in notification_switches:
                switch = self.query_one(f"#{notif_id}")
                switch.disabled = not event.value
                # When disabling, also set value to False
                if not event.value:
                    switch.value = False

    async def key_enter(self) -> None:
        """Create admin when Enter is pressed."""
        # Check if any switch has focus
        switch_ids = [
            "is_sudo",
            "notif_master",
            "notif_create",
            "notif_modify",
            "notif_delete",
            "notif_status_change",
            "notif_reset_data_usage",
            "notif_data_reset_by_next",
            "notif_subscription_revoked",
        ]
        if (
            not any(self.query_one(f"#{switch_id}").has_focus for switch_id in switch_ids)
            and not self.query_one("#cancel").has_focus
        ):
            await self.on_button_pressed(Button.Pressed(self.query_one("#create")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            username = self.query_one("#username").value.strip()
            password = self.query_one("#password").value.strip()
            confirm_password = self.query_one("#confirm_password").value.strip()
            telegram_id = self.query_one("#telegram_id").value or None
            discord_webhook = self.query_one("#discord_webhook").value.strip() or None
            discord_id = self.query_one("#discord_id").value or None
            is_sudo = self.query_one("#is_sudo").value
            sub_template = self.query_one("#sub_template").value.strip() or None
            sub_domain = self.query_one("#sub_domain").value.strip() or None
            profile_title = self.query_one("#profile_title").value.strip() or None
            support_url = self.query_one("#support_url").value.strip() or None

            # Build notification_enable object (always create, never None for new admins)
            notification_enable = UserNotificationEnable(
                create=self.query_one("#notif_create").value,
                modify=self.query_one("#notif_modify").value,
                delete=self.query_one("#notif_delete").value,
                status_change=self.query_one("#notif_status_change").value,
                reset_data_usage=self.query_one("#notif_reset_data_usage").value,
                data_reset_by_next=self.query_one("#notif_data_reset_by_next").value,
                subscription_revoked=self.query_one("#notif_subscription_revoked").value,
            )

            if password != confirm_password:
                self.notify("Password and confirm password do not match", severity="error", title="Error")
                return
            try:
                await self.operation.create_admin(
                    self.db,
                    AdminCreate(
                        username=username,
                        password=password,
                        telegram_id=telegram_id,
                        discord_webhook=discord_webhook,
                        discord_id=discord_id,
                        is_sudo=is_sudo,
                        sub_template=sub_template,
                        sub_domain=sub_domain,
                        profile_title=profile_title,
                        support_url=support_url,
                        notification_enable=notification_enable,
                    ),
                    SYSTEM_ADMIN,
                )
                self.notify("Admin created successfully", severity="success", title="Success")
                await self.key_escape()
                self.on_close()
            except ValidationError as e:
                self.format_tui_validation_error(e)
            except ValueError as e:
                self.notify(str(e), severity="error", title="Error")
        elif event.button.id == "cancel":
            await self.key_escape()


class AdminModifyModale(BaseModal):
    def __init__(
        self,
        db: AsyncSession,
        operation: AdminOperation,
        admin: Admin,
        on_close: callable,
        format_tui_validation_error: callable,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db = db
        self.operation = operation
        self.admin = admin
        self.on_close = on_close
        self.format_tui_validation_error = format_tui_validation_error

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-form"):
            yield Static("Modify admin", classes="title")
            yield Vertical(
                Input(placeholder="Username", id="username", disabled=True),
                Input(placeholder="Password", password=True, id="password"),
                Input(placeholder="Confirm Password", password=True, id="confirm_password"),
                Input(placeholder="Telegram ID", id="telegram_id", type="integer"),
                Input(placeholder="Discord ID", id="discord_id", type="integer"),
                Input(placeholder="Discord Webhook", id="discord_webhook"),
                Input(placeholder="Sub Template", id="sub_template"),
                Input(placeholder="Sub Domain", id="sub_domain"),
                Input(placeholder="Profile Title", id="profile_title"),
                Input(placeholder="Support URL", id="support_url"),
                Horizontal(
                    Static("Is sudo: ", classes="label"),
                    Switch(animate=False, id="is_sudo"),
                    Static("Is disabled: ", classes="label"),
                    Switch(animate=False, id="is_disabled"),
                    classes="switch-container",
                ),
                Static("", id="legacy_notif_warning", classes="label"),
                Horizontal(
                    Static("Enable Notifications: ", classes="label"),
                    Switch(animate=False, id="notif_master", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Create:           ", classes="label"),
                    Switch(animate=False, id="notif_create", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Modify:           ", classes="label"),
                    Switch(animate=False, id="notif_modify", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  User Delete:           ", classes="label"),
                    Switch(animate=False, id="notif_delete", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Status Change:         ", classes="label"),
                    Switch(animate=False, id="notif_status_change", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Reset Data Usage:      ", classes="label"),
                    Switch(animate=False, id="notif_reset_data_usage", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Data Reset By Next:    ", classes="label"),
                    Switch(animate=False, id="notif_data_reset_by_next", value=False),
                    classes="switch-container",
                ),
                Horizontal(
                    Static("  Subscription Revoked:  ", classes="label"),
                    Switch(animate=False, id="notif_subscription_revoked", value=False),
                    classes="switch-container",
                ),
                classes="input-container",
            )
            yield Horizontal(
                Button("Save", id="save", variant="success"),
                Button("Cancel", id="cancel", variant="error"),
                classes="button-container",
            )

    async def on_mount(self) -> None:
        self.query_one("#username").value = self.admin.username
        if self.admin.telegram_id:
            self.query_one("#telegram_id").value = str(self.admin.telegram_id)
        if self.admin.discord_webhook:
            self.query_one("#discord_webhook").value = self.admin.discord_webhook
        if self.admin.sub_template:
            self.query_one("#sub_template").value = self.admin.sub_template
        if self.admin.sub_domain:
            self.query_one("#sub_domain").value = self.admin.sub_domain
        if self.admin.profile_title:
            self.query_one("#profile_title").value = self.admin.profile_title
        if self.admin.support_url:
            self.query_one("#support_url").value = self.admin.support_url
        self.query_one("#is_sudo").value = self.admin.is_sudo
        self.query_one("#is_disabled").value = self.admin.is_disabled

        # Load existing notification preferences (notification_enable is a dict from SQLAlchemy)
        notif = self.admin.notification_enable or {}
        master_on = any(
            [
                notif.get("create", False),
                notif.get("modify", False),
                notif.get("delete", False),
                notif.get("status_change", False),
                notif.get("reset_data_usage", False),
                notif.get("data_reset_by_next", False),
                notif.get("subscription_revoked", False),
            ]
        )

        self.query_one("#notif_master").value = master_on
        self.query_one("#notif_create").value = notif.get("create", False)
        self.query_one("#notif_modify").value = notif.get("modify", False)
        self.query_one("#notif_delete").value = notif.get("delete", False)
        self.query_one("#notif_status_change").value = notif.get("status_change", False)
        self.query_one("#notif_reset_data_usage").value = notif.get("reset_data_usage", False)
        self.query_one("#notif_data_reset_by_next").value = notif.get("data_reset_by_next", False)
        self.query_one("#notif_subscription_revoked").value = notif.get("subscription_revoked", False)

        # Enable/disable individual switches based on master toggle
        for notif_id in [
            "notif_create",
            "notif_modify",
            "notif_delete",
            "notif_status_change",
            "notif_reset_data_usage",
            "notif_data_reset_by_next",
            "notif_subscription_revoked",
        ]:
            self.query_one(f"#{notif_id}").disabled = not master_on

        password_input = self.query_one("#password")
        self.set_focus(password_input)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle master toggle changes to enable/disable individual notification switches."""
        if event.switch.id == "notif_master":
            notification_switches = [
                "notif_create",
                "notif_modify",
                "notif_delete",
                "notif_status_change",
                "notif_reset_data_usage",
                "notif_data_reset_by_next",
                "notif_subscription_revoked",
            ]
            for notif_id in notification_switches:
                switch = self.query_one(f"#{notif_id}")
                switch.disabled = not event.value
                # When disabling, also set value to False
                if not event.value:
                    switch.value = False

    async def key_enter(self) -> None:
        """Save admin when Enter is pressed."""
        # Check if any switch has focus
        switch_ids = [
            "is_sudo",
            "is_disabled",
            "notif_master",
            "notif_create",
            "notif_modify",
            "notif_delete",
            "notif_status_change",
            "notif_reset_data_usage",
            "notif_data_reset_by_next",
            "notif_subscription_revoked",
        ]
        if (
            not any(self.query_one(f"#{switch_id}").has_focus for switch_id in switch_ids)
            and not self.query_one("#cancel").has_focus
        ):
            await self.on_button_pressed(Button.Pressed(self.query_one("#save")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            password = self.query_one("#password").value.strip() or None
            confirm_password = self.query_one("#confirm_password").value.strip() or None
            telegram_id = self.query_one("#telegram_id").value or 0
            discord_webhook = self.query_one("#discord_webhook").value.strip() or None
            discord_id = self.query_one("#discord_id").value or 0
            is_sudo = self.query_one("#is_sudo").value
            is_disabled = self.query_one("#is_disabled").value
            sub_template = self.query_one("#sub_template").value.strip() or None
            sub_domain = self.query_one("#sub_domain").value.strip() or None
            profile_title = self.query_one("#profile_title").value.strip() or None
            support_url = self.query_one("#support_url").value.strip() or None

            # Build notification_enable object (keep None for legacy admins, otherwise build)
            if self.admin.notification_enable is None:
                notification_enable = None
            else:
                notification_enable = UserNotificationEnable(
                    create=self.query_one("#notif_create").value,
                    modify=self.query_one("#notif_modify").value,
                    delete=self.query_one("#notif_delete").value,
                    status_change=self.query_one("#notif_status_change").value,
                    reset_data_usage=self.query_one("#notif_reset_data_usage").value,
                    data_reset_by_next=self.query_one("#notif_data_reset_by_next").value,
                    subscription_revoked=self.query_one("#notif_subscription_revoked").value,
                )

            if password != confirm_password:
                self.notify("Password and confirm password do not match", severity="error", title="Error")
                return
            try:
                await self.operation.modify_admin(
                    self.db,
                    self.admin.username,
                    AdminModify(
                        password=password,
                        telegram_id=telegram_id,
                        discord_webhook=discord_webhook,
                        discord_id=discord_id,
                        is_sudo=is_sudo,
                        is_disabled=is_disabled,
                        sub_template=sub_template,
                        sub_domain=sub_domain,
                        profile_title=profile_title,
                        support_url=support_url,
                        notification_enable=notification_enable,
                    ),
                    SYSTEM_ADMIN,
                )
                self.notify("Admin modified successfully", severity="success", title="Success")
                await self.key_escape()
                self.on_close()
            except ValidationError as e:
                self.format_tui_validation_error(e)
            except ValueError as e:
                self.notify(str(e), severity="error", title="Error")
        elif event.button.id == "cancel":
            await self.key_escape()


class AdminContent(Static):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.db: AsyncSession = None
        self.admin_operator = AdminOperation(OperatorType.CLI)
        self.table: DataTable = None
        self.no_admins: Static = None
        self.current_page = 1
        self.page_size = 10
        self.total_admins = 0

    BINDINGS = [
        ("c", "create_admin", "Create admin"),
        ("m", "modify_admin", "Modify admin"),
        ("r", "reset_admin_usage", "Reset admin usage"),
        ("d", "delete_admin", "Delete admin"),
        ("u", "delete_admin_users", "Delete admin users"),
        ("i", "import_from_env", "Import from env"),
        ("p", "previous_page", "Previous page"),
        ("n", "next_page", "Next page"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="admin-list")
        yield Static(
            "No admin found\n\nCreate an admin by pressing 'c'\n\nhelp by pressing '?'",
            classes="title box",
            id="no-admins",
        )
        yield Static("", id="pagination-info", classes="pagination-info")

    async def on_mount(self) -> None:
        self.db = await anext(get_db())
        self.table = self.query_one("#admin-list")
        self.no_admins = self.query_one("#no-admins")
        self.pagination_info = self.query_one("#pagination-info")
        self.no_admins.styles.display = "none"
        self.table.styles.display = "none"
        self.table.cursor_type = "row"
        self.table.styles.text_align = "center"
        await self.admins_list()

    def _center_text(self, text, width):
        padding = width - len(text)
        left_padding = padding // 2
        right_padding = padding - left_padding
        return " " * left_padding + text + " " * right_padding

    async def admins_list(self):
        self.table.clear()
        self.table.columns.clear()
        columns = (
            "Username",
            "Used Traffic",
            "Lifetime Used Traffic",
            "Users Usage",
            "Is sudo",
            "Is disabled",
            "Created at",
            "Telegram ID",
            "Discord ID",
            "Discord Webhook",
        )
        self.total_admins = await self.admin_operator.get_admins_count(self.db)
        offset = (self.current_page - 1) * self.page_size
        limit = self.page_size
        admins = await self.admin_operator.get_admins(self.db, offset=offset, limit=limit)
        if not admins:
            self.no_admins.styles.display = "block"
            self.pagination_info.update("")
            return
        else:
            self.no_admins.styles.display = "none"
            self.table.styles.display = "block"
        users_usages = await asyncio.gather(*[self.calculate_admin_usage(admin.id) for admin in admins])

        admins_data = [
            (
                admin.username,
                readable_size(admin.used_traffic),
                readable_size(admin.lifetime_used_traffic),
                users_usages[i],
                "✔️" if admin.is_sudo else "✖️",
                "✔️" if admin.is_disabled else "✖️",
                readable_datetime(admin.created_at),
                str(admin.telegram_id or "✖️"),
                str(admin.discord_id or "✖️"),
                str(admin.discord_webhook or "✖️"),
            )
            for i, admin in enumerate(admins)
        ]
        column_widths = [
            max(len(str(columns[i])), max(len(str(row[i])) for row in admins_data)) for i in range(len(columns))
        ]

        centered_columns = [self._center_text(column, column_widths[i]) for i, column in enumerate(columns)]
        self.table.add_columns(*centered_columns)
        i = 1
        for row, adnin in zip(admins_data, admins):
            centered_row = [self._center_text(str(cell), column_widths[i]) for i, cell in enumerate(row)]
            label = Text(f"{i + offset}")
            i += 1
            self.table.add_row(*centered_row, key=adnin.username, label=label)

        total_pages = (self.total_admins + self.page_size - 1) // self.page_size
        self.pagination_info.update(
            f"Page {self.current_page}/{total_pages} (Total admins: {self.total_admins})\nPress `n` for go to the next page and `p` to back to previose page"
        )

    @property
    def selected_admin(self):
        return self.table.coordinate_to_cell_key(Coordinate(self.table.cursor_row, 0)).row_key.value

    async def action_delete_admin(self):
        if not self.table.columns:
            return
        admin = await self.admin_operator.get_validated_admin(self.db, username=self.selected_admin)
        user_count = len(admin.users or [])
        self.app.push_screen(
            AdminDelete(self.db, self.admin_operator, self.selected_admin, self._refresh_table, user_count)
        )

    async def action_delete_admin_users(self):
        if not self.table.columns:
            return
        admin = await self.admin_operator.get_validated_admin(self.db, username=self.selected_admin)
        user_count = len(admin.users or [])
        self.app.push_screen(
            AdminDeleteUsers(self.db, self.admin_operator, self.selected_admin, self._refresh_table, user_count)
        )

    def _refresh_table(self):
        self.run_worker(self.admins_list)

    async def action_create_admin(self):
        self.app.push_screen(
            AdminCreateModale(self.db, self.admin_operator, self._refresh_table, self.format_tui_validation_error)
        )

    async def action_modify_admin(self):
        if not self.table.columns:
            return
        admin = await self.admin_operator.get_validated_admin(self.db, username=self.selected_admin)
        self.app.push_screen(
            AdminModifyModale(
                self.db, self.admin_operator, admin, self._refresh_table, self.format_tui_validation_error
            )
        )

    async def action_import_from_env(self):
        try:
            username, password = config("SUDO_USERNAME"), config("SUDO_PASSWORD")
        except UndefinedValueError:
            self.notify(
                "Unable to get SUDO_USERNAME and/or SUDO_PASSWORD.\n"
                "Make sure you have set them in the env file or as environment variables.",
                severity="error",
                title="Error",
            )
            return
        if not (username and password):
            self.notify(
                "Unable to retrieve username and password.\nMake sure both SUDO_USERNAME and SUDO_PASSWORD are set.",
                severity="error",
                title="Error",
            )
            return
        try:
            # Create with all notifications disabled (default for new admins)
            notification_enable = UserNotificationEnable(
                create=False,
                modify=False,
                delete=False,
                status_change=False,
                reset_data_usage=False,
                data_reset_by_next=False,
                subscription_revoked=False,
            )
            await self.admin_operator.create_admin(
                self.db,
                AdminCreate(
                    username=username, password=password, is_sudo=True, notification_enable=notification_enable
                ),
                SYSTEM_ADMIN,
            )
            self.notify("Admin created successfully", severity="success", title="Success")
            self._refresh_table()
        except ValidationError as e:
            self.format_tui_validation_error(e)
        except ValueError as e:
            self.notify(str(e), severity="error", title="Error")

    async def action_reset_admin_usage(self):
        if not self.table.columns:
            return
        self.app.push_screen(AdminResetUsage(self.db, self.admin_operator, self.selected_admin, self._refresh_table))

    async def action_previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            await self.admins_list()

    async def action_next_page(self):
        total_pages = (self.total_admins + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.current_page += 1
            await self.admins_list()

    async def calculate_admin_usage(self, admin_id: int) -> str:
        usage = await self.db.execute(select(func.sum(User.used_traffic)).filter_by(admin_id=admin_id))
        return readable_size(int(usage.scalar() or 0))

    async def key_enter(self) -> None:
        if self.table.columns:
            await self.action_modify_admin()

    async def on_prune(self, event):
        await self.db.close()
        return await super().on_prune(event)

    def format_tui_validation_error(self, errors: ValidationError):
        for error in errors.errors():
            for err in error["msg"].split(";"):
                self.notify(
                    title=f"Error: {error['loc'][0].replace('_', ' ').capitalize()}",
                    message=err.strip(),
                    severity="error",
                )
