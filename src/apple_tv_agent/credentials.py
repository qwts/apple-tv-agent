"""Native-only credential persistence. No credentials are serialized by this module."""

import sys
from uuid import UUID

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import ProtocolName


def vault_error(reason="vault_unavailable"):
    return AgentError(
        ErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
        details={
            "reason": reason,
            "recovery": "Unlock the native vault and allow this application access, then retry locally. On Linux, use a signed-in desktop session with D-Bus and an unlocked Secret Service keyring; headless sessions without that service are unsupported.",
        },
    )


class NativeCredentialStore:
    service = "apple-tv-agent"

    def __init__(self):
        import keyring

        try:
            backend = keyring.get_keyring()
            if sys.platform == "darwin":
                from keyring.backends.macOS import Keyring

                expected = Keyring
            elif sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring

                expected = WinVaultKeyring
            elif sys.platform == "linux":
                from keyring.backends.SecretService import Keyring

                expected = Keyring
            else:
                raise vault_error("native_backend_required")
            if type(backend) is not expected:
                raise vault_error("native_backend_required")
            self.backend = backend
        except AgentError:
            raise
        except Exception:
            raise vault_error() from None

    @staticmethod
    def account(device_id, protocol):
        return f"{UUID(device_id)}:{ProtocolName(protocol).value}"

    def get(self, device_id, protocol):
        try:
            return self.backend.get_password(self.service, self.account(device_id, protocol))
        except Exception:
            raise vault_error() from None

    def set(self, device_id, protocol, value):
        # Read before overwrite, verify afterward, and restore on a failed write/readback.
        previous = self.get(device_id, protocol)
        account = self.account(device_id, protocol)
        try:
            self.backend.set_password(self.service, account, value)
            if self.backend.get_password(self.service, account) != value:
                raise vault_error("write_unverified")
        except Exception:
            try:
                if previous is None:
                    self.delete(device_id, protocol)
                else:
                    self.backend.set_password(self.service, account, previous)
                    if self.backend.get_password(self.service, account) != previous:
                        raise vault_error()
            except Exception:
                raise vault_error("write_failed_restore_unverified") from None
            raise vault_error("write_failed_previous_restored") from None

    def delete(self, device_id, protocol):
        from keyring.errors import PasswordDeleteError

        try:
            if self.get(device_id, protocol) is None:
                return
            try:
                self.backend.delete_password(self.service, self.account(device_id, protocol))
            except PasswordDeleteError:
                # Some backends report an already absent credential as an error.
                if self.get(device_id, protocol) is not None:
                    raise
            if self.get(device_id, protocol) is not None:
                raise vault_error("delete_unverified")
        except Exception:
            raise vault_error("delete_failed") from None
