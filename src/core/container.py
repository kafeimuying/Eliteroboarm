"""
Dependency Injection Container
"""

from typing import Any, Callable, Dict, TypeVar, Type

T = TypeVar('T')

class Container:
    """
    Simple dependency injection container
    """
    _instances: Dict[Any, Any] = {}
    _factories: Dict[Any, Callable[[], Any]] = {}
    _singletons: Dict[Any, Any] = {}

    @classmethod
    def register(cls, key: Type[T] | str, instance: T) -> None:
        """
        Register a singleton instance

        Args:
            key: The registration key (type or string)
            instance: The instance to register
        """
        if isinstance(key, type):
            cls._instances[key] = instance
            cls._instances[key.__name__] = instance
        else:
            cls._instances[key] = instance

    @classmethod
    def register_factory(cls, key: Type[T] | str, factory: Callable[[], T]) -> None:
        """
        Register a factory function

        Args:
            key: The registration key (type or string)
            factory: Factory function that creates the instance
        """
        if isinstance(key, type):
            cls._factories[key] = factory
            cls._factories[key.__name__] = factory
        else:
            cls._factories[key] = factory

    @classmethod
    def register_singleton(cls, key: Type[T] | str, factory: Callable[[], T]) -> None:
        """
        Register a singleton factory (called only once)

        Args:
            key: The registration key (type or string)
            factory: Factory function that creates the instance
        """
        if isinstance(key, type):
            cls._singletons[key] = factory
            cls._singletons[key.__name__] = factory
        else:
            cls._singletons[key] = factory

    @classmethod
    def resolve(cls, key: Type[T] | str, default: T = None) -> T:
        """
        Resolve a dependency

        Args:
            key: The registration key (type or string)

        Returns:
            The resolved instance

        Raises:
            ValueError: If the dependency is not found
        """
        # Try direct instances first
        if key in cls._instances:
            return cls._instances[key]

        # Try singletons (created only once)
        if key in cls._singletons:
            if key not in cls._instances:  # Not created yet
                cls._instances[key] = cls._singletons[key]()
            return cls._instances[key]

        # Try type name resolution
        if isinstance(key, type) and key.__name__ in cls._instances:
            return cls._instances[key.__name__]
        if isinstance(key, type) and key.__name__ in cls._singletons:
            if key.__name__ not in cls._instances:
                cls._instances[key.__name__] = cls._singletons[key.__name__]()
            return cls._instances[key.__name__]

        # Try factories
        if key in cls._factories:
            return cls._factories[key]()

        if isinstance(key, type) and key.__name__ in cls._factories:
            return cls._factories[key.__name__]()

        # Return default if provided and dependency not found
        if default is not None:
            return default

        raise ValueError(f"Dependency {key} not found")

    @classmethod
    def is_registered(cls, key: Type[T] | str) -> bool:
        """
        Check if a dependency is registered

        Args:
            key: The registration key

        Returns:
            True if registered, False otherwise
        """
        return (key in cls._instances or
                key in cls._factories or
                key in cls._singletons or
                (isinstance(key, type) and key.__name__ in cls._instances) or
                (isinstance(key, type) and key.__name__ in cls._factories) or
                (isinstance(key, type) and key.__name__ in cls._singletons))

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registrations (useful for testing)
        """
        cls._instances.clear()
        cls._factories.clear()
        cls._singletons.clear()

    @classmethod
    def get_instance_count(cls) -> int:
        """
        Get the number of registered instances and factories

        Returns:
            Total number of registered items
        """
        return (len(cls._instances) + len(cls._factories) + len(cls._singletons))