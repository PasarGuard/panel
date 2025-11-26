from datetime import datetime as dt, timedelta as td, timezone as tz
from html import escape

from aiogram.utils.formatting import html_decoration

from app.models.group import Group
from app.models.system import SystemStats
from app.models.user import UserResponse, UserStatus
from app.subscription.share import STATUS_EMOJIS
from app.telegram.utils.shared import readable_size

b = html_decoration.bold
c = html_decoration.code
i = html_decoration.italic
u = html_decoration.underline
ln = html_decoration.link
p = html_decoration.pre
pl = html_decoration.pre_language
sp = html_decoration.spoiler
st = html_decoration.strikethrough
bl = html_decoration.blockquote
ebl = html_decoration.expandable_blockquote


class Button:
    modify_groups = "👥 Modify Groups"
    subscription_url = "🔗 Subscription URL"
    modify_note = "📝 Modify Note"
    random_username = "🎲 Random Username"
    modify_data_limit = "📶 Modify Data Limit"
    modify_expiry = "📅 Modify Expiry"
    delete_expired = "⌛ Delete Expired"
    bulk_actions = "🔧 Bulk Actions"
    bulk_create_from_template = "👥 Bulk From Template"
    open_panel = "🎛 Open Panel"
    done = "✅ Done"
    search = "🔎 Search"
    enable = "✅ Enable"
    disable = "❌ Disable"
    revoke_sub = "📵 Revoke Sub"
    reset_usage = "🔄 Reset Usage"
    delete = "🗑 Delete"
    activate_next_plan = "☑ Activate Next Plan"
    confirm = "✅ Confirm"
    cancel = "❌ Cancel"
    create_user = "👤 Create User"
    create_user_from_template = "👤 Create User From Template"
    random_strategy = "🎲 Random"
    sequence_strategy = "🔢 Sequence"
    modify_with_template = "📦 Modify with Template"
    sync_users = "🔄 Sync Users"
    refresh_data = "♻ Refresh"
    users = "👥 Users"
    on_hold = "🔘 On-Hold"
    back = "🔙 Back"


