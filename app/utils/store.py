from sqlalchemy.ext.asyncio import AsyncSession


class DictStorage(dict):
    def __init__(self, update_func):
        super().__init__()
        self.update_func = update_func

    def __getitem__(self, key):
        return super().__getitem__(key)

    def __iter__(self):
        return super().__iter__()

    def __str__(self):
        return super().__str__()

    def values(self):
        return super().values()

    def keys(self):
        return super().keys()

    def get(self, key, default=None):
        return super().get(key, default)

    async def update(self, db: AsyncSession):
        await self.update_func(self, db)
