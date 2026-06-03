"""The LiveTradingGate: real-money execution is structurally impossible unless
EVERY control is satisfied. With 2FA/opt-in/step-up/confirmation deferred, this
currently refuses live trading by construction — which is the point.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import PermissionDeniedError


@dataclass(frozen=True, slots=True)
class GateStatus:
    feature_enabled: bool
    user_opted_in: bool
    twofa_enabled: bool
    recent_step_up: bool
    kill_switch_clear: bool
    risk_ok: bool
    confirmation_valid: bool

    def blocked_reasons(self) -> list[str]:
        checks = {
            "live_feature_disabled": self.feature_enabled,
            "user_not_opted_in": self.user_opted_in,
            "2fa_not_enabled": self.twofa_enabled,
            "no_recent_2fa_step_up": self.recent_step_up,
            "kill_switch_engaged": self.kill_switch_clear,
            "risk_limits_breached": self.risk_ok,
            "missing_confirmation": self.confirmation_valid,
        }
        return [reason for reason, ok in checks.items() if not ok]

    @property
    def allowed(self) -> bool:
        return not self.blocked_reasons()


class LiveTradingGate:
    @staticmethod
    def evaluate(
        settings: Settings,
        *,
        user_opted_in: bool = False,
        twofa_enabled: bool = False,
        recent_step_up: bool = False,
        kill_switch_clear: bool = True,
        risk_ok: bool = True,
        confirmation_valid: bool = False,
    ) -> GateStatus:
        return GateStatus(
            feature_enabled=settings.live_trading_enabled,
            user_opted_in=user_opted_in,
            twofa_enabled=twofa_enabled,
            recent_step_up=recent_step_up,
            kill_switch_clear=kill_switch_clear,
            risk_ok=risk_ok,
            confirmation_valid=confirmation_valid,
        )

    @staticmethod
    def assert_allowed(status: GateStatus) -> None:
        if not status.allowed:
            raise PermissionDeniedError(
                "Live trading is blocked: " + ", ".join(status.blocked_reasons())
            )
