# casino/api/_auth.py
# Authorization pipeline for casino's WebSocket services.
#
# Mirrors bed.api.bank.BankService._check_access for token-aware
# authorization: every per-op handler delegates to the same five gates
# in order -- session resolve, wire-token validation, session-token
# validation, wire-shape invariants, then
# ``bbsengine6.casino.access()`` policy.
#
# Casino owns its own auth copy (token codec, envelope helpers, the
# pipeline helpers) instead of importing ``bed.api.*`` because the
# casino package must remain importable in door-mode / standalone test
# contexts where bed is not on the path. The token codec is a 1:1
# duplicate of ``bed.api.auth._encode_token`` / ``_decode_token`` --
# any change there must be mirrored here so a token minted by one
# is consumable by the other.
#
# Pipeline:
#   1. :func:`_get_or_bind_session_for` -- look up the session bound
#      to the websocket. When the WS has no bound session but the wire
#      carries a valid token, the session is lazily bound from the
#      token's claims (mirrors ``bed.api.auth.AuthService._handle_reconnect``).
#      Standalone tests that construct the service without token
#      wiring degrade to session-only lookup.
#   2. :func:`_validate_wire_token` -- when ``message["token"]`` is
#      present, decode + HMAC verify + store check + expiry + instance
#      match. Stash claims under ``message["claims"]``. The wire token
#      is preferred over the session-bound snapshot because it is
#      read from the token file on the client just before the WS send
#      and catches the case where the session-bound snapshot has been
#      revoked since WS open.
#   3. :func:`_validate_session_token` -- when the wire token is
#      absent, validate ``state.auth_service_token`` (set by the auth
#      flow at WS bind time).
#   4. Op-specific shape validation -- stays in the handler because
#      envelope codes are a wire-protocol concern. Helpers for the
#      common cases (``moniker`` required, positive ``amount``, etc.)
#      live in :func:`_validate_shape` for ops that share a shape.
#   5. ``bbsengine6.casino.access()`` policy decision.
#
# When the service is constructed without ``secret`` /
# ``token_store`` / ``instance_id`` the token gates become no-ops
# (matches ``bed.api.bank.BankService._check_access`` legacy mode);
# the per-op policy still runs.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, Optional, Tuple

from bbsengine6.casino import access as _casino_access


# ----- Wire-protocol error envelopes ----------------------------------

CODE_TOKEN_INVALID = "token_invalid"
CODE_TOKEN_REVOKED = "token_revoked"
CODE_INSTANCE_MISMATCH = "instance_mismatch"
CODE_TOKEN_EXPIRED = "token_expired"
CODE_NOT_AUTHENTICATED = "not_authenticated"
CODE_FORBIDDEN = "forbidden"
CODE_BAD_CREDENTIALS = "bad_credentials"
CODE_MISSING_CREDENTIALS = "missing_credentials"
CODE_DATABASE_ERROR = "database_error"
CODE_OPERATION_FAILED = "operation_failed"
CODE_MISSING_MONIKER = "missing_moniker"
CODE_INVALID_AMOUNT = "invalid_amount"
CODE_INVALID_REQUEST = "invalid_request"
CODE_NOT_AT_TABLE = "not_at_table"

_TOKEN_CLAIM_VERSION = 1
_SUPPORTED_TOKEN_VERSIONS = frozenset({_TOKEN_CLAIM_VERSION})


