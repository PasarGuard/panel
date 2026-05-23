from app.models.settings import HWIDSettings


def resolve_effective_hwid_settings(
    global_hwid: HWIDSettings, role_hwid: HWIDSettings | dict | None
) -> HWIDSettings | None:
    if isinstance(role_hwid, dict):
        if not role_hwid:
            role_hwid = None
        else:
            try:
                role_hwid = HWIDSettings.model_validate(role_hwid)
            except Exception:
                role_hwid = None

    if role_hwid is None:
        return global_hwid

    if not role_hwid.enabled:
        return None

    # enabled=True: None fields inherit from global, explicit values (including 0) override
    return HWIDSettings(
        enabled=True,
        forced=role_hwid.forced,
        fallback_limit=role_hwid.fallback_limit if role_hwid.fallback_limit is not None else global_hwid.fallback_limit,
        min_limit=role_hwid.min_limit if role_hwid.min_limit is not None else global_hwid.min_limit,
        max_limit=role_hwid.max_limit if role_hwid.max_limit is not None else global_hwid.max_limit,
    )
