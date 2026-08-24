# Kroma Events Package

# Python 3.14+ Compatibility Patch for Django 5.1 template context copy:
# In Python 3.14, `copy(super())` inside `BaseContext.__copy__` returns a `super` proxy
# object rather than copying instance attributes, raising:
# `AttributeError: 'super' object has no attribute 'dicts'`.
try:
    from django.template.context import BaseContext

    def _patched_base_context_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _patched_base_context_copy
except Exception:
    pass