class TokenError(Exception):
    """Raised by the token codec on any decode/verify failure.

    The ``code`` is the wire-protocol error code the handler should
    surface to the client (one of ``token_invalid`` /
    ``token_expired`` / ``token_revoked`` / ``instance_mismatch``).
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def encode_token(claims: Dict[str, Any], secret: bytes) -> str:
    """Mint a bearer token from ``claims`` using ``secret``.

    Format: ``<urlsafe-b64-payload>.<hex hmac-sha256>``. The payload
    is the JSON of ``claims`` with sorted keys and no whitespace so
    the canonical byte sequence matches between minter and verifier.
    Used by tests; production minting lives in
    ``bed.api.auth.AuthService._mint_record``.
    """
    payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64encode(payload)
    mac = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{mac}"


def decode_token(token: str, secret: bytes) -> Dict[str, Any]:
    """Decode and verify ``token`` using ``secret``.

    Raises :class:`TokenError` on any malformed / bad-signature /
    unsupported-version input.
    """
    if not isinstance(token, str) or "." not in token:
        raise TokenError(CODE_TOKEN_INVALID, "malformed token")
    payload_b64, mac = token.rsplit(".", 1)
    if not payload_b64 or not mac:
        raise TokenError(CODE_TOKEN_INVALID, "malformed token")
    expected = hmac.new(
        secret, payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise TokenError(CODE_TOKEN_INVALID, "bad signature")
    try:
        claims = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise TokenError(CODE_TOKEN_INVALID, f"unparseable claims: {e}") from e
    if not isinstance(claims, dict):
        raise TokenError(CODE_TOKEN_INVALID, "claims not an object")
    version = claims.get("version")
    if not isinstance(version, int) or version not in _SUPPORTED_TOKEN_VERSIONS:
        raise TokenError(
            CODE_TOKEN_INVALID,
            f"unsupported token version: {version!r}",
        )
    return claims


# ----- Error envelopes ------------------------------------------------


def error_envelope(
    code: str, message: str = "", *, recoverable: bool = False
) -> Dict[str, Any]:
    """Build the standard error envelope used by every casino handler.

    ``recoverable`` is a hint for the client: ``True`` means the
    client may retry after a reconnect (e.g. ``token_expired``).
    """
    return {
        "type": "error",
        "code": code,
        "message": message or code,
        "recoverable": bool(recoverable),
    }


def forbidden(message: str = "Operation not permitted") -> Dict[str, Any]:
    return error_envelope(CODE_FORBIDDEN, message)


def not_authenticated(message: str = "Not authenticated") -> Dict[str, Any]:
    return error_envelope(CODE_NOT_AUTHENTICATED, message)


# ----- Session adapter ------------------------------------------------


class _CasinoSessionState:
    """Duck-typed mirror of ``bed.api.session.SessionState``.

    Casino's standalone ``CasinoSessionManager`` stores per-session
    state as plain dicts (``{"moniker": ..., "is_sysop": ...}``) so
    the existing door-mode handler code keeps working. ``bbsengine6.casino.access``
    reads state via ``getattr(session, "moniker")`` /
    ``getattr(session, "is_sysop")`` / ``getattr(session, "table_moniker")``
    so we wrap the dict in this adapter for the access() call.

    When the casino router runs under BED the handler's
    ``self.sessions`` is BED's :class:`SessionRegistry`, which already
    returns real :class:`SessionState` dataclasses -- the wrapper
    short-circuits in that case (``from_state`` returns the input
    unchanged).
    """

    __slots__ = (
        "session_id",
        "websocket_id",
        "moniker",
        "is_sysop",
        "table_moniker",
        "spectator_of",
        "auth_service_token",
        "loginid",
        "balance",
        "_wrapped",
    )

    def __init__(
        self,
        *,
        session_id: str,
        websocket_id: str,
        moniker: str,
        is_sysop: bool,
        table_moniker: Optional[str] = None,
        spectator_of: Optional[set] = None,
        auth_service_token: Optional[str] = None,
        loginid: Optional[str] = None,
        balance: Optional[int] = None,
    ) -> None:
        self.session_id = session_id
        self.websocket_id = websocket_id
        self.moniker = moniker
        self.is_sysop = bool(is_sysop)
        self.table_moniker = table_moniker
        self.spectator_of = set(spectator_of) if spectator_of else set()
        self.auth_service_token = auth_service_token
        self.loginid = loginid
        self.balance = balance
        self._wrapped = None

    @classmethod
    def from_state(cls, state: Any) -> "_CasinoSessionState":
        """Wrap ``state`` if it is a plain dict; return as-is otherwise.

        ``SessionState`` (dataclass) and ``_CasinoSessionState``
        already expose the expected attributes and pass through
        unchanged. A ``dict`` is upgraded to ``_CasinoSessionState``
        so ``getattr(session, "moniker")`` works inside access().
        """
        if state is None or isinstance(state, _CasinoSessionState):
            return state  # type: ignore[return-value]
        if isinstance(state, dict):
            return cls(
                session_id=str(state.get("session_id") or ""),
                websocket_id=str(state.get("websocket_id") or ""),
                moniker=str(state.get("moniker") or ""),
                is_sysop=bool(state.get("is_sysop", False)),
                table_moniker=state.get("table_moniker"),
                spectator_of=set(state.get("spectator_of") or set()),
                auth_service_token=state.get("auth_service_token"),
                loginid=state.get("loginid"),
                balance=state.get("balance"),
            )
        # Already attribute-style (e.g. bed.api.session.SessionState).
        return state  # type: ignore[return-value]


# ----- Pipeline helpers -----------------------------------------------


def _validate_token_against_store(
    self_ref: Any,
    token: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Shared core for :func:`_validate_session_token` and
    :func:`_validate_wire_token`. Returns the same ``(claims, None)``
    / ``(None, error_envelope)`` tuple shape.

    A ``token`` of ``""`` / ``None`` returns ``(None, None)`` (no
    token was supplied). An unset ``secret`` / ``token_store`` /
    ``instance_id`` also returns ``(None, None)`` so legacy /
    unit-test callers degrade gracefully to session-bound authorization.

    Expiry is checked BEFORE the store lookup so a token whose clock
    has run out surfaces as ``token_expired`` even when the
    in-memory store's lazy-GC has already purged the record (which
    would otherwise mask the expiry as ``token_revoked``).
    """
    token = (token or "").strip()
    if not token:
        return None, None

    secret = getattr(self_ref, "secret", None)
    token_store = getattr(self_ref, "token_store", None)
    instance_id = getattr(self_ref, "instance_id", None)
    if not secret or token_store is None or not instance_id:
        return None, None

    try:
        claims = decode_token(token, secret)
    except TokenError as e:
        return None, error_envelope(e.code, str(e), recoverable=False)

    now_fn = getattr(self_ref, "_now", None)
    now = float(now_fn()) if callable(now_fn) else None
    expires_at_claim = float(claims.get("expires_at") or 0.0)  # type: ignore[arg-type]  # noqa
    if now is not None and expires_at_claim <= now:
        try:
            token_store.delete(token)
        except Exception:
            pass
        return None, error_envelope(
            CODE_TOKEN_EXPIRED,
            "Token has expired",
            recoverable=True,
        )

    store_record = token_store.get(token)
    if store_record is None:
        return None, error_envelope(
            CODE_TOKEN_REVOKED,
            "Token is no longer valid",
            recoverable=False,
        )
    if store_record.bed_instance_id != instance_id:
        token_store.delete(token)
        return None, error_envelope(
            CODE_INSTANCE_MISMATCH,
            "Token was issued by a different bed instance",
            recoverable=False,
        )

    return claims, None


