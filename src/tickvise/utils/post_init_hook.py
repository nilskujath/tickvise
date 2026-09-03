"""
Provides a metaclass-based mechanism for running code directly after an object is fully
initialized.
This is useful when a base class needs to trigger an action (e.g., starting a thread)
that depends on state set up by its subclasses further down the `__init__` chain.
"""

from abc import ABC, abstractmethod, ABCMeta


class PostInitHookMeta(ABCMeta):
    """
    Metaclass that, upon instantiation of a class that uses it, calls `_post_init_hook`
    on the newly created instance after the entire `__init__` chain has completed.

    Classes using this metaclass are expected to implement a `_post_init_hook` method
    (see `HasPostInitHook` base class).
    A `TypeError` is raised at instantiation time if the method is missing.
    """

    def __call__(cls, *args, **kwargs):
        """
        Override of the default class instantiation.

        Runs the entire `__init__` chain via `super().__call__()`, then calls
        `_post_init_hook` before returning the fully initialized instance.
        """
        instance = super().__call__(*args, **kwargs)
        hook = getattr(instance, "_post_init_hook", None)
        if hook is None:
            raise TypeError(
                f"{cls.__name__} uses PostInitHookMeta but does not implement a "
                f"_post_init_hook method. Consider inheriting from HasPostInitHook, "
                f"which enforces this via @abstractmethod."
            )
        hook()
        return instance


class HasPostInitHook(ABC, metaclass=PostInitHookMeta):
    """
    Base class for classes that need a hook called after the entire `__init__`
    chain has completed.
    Subclasses must implement `_post_init_hook`.

    Uses `PostInitHookMeta` as its metaclass to automatically call the hook after
    the entire `__init__` chain has completed.
    """

    @abstractmethod
    def _post_init_hook(self) -> None:
        """
        Abstract method that must be implemented by subclasses to define any actions
        that should happen directly after the class instance is fully initialized.

        Called automatically by the metaclass `PostInitHookMeta` after the entire
        `__init__` chain has completed.
        """
        ...
