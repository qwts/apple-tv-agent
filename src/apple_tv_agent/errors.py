"""Stable public errors. Exception text is never part of the CLI response."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_AMBIGUOUS = "DEVICE_AMBIGUOUS"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    PAIRING_REQUIRED = "PAIRING_REQUIRED"
    INTERACTIVE_REQUIRED = "INTERACTIVE_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    CREDENTIAL_STORE_UNAVAILABLE = "CREDENTIAL_STORE_UNAVAILABLE"
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    DEVICE_BUSY = "DEVICE_BUSY"
    CONFIG_ERROR = "CONFIG_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERRORS = {
    ErrorCode.INVALID_ARGUMENT: (2, "Invalid arguments. Run apple-tv-agent --help for usage."),
    ErrorCode.DEVICE_NOT_FOUND: (2, "The selected device was not found."),
    ErrorCode.DEVICE_AMBIGUOUS: (2, "Select a device ID or configure a default."),
    ErrorCode.IDENTITY_MISMATCH: (2, "Device identity changed. Explicit pairing is required."),
    ErrorCode.PAIRING_REQUIRED: (3, "Pair the selected device in a local terminal."),
    ErrorCode.INTERACTIVE_REQUIRED: (3, "Run pairing in a local interactive terminal."),
    ErrorCode.AUTH_FAILED: (3, "Device authentication failed. Check pairing before retrying."),
    ErrorCode.CREDENTIAL_STORE_UNAVAILABLE: (3, "The native credential store is unavailable."),
    ErrorCode.UNSUPPORTED_FEATURE: (4, "The selected device does not support this feature."),
    ErrorCode.FEATURE_UNAVAILABLE: (4, "This feature is currently unavailable."),
    ErrorCode.TIMEOUT: (5, "The operation exceeded its deadline."),
    ErrorCode.NETWORK_ERROR: (5, "The device connection failed."),
    ErrorCode.DEVICE_BUSY: (5, "Another operation is using the selected device."),
    ErrorCode.CONFIG_ERROR: (6, "The local configuration could not be read or updated."),
    ErrorCode.INTERNAL_ERROR: (1, "An internal error occurred."),
}


class AgentError(Exception):
    def __init__(self, code: ErrorCode, *, details=None, retryable=False):
        self.code = code
        self.details = {} if details is None else details
        self.retryable = retryable
        super().__init__(ERRORS[code][1])

    @property
    def exit_code(self):
        return ERRORS[self.code][0]
