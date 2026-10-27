"""Repository exceptions for SAHAKAR–SEVA."""


class RepositoryError(Exception):
    """Base exception for all repository errors."""


class UserNotFoundError(RepositoryError):
    """Raised when a user is not found by ID or identifier."""


class IdentityConflictError(RepositoryError):
    """Raised when a verified external identity cannot be linked due to conflicting data."""


class WorkerProfileExistsError(RepositoryError):
    """Raised when attempting to create a duplicate worker profile for a user."""


class WorkerProfileNotFoundError(RepositoryError):
    """Raised when a worker profile is not found for a user."""


class OrganizationNotFoundError(RepositoryError):
    """Raised when an organization is not found."""


# --- Phase 3A: service taxonomy -------------------------------------------------------


class ServiceCategoryNotFoundError(RepositoryError):
    """Raised when a service category is not found."""


class SkillNotFoundError(RepositoryError):
    """Raised when a skill does not exist."""


class SkillInactiveError(RepositoryError):
    """Raised when a worker tries to declare a skill that is inactive or in an inactive category."""


class WorkerSkillExistsError(RepositoryError):
    """Raised when a worker has already declared the given skill."""


class WorkerSkillNotFoundError(RepositoryError):
    """Raised when removing a skill the worker has not declared."""