class Message:
    enter_modify_note = "📝 Enter new Note:"
    enter_modify_data_limit = "📶 Enter new Data Limit (GB):\nSend 0 for unlimited."
    enter_modify_expiry = "📅 Enter new Expiry (days):\nSend 0 for unlimited."
    enter_bulk_data_limit = "📶 Enter data limit change (GB):\nPositive and Negative values are allowed."
    enter_bulk_expiry = "📅 Enter Expiry change (days):\nPositive and Negative values are allowed."
    enter_bulk_count = "👥 Enter how many users to create (1-500):"
    enter_bulk_sequence_username = "🗣 Enter base username for sequence strategy (e.g. user1):"
    enter_bulk_sequence_start_number = "🔢 Enter starting number (default 1). Send empty to auto-use 1:"
    enter_expire_before = "📅 Delete Users expired before (days):\nSend 0 for all."
    choose_username_strategy = "🎯 Choose username generation strategy:"
    choose_action = "🔧 Choose an Action:"
    there_is_no_template = "❌ There is no Template!"
    user_not_found = "❌ User not found!"
    confirm = "⚠ Are you sure you want to proceed?"
    enter_username = "🗣 Enter new user's Username:"
    username_already_exist = "❌ Username already exists."
    enter_data_limit = "🌐 Enter Data Limit (GB):\nSend 0 for unlimited."
    data_limit_not_valid = "❌ Data limit is not valid."
    enter_duration = "📅 Enter duration (days):\nSend 0 for unlimited."
    duration_not_valid = "❌ Duration is not valid."
    start_number_not_valid = "❌ Start number must be a non-negative integer."
    bulk_count_not_valid = "❌ Count must be between 1 and 500."
    choose_status = "Do you want to enable it or keep it on-hold?"
    enter_on_hold_timeout = "🔌 Enter On-Hold timeout duration (days):\nSend 0 for Never."
    select_groups = "👥 Select Groups:"
    select_a_group = "❌ You have to select at least one group."
    canceled = "💢 Operation Canceled"
    user_created = "✅ User created successfully"
    refreshed = "♻ Refreshed successfully"
    syncing = "🔄 Syncing..."
    synced = "✅ Users successfully Synced"
    choose_a_template = "📦 Choose a Template:"

    @staticmethod
    def start(stats: SystemStats):
        memory_percentage = int(stats.mem_used / stats.mem_total * 100)
        return f"""\
⚙ {b("PasarGuard Version")}: {c(stats.version)}

📊 {b("CPU Usage")}: {c(stats.cpu_usage)} %
🎛 {b("CPU Cores")}: {c(stats.cpu_cores)}
📈 {b("Memory")}: {c(readable_size(stats.mem_used))} / {c(readable_size(stats.mem_total))} ({c(memory_percentage)} %)
🌐 {b("Total Data Usage")}: {c(readable_size(stats.outgoing_bandwidth + stats.incoming_bandwidth))}

👥 {b("Total Users")}: {c(stats.total_user)}
🟢 {b("Online Users")}: {c(stats.online_users)}
🔘 {b("Active Users")}: {c(stats.active_users)}
🔌 {b("On-Hold Users")}: {c(stats.on_hold_users)}
⌛ {b("Expired Users")}: {c(stats.expired_users)}
🪫 {b("Limited Users")}: {c(stats.limited_users)}
🔴 {b("Disabled Users")}: {c(stats.disabled_users)}
"""

    @staticmethod
    def status_emoji(status: UserStatus):
        return STATUS_EMOJIS[status.value]

    @staticmethod
    def user_details(user: UserResponse, groups: list[Group]) -> str:
        data_limit = c(readable_size(user.data_limit)) if user.data_limit else "∞"
        used_traffic = c(readable_size(user.used_traffic))
        expire = user.expire.strftime("%Y-%m-%d %H:%M") if user.expire else "∞"
        days_left = (user.expire - dt.now(tz.utc)).days if user.expire else "∞"
        on_hold_timeout = user.on_hold_timeout.strftime("%Y-%m-%d %H:%M") if user.on_hold_timeout else "-"
        on_hold_expire_duration = td(seconds=user.on_hold_expire_duration).days if user.on_hold_expire_duration else "0"
        online_at = bl(user.online_at.strftime("%Y-%m-%d %H:%M:%S")) if user.online_at else "-"
        admin = ln(user.admin.username, f"tg://user?id={user.admin.telegram_id}") if user.admin else "-"
        note = bl(escape(user.note)) if user.note else "-"
        emojy_status = Message.status_emoji(user.status)
        groups = ", ".join([g.name for g in groups])

        if user.status == UserStatus.on_hold:
            expire_text = f"{b('On Hold Duration: ')} {c(on_hold_expire_duration)} days\n"
            expire_text += f"{b('On Hold Timeout:')} {c(on_hold_timeout)}"
        else:
            expire_text = f"{b('Expire: ')} {c(expire)}\n"
            expire_text += f"{b('Days left: ')} {c(days_left)}"

        return f"""\
👤 {b("User Information")}

{b("Status:")} {emojy_status} {user.status.value.replace("_", " ").title()}
{b("Username:")} {c(user.username)}

{b("Data Limit:")} {data_limit}
{b("Used Traffic:")} {used_traffic}
{b("Data Limit Strategy:")} {user.data_limit_reset_strategy.value.replace("_", " ").title()}
{expire_text}
{b("Online At:")} {online_at}
{b("Groups:")} {c(groups)}
{b("Admin:")} {admin}
{b("Note:")} {note}"""

    @staticmethod
    def user_short_detail(user: UserResponse) -> str:
        data_limit = readable_size(user.data_limit) if user.data_limit else "∞"
        used_traffic = readable_size(user.used_traffic)
        if user.status == UserStatus.on_hold:
            expiry = int(user.on_hold_expire_duration / 24 / 60 / 60)
        else:
            expiry = (user.expire - dt.now(tz.utc)).days if user.expire else "∞"
        return f"{used_traffic} / {data_limit} | {expiry} days\n{user.note or ''}"

    @classmethod
    def client_user_details(cls, user: UserResponse) -> str:
        data_limit = c(readable_size(user.data_limit)) if user.data_limit else "∞"
        used_traffic = c(readable_size(user.used_traffic))
        expire = user.expire.strftime("%Y-%m-%d %H:%M") if user.expire else "∞"
        days_left = (user.expire - dt.now(tz.utc)).days if user.expire else "∞"
        online_at = bl(user.online_at.strftime("%Y-%m-%d %H:%M:%S")) if user.online_at else "-"
        emojy_status = cls.status_emoji(user.status)

        return f"""\
👤 {b("User Information")}

{b("Status:")} {emojy_status} {user.status.value.replace("_", " ").title()}
{b("Username:")} {c(user.username)}
{b("Data Limit:")} {data_limit}
{b("Used Traffic:")} {used_traffic}
{b("Data Limit Strategy:")} {user.data_limit_reset_strategy.value.replace("_", " ").title()}
{b("Expire:")} {c(expire)}
{b("Days left:")} {c(days_left)}
{b("Online At:")} {online_at}
{b("Subscription URL:")}
{p(user.subscription_url)}
"""

    @staticmethod
    def confirm_disable_user(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Disable')} {c(username)}?"

    @staticmethod
    def confirm_enable_user(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Enable')} {c(username)}?"

    @staticmethod
    def confirm_delete_user(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Delete')} {c(username)}?"

    @staticmethod
    def confirm_revoke_sub(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Revoke Subscription')} of {c(username)}?"

    @staticmethod
    def confirm_reset_usage(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Reset Usage')} of {c(username)}?"

    @staticmethod
    def confirm_activate_next_plan(username: str) -> str:
        return f"⚠ Are you sure you want to {b('Activate Next Plan')} for {c(username)}?"

    @classmethod
    def confirm_delete_expired(cls, expired_before_days: int | str) -> str:
        return f"⚠ Are you sure you want to delete all users expired before {expired_before_days} days ago?"

    @staticmethod
    def user_disabled(username: str) -> str:
        return f"✅ {username} has been successfully disabled."

    @staticmethod
    def user_enabled(username: str) -> str:
        return f"✅ {username} has been successfully enabled."

    @staticmethod
    def user_deleted(username: str) -> str:
        return f"✅ {username} has been successfully deleted."

    @staticmethod
    def user_sub_revoked(username: str) -> str:
        return f"✅ {username}'s subscription has been successfully revoked."

    @staticmethod
    def user_reset_usage(username: str) -> str:
        return f"✅ {username}'s usage has been successfully reset."

    @staticmethod
    def user_next_plan_activated(username: str) -> str:
        return f"✅ {username}'s next plan has been successfully activated."

    @classmethod
    def users_deleted(cls, count):
        return f"✅ {count} users successfully deleted."

    @classmethod
    def confirm_modify_expiry(cls, days: int) -> str:
        if days > 0:
            return f"⚠ Are you sure you want to extend users expiry by {c(days)} days?"
        else:
            return f"⚠ Are you sure you want to subtract {c(abs(days))} days from users expiry?"

    @classmethod
    def users_expiry_changed(cls, result: int, amount: int):
        if amount > 0:
            return f"✅ {result} users successfully extended by {amount} days."
        else:
            return f"✅ {result} users successfully subtracted by {abs(amount)} days."

    @classmethod
    def confirm_modify_data_limit(cls, amount: int) -> str:
        if amount > 0:
            return f"⚠ Are you sure you want to increase users data limit by {c(amount)} GB?"
        else:
            return f"⚠ Are you sure you want to decrease users data limit by {c(abs(amount))} GB?"

    @classmethod
    def users_data_limit_changed(cls, result: int, amount: int):
        if amount > 0:
            return f"✅ {result} users successfully increased by {amount} GB."
        else:
            return f"✅ {result} users successfully decreased by {abs(amount)} GB."

    @staticmethod
    def bulk_users_created(created: int):
        return f"✅ {created} users created from template."

    @staticmethod
    def bulk_users_not_created():
        return "❌ No users were created. Please review the template or usernames."


__all__ = ["Button", "Message"]