def _validate_session_token(
    self_ref: Any, state: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    raw = getattr(state, "auth_service_token", None)
    return _validate_token_against_store(self_ref, raw if isinstance(raw, str) else "")


def _validate_wire_token(
    self_ref: Any, message: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    return _validate_token_against_store(self_ref, message.get("token") or "")


def _get_session_state(
    self_ref: Any, websocket: Any
) -> Optional[_CasinoSessionState]:
    """Look up the session bound to ``websocket`` and wrap it for access().

    Returns ``None`` when the websocket has no bound session (the
    caller decides how to surface the denial -- typically a
    ``not_authenticated`` envelope).
    """
    sessions = getattr(self_ref, "sessions", None)
    if sessions is None or websocket is None:
        return None
    try:
        ws_id = str(websocket.id)
    except Exception:
        return None

    state = None
    # BED's SessionRegistry has ``get_by_websocket``.
    get_by_websocket = getattr(sessions, "get_by_websocket", None)
    if callable(get_by_websocket):
        try:
            state = get_by_websocket(ws_id)
        except Exception:
            state = None
    if state is not None:
        return _CasinoSessionState.from_state(state)

    # Casino's CasinoSessionManager stores under ``id(websocket)`` (int).
    # Look up by int key (legacy / standalone path).
    get_session = getattr(sessions, "get_session", None)
    if callable(get_session):
        try:
            state = get_session(ws_id)
        except Exception:
            state = None
        if state is None:
            try:
                state = get_session(int(ws_id))
            except Exception:
                state = None
    if state is not None:
        # CasinoSessionManager's record is a dict -- wrap it.
        if isinstance(state, dict):
            state["session_id"] = state.get("session_id") or ws_id
            state["websocket_id"] = state.get("websocket_id") or ws_id
            return _CasinoSessionState.from_state(state)
        return _CasinoSessionState.from_state(state)
    return None


def _get_or_bind_session_for(
    self_ref: Any,
    websocket: Any,
    message: Dict[str, Any],
) -> Tuple[Optional[_CasinoSessionState], Optional[Dict[str, Any]]]:
    """Return the session for ``websocket``, lazily binding from a
    valid wire token when no session is bound yet.

    The CLI's casino tools run each per-op call under a fresh
    ``asyncio.run`` (one per subcommand) which closes its event loop
    and forces :class:`BedConnection` to open a new WebSocket on the
    next call. Each new WebSocket is a fresh ``websocket.id`` in the
    server's eyes, so without this fallback the session registered by
    the prior ``auth reconnect`` is no longer reachable and every op
    returns ``not_authenticated``.

    The fallback mirrors the ``auth reconnect`` handshake: when a
    valid wire token is present, its ``session_id`` / ``moniker`` /
    ``is_sysop`` / ``loginid`` claims are used to either re-bind an
    existing session entry (its WS mapping is updated) or synthesize
    a fresh one if the server's session registry has lost the entry
    (e.g. after a process restart). The wire token becomes the new
    ``state.auth_service_token`` so subsequent defense-in-depth
    checks see a consistent snapshot. The validated claims are
    stashed on ``message["claims"]`` so the downstream
    :func:`bbsengine6.casino.access` call can prefer claim-derived
    ``moniker`` / ``is_sysop`` over the in-memory session attributes.

    Returns ``(state, err)`` -- ``err`` is non-None when the WS has
    no bound session AND the wire token (if any) fails to validate.
    """
    state = _get_session_state(self_ref, websocket)
    if state is not None:
        return state, None

    wire_token = (message.get("token") or "").strip()
    if not wire_token:
        return None, not_authenticated()

    claims, token_err = _validate_wire_token(self_ref, message)
    if token_err is not None:
        return None, token_err
    if claims is None:
        return None, not_authenticated()

    session_id = (claims.get("session_id") or "").strip()
    if not session_id:
        return None, not_authenticated()

    try:
        ws_id = str(websocket.id)
    except Exception:
        return None, not_authenticated()

    sessions = getattr(self_ref, "sessions", None)
    moniker = (claims.get("moniker") or "").strip()
    is_sysop = bool(claims.get("is_sysop", False))
    loginid = claims.get("loginid")

    new_state = _CasinoSessionState(
        session_id=session_id,
        websocket_id=ws_id,
        moniker=moniker,
        is_sysop=is_sysop,
        auth_service_token=wire_token,
        loginid=loginid,
    )

    # Mirror the bind into whichever session registry the service uses
    # so subsequent calls hit the fast path. The wrapper around the
    # dict-backed CasinoSessionManager writes back through ``get_session`` /
    # attribute mutation; the SessionRegistry path delegates to ``bind``.
    if sessions is not None:
        bind = getattr(sessions, "bind", None)
        if callable(bind):
            try:
                bind(
                    session_id,
                    ws_id,
                    moniker,
                    is_sysop,
                    loginid=loginid,
                )
                # Stash the wire token on the freshly-bound state so the
                # next defense-in-depth check sees a consistent snapshot.
                bound = getattr(sessions, "get_by_session", None)
                if callable(bound):
                    st = bound(session_id)
                    if st is not None:
                        setattr(st, "auth_service_token", wire_token)
            except Exception:
                pass

    message["claims"] = claims
    return new_state, None


# ----- Per-op shape validation ----------------------------------------


def _validate_shape(op: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate the wire-shape invariants ``bbsengine6.casino.access``
    intentionally does not check. Returns ``None`` on success or an
    error envelope on failure. Per-op shape that lives in the handler
    (slot spin ``bet``, yahtzee dice counts, etc.) stays there.
    """
    if op in (
        "create_table",
        "update_table",
        "join_table",
        "leave_table",
        "watch_table",
        "stop_watching",
        "bet",
        "slot_spin",
        "slot_paytable",
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
        "yahtzee_quick_play",
        "tictactoe_quick_play",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    ):
        # All gameplay / table ops. ``table_moniker`` is checked where
        # relevant inside the handler so we don't reject before the
        # access() policy can confirm the player is seated.
        pass

    if op == "kick_player":
        player_moniker = (message.get("player_moniker") or "").strip()
        if not player_moniker:
            return error_envelope(
                CODE_INVALID_REQUEST, "player_moniker required"
            )
        table_monikers = message.get("table_monikers") or []
        if not table_monikers:
            return error_envelope(
                CODE_INVALID_REQUEST, "table_monikers required"
            )

    if op in ("slot_history",):
        target = (message.get("moniker") or "").strip()
        if not target:
            return error_envelope(
                CODE_MISSING_MONIKER, "moniker required"
            )

    return None


# ----- Public pipeline -----------------------------------------------


def check_access(
    self_ref: Any,
    websocket: Any,
    op: str,
    message: Dict[str, Any],
) -> Tuple[Optional[_CasinoSessionState], Optional[Dict[str, Any]]]:
    """Run the five access gates in order and return ``(state, err)``.

    Mirrors ``bed.api.bank.BankService._check_access`` so a token
    minted by ``bed.api.auth.AuthService`` is consumable here without
    any re-implementation. Returns ``(state, None)`` on allow,
    ``(state_or_None, error_envelope)`` on deny.

    Public ops (currently ``list_tables``) bypass the
    ``not_authenticated`` gate -- the lobby listing is intentionally
    open to anonymous viewers, mirroring the legacy door-mode
    behavior. The token / shape / policy gates still run so a
    malformed request never reaches the service layer.
    """
    state, err = _get_or_bind_session_for(self_ref, websocket, message)
    if err is not None and op == "list_tables":
        state = None
        err = None
    if err is not None:
        return None, err

    if "claims" not in message:
        claims, err = _validate_wire_token(self_ref, message)
        if err is not None:
            return state, err
        if claims is not None:
            message["claims"] = claims
        elif state is not None:
            claims, err = _validate_session_token(self_ref, state)
            if err is not None:
                return state, err
            if claims is not None:
                message["claims"] = claims

    # Normalize wire shape for the policy: ``kick_player`` carries
    # ``table_monikers`` (plural list) on the wire, but the policy in
    # :mod:`bbsengine6.casino` looks at ``table_moniker`` (singular).
    # The handler's per-table loop re-runs the policy with each
    # table's owner, so the gate only needs the first entry to make
    # an authentication-level decision.
    if op == "kick_player":
        if not message.get("table_moniker"):
            tm_list = message.get("table_monikers")
            if isinstance(tm_list, list) and tm_list:
                message["table_moniker"] = tm_list[0]

    err = _validate_shape(op, message)
    if err is not None:
        return state, err

    if not _casino_access(self_ref.args, op, session=state, message=message):
        return state, forbidden("Operation not permitted for this session")

    return state, None


# ----- Map wire-protocol type -> domain verb --------------------------

# The casino router owns the verb vocabulary; ``bbsengine6.casino.access``
# takes the domain verb. Each handler's message dispatch translates
# ``message["type"]`` to the right ``op`` before calling
# :func:`check_access`.
TYPE_TO_OP: Dict[str, str] = {
    "list_tables": "list_tables",
    "create_table": "create_table",
    "update_table": "update_table",
    "join_table": "join_table",
    "leave_table": "leave_table",
    "watch_table": "watch_table",
    "stop_watching": "stop_watching",
    "kick_player": "kick_player",
    "bet": "bet",
    "hit": "hit",
    "stand": "stand",
    "double": "double",
    "split": "split",
    "surrender": "surrender",
    "chat_table": "chat_table",
    "chat_global": "chat_global",
    "emote": "emote",
    "slot_spin": "slot_spin",
    "slot_paytable": "slot_paytable",
    "slot_history": "slot_history",
    "yahtzee_quick_play": "yahtzee_quick_play",
    "yahtzee_roll": "yahtzee_roll",
    "yahtzee_reroll": "yahtzee_reroll",
    "yahtzee_score": "yahtzee_score",
    "tictactoe_quick_play": "tictactoe_quick_play",
    "tictactoe_move": "tictactoe_move",
    "tictactoe_resign": "tictactoe_resign",
    "tictactoe_join": "tictactoe_join",
}


# ----- Mint helpers (used by tests; bed owns production minting) -----


def mint_token_record(
    *,
    secret: bytes,
    instance_id: str,
    moniker: str,
    session_id: str,
    websocket_id: str,
    is_sysop: bool = False,
    loginid: Optional[str] = None,
    issued_at: Optional[float] = None,
    expires_at: Optional[float] = None,
    ttl_seconds: int = 900,
) -> Any:
    """Build a ``bed.api.token_store.TokenRecord`` suitable for
    ``TokenStore.put``.

    The contract mirrors the bed dataclass -- tests construct the
    record here so a single token store stub satisfies both minter
    and verifier. The casino package imports
    :class:`bed.api.token_store.TokenRecord` lazily because casino
    must remain importable in door-mode / standalone test contexts
    where bed is not on the path.
    """
    import time as _time

    if issued_at is None:
        issued_at = _time.time()
    if expires_at is None:
        expires_at = issued_at + ttl_seconds
    claims = {
        "version": _TOKEN_CLAIM_VERSION,
        "moniker": moniker,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "session_id": session_id,
        "is_sysop": bool(is_sysop),
        "bed_instance_id": instance_id,
        "websocket_id": websocket_id,
        "loginid": loginid,
    }
    token = encode_token(claims, secret)

    try:
        from bed.api.token_store import TokenRecord
    except Exception:
        # Bed is not importable -- fall back to a plain dict so the
        # test caller can still drive a stub store via ``__getitem__``.
        return {
            "token": token,
            "moniker": moniker,
            "session_id": session_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "is_sysop": bool(is_sysop),
            "bed_instance_id": instance_id,
            "websocket_id": websocket_id,
            "claims": claims,
            "loginid": loginid,
        }
    return TokenRecord(
        token=token,
        moniker=moniker,
        session_id=session_id,
        issued_at=issued_at,
        expires_at=expires_at,
        is_sysop=bool(is_sysop),
        bed_instance_id=instance_id,
        websocket_id=websocket_id,
        claims=claims,
        loginid=loginid,
    )


__all__ = [
    "CODE_DATABASE_ERROR",
    "CODE_FORBIDDEN",
    "CODE_INSTANCE_MISMATCH",
    "CODE_INVALID_AMOUNT",
    "CODE_INVALID_REQUEST",
    "CODE_MISSING_CREDENTIALS",
    "CODE_MISSING_MONIKER",
    "CODE_NOT_AT_TABLE",
    "CODE_NOT_AUTHENTICATED",
    "CODE_OPERATION_FAILED",
    "CODE_TOKEN_EXPIRED",
    "CODE_TOKEN_INVALID",
    "CODE_TOKEN_REVOKED",
    "TYPE_TO_OP",
    "TokenError",
    "check_access",
    "decode_token",
    "encode_token",
    "error_envelope",
    "forbidden",
    "mint_token_record",
    "not_authenticated",
]
