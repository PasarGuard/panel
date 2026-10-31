from app.models.my_hosts import HostPreference, MyHostsPolicy
from app.models.subscription import SubscriptionInboundData


def personalize_hosts(
    hosts: dict[int, SubscriptionInboundData], preferences: dict | None, policy: MyHostsPolicy
) -> tuple[list[SubscriptionInboundData], bool]:
    """Copy presentation overrides without mutating the shared HostManager/NATS state."""
    if not policy.enabled or not preferences:
        return list(hosts.values()), False
    result = []
    ordered = False
    for index, (host_id, host) in enumerate(hosts.items()):
        preference = preferences.get(str(host_id))
        if preference is None:
            preference = HostPreference()
        elif not isinstance(preference, HostPreference):
            preference = HostPreference.model_validate(preference)
        if policy.allow_disable and preference.is_disabled:
            continue
        if policy.allow_rename and preference.remark:
            host = host.model_copy(update={"remark": preference.remark})
        position = preference.position if policy.allow_reorder else None
        ordered |= position is not None
        result.append((position is None, position if position is not None else index, index, host))
    if ordered:
        result.sort(key=lambda item: item[:3])
    return [item[3] for item in result], ordered
